"""DuckDuckGo web search fallback when Qdrant retrieval is insufficient."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Iterable, List, Optional

from src.agents.models import CollectionNotFoundError
from src.config import (
    QDRANT_MIN_HITS,
    QDRANT_MIN_SCORE,
    WEB_SEARCH_ENABLED,
    WEB_SEARCH_MAX_QUERIES,
    WEB_SEARCH_MAX_RESULTS,
    WEB_SEARCH_TIMEOUT,
)

logger = logging.getLogger(__name__)

_TEST_GEN_PREFIX = re.compile(
    r"^\s*(?:please\s+|kindly\s+|can\s+you\s+|could\s+you\s+|i\s+want\s+(?:you\s+to\s+)?|i\s+need\s+)?"
    r"(?:generate|create|write|prepare|give|provide|make|draft)\s+"
    r"(?:\d+\s+)?"
    r"(?:manual\s+)?(?:test\s*cases?|testcases?|scenarios?|tests?)\s+"
    r"(?:for|on|of|about|covering)?\s*",
    re.IGNORECASE,
)


def qdrant_is_sufficient(scored_hits: Iterable[float]) -> bool:
    """Return True when enough Qdrant hits meet the cosine score threshold."""
    high_score_count = sum(1 for score in scored_hits if score is not None and score >= QDRANT_MIN_SCORE)
    return high_score_count >= QDRANT_MIN_HITS


def _normalize_query(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def search_subject(user_input: str) -> str:
    """Strip generate-N-testcases wrapping so the search target is the app/domain."""
    text = _normalize_query(user_input)
    if not text:
        return ""
    stripped = _TEST_GEN_PREFIX.sub("", text).strip(" .:-")
    return _normalize_query(stripped or text)


def rewrite_user_query_for_search(user_input: str) -> str:
    """Turn a generation request into a feature-oriented web search query."""
    text = _normalize_query(user_input)
    subject = search_subject(user_input)
    if not subject:
        return ""
    if subject.casefold() != text.casefold() and not re.search(
        r"\b(feature|flow|module|functionality)\b", subject, re.IGNORECASE
    ):
        return f"{subject} features user flows"
    return subject


def build_search_queries(user_input: str, rag_queries: Optional[List[str]] = None) -> List[str]:
    """Build a deduplicated, capped list of search queries."""
    queries: List[str] = []
    rewritten = rewrite_user_query_for_search(user_input)
    subject = search_subject(user_input)
    for query in (rewritten, subject):
        if query and query not in queries:
            queries.append(query)
    if rag_queries:
        for query in rag_queries:
            cleaned = _normalize_query(query)
            if cleaned and cleaned not in queries:
                queries.append(cleaned)
    return queries[:WEB_SEARCH_MAX_QUERIES]


def format_web_results_as_retrieved_info(results: List[dict]) -> str:
    """Format web snippets for scenario/MTC prompts."""
    if not results:
        return ""

    lines = [
        "NOTE: The following context was retrieved from public web search, not from project documents.",
        "This is the DOCUMENT CONTENT / source of truth for test generation.",
        "Ground every scenario in these snippets. Use only modules, fields, and flows named here.",
        "Ignore off-topic hits that do not match the user query.",
        "Do not invent UI labels or validations unless a snippet describes them.",
        "",
    ]
    for idx, item in enumerate(results, start=1):
        title = (item.get("title") or "Untitled").strip()
        href = (item.get("href") or item.get("url") or "").strip()
        body = (item.get("body") or item.get("snippet") or "").strip()
        lines.append(f"[{idx}] {title}")
        if href:
            lines.append(f"URL: {href}")
        if body:
            lines.append(f"Snippet: {body}")
        lines.append("")
    return "\n".join(lines).strip()


def _search_ddg_sync(query: str, max_results: int) -> List[dict]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        raw = ddgs.text(query, max_results=max_results)
    if not raw:
        return []
    normalized: List[dict] = []
    for item in raw:
        normalized.append(
            {
                "title": item.get("title", ""),
                "href": item.get("href") or item.get("url", ""),
                "body": item.get("body") or item.get("snippet", ""),
            }
        )
    return normalized


async def search_web(queries: List[str], max_results: int | None = None) -> List[dict]:
    """Run DuckDuckGo search for each query; return deduplicated snippets."""
    if not queries:
        return []

    limit = max_results or WEB_SEARCH_MAX_RESULTS
    seen_urls: set[str] = set()
    combined: List[dict] = []

    for query in queries:
        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(_search_ddg_sync, query, limit),
                timeout=WEB_SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Web search timed out | query=%r timeout=%ss", query, WEB_SEARCH_TIMEOUT)
            continue
        except Exception as exc:
            logger.warning("Web search failed | query=%r error=%s", query, exc)
            continue

        for item in results:
            url = (item.get("href") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            combined.append(item)
            if len(combined) >= limit:
                return combined

    return combined


async def web_search_fallback_or_raise(
    reason: str,
    user_input: str,
    rag_queries: Optional[List[str]] = None,
) -> str:
    """
    Attempt web search when Qdrant is insufficient.

    Returns formatted retrieved_info on success, otherwise raises CollectionNotFoundError
    so the existing Generic MTC fallback can run.
    """
    if not WEB_SEARCH_ENABLED:
        logger.info("Web search disabled | reason=%s", reason)
        raise CollectionNotFoundError(f"Qdrant insufficient ({reason}); web search disabled")

    queries = build_search_queries(user_input, rag_queries)
    start = time.time()
    logger.info(
        "Web search triggered | reason=%s query_count=%s queries=%s",
        reason,
        len(queries),
        queries,
    )

    results = await search_web(queries)
    duration = time.time() - start

    if not results:
        logger.warning(
            "Web search returned no results | reason=%s duration=%.3fs",
            reason,
            duration,
        )
        raise CollectionNotFoundError(
            f"Qdrant insufficient ({reason}) and web search returned no results"
        )

    logger.info(
        "Web search succeeded | reason=%s result_count=%s duration=%.3fs titles=%s urls=%s",
        reason,
        len(results),
        duration,
        [item.get("title") for item in results],
        [item.get("href") for item in results],
    )
    formatted = format_web_results_as_retrieved_info(results)
    logger.debug("Web search snippets | reason=%s content=%s", reason, formatted)
    return formatted
