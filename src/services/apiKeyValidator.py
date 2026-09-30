import ast
import json
import litellm
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    force=True   
)
logger = logging.getLogger(__name__)

PROVIDER_MAP = {
    "OpenAi": "openai",
    "Groq": "groq",
    "DefaultFireFlink": "groq",
    "Anthropic": "anthropic",
    "Gemini": "gemini",
    "gemini_enterprise": "vertex_ai",
    "Azure_AI": "openai",
}


def _extract_provider_message(error_message: str) -> str:
    """
    Pulls the underlying provider error message out of litellm's exception
    text (e.g. the exact "try again in Xs" / quota detail), instead of
    discarding it for a generic string.
    """
    if "- {" in error_message:
        try:
            error_dict = ast.literal_eval(error_message.split(" - ", 1)[1])
            return error_dict.get("error", {}).get("message", error_message)
        except Exception:
            return error_message

    if "- [" in error_message:
        try:
            error_list = ast.literal_eval(error_message.split(" - ", 1)[1])
            return error_list[0]["error"]["message"]
        except Exception:
            return error_message
    if "litellm" in error_message.lower() and " - " in error_message:
        return error_message.split(" - ", 1)[1].strip()

    return error_message


_VALIDATION_CACHE = {}
CACHE_TTL_SECONDS = 900  # 15 minutes


def validateApiKey(
    serviceProvider: str,
    model: str,
    apiKey: str | None = None,
    sa_info: str | dict | None = None,
    resourceId: str | None = None,
    vertex_project: str | None = None,
    vertex_location: str | None = None,
):
    """
    Raises on failure (let the caller's except block route it through
    build_error_response). Returns (True, message) only on success.
    Caches valid results for CACHE_TTL_SECONDS for DefaultFireFlink and OpenAi only.
    """
    import time
    sa_key_part = json.dumps(sa_info, sort_keys=True) if isinstance(sa_info, dict) else (sa_info or "")
    cache_key = (serviceProvider, model, apiKey or "", sa_key_part, resourceId or "", vertex_project or "", vertex_location or "")

    now = time.time()
    should_cache = serviceProvider in ("DefaultFireFlink", "OpenAi")
    if should_cache and cache_key in _VALIDATION_CACHE:
        cached_time, cached_result = _VALIDATION_CACHE[cache_key]
        if now - cached_time < CACHE_TTL_SECONDS:
            logger.info(f"TIMING | validateApiKey (CACHED) | Key: {serviceProvider}/{model}")
            return cached_result

    provider = PROVIDER_MAP.get(serviceProvider)

    if provider is None:
        raise ValueError(f"Unsupported service provider: {serviceProvider}")

    if provider == "gemini" and model.startswith("models/"):
        model = "gemini/" + model.split("/", 1)[1]

    if provider == "vertex_ai" and "/" in model:
        # Strip prefixes like "publishers/google/models/gemini-2.5-flash"
        # or "models/gemini-2.5-flash" down to the bare model id.
        model = model.rsplit("/", 1)[-1]

    if provider == "vertex_ai":
        if not sa_info:
            raise ValueError("Service account info is required for Gemini Enterprise.")

        if isinstance(sa_info, str):
            try:
                creds = json.loads(sa_info)
            except json.JSONDecodeError:
                raise ValueError("Invalid service account JSON format.")
        else:
            creds = sa_info

        if not vertex_project:
            vertex_project = creds.get("project_id")
        if not vertex_project:
            raise ValueError("vertex_project is required for Gemini Enterprise.")
        if not vertex_location:
            vertex_location = "us-central1"

        kwargs = {
            "model": model,
            "custom_llm_provider": provider,
            "vertex_credentials": creds,
            "vertex_project": vertex_project,
            "vertex_location": vertex_location,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
            "timeout": 10,
        }
    else:
        if not apiKey:
            raise ValueError(f"api_key is required for {serviceProvider}.")

        kwargs = {
            "model": model,
            "custom_llm_provider": provider,
            "api_key": apiKey,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
            "timeout": 10,
        }

        if provider == "openai" and resourceId:
            # Azure OpenAI / Azure Foundry — unified /openai/v1/ endpoint
            kwargs["api_base"] = f"https://{resourceId}.openai.azure.com/openai/v1/"

    t_start = time.time()
    try:
        litellm.completion(**kwargs)
        duration = time.time() - t_start
        logger.info(f"TIMING | validateApiKey | Duration: {duration:.3f}s")
        logger.info(f"Actaull serviceProvider & model for liteLLM :{serviceProvider}|{model} ")
        result = (True, "API key is valid.")
        if should_cache:
            _VALIDATION_CACHE[cache_key] = (now, result)
        return result
    except Exception as e:
        duration = time.time() - t_start
        logger.info(f"TIMING | validateApiKey (FAILED) | Duration: {duration:.3f}s")
        # Any failure — auth, rate limit, bad model, network, whatever —
        # is treated as "could not confirm the key," not a silent pass.
        raise RuntimeError(_extract_provider_message(str(e))) from e
