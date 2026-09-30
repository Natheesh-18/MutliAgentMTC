import asyncio
import logging
from typing import List, Union, Optional, Any, Tuple

from src.llm.client import LLMClient
from src.processing.document.prompts import moduleExtractionPrompt

logger = logging.getLogger(__name__)


async def summarize_chunks(
    chunks: Union[str, List[str]],
    serviceProvider: str,
    model: str,
    apiKey: str = "",
    resourceId: Optional[str] = None,
    resource: Optional[str] = None,
    sa_info: Optional[Any] = None,
    temperature: float = 0.2,
    max_concurrent: int = 3,
) -> Tuple[List[str], int, int]:
    """
    Summarize one or more document text chunks into structured QA modules.

    Handles single chunks directly and batches multiple chunks in parallel
    using asyncio.gather and Semaphore concurrency control.
    """
    if isinstance(chunks, str):
        chunk_list = [chunks] if chunks.strip() else []
    else:
        chunk_list = [c.strip() for c in chunks if c.strip()]

    if not chunk_list:
        return [], 0, 0

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_single(chunk: str, index: int) -> Tuple[int, str, int, int]:
        system_prompt, user_prompt = moduleExtractionPrompt(content=chunk)

        async with semaphore:
            try:
                logger.info("Summarizing chunk %d/%d", index + 1, len(chunk_list))
                response, ip_tokens, op_tokens = await LLMClient.generate_async(
                    serviceProvider=serviceProvider,
                    model=model,
                    apiKey=apiKey,
                    resourceId=resourceId,
                    resource=resource,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    sa_info=sa_info,
                    temperature=temperature,
                    retry_attempts=2,
                    return_usage=True,
                )

                summary = str(response).strip() if response else ""
                logger.info(
                    "Completed chunk %d/%d | in=%d out=%d",
                    index + 1,
                    len(chunk_list),
                    ip_tokens or 0,
                    op_tokens or 0,
                )
                return index, summary, ip_tokens or 0, op_tokens or 0
            except Exception as e:
                logger.error("Error summarizing chunk %d: %s", index + 1, e, exc_info=True)
                return index, chunk, 0, 0

    # Fast-path for single chunk (no gather overhead)
    if len(chunk_list) == 1:
        _, summary, ip_tokens, op_tokens = await _process_single(chunk_list[0], 0)
        return [summary], ip_tokens, op_tokens

    # Parallel execution for multiple chunks
    tasks = [_process_single(c, i) for i, c in enumerate(chunk_list)]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x[0])

    summaries = [res[1] for res in results]
    total_input_tokens = sum(res[2] for res in results)
    total_output_tokens = sum(res[3] for res in results)

    return summaries, total_input_tokens, total_output_tokens
