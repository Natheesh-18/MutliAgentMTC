"""
In-process registry for cancelling async manual testcase generation jobs.

Keyed by unique_id (Mongo parent _id). Mongo generation_status is the durable
signal; the in-memory flag + task cancel provide fast same-process stop.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


class GenerationCancelled(Exception):
    """Raised when MTC generation is terminated by the user."""

    def __init__(self, unique_id: str = "", message: str = "Manual testcase generation was terminated."):
        self.unique_id = unique_id
        super().__init__(message)


_lock = threading.Lock()
_jobs: Dict[str, dict] = {}
_cancelled_ids: Set[str] = set()


def register_job(
    unique_id: str,
    prompt_id: str = "",
    session_id: str = "",
    task: Optional[asyncio.Task] = None,
) -> None:
    if not unique_id:
        return
    with _lock:
        if unique_id in _cancelled_ids:
            # Terminate was requested before the worker registered
            cancelled = threading.Event()
            cancelled.set()
        else:
            cancelled = threading.Event()
        _jobs[unique_id] = {
            "task": task or asyncio.current_task(),
            "cancelled": cancelled,
            "prompt_id": prompt_id,
            "session_id": session_id,
        }
    logger.info(f"Registered generation job | unique_id={unique_id} prompt_id={prompt_id}")

def unregister_job(unique_id: str) -> None:
    if not unique_id:
        return
    with _lock:
        _jobs.pop(unique_id, None)
        _cancelled_ids.discard(unique_id)
    logger.info(f"Unregistered generation job | unique_id={unique_id}")

def is_cancelled(unique_id: str) -> bool:
    if not unique_id:
        return False
    with _lock:
        if unique_id in _cancelled_ids:
            return True
        job = _jobs.get(unique_id)
        if job and job["cancelled"].is_set():
            return True
    return False

def check_cancelled(unique_id: str) -> None:
    """Raise GenerationCancelled if this job was terminated."""
    if is_cancelled(unique_id):
        raise GenerationCancelled(unique_id=unique_id)

def request_cancel(unique_id: str) -> bool:
    """
    Mark job cancelled for graceful stop.
    Does not hard-cancel the asyncio task so the worker can finish
    already-generated testcases, tokens, and follow-up before completing.
    Returns True if the job was known in-memory.
    """
    if not unique_id:
        return False

    known = False
    with _lock:
        _cancelled_ids.add(unique_id)
        job = _jobs.get(unique_id)
        if job:
            known = True
            job["cancelled"].set()

    logger.info(f"Cancel requested | unique_id={unique_id} known_in_memory={known}")
    return known

def find_unique_ids_by_prompt(prompt_id: str) -> list:
    """Resolve all in-memory unique_ids for a prompt_id."""
    if not prompt_id:
        return []
    with _lock:
        return [
            uid
            for uid, job in _jobs.items()
            if job.get("prompt_id") == prompt_id
        ]

def request_cancel_by_prompt(prompt_id: str) -> list:
    """
    Cancel all in-memory jobs matching prompt_id.
    Returns the list of unique_ids that were signalled.
    """
    unique_ids = find_unique_ids_by_prompt(prompt_id)
    for uid in unique_ids:
        request_cancel(uid)
    return unique_ids

def mark_cancelled_from_mongo(unique_id: str, generation_status: Optional[str]) -> None:
    """Sync in-memory cancel flag when Mongo already says cancelled (multi-worker)."""
    if unique_id and generation_status == "cancelled":
        request_cancel(unique_id)
