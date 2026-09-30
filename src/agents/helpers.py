"""Standalone helpers used by AgentOperation and the LLM client."""
import json
import logging
import os
import re
from datetime import datetime

from dotenv import load_dotenv

from src.persistence.mongo_client import get_async_client

load_dotenv()
logger = logging.getLogger(__name__)

manualTestCase = None

token_usage = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
}


def get_manual_test_case():
    global manualTestCase
    if manualTestCase is None:
        from src.persistence.prompt import Prompt
        manualTestCase = Prompt("openai/gpt-oss-20b")
    return manualTestCase


async def update_ai_service_instance_token_usage(
    mongo_url: str,
    license_id: str,
    service_provider: str,
    tokens: int,
):
    profile = os.getenv("PROFILE")

    if profile:
        db_name = f"optimize_{profile}_{license_id}"
    else:
        db_name = f"optimize_{license_id}"

    client = get_async_client()
    try:
        collection = client[db_name]["ai_service_instances"]

        filter_query = {"serviceProvider": service_provider}
        update_query = {
            "$inc": {"tokens": -tokens},
            "$set": {"updatedAt": datetime.utcnow()},
        }

        await collection.update_one(filter_query, update_query)
        logger.info(f"Deducted {tokens} tokens for service provider {service_provider}")
    except Exception as e:
        logger.error(f"Failed to deduct tokens from ai_service_instances: {e}")


def extract_summary(text: str) -> str:
    match = re.search(r'"summary"\s*:\s*"([^"]*)"', text)
    return match.group(1) if match else ""


def recover_completed_test_cases(text: str) -> dict:
    """
    Recover ONLY fully completed test cases from a possibly truncated LLM output.
    Drops any incomplete / truncated test cases.
    """
    test_cases = []
    pattern = re.compile(
        r'\{\s*"Test Case Name"\s*:\s*"[^"]+"[\s\S]*?"testCaseType"\s*:\s*"[^"]+"\s*\}',
        re.MULTILINE,
    )

    for match in pattern.findall(text):
        try:
            tc = json.loads(match)
            test_cases.append(tc)
        except Exception:
            continue

    return {
        "summary": extract_summary(text),
        "Test Cases": test_cases,
    }
