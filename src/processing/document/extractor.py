import io
import re
import time
import base64
import asyncio
import logging

from pathlib import Path
from typing import Optional, Union

from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from src.llm.client import ImageLLMClient
from src.utils.s3_container import _extension_from_content
from src.processing.document.prompts import imageAnalysisPrompt


logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class DocumentExtractor:

    def __init__(self):
        logger.info("Initializing Docling DocumentConverter instances...")
        pdf_options = PdfPipelineOptions()
        # Required for PDFs: renders actual image pixel data from embedded pictures.
        # Without this, picture.get_image() returns None for all PDF pictures.
        pdf_options.generate_picture_images = True
        pdf_options.do_table_structure = True
        pdf_options.do_ocr = False

        self.pdf_converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
        )
        self.docx_converter = DocumentConverter()
        logger.info("Docling DocumentConverter instances ready.")

    async def extract(
        self,
        file_data: Union[bytes, str, Path],
        serviceProvider: str,
        model: str,
        apiKey: str = "",
        file_extension: Optional[str] = None,
        sa_info=None,
        resourceId=None,
        resource=None,
    ) -> tuple:

        start_time = time.time()

        # ── Handle In-Memory Bytes vs File Path ───────────────────────────────
        if isinstance(file_data, (bytes, bytearray)):
            file_bytes = bytes(file_data)
            if not file_bytes:
                raise ValueError("Unable to generate manual test cases as the uploaded file is empty. Please upload a valid document.")

            ext = (file_extension or _extension_from_content(file_bytes) or "").lower()
            doc_name = f"document{ext}" if ext else "document"
            logger.info(f"Starting document extraction (in-memory) | type={ext} | provider={serviceProvider}")
        else:
            path = Path(file_data)
            if not path.exists():
                raise FileNotFoundError(f"Document not found: {file_data}")
            file_bytes = path.read_bytes()
            if not file_bytes:
                raise ValueError(f"Unable to generate manual test cases as the uploaded file '{path.name}' is empty. Please upload a valid document.")

            ext = (file_extension or path.suffix or _extension_from_content(file_bytes) or "").lower()
            doc_name = path.name
            logger.info(f"Starting document extraction (file path) | file={doc_name} | provider={serviceProvider}")

        if not ext or ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported or unknown file type '{ext}'. "
                f"Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        # ── TXT: plain text, no embedded images — decode directly ────────────
        if ext == ".txt":
            txt_content = file_bytes.decode("utf-8", errors="replace")
            if not txt_content.strip():
                raise ValueError("Unable to generate manual test cases as the uploaded file contains no readable content. Please upload a valid document.")
            duration = time.time() - start_time
            logger.info(f"TXT file processed in {duration:.2f}s | skipping image extraction.")
            return txt_content, 0, 0

        # ── Choose pre-warmed converter (PDF vs DOCX) ─────────────────────────
        converter = self.pdf_converter if ext == ".pdf" else self.docx_converter

        parse_start_time = time.time()
        document_stream = DocumentStream(name=doc_name, stream=io.BytesIO(file_bytes))
        result = converter.convert(document_stream)
        document = result.document
        parse_duration = time.time() - parse_start_time

        logger.info(
            f"Document parsed in {parse_duration:.2f}s | pictures_found={len(document.pictures)}"
        )

        # ── Parallel Async Image Summarization via ImageLLMClient ────────────
        semaphore = asyncio.Semaphore(5)
        system_prompt, user_prompt = imageAnalysisPrompt()

        async def _summarize_single_image(index: int, picture) -> tuple:
            image = picture.get_image(document)
            if image is None or image.width < 100 or image.height < 100:
                # Skip icons, logos, and line breaks
                logger.info(f"Skipping this image {index}")
                return index, "", 0, 0

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            async with semaphore:
                img_start_time = time.time()
                try:
                    llm_result, ip_tokens, op_tokens = await ImageLLMClient.generate_async(
                        serviceProvider=serviceProvider,
                        model=model,
                        apiKey=apiKey,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        images=[{"mime_type": "image/png", "data": image_base64}],
                        sa_info=sa_info,
                        resourceId=resourceId,
                        resource=resource,
                        response_format={"type": "json_object"},
                        return_usage=True,
                    )

                    img_duration = time.time() - img_start_time

                    if isinstance(llm_result, dict):
                        summary = llm_result.get("summary") or llm_result.get("description") or ""
                    else:
                        summary = str(llm_result).strip() if llm_result else ""

                    logger.info(
                        f"Image {index}/{len(document.pictures)} summarized in {img_duration:.2f}s | "
                        f"in={ip_tokens} out={op_tokens} | summary={summary[:80]}"
                    )
                    return index, summary, ip_tokens or 0, op_tokens or 0
                except Exception as e:
                    img_duration = time.time() - img_start_time
                    logger.error(
                        f"Image {index}/{len(document.pictures)} summarization failed after {img_duration:.2f}s: {e}"
                    )
                    return index, "", 0, 0

        if document.pictures:
            img_tasks_start = time.time()
            tasks = [
                _summarize_single_image(index, pic)
                for index, pic in enumerate(document.pictures, start=1)
            ]
            results = await asyncio.gather(*tasks)
            # Guarantee strict index ordering matching document placeholder sequence
            results.sort(key=lambda x: x[0])

            image_summaries = [res[1] for res in results]
            imgs_ip_tokens = sum(res[2] for res in results)
            imgs_op_tokens = sum(res[3] for res in results)
            total_image_time = time.time() - img_tasks_start
        else:
            image_summaries = []
            imgs_ip_tokens = 0
            imgs_op_tokens = 0
            total_image_time = 0.0

        # Export markdown with placeholders, then replace each one inline
        content = document.export_to_markdown(image_mode="placeholder")
        placeholders_found = re.findall(r"<!--.*?-->", content)
        logger.debug(f"Docling placeholder tokens found in markdown: {placeholders_found}")

        summary_iter = iter(image_summaries)

        def replace_placeholder(match):
            summary = next(summary_iter, "")
            text = summary if isinstance(summary, str) else str(summary)
            return f"\n[IMAGE SUMMARY: {text}]\n" if text.strip() else ""

        # Match both <!-- image --> and <!-- picture --> variants emitted by docling
        extracted_text = re.sub(r"<!--\s*(?:image|picture)\s*-->", replace_placeholder, content)

        if not extracted_text.strip():
            raise ValueError("Unable to generate manual test cases as the uploaded file contains no readable content. Please upload a valid document.")

        total_duration = time.time() - start_time
        replaced_count = len(image_summaries) - sum(1 for s in image_summaries if not s)
        logger.info(
            f"Extraction complete | name={doc_name} | total_time={total_duration:.2f}s "
            f"(parse_time={parse_duration:.2f}s, image_time={total_image_time:.2f}s) | "
            f"images_replaced={replaced_count} | imgs_ip_tokens={imgs_ip_tokens} | imgs_op_tokens={imgs_op_tokens}"
        )

        return extracted_text, imgs_ip_tokens, imgs_op_tokens


# ── Singleton Instance & Accessor ────────────────────────────────────────────

_document_extractor: Optional[DocumentExtractor] = None


def get_document_extractor() -> DocumentExtractor:
    """
    Return the global singleton DocumentExtractor instance.
    On first call, instantiates DocumentExtractor and loads all Docling models.
    On all subsequent calls, returns the already-loaded instance instantly.
    """
    global _document_extractor
    if _document_extractor is None:
        _document_extractor = DocumentExtractor()
    return _document_extractor


async def preprocess_file(
    file_data: Union[bytes, str, Path],
    serviceProvider: str,
    model: str,
    apiKey: str = "",
    file_extension: Optional[str] = None,
    sa_info=None,
    resourceId=None,
    resource=None,
) -> tuple:
    """
    Main entry point for document preprocessing (PDF, DOCX, TXT).
    Extracts text, layout structure, and summarizes embedded images using Docling and LLM.

    Supports:
        - In-memory bytes: await preprocess_file(file_data=raw_bytes, serviceProvider=..., model=..., ...)
        - File path string: await preprocess_file(file_data="/path/to/file.pdf", serviceProvider=..., model=..., ...)
    """
    return await get_document_extractor().extract(
        file_data=file_data,
        serviceProvider=serviceProvider,
        model=model,
        apiKey=apiKey,
        file_extension=file_extension,
        sa_info=sa_info,
        resourceId=resourceId,
        resource=resource,
    )
