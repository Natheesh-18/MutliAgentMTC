import os,json
import time
import asyncio, io
from typing import Dict, Any, Optional, Union, Tuple
import logging
from urllib import response
from groq import Groq, AsyncGroq
from anthropic import Anthropic, AsyncAnthropic
from openai import OpenAI, AsyncOpenAI
import google.generativeai as genai
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.oauth2 import service_account
from src.core.exception import APIError
# from post_response import Save_Error
from json_repair import repair_json
from PIL import Image
import base64
import re

from src.core.exception import build_api_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    force=True   
)
logger=logging.getLogger(__name__)

def parse_json_response(raw_text: str, provider: str):
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        logging.warning(f"{provider} response was not valid JSON. Trying jsonRepair.")
        try:
            json_content = repair_json(raw_text, return_objects=True)                                
            return json_content
        except json.JSONDecodeError:
            logging.warning("Trying repair with recoverCompletedTestCases")
            from src.agents.operations import recover_completed_test_cases
            try:
                json_content = recover_completed_test_cases(raw_text)
                return json_content
            except json.JSONDecodeError as e:
                raise APIError(
                    responseCode=400,
                    message=f"Invalid JSON response from {provider}",
                )


class LLMClient:
    """
    Global LLM Client to handle model selection and API calls.
    Supports: Groq, OpenAI, Anthropic, Gemini, DefaultFireFlink (Groq).
    """
    _client_cache: Dict[str, Any] = {}

    @staticmethod
    def _get_async_openai_client(apiKey: str) -> AsyncOpenAI:
        """Get or create cached AsyncOpenAI client (OpenAI only)."""
        cache_key = f"openai:{apiKey}"
        if cache_key not in LLMClient._client_cache:
            LLMClient._client_cache[cache_key] = AsyncOpenAI(api_key=apiKey)
        return LLMClient._client_cache[cache_key]

    @staticmethod
    def _get_defaultfireflink_async_client(apiKey: str) -> AsyncGroq:
        """Get or create cached AsyncGroq client for DefaultFireFlink."""
        cache_key = f"defaultfireflink:{apiKey}"
        if cache_key not in LLMClient._client_cache:
            LLMClient._client_cache[cache_key] = AsyncGroq(api_key=apiKey)
        return LLMClient._client_cache[cache_key]

    @staticmethod
    async def generate_async(
        serviceProvider: str, 
        model: str, 
        apiKey: str, 
        system_prompt: str, 
        user_prompt: str, 
        sa_info: Optional[Any] = None, 
        resourceId: Optional[Any] = None,
        resource: Optional[Any] = None,
        temperature: float = 0.5,
        response_format: Optional[Dict] = None,
        return_usage: bool = False,
        retry_attempts: int = 2,
        max_tokens: Optional[int] = None,
        unique_id: Optional[int] = None,
        mongoCollectionName: Optional[str] = None,
    ) -> Union[str, Dict, Tuple[Dict, int, int]]:
        """
        Generates a response from the specified LLM provider asynchronously.
        Returns raw content string or JSON object (parsed from the response).
        """
        for attempt in range(retry_attempts + 1):
            try:
                if serviceProvider in ["DefaultFireFlink", "Groq"]:
                    if serviceProvider == "DefaultFireFlink":
                        logger.info(f"Calling DefaultFireFlink API with model:{model}")
                        start_time = time.time()
                        client = LLMClient._get_defaultfireflink_async_client(apiKey)
                    else:
                        logger.info(f"Calling Groq API with model:{model}")
                        start_time = time.time()
                        client = AsyncGroq(api_key=apiKey)

                    if model in ["openai/gpt-oss-120b"]:
                        max_tokens = 32000

                    current_system_prompt = system_prompt
                    if response_format and "json" not in current_system_prompt.lower():
                        current_system_prompt += "\n\nYou MUST respond ONLY with a valid JSON object."

                    kwargs = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": current_system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": temperature,
                        "stream": False,
                        "max_tokens": max_tokens if max_tokens else 32000,
                    }

                    if response_format:
                        kwargs["response_format"] = response_format

                    response = await client.chat.completions.create(**kwargs)
                    elapsed = time.time() - start_time

                    content = response.choices[0].message.content

                    if not content or not content.strip():
                        raise APIError(
                            responseCode=500,
                            message="Empty response from model.",
                            debug_message="Model returned empty completion."
                        )

                    if response_format:
                        content = parse_json_response(content, serviceProvider)
                    if return_usage:
                        input_tokens = response.usage.prompt_tokens
                        output_tokens = response.usage.completion_tokens
                        return content, input_tokens, output_tokens

                    return content

                elif serviceProvider =="Anthropic":
                    logger.info(f"The anthropic model is: {model}")
                    
                    client = AsyncAnthropic(api_key=apiKey)
                    
                    # Initialize default structure for advanced configuration parameters
                    current_temperature = temperature
                    
                    if model == "claude-haiku-4-5-20251001":
                        max_tokens = 64000
                        
                    elif model in ["claude-sonnet-4-6", "claude-opus-4-6"]:
                        max_tokens = 65000
                        current_temperature = 1.0
                        
                    elif model == "claude-opus-4-8":
                        max_tokens = 65000
                        current_temperature = 1.0

                    # Package parameters — only temperature is a valid stream() parameter
                    extra_params = {}
                    if current_temperature is not None:
                        extra_params["temperature"] = current_temperature
                    
                    print("#"*70)
                    print("Model: ", model)
                    print("Max Token: ", max_tokens)
                    print("Temperature: ", current_temperature)
                    print("#"*70)
                    anthropic_system_prompt = system_prompt
                    if response_format:
                        anthropic_system_prompt += "\n\nCRITICAL: You MUST respond with ONLY a valid JSON object. No explanations, no markdown formatting, no code fences, no extra text — raw JSON only."

                    async with client.messages.stream(
                        model=model,   
                        max_tokens=max_tokens,
                        system=anthropic_system_prompt,
                        messages=[
                            {"role": "user", "content": user_prompt}
                        ],
                        **extra_params
                    ) as stream:
                        async for text in stream.text_stream:
                            pass
                        final_message = await stream.get_final_message()
                        
                    content = final_message.content[0].text

                    if response_format:
                        content = parse_json_response(content, serviceProvider)
                    if return_usage:
                        input_tokens = final_message.usage.input_tokens
                        output_tokens = final_message.usage.output_tokens
                        return content, input_tokens, output_tokens

                    return content

                elif serviceProvider == 'OpenAi':
                    client = LLMClient._get_async_openai_client(apiKey)
                    completion_kwargs = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                    }
                    if model in ["gpt-5-2025-08-07"]:
                        completion_kwargs["reasoning_effort"] = "minimal"
                        completion_kwargs["max_completion_tokens"] = 65000
                    else:
                        completion_kwargs["temperature"] = (
                            1 if model in ["o4-mini-2025-04-16"] else temperature
                        )
                        completion_kwargs["max_completion_tokens"] = (
                            65000 if model in ["o4-mini-2025-04-16"] else 32000
                        )
                    # Structured output
                    if response_format:
                        completion_kwargs["response_format"] = response_format

                    response = await client.chat.completions.create(
                        **completion_kwargs
                    )
                    content = response.choices[0].message.content

                    if response_format:
                        content = parse_json_response(content, serviceProvider)
                    if return_usage:
                        input_tokens = response.usage.prompt_tokens
                        output_tokens = response.usage.completion_tokens
                        return content, input_tokens, output_tokens

                    return content

                elif serviceProvider == 'Gemini':
                    genai.configure(api_key=apiKey)
                    client = genai.GenerativeModel(model)
                    generation_config = {
                        "temperature": temperature,
                        "response_mime_type": "application/json",
                        "max_output_tokens": 32768
                    }

                    response = await client.generate_content_async(
                        contents=[
                            {"role": "user", "parts": [{"text": system_prompt}]},
                            {"role": "user", "parts": [{"text": user_prompt}]}
                        ],
                        generation_config=generation_config
                    )

                    content = response.text
                    if response_format:
                        content = parse_json_response(content, serviceProvider)
                    if return_usage:
                        input_tokens = response.usage_metadata.prompt_token_count
                        output_tokens = response.usage_metadata.candidates_token_count
                        return content, input_tokens, output_tokens

                    return content

                elif serviceProvider == "gemini_enterprise":
                    if isinstance(sa_info, str):
                        try:
                            sa_info = json.loads(sa_info)
                        except json.JSONDecodeError:
                            raise ValueError("Invalid service account JSON")

                    PROJECT_ID = sa_info["project_id"]
                    LOCATION = "us-central1"
                    
                    credentials = service_account.Credentials.from_service_account_info(sa_info)

                    vertexai.init(
                        project=PROJECT_ID,
                        location=LOCATION,
                        credentials=credentials,
                    )

                    client = GenerativeModel(model)
                    generation_config = {
                        "temperature": temperature,
                        "response_mime_type": "application/json",
                        "max_output_tokens": 8192 if model in ["publishers/meta/models/llama-3.3-70b-instruct-maas","publishers/google/models/gemini-2.0-flash-lite-001","publishers/google/models/gemini-2.0-flash-001"] else 32768
                    }

                    response = await client.generate_content_async(
                        contents=[
                            {"role": "user", "parts": [{"text": system_prompt}]},
                            {"role": "user", "parts": [{"text": user_prompt}]}
                        ],
                        generation_config=generation_config
                    )
                    raw_text = getattr(response, "text", "")
                    if not raw_text:
                        raise ValueError("Empty response from Gemini")

                    content = response.text
                    if response_format:
                        content = parse_json_response(content, serviceProvider)
                    if return_usage:
                        try:
                            input_tokens = response.usage_metadata.prompt_token_count
                            output_tokens = response.usage_metadata.candidates_token_count
                        except AttributeError:
                            input_tokens = 0
                            output_tokens = 0
                        return content, input_tokens, output_tokens

                    return content

                elif serviceProvider == "Azure_AI":
                    logging.info(f"Entering into Azure service Provider")
                    if resource == "AzureFoundry":
                        base_url = f"https://{resourceId}.services.ai.azure.com/openai/v1"
                    else:
                        base_url = f"https://{resourceId}.openai.azure.com/openai/v1/"
                    logging.info(f"\033[93mbase_url:{base_url}\033[0m")

                    client = AsyncOpenAI(
                        api_key=apiKey,
                        base_url=base_url
                    )
                    kwargs = {
                        "model": model,
                        "temperature": 0.5,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    }

                    if response_format:
                        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
                            kwargs["response_format"] = {"type": "json_object"}
                        else:
                            kwargs["response_format"] = response_format

                    response = await client.chat.completions.create(**kwargs)
                    content = response.choices[0].message.content

                    if isinstance(content, list):
                        content = content[0]

                    if not content or not content.strip():
                        raise APIError(
                            responseCode=500,
                            message="Empty response from model.",
                            debug_message="Model returned empty completion."
                        )

                    if response:
                        content = parse_json_response(content, serviceProvider)
                    if return_usage:
                        input_tokens = response.usage.prompt_tokens
                        output_tokens = response.usage.completion_tokens
                        return content, input_tokens, output_tokens

                    return content

                else:
                    raise ValueError(f"Unsupported serviceProvider: {serviceProvider}")

            except Exception as e:
                logger.info(f"Actual Exception caught in serviceProvider:{serviceProvider} LLMClient : {str(e)}")
                logger.info(f"LLM Call Failed ({serviceProvider}) (Attempt {attempt+1}/{retry_attempts + 1})")
                if attempt < retry_attempts:
                    print(f"Retrying in {2 ** attempt} seconds...")
                    await asyncio.sleep(2 ** attempt)
                    continue
                api_error = build_api_error(e, service_provider=serviceProvider)
                logger.error(f"LLM Client call failed: {api_error.message}")
                raise api_error


# ---------------------------------------------------------------------------
# Vision capability registry & non-retryable error detection
# ---------------------------------------------------------------------------

_NON_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({400, 401, 403, 404})

def _is_non_retryable_error(exc: Exception) -> bool:
    """Determine whether an exception represents an error that will never
    succeed on retry (e.g. bad request, auth failure, not found).

    Checks both the OpenAI-style ``status_code`` attribute and a status code
    embedded in the string representation (``Error code: NNN``).
    """

    status_code = getattr(exc, "status_code", None)
    if status_code and int(status_code) in _NON_RETRYABLE_STATUS_CODES:
        return True

    match = re.search(r"Error code:\s*(\d+)", str(exc))
    if match and int(match.group(1)) in _NON_RETRYABLE_STATUS_CODES:
        return True

    return False

class ImageLLMClient:
    """
    Universal LLM Client for handling image/multimodal payloads across
    different service providers.
    """

    @staticmethod
    async def generate_async(
        serviceProvider: str, 
        model: str, 
        apiKey: str, 
        system_prompt: str, 
        user_prompt: str,
        images: list, 
        sa_info: Optional[Any] = None, 
        resourceId: Optional[Any] = None,
        resource: Optional[Any] = None,
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
        return_usage: bool = False,
        retry_attempts: int = 2,
        unique_id: Optional[int] = None,
        mongoCollectionName: Optional[str] = None,
    ) -> Union[str, Dict, Tuple[Dict, int, int]]:
        logger = logging.getLogger(__name__)

        for attempt in range(retry_attempts + 1):
            try:
                # Setup provider fallback for DefaultFireFlink
                if serviceProvider == "DefaultFireFlink":
                    serviceProvider = "OpenAi"
                    apiKey = os.getenv("OPENAI_API_KEY")
                    model = "gpt-4.1-mini-2025-04-14"

                if serviceProvider in ["OpenAi", "Azure_AI", "Groq"]:
                    user_content = []
                    if user_prompt:
                        user_content.append({"type": "text", "text": user_prompt})

                    for img in images:
                        if isinstance(img, dict):
                            mime = img.get("mime_type", "image/png")
                            base64_data = img.get("data")
                        else:
                            if img.startswith("data:image"):
                                user_content.append({
                                    "type": "image_url",
                                    "image_url": {"url": img, "detail": "auto"}
                                })
                                continue
                            else:
                                mime = "image/png"
                                base64_data = img

                        user_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{base64_data}",
                                "detail": "auto"
                            }
                        })

                    base_url = None
                    if serviceProvider == "Groq":
                        base_url = "https://api.groq.com/openai/v1"
                    elif serviceProvider == "Azure_AI":
                        if resource == "AzureFoundry":
                            base_url = f"https://{resourceId}.services.ai.azure.com/openai/v1"
                        else:
                            base_url = f"https://{resourceId}.openai.azure.com/openai/v1/"

                    client_kwargs = {"api_key": apiKey}
                    if base_url:
                        client_kwargs["base_url"] = base_url

                    if serviceProvider == "OpenAi":
                        client = LLMClient._get_async_openai_client(apiKey)
                    else:
                        client = AsyncOpenAI(**client_kwargs)

                    payload = {
                        "model": model,
                        "temperature": 1 if model in ["o4-mini-2025-04-16", "gpt-5-2025-08-07"] else temperature,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content}
                        ]
                    }
                    if response_format:
                        payload["response_format"] = response_format

                    response = await client.chat.completions.create(**payload)
                    content = response.choices[0].message.content
                    if isinstance(content, list):
                        content = content[0]

                    if not content or not content.strip():
                        raise APIError(responseCode=500, message="Empty response from model.")

                    json_content = parse_json_response(content, serviceProvider)
                    if return_usage:
                        return json_content, response.usage.prompt_tokens, response.usage.completion_tokens
                    return json_content

                elif serviceProvider == "Gemini":
                    genai.configure(api_key=apiKey)
                    client = genai.GenerativeModel(
                        model_name=model,
                        system_instruction=system_prompt if system_prompt else None
                    )

                    parts = []
                    if user_prompt:
                        parts.append(user_prompt)

                    for img in images:
                        if isinstance(img, dict):
                            base64_data = img.get("data")
                        else:
                            base64_data = img
                            if base64_data.startswith("data:image"):
                                base64_data = base64_data.split("base64,")[1]

                        image_bytes = base64.b64decode(base64_data)
                        pil_image = Image.open(io.BytesIO(image_bytes))
                        parts.append(pil_image)

                    generation_config = {
                        "temperature": temperature,
                        "max_output_tokens": 32768
                    }
                    if response_format:
                        generation_config["response_mime_type"] = "application/json"

                    response = await client.generate_content_async(
                        contents=parts,
                        generation_config=generation_config
                    )

                    json_content = parse_json_response(response.text, serviceProvider)
                    if return_usage:
                        try:
                            in_tokens = response.usage_metadata.prompt_token_count
                            out_tokens = response.usage_metadata.candidates_token_count
                        except Exception:
                            in_tokens = 0
                            out_tokens = 0
                        return json_content, in_tokens, out_tokens
                    return json_content

                elif serviceProvider == "gemini_enterprise":
                    if isinstance(sa_info, str):
                        try:
                            sa_info = json.loads(sa_info)
                        except json.JSONDecodeError:
                            raise APIError(responseCode=400, message="Invalid service account JSON")

                    PROJECT_ID = sa_info["project_id"]
                    LOCATION = "us-central1"
                    credentials = service_account.Credentials.from_service_account_info(sa_info)
                    
                    vertexai.init(project=PROJECT_ID, location=LOCATION, credentials=credentials)
                    client = GenerativeModel(model, system_instruction=system_prompt if system_prompt else None)

                    parts = []
                    if user_prompt:
                        parts.append(user_prompt)

                    for img in images:
                        if isinstance(img, dict):
                            mime = img.get("mime_type", "image/png")
                            base64_data = img.get("data")
                        else:
                            mime = "image/png"
                            base64_data = img
                            if base64_data.startswith("data:image"):
                                mime = base64_data.split(";")[0].split(":")[1]
                                base64_data = base64_data.split("base64,")[1]

                        parts.append(Part.from_data(
                            data=base64.b64decode(base64_data),
                            mime_type=mime
                        ))

                    generation_config = {
                        "temperature": temperature,
                        "max_output_tokens": 8192 if model in ["publishers/meta/models/llama-3.3-70b-instruct-maas","publishers/google/models/gemini-2.0-flash-lite-001","publishers/google/models/gemini-2.0-flash-001"] else 32768
                    }
                    if response_format:
                        generation_config["response_mime_type"] = "application/json"

                    response = await client.generate_content_async(
                        contents=parts,
                        generation_config=generation_config
                    )

                    if not getattr(response, "text", ""):
                        raise ValueError("Empty response from Vertex AI Gemini")

                    json_content = parse_json_response(response.text, serviceProvider)
                    if return_usage:
                        try:
                            in_tokens = response.usage_metadata.prompt_token_count
                            out_tokens = response.usage_metadata.candidates_token_count
                        except Exception:
                            in_tokens = 0
                            out_tokens = 0
                        return json_content, in_tokens, out_tokens
                    return json_content

                elif serviceProvider == "Anthropic":
                    user_content = []
                    if user_prompt:
                        user_content.append({"type": "text", "text": user_prompt})

                    for img in images:
                        if isinstance(img, dict):
                            mime = img.get("mime_type", "image/png")
                            base64_data = img.get("data")
                        else:
                            mime = "image/png"
                            base64_data = img
                            if base64_data.startswith("data:image"):
                                mime = base64_data.split(";")[0].split(":")[1]
                                base64_data = base64_data.split("base64,")[1]

                        user_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": base64_data
                            }
                        })

                    client = AsyncAnthropic(api_key=apiKey)
                    response = await client.messages.create(
                        model=model,
                        max_tokens=4096,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_content}],
                        temperature=temperature
                    )

                    content = response.content[0].text
                    json_content = parse_json_response(content, serviceProvider)
                    if return_usage:
                        return json_content, response.usage.input_tokens, response.usage.output_tokens
                    return json_content

                else:
                    raise ValueError(f"Unsupported image serviceProvider: {serviceProvider}")

            except Exception as e:
                logger.error(
                    f"ImageLLMClient LLM Call Failed ({serviceProvider}) "
                    f"(Attempt {attempt + 1}/{retry_attempts + 1}): {str(e)}"
                )

                if _is_non_retryable_error(e):
                    logger.warning(
                        f"ImageLLMClient: Non-retryable error detected "
                        f"(HTTP {getattr(e, 'status_code', '?')}). "
                        f"Skipping remaining {retry_attempts - attempt} retries."
                    )
                elif attempt < retry_attempts:
                    await asyncio.sleep(2 ** attempt)
                    continue

                api_error = build_api_error(e, serviceProvider)
                logger.error(f"ImageLLMClient call failed: {api_error.message}")
                raise api_error
