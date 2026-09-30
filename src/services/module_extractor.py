
import json
import logging
import re
import time
import os
from typing import Any, Dict, List, Optional

from groq import Groq
from json_repair import repair_json
from pydantic import BaseModel, Field, ValidationError

from src.agents.prompts import aiDataSourcePreprocess
from dotenv import load_dotenv
load_dotenv()
api_key=os.getenv("GROQ_API_KEY")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    force=True   
)
logger = logging.getLogger(__name__)

class LLMConfig:
    """Runtime configuration for LLM calls."""
    model: str = "openai/gpt-oss-20b"
    temperature: float = 0.2
    max_tokens: int = 65000
    max_retries: int = 5
    initial_delay: float = 3.0
    response_format: Dict[str, str] = {"type": "json_object"}

class ModuleExtractorClient:
    _instance = None

    def __new__(cls, api_key: str):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = Groq(api_key=api_key)

        return cls._instance

    def get_client(self):
        return self.client

class ModuleMetadata(BaseModel):
    description: str = ""
    preConditions: List[str] = Field(default_factory=list)

class Module(BaseModel):
    moduleName: str = ""
    credential: Dict[str, Any] = Field(default_factory=dict)
    functionalFlow: List[str] = Field(default_factory=list)
    acceptanceCriteria: List[str] = Field(default_factory=list)
    metadata: ModuleMetadata = Field(default_factory=ModuleMetadata)

class ModuleExtractionResponse(BaseModel):
    modules: List[Module] = Field(default_factory=list)
    leftOverData: str = ""

def remove_blank_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if line.strip())

def build_accumulated_context(
    module_names: List[str],
    descriptions: List[str],
    preconditions: List[List[str]],
) -> str:
    if not module_names or not descriptions:
        return ""

    lines = ["--- ACCUMULATED APPLICATION CONTEXT ---", "All modules extracted so far:"]
    for idx, (name, desc, precond) in enumerate(zip(module_names, descriptions, preconditions), 1):
        precond_str = "; ".join(precond) if precond else "None"
        lines.append(f"{idx}. {name}: {desc}")
        lines.append(f"   Preconditions: {precond_str}")

    lines.append("--- END ACCUMULATED CONTEXT ---\n")
    return "\n".join(lines)

def parse_or_repair_json(raw: str) -> Any:
    if not raw or not raw.strip():
        raise ValueError("Empty LLM response received")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Standard JSON parsing failed, attempting repair...")
        try:
            return repair_json(raw, return_objects=True)
        except Exception as e:
            logger.error(f"JSON repair failed: {e}")
            raise

def normalize_module_dict(mod: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(mod, dict):
        return {}

    if "metadata" not in mod or not isinstance(mod["metadata"], dict):
        mod["metadata"] = {"description": "", "preConditions": []}
    else:
        mod["metadata"].setdefault("description", "")
        mod["metadata"].setdefault("preConditions", [])

    return mod

def normalize_parsed_result(parsed: Any) -> Dict[str, Any]:
    if isinstance(parsed, list):
        return {"modules": [normalize_module_dict(m) for m in parsed], "leftOverData": ""}

    if not isinstance(parsed, dict):
        return {"modules": [], "leftOverData": ""}

    parsed.setdefault("modules", [])
    parsed.setdefault("leftOverData", "")

    if isinstance(parsed["modules"], list):
        parsed["modules"] = [normalize_module_dict(m) for m in parsed["modules"]]

    return parsed

def moduleOptimizer(
    content: str,
    accumulated_descriptions: Optional[List[str]] = None,
    accumulated_module_names: Optional[List[str]] = None,
    accumulated_preconditions: Optional[List[List[str]]] = None,
    apiKey: Optional[str] = None,
    model: Optional[str] = None,
    serviceProvider: Optional[str] = None,
    forceFinalize: bool = False,
    config: Optional[LLMConfig] = None,
) -> Optional[Dict[str, Any]]:

    if not apiKey:
        logger.error("No API key provided to moduleOptimizer")
        return None

    cfg = config or LLMConfig()
    use_model = model or cfg.model

    # Clean input
    content = remove_blank_lines(content)
    logger.debug(f"Input content length: {len(content)} chars")

    # Build accumulated context
    accumulated_context = build_accumulated_context(
        accumulated_module_names or [],
        accumulated_descriptions or [],
        accumulated_preconditions or [],
    )
    if accumulated_context:
        logger.debug(f"Accumulated context from {len(accumulated_module_names or [])} modules")

    system_prompt, user_prompt = aiDataSourcePreprocess(content, accumulated_context, forceFinalize)

    AiDataSrcClient = ModuleExtractorClient(api_key).get_client()

    last_exception: Optional[Exception] = None

    for attempt in range(1, cfg.max_retries + 1):
        try:
            logger.info(f"LLM call attempt {attempt}/{cfg.max_retries} | model={"**********"}")

            response = AiDataSrcClient.chat.completions.create(
                model=use_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                stream=False,
                response_format=cfg.response_format,
            )

            raw_result = response.choices[0].message.content
            if not raw_result:
                raise ValueError("Empty content in LLM response")

            logger.debug(f"Raw response length: {len(raw_result)} chars")

            # Parse & normalize
            parsed = parse_or_repair_json(raw_result)
            normalized = normalize_parsed_result(parsed)

            # Validate via Pydantic
            validated = ModuleExtractionResponse.model_validate(normalized)
            logger.info(
                f"Extraction successful: {len(validated.modules)} modules, "
                f"{len(validated.leftOverData)} chars leftover"
            )

            return validated.model_dump()

        except ValidationError as e:
            logger.warning(f"Schema validation failed (attempt {attempt}): {e}")
            last_exception = e

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"JSON parse error (attempt {attempt}): {e}")
            last_exception = e

        except Exception as e:
            logger.warning(f"LLM/API error (attempt {attempt}): {e}")
            last_exception = e

        # Exponential backoff (unless last attempt)
        if attempt < cfg.max_retries:
            delay = cfg.initial_delay * (2 ** (attempt - 1))
            logger.info(f"Retrying in {delay:.1f}s...")
            time.sleep(delay)

    logger.error(f"All {cfg.max_retries} attempts failed. Last error: {last_exception}")
    return None