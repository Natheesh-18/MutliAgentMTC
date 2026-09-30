"""Shared application singletons and streaming helpers."""
import asyncio
import json
import logging
import os
import time

import boto3
import hvac
from bson import ObjectId
from datetime import datetime
from fastapi import Request

from src.persistence.document_processor import DocumentProcessor
from src.persistence.mongo_client import resolve_mongo_url as get_mongo_url
from src.persistence.prompt import EMBEDDINGS, Prompt, get_embeddings

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
POLL_INTERVAL_ACTIVE = 0.3
POLL_INTERVAL_IDLE = 0.8
MAX_STREAM_SECONDS = 300
MAX_CONSECUTIVE_ERRORS = 5
PING_INTERVAL = 20

MONGO_URL = None
MONGO_CLIENT = None

manualTestCase = Prompt("openai/gpt-oss-20b")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)

manualTestCaseDoc = DocumentProcessor(
    embeddings=EMBEDDINGS,
    qdrant_host=os.getenv("QDRANT_HOST"),
    qdrant_port=os.getenv("QDRANT_PORT"),
)


def get_collection(license_id: str):
    """Get database collections using the shared MongoDB client."""
    env = os.getenv("PROFILE")
    db_name = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
    db = MONGO_CLIENT[db_name]
    details_col = db[os.getenv("user_prompt_details_collection")]
    prompt_col = db[os.getenv("user_prompt_collection")]
    return details_col, prompt_col


def serialize(doc: dict) -> dict:
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = serialize(v)
        elif isinstance(v, list):
            result[k] = [serialize(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result




async def event_generator(
    request: Request,
    license_id: str,
    prompt_id: str,
    session_id: str,
    cursor: int,
):
    try:
        details_col, prompt_col = get_collection(license_id)
    except Exception as e:
        logger.error(f"DB connection failed | prompt_id={prompt_id} | {e}")
        yield f"event: ERROR\ndata: {json.dumps({'message': 'Database connection failed'})}\n\n"
        return

    last_sent = cursor
    sent_count = 0
    consecutive_errs = 0
    start_time = time.monotonic()

    logger.info(
        f"Stream started | prompt_id={prompt_id} session_id={session_id} "
        f"cursor={cursor}"
    )


    try:
        existing = await details_col.find(
            {
                "prompt_id": prompt_id,
                "session_id": session_id,
                "mtc_index": {"$gt": last_sent},
            },
            sort=[("mtc_index", 1)],
        ).to_list(100)

        logger.info(
            f"DEBUG stream_generation phase 1 query: prompt_id={prompt_id}, "
            f"session_id={session_id}, gt={last_sent}, found={len(existing)}"
        )

        for doc in existing:
            if await request.is_disconnected():
                return
            yield f"data: {json.dumps(serialize(doc))}\n\n"
            last_sent = doc["mtc_index"]
            sent_count += 1

        logger.info(
            f"Phase 1 done | replayed={sent_count} last_index={last_sent} prompt_id={prompt_id}"
        )

    except Exception as e:
        logger.error(f"Phase 1 failed | prompt_id={prompt_id} | {e}")
        yield f"event: ERROR\ndata: {json.dumps({'message': 'Failed to load existing MTCs'})}\n\n"
        return

    found_last_poll = False
    last_ping_time = time.monotonic()

    while True:
        if time.monotonic() - start_time > MAX_STREAM_SECONDS:
            logger.warning(f"Stream timeout | prompt_id={prompt_id}")
            yield "event: EOF\ndata: timeout\n\n"
            break

        if await request.is_disconnected():
            logger.info(f"Client disconnected | prompt_id={prompt_id}")
            break

        try:
            prompt_meta = await prompt_col.find_one(
                {"prompt_id": prompt_id, "session_id": session_id},
                sort=[("created_at", -1)],
            )

            new_docs = await details_col.find(
                {
                    "prompt_id": prompt_id,
                    "session_id": session_id,
                    "mtc_index": {"$gt": last_sent},
                },
                sort=[("mtc_index", 1)],
            ).to_list(100)

            found_last_poll = len(new_docs) > 0


            for doc in new_docs:
                if await request.is_disconnected():
                    return
                yield f"data: {json.dumps(serialize(doc))}\n\n"
                last_sent = doc["mtc_index"]
                sent_count += 1
                last_ping_time = time.monotonic()

            if found_last_poll:
                logger.info(
                    f"Phase 2 batch | new={len(new_docs)} total_sent={sent_count} last_index={last_sent}"
                )

            logger.debug(
                f"Poll state | prompt_id={prompt_id} session_id={session_id} "
                f"found={prompt_meta is not None} "
                f"is_complete={prompt_meta.get('is_complete') if prompt_meta else None} "
                f"status={prompt_meta.get('generation_status') if prompt_meta else None}"
            )

            if prompt_meta and prompt_meta.get("is_complete"):
                generation_status = prompt_meta.get("generation_status")
                error_msg = prompt_meta.get("error_message")

                pending_docs = await details_col.count_documents(
                    {
                        "prompt_id": prompt_id,
                        "session_id": session_id,
                        "mtc_index": {"$gt": last_sent},
                    }
                )

                if pending_docs > 0:
                    consecutive_errs = 0
                    await asyncio.sleep(POLL_INTERVAL_ACTIVE)
                    continue

                if generation_status == "cancelled":
                    logger.info(
                        f"Generation cancelled | total_sent={sent_count} prompt_id={prompt_id}"
                    )
                    yield (
                        f"event: CANCELLED\ndata: {json.dumps({'message': 'Manual testcase generation was terminated.', 'total_sent': sent_count})}\n\n"
                    )
                    break

                if error_msg:
                    logger.warning(f"SSE stream detected worker failure: {error_msg}")
                    yield f"event: ERROR\ndata: {json.dumps({'message': error_msg})}\n\n"
                    break

                logger.info(
                    f"Generation complete | total_sent={sent_count} prompt_id={prompt_id}"
                )
                yield "event: EOF\ndata: done\n\n"
                break

            consecutive_errs = 0

        except Exception as e:
            consecutive_errs += 1
            logger.error(f"Poll error #{consecutive_errs} | prompt_id={prompt_id} | {e}")
            if consecutive_errs >= MAX_CONSECUTIVE_ERRORS:
                yield f"event: ERROR\ndata: {json.dumps({'message': 'Repeated DB errors. Stream aborted.'})}\n\n"
                break

        current_time = time.monotonic()
        if current_time - last_ping_time >= PING_INTERVAL:
            if not await request.is_disconnected():
                yield "event: ping\ndata: {}\n\n"
                last_ping_time = current_time
                logger.debug(f"Heartbeat sent | prompt_id={prompt_id}")

        await asyncio.sleep(
            POLL_INTERVAL_ACTIVE if found_last_poll else POLL_INTERVAL_IDLE
        )

    logger.info(f"Stream closed | prompt_id={prompt_id} total_sent={sent_count}")
