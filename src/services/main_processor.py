
import os
import json
import re
import logging
from io import BytesIO
from typing import List, Dict, Any
from llama_index.core import Document
from qdrant_client import models
from src.services.final_chunking import ProductionHierarchyChunker
from docling.datamodel.document import DocumentStream
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from src.processing.document import get_document_extractor
from src.services.aiDataSrcService import (
    preprocessDocumentWithImagesTables
)
from src.services.module_extractor import moduleOptimizer
logger = logging.getLogger(__name__)
extractor = get_document_extractor()
pdf_converter = extractor.pdf_converter 
docx_converter = extractor.docx_converter

markdown_parser = MarkdownNodeParser()
fallback_splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=150)
hierarchy_engine = ProductionHierarchyChunker()


def init_collection(collection_name: str, client) -> None:
    """Creates a collection for Dense Search with MPNet specs."""
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
        )
        logger.info(f"Collection '{collection_name}' (MPNet 768d) initialized.")


def process_document_to_modules(file_bytes: bytes,file_name: str, apiKey ,model,serviceProvider,output_file: str = "extracted_modules.json") -> Dict[str, Any]:

    # ---- Basic validation ----
    if not file_bytes or len(file_bytes) == 0:
        logger.warning(f"Empty file received: {file_name}")
        return {"error": f"Unable to process the uploaded file. Please upload a valid file"}

    logger.info(f"Starting document processing for: {file_name} ({len(file_bytes)} bytes)")
    logger.info(f"\nProcessing file: {file_name}")

    all_processed_nodes = []

    try:
        ext = os.path.splitext(file_name)[1].lower()

        if ext == ".txt":
            # ---- .txt: decode directly from bytes ----
            logger.info(".txt file detected — reading content directly (no DoclingReader)")
            raw_text = file_bytes.decode("utf-8", errors="ignore")

            if not raw_text.strip():
                raise ValueError("Unable to process the uploaded file. Please upload a valid file")

            logger.info(f"File content length: {len(raw_text)} characters")
            docs = [Document(text=raw_text, metadata={"file_name": file_name})]
        else:
            # ---- .pdf / .docx: convert from BytesIO via DocumentStream ----
            logger.info(f"{ext} file detected — converting via Docling DocumentStream")
            converter = pdf_converter if ext == ".pdf" else docx_converter
            document_stream = DocumentStream(name=file_name, stream=BytesIO(file_bytes))
            docling_document = converter.convert(document_stream).document

            if not docling_document:
                raise ValueError(f"No content could be extracted from file: {file_name}")

            processed_text = preprocessDocumentWithImagesTables(
                docling_document, apiKey, model, serviceProvider
            )

            if not processed_text or not processed_text.strip():
                raise ValueError("Unable to process the uploaded file. Please upload a valid file")

            docs = [
                Document(
                    text=hierarchy_engine._preprocess_document(processed_text),
                    metadata={"file_name": file_name}
                )
            ]

            if not any(d.text.strip() for d in docs):
                raise ValueError("Unable to process the uploaded file. Please upload a valid file")

        nodes = markdown_parser.get_nodes_from_documents(docs)
        # after_md_file = (os.path.splitext(file_name)[0] + "_after_md.md")

        # with open(after_md_file, "w", encoding="utf-8") as f:
        #     f.write("\n\n".join(node.text for node in nodes))

        # print(f"After Markdown parsing: {after_md_file}")
        if not nodes:
            raise ValueError(f"No chunks could be generated from file content: {file_name}")
        
        # Fallback Splitting for Large Blocks
        refined_nodes = []
        for node in nodes:
            if (len(node.get_content()) // 4) > 1024:
                refined_nodes.extend(fallback_splitter.get_nodes_from_documents([node]))
            else:
                refined_nodes.append(node)
        
        # Clubbing to Target Size (512 tokens)
        final_chunks = hierarchy_engine.get_nodes_from_documents(refined_nodes)
        all_processed_nodes.extend(final_chunks)

        if not all_processed_nodes:
            raise ValueError(f"Chunking produced no output for file: {file_name}")
    except ValueError as e:
        logger.warning(f"Validation error for {file_name}: {e}")
        return {"error": str(e)}
        
    except Exception as e:
        logger.exception(f"Error processing {file_name}: {e}")
        return {"error": f"Processing failed for {file_name}: {str(e)}"}
    
    logger.info(f"Generated {len(all_processed_nodes)} chunks")
    
    # Step 3: Process chunks in groups of 3 through LLM with enhanced chaining
    all_modules = []
    carried_over_content = ""
    accumulated_descriptions = []
    accumulated_module_names = []
    accumulated_preconditions = []

    FINAL_LEFTOVER_MAX_RETRIES = 2
    final_leftover_attempts = 0
    
    chunk_groups = [all_processed_nodes[i:i+3] for i in range(0, len(all_processed_nodes), 3)]
    i = 0
    
    while i < len(chunk_groups) or carried_over_content.strip():
        if i < len(chunk_groups):
            chunk_group = chunk_groups[i]
            i += 1
        else:
            chunk_group = []
        # NEW: detect the tail state — no real chunks left, only leftover text
        isFinalLeftover = (i >= len(chunk_groups)) and (not chunk_group) and bool(carried_over_content.strip())
        if isFinalLeftover:
            final_leftover_attempts += 1

        logger.info(
            f"Processing chunk group {i}/{len(chunk_groups)} ({len(chunk_group)} chunks)"
            + (f" [FINAL LEFTOVER PASS - attempt {final_leftover_attempts}/{FINAL_LEFTOVER_MAX_RETRIES}]" if isFinalLeftover else "")
        )

        combined_content = "\n\n".join([node.text for node in chunk_group])

        if carried_over_content.strip():
            combined_content = carried_over_content + "\n\n" + combined_content
            logger.info(f"Added {len(carried_over_content)} chars from previous leftover")

        if accumulated_descriptions:
            context_info = "\n\n--- ACCUMULATED MODULE CONTEXT ---\n"
            context_info += "Previously extracted modules in this application:\n"
            for idx, (name, desc,precond) in enumerate(zip(accumulated_module_names, accumulated_descriptions,accumulated_preconditions), 1):
                precond_str = "; ".join(precond) if precond else "None"
                context_info += f"{idx}. {name}: {desc}\n Preconditions: {precond_str}"
            context_info += "--- END ACCUMULATED CONTEXT ---\n\n"
            
            combined_content = context_info + combined_content
            logger.info(f"Added accumulated context from {len(accumulated_descriptions)} previous modules")

        carried_over_content = ""

        try:
            # Send to LLM for module extraction with enhanced context
            result = moduleOptimizer(
                combined_content,
                accumulated_descriptions,
                accumulated_module_names,
                accumulated_preconditions,
                apiKey,
                model,
                serviceProvider,
                forceFinalize=isFinalLeftover,
            )

            if not result:
                logger.warning("Empty response from LLM")
                if isFinalLeftover:
                    carried_over_content = ""
                continue

            # Parse JSON response
            parsed_result = result if isinstance(result, dict) else json.loads(result)

            if "modules" in parsed_result:
                extracted_modules = parsed_result["modules"]
                all_modules.extend(extracted_modules)
                logger.info(f"Extracted {len(extracted_modules)} modules")

                for module in extracted_modules:
                    module_name = module.get("moduleName", "Unknown Module")
                    accumulated_module_names.append(module_name)

                    desc = module.get("metadata", {}).get("description", "No description available")
                    accumulated_descriptions.append(desc)

                    precond = module.get("metadata", {}).get("preConditions", [])
                    accumulated_preconditions.append(precond)

            if "leftOverData" in parsed_result and parsed_result["leftOverData"].strip():
                carried_over_content = parsed_result["leftOverData"].strip()

            # Safety net for final leftover
            if isFinalLeftover and carried_over_content.strip():
                if final_leftover_attempts >= FINAL_LEFTOVER_MAX_RETRIES:
                    logger.warning(
                        f"Final leftover discarded after {final_leftover_attempts} attempts "
                        f"({len(carried_over_content)} chars)"
                    )
                    carried_over_content = ""
                else:
                    logger.info(f"Final leftover unresolved — retrying.")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response preview: {result[:200]}...")

            # Recovery attempt
            try:
                json_match = re.search(r"\{.*\}", result, re.DOTALL)
                if json_match:
                    parsed_result = json.loads(json_match.group(0))
                    if "modules" in parsed_result:
                        extracted_modules = parsed_result["modules"]
                        all_modules.extend(extracted_modules)
                        logger.info(f"Extracted {len(extracted_modules)} modules")
                        for module in extracted_modules:
                            module_name = module.get("moduleName", "Unknown Module")
                            accumulated_module_names.append(module_name)
                            desc = module.get("metadata", {}).get("description", "No description available")
                            accumulated_descriptions.append(desc)
                            precond = module.get("metadata", {}).get("preConditions", [])
                            accumulated_preconditions.append(precond)

                    if "leftOverData" in parsed_result and parsed_result["leftOverData"].strip():
                        carried_over_content = parsed_result["leftOverData"].strip()

                    if isFinalLeftover and carried_over_content.strip():
                        if final_leftover_attempts >= FINAL_LEFTOVER_MAX_RETRIES:
                            carried_over_content = ""
                        else:
                            logger.info("Final leftover (recovered) unresolved — retrying.")
                else:
                    if isFinalLeftover:
                        carried_over_content = ""
            except Exception as recovery_error:
                logger.error(f"Recovery attempt failed: {recovery_error}")
                if isFinalLeftover:
                    carried_over_content = ""

        except Exception as e:
            logger.exception(f"Error processing chunk group {i}: {e}")
            if isFinalLeftover:
                logger.warning(f"Final leftover discarded due to exception: {e}")
                carried_over_content = ""

    final_result = {"modules": all_modules}

    logger.info(f"Processing complete! Total chunks: {len(all_processed_nodes)}, Modules: {len(all_modules)}")

    return final_result