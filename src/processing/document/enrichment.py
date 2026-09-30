import asyncio
import logging
from typing import Optional, Any, Tuple
from src.processing.document.chunker import chunk_text
from src.processing.document.summarizer import summarize_chunks
from src.core.exception import APIError


logger = logging.getLogger(__name__)


async def enrich_document_content(
    full_text: str,
    serviceProvider: str,
    model: str,
    apiKey: str = "",
    resourceId: Optional[str] = None,
    resource: Optional[str] = None,
    sa_info: Optional[Any] = None,
    max_concurrent: int = 3,
) -> Tuple[str, int, int]:

    if not full_text or not full_text.strip():
        raise ValueError("Unable to generate manual test cases as the document contains no readable content. Please upload a valid document.")

    chunks = chunk_text(full_text, max_chars=20000)

    logger.info(f"Enriching document content | total_chunks={len(chunks)} | provider={serviceProvider} | model={model}")

    # Parallel chunk summarization & enrichment
    summaries, file_input_tokens, file_output_tokens = await summarize_chunks(
        chunks=chunks,
        apiKey=apiKey,
        resourceId=resourceId,
        resource=resource,
        serviceProvider=serviceProvider,
        model=model,
        sa_info=sa_info,
        max_concurrent=max_concurrent,
    )

    enriched_summary = "\n\n".join(summaries)

    # Token reporting
    logger.info(f"Enrichment Complete | In Tokens: {file_input_tokens} | Out Tokens: {file_output_tokens} | Total: {file_input_tokens + file_output_tokens}")

    return enriched_summary, file_input_tokens, file_output_tokens
