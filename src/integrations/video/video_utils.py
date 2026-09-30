from urllib.parse import quote, unquote
from typing import Iterator
import cv2
import base64
import os
from qdrant_client.http import models as qmodels
from src.api.runtime import *
from openai import OpenAI
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)
import time
from pydantic import BaseModel, Field, AliasChoices,ValidationError,field_validator
import json

from groq import Groq
token_usage = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
}
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)
VECTOR_SIZE = 768
import logging
logger = logging.getLogger(__name__)

VIDEO_FRAME_BATCH_SIZE = int(os.getenv("VIDEO_FRAME_BATCH_SIZE", "500"))
DOWNLOAD_CHUNK_SIZE = 8192

def ensure_collection(collection_name,qdrant_client):
    existing = [c.name for c in qdrant_client.get_collections().collections]
    if collection_name not in existing:
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=VECTOR_SIZE,
                distance=qmodels.Distance.COSINE
            )
        )

def _encode_frame_to_base64(
    frame,
    max_width: int = 640,
    jpeg_quality: int = 65,
) -> str | None:
    height, width = frame.shape[:2]

    if width > max_width:
        ratio = max_width / width
        new_height = int(height * ratio)
        frame = cv2.resize(
            frame,
            (max_width, new_height),
            interpolation=cv2.INTER_AREA,
        )

    success, buffer = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
    )
    if success:
        return base64.b64encode(buffer).decode("ascii")
    return None


def iter_frame_batches(
    video_path: str,
    batch_size: int | None = None,
    frame_interval_seconds: float = 1.0,
    max_width: int = 640,
    jpeg_quality: int = 65,
) -> Iterator[list[str]]:
    """Yield base64 JPEG frames in batches without holding all frames in memory."""
    batch_size = batch_size or VIDEO_FRAME_BATCH_SIZE
    cap = cv2.VideoCapture(video_path)

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30

        frame_interval = max(1, round(fps * frame_interval_seconds))
        frame_number = 0
        batch: list[str] = []

        while True:
            success, frame = cap.read()
            if not success:
                break

            if frame_number % frame_interval == 0:
                encoded = _encode_frame_to_base64(frame, max_width, jpeg_quality)
                if encoded:
                    batch.append(encoded)
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []

            frame_number += 1

        if batch:
            yield batch
    finally:
        cap.release()


def extract_frames(
    video_path: str,
    frame_interval_seconds: float = 1.0,
    max_width: int = 640,
    jpeg_quality: int = 65,
):
    frames = []
    for batch in iter_frame_batches(
        video_path,
        batch_size=VIDEO_FRAME_BATCH_SIZE,
        frame_interval_seconds=frame_interval_seconds,
        max_width=max_width,
        jpeg_quality=jpeg_quality,
    ):
        frames.extend(batch)
    return frames

VIDEO_CONTENT_EXTRACTION_PROMPT = """
You are analyzing a sequence of screenshots extracted from a screen recording of a website or mobile app, captured at one frame per second, in chronological order.

IMPORTANT: The very first image provided to you in this request is a fixed REFERENCE FRAME — it always shows the entry point / home screen / launch state of the application for the entire session, regardless of which part of the video the remaining frames belong to. All frames after the reference frame are the actual sequential batch you must analyze.
STRICT: Duplicate module_name not allowed,module_name should be always unique

===== VALIDITY GATE (check this FIRST, before anything else) =====
Before extracting any modules, determine whether this batch actually shows a website/app UI walkthrough with a user performing on-screen actions (navigation, taps, clicks, form entry, etc.).

Set "is_valid_video" to false if the frames show any of the following instead:
- Content unrelated to a UI/app/website (e.g. a person, an animal, outdoor scenery, a physical object, a video call, etc.)
- Entirely blank, black, static, or corrupted frames with no discernible UI
- Frames that are too irrelevant, low-quality, or inconsistent to identify any real screen or user action

Set "is_valid_video" to true only if the frames clearly show a UI being used (a website or app screen with visible navigation/interaction).

If "is_valid_video" is false: set "modules" to an empty array [] and do NOT attempt to extract, infer, or fabricate any module, URL, credential, or step. Do not guess based on partial similarity — if in doubt about relevance to a UI walkthrough, and the content is clearly not a screen recording, mark it invalid.

If "is_valid_video" is true, proceed with the full module extraction below.

===== MODULE SEGMENTATION RULE (do not violate) =====
Segment modules at the SAME granularity you would if there were no reference frame at all — purely based on distinct user intents/activities visible in the batch frames (e.g. Homepage Browsing, Login, Sign Up, Search Product, View Product Detail, Cart Review, Checkout - Delivery Details, Checkout - Payment, etc.). The reference frame must NEVER be a reason to merge two distinct modules into one.

===== FLOW RECONSTRUCTION RULE (do not violate) =====
Every module's "flow" array must reconstruct the FULL CUMULATIVE PATH from the application entry point through EVERY module that was already completed earlier in this session, before detailing this module's own steps. Do not jump straight from "entry point" to this module's own actions — that skips the journey and is WRONG.

IMPORTANT: Always start from smallest module then go to higher module, example: home page -> login -> sign up -> and so on.
Generate as much as possible module
**VERY IMPORTANT** : The initial step for every module should be given properly without missing any step and module should be completed properly.
Build each module's "flow" in exactly this structure:
1. Step 1: "User starts at the application entry point (<url/screen from reference frame>)".
2. One summarizing step for EACH module that occurred earlier in this session (in order), phrased briefly, e.g.:
The steps should be completely given with proper initial flow 
clickable actions should be given properly without missing any button,field etc
   - "User completes Login/Sign Up"
   - "User completes Search Product"
   - "User completes View Product Detail"
   - "User completes Cart Review" etc...
Very important: Do not mix the sign up process and buying the product process (sign up(allfieldfilling)->seraching->add cart->then filling dilivery details(allfielddilling))
In the module give each and every step very detail step by step do not miss a single step also
   Include one such step per prior module, even if that module was analyzed in an earlier batch (infer briefly from context available in this batch, e.g. a payment page implies delivery details were already completed).
   If this is the very FIRST module in the entire session (nothing precedes it), skip this step entirely.
3. Then, this module's OWN step-by-step actions in full detail — every field entered, every button clicked, every screen transition actually visible in the batch frames. Do not compress this part; this is the level of detail that matters most.

If the navigation path connecting entry point to this module is not inferable at all (very rare), use: "Continuing from entry point (navigation prior to this batch not visible)" as step 1 instead, then proceed with this module's own actions.

For each module, extract:

1. "module_name": A short, clear label for the flow.
2. "entry_point_url": Take the exact application url of starting(starting url every where for every module)
3. "credentials": Any username, email, password, OTP, or other credential/input values visible on screen DURING THIS SPECIFIC MODULE ONLY. Capture as {"field_name": "value"}. If masked, use "masked". If none, use {}.
4. "flow": Per the FLOW RECONSTRUCTION RULE above — cumulative prior-module summary steps, then this module's own detailed steps.

Rules:
-for entry_point_url never give this https://www.google.com give the exact application url 
- Base every field strictly on what is visibly present in the frames. Never invent a URL, credential, or step not shown — except for brief prior-module summary steps, which may be inferred logically from what modules necessarily preceded this one.
- Ignore blank/black/no-change frames within an otherwise valid UI video — this is different from the whole batch being invalid.
- Output ONLY a single valid JSON object (not an array at the top level). No prose, no markdown fences, no commentary.

module_name : Should be always uniqued/duplicate module_name not allowed

Output format (valid video):
{
  "is_valid_video": true,
  "modules": [
    {
      "module_name": "...",
      "entry_point_url": "...",
      "credentials": {},
      "flow": [
        "User starts at the application entry point (...)",
        "User completes <PriorModule1> (...)",
        "User completes <PriorModule2> (...)",
        "... this module's own detailed steps ..."
      ]
    }
  ]
}

Output format (invalid video):
{
  "is_valid_video": false,
  "modules": []
}

Rule : 1. Give exact json format as given above
       2. start and close the json properly
       3. Nevere generate duplicate module name
"""

def previous_module(previous_last_module,module_names):
    previous_module_json = previous_last_module.model_dump_json(indent=2)
    continuation_instruction = f"""
The following module is the LAST module extracted from the previous batch, and it may be incomplete:
{previous_module_json}

**STRTCI RULE**: Already exist module: {module_names} : This module not allowed
And use this module for sequencing the step in the furture modules.
Always module name should be different
Same Module name not accepted

===== CONTINUATION RULE (read carefully) =====
Only append to this module the frames that are a DIRECT, UNBROKEN continuation of its own last listed step 
— same screen, same task, no navigation away. The instant a frame shows ANY of the following, this module 
is CLOSED immediately at that point (do not include that frame or anything after it in it):
- navigation to a different screen/section (e.g. homepage, a different category, account settings, logout)
- the start of a visibly different user intent, even if related (e.g. browsing a new product category, 
  managing the cart again, viewing account/profile sections)
- a page reload/redirect that lands somewhere unrelated to what this module was doing

Do NOT keep appending steps to this module just because the session is continuous — a continuous SESSION is 
not the same as a continuous MODULE. If in doubt about whether a frame still belongs, treat it as NOT 
belonging and close the module there.

If this module receives any new steps in this batch, output it as the FIRST object in "modules", using the 
SAME "module_name" as above, with its "flow" containing ONLY the newly observed steps to append (not the 
old ones already given to you), and set "is_continuation": true on it. If nothing in this batch continues 
it at all (the very first relevant frame already shows a new intent), omit it from "modules" entirely.

Once this module is closed, extract every remaining frame in this batch into NEW modules in "modules", 
following the exact same MODULE SEGMENTATION RULE and FLOW RECONSTRUCTION RULE as normal — including 
creating MULTIPLE separate new modules if multiple distinct intents appear later in the batch (e.g. 
"Homepage Browsing", "Browsing Storage & Organisation", "Product Detail - Shelving Unit", "Cart Management", 
"Account Settings", "Logout" would each be their OWN module, not merged together just because they came 
after the pending one). For every NEW module, begin its "flow" using all previously completed modules 
(including the now-closed pending one) exactly as described in the FLOW RECONSTRUCTION RULE, and do NOT set 
"is_continuation" on these.
"""
    return continuation_instruction

module_schema = {
    "type": "object",
    "properties": {
        "is_valid_video": {
            "type": "boolean"
        },
        "modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string"
                    },
                    "entry_point_url": {
                        "type": "string"
                    },
                    "credentials": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_name": {
                                    "type": "string"
                                },
                                "value": {
                                    "type": "string"
                                }
                            },
                            "required": [
                                "field_name",
                                "value"
                            ],
                            "additionalProperties": False
                        }
                    },
                    "flow": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    }
                },
                "required": [
                    "module_name",
                    "entry_point_url",
                    "credentials",
                    "flow"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": [
        "is_valid_video",
        "modules"
    ],
    "additionalProperties": False
}


class LLMError(Exception):
    pass

class Module(BaseModel):
    module_name: str
    entry_point_url: str
    credentials: Dict[str, str] = Field(default_factory=dict)
    flow: List[str]

    @field_validator("credentials", mode="before")
    @classmethod
    def convert_credentials(cls, value: Any):
        # Already a dictionary
        if isinstance(value, dict):
            return value

        # Convert list -> dictionary
        if isinstance(value, list):
            return {
                item["field_name"]: item["value"]
                for item in value
                if "field_name" in item and "value" in item
            }

        return {}
    
class VideoAnalysis(BaseModel):
    is_valid_video: bool
    modules: List[Module] = Field(
        validation_alias=AliasChoices("modules", "module")
    )

class ResponseParsingError(Exception):
    pass

class VideoAPIError(Exception):
    def __init__(self, responseCode: int, message: str):
        self.responseCode = responseCode
        self.message = message
        self.status = "FAILURE"

        self.error = {
            "responseCode": responseCode,
            "message": message,
        }
        super().__init__(str(self.error))


class EndToEndFlow(BaseModel):
    entry_point: str = Field(
        description=(
            "The starting URL or entry point of the application. "
            "Use an empty string if unavailable."
        )
    )
    steps: List[str] = Field(
        description="Ordered list of end-to-end test steps."
    )


class E2EFlowResponse(BaseModel):
    end_to_end_flow: EndToEndFlow

class AudioChecking(BaseModel):
    related: bool

def extract_the_last_module(batch_response):
    logger.info("last module extraction started")
    
    last_module=batch_response.modules[-1]
    module_names = [module.module_name for module in batch_response.modules[:-1]]
    return last_module,module_names


def _call_llm_for_frame_batch(
    batch: list[str],
    *,
    previous_last_module,
    module_names: list[str],
    batch_index: int,
    max_retries: int = 2,
    retry_delay: int = 5,
) -> VideoAnalysis:
    content = []
    if previous_last_module is None:
        content.append({
            "type": "input_text",
            "text": VIDEO_CONTENT_EXTRACTION_PROMPT,
        })
    else:
        add_previous_module = previous_module(previous_last_module, module_names)
        content.append({
            "type": "input_text",
            "text": add_previous_module + "\n\n" + VIDEO_CONTENT_EXTRACTION_PROMPT,
        })

    content.extend([
        {
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{frame}",
        }
        for frame in batch
    ])

    batch_response = None
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"LLM call started for batch {batch_index} ({len(batch)} frames)")
            response = client.responses.create(
                model="gpt-4.1-mini",
                input=[{"role": "user", "content": content}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "video_analysis",
                        "strict": True,
                        "schema": module_schema,
                    }
                },
            )
            batch_response = response.output_text
            logger.info(f"LLM call ended for batch {batch_index}")
            break
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}. Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
            else:
                logger.exception(f"LLM call failed for batch {batch_index}")
                raise LLMError(str(e)) from e

    try:
        if isinstance(batch_response, list) and len(batch_response) > 0:
            batch_response = batch_response[0]
        if isinstance(batch_response, str):
            parsed = VideoAnalysis.model_validate_json(batch_response)
        else:
            parsed = VideoAnalysis.model_validate(batch_response)
    except Exception as e:
        logger.exception("Invalid response schema from LLM")
        raise ResponseParsingError(str(e)) from e

    if parsed.is_valid_video is False:
        logger.warning("Invalid software application recording uploaded.")
        raise VideoAPIError(
            responseCode=400,
            message="Invalid software application recording uploaded.",
        )
    return parsed


def _merge_video_batch_response(
    merged_response: VideoAnalysis | None,
    batch_response: VideoAnalysis,
) -> VideoAnalysis:
    if merged_response is None:
        return batch_response.model_copy(deep=True)

    for new_module in batch_response.modules:
        if (
            merged_response.modules
            and merged_response.modules[-1].module_name == new_module.module_name
        ):
            merged_response.modules[-1] = new_module
        else:
            merged_response.modules.append(new_module)
    return merged_response


def analyze_video_frame_batches(frame_batches: Iterator[list[str]]) -> VideoAnalysis:
    """Analyze video frames batch-by-batch to limit peak memory usage."""
    previous_last_module = None
    module_names: list[str] = []
    merged_response = None
    batch_index = 0

    for batch in frame_batches:
        if not batch:
            continue

        batch_index += 1
        print(f"Processing batch {batch_index}")
        logger.info(f"Processing frame batch {batch_index}: {len(batch)} frame(s)")

        batch_response = _call_llm_for_frame_batch(
            batch,
            previous_last_module=previous_last_module,
            module_names=module_names,
            batch_index=batch_index,
        )

        try:
            merged_response = _merge_video_batch_response(merged_response, batch_response)
        except Exception as e:
            logger.warning(f"Fail to merge the responses:{e}")
            raise

        try:
            logger.info("Fetching the last module from previous json")
            previous_last_module, module_names = extract_the_last_module(batch_response)
            logger.info("Fetching completed for the last module from previous json")
        except Exception as e:
            logger.exception("Response parsing failed")
            raise ResponseParsingError(str(e)) from e

    if merged_response is None:
        raise VideoAPIError(
            responseCode=400,
            message="Invalid software application recording uploaded.",
        )
    return merged_response


def analyze_video_frames(frames):
    def _list_batches() -> Iterator[list[str]]:
        for start in range(0, len(frames), VIDEO_FRAME_BATCH_SIZE):
            yield frames[start:start + VIDEO_FRAME_BATCH_SIZE]

    return analyze_video_frame_batches(_list_batches())

import imageio_ffmpeg
import subprocess
import tempfile
import re
import os
def extract_audio_from_video_large(video_path):
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    # Create a temporary WAV path
    fd, temp_audio_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        probe = subprocess.run(
            [
                ffmpeg_path,
                "-hide_banner",
                "-i",
                video_path
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )

        if "Audio:" not in probe.stderr:
            return {
                "has_audio": False,
                "audio_path": None
            }

        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i", video_path,
                "-vn",
                "-ac", "1",
                "-ar", "16000",
                "-c:a", "pcm_s16le",
                temp_audio_path
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        silence_check = subprocess.run(
            [
                ffmpeg_path,
                "-hide_banner",
                "-i", temp_audio_path,
                "-af", "silencedetect=noise=-50dB:d=0.5",
                "-f", "null",
                "NUL" if os.name == "nt" else "/dev/null"
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )

        stderr = silence_check.stderr

        # Get audio duration
        duration_match = re.search(
            r"Duration:\s*(\d+):(\d+):([\d.]+)",
            probe.stderr
        )

        duration = None

        if duration_match:
            hours = int(duration_match.group(1))
            minutes = int(duration_match.group(2))
            seconds = float(duration_match.group(3))

            duration = (
                hours * 3600 +
                minutes * 60 +
                seconds
            )

        silence_starts = re.findall(
            r"silence_start:\s*([\d.]+)",
            stderr
        )

        silence_ends = re.findall(
            r"silence_end:\s*([\d.]+)",
            stderr
        )

        completely_silent = False

        if duration is not None:

            # Case 1:
            # silence starts near beginning and extends to end
            if silence_starts:
                first_silence_start = float(silence_starts[0])

                if first_silence_start <= 0.1:

                    # If there is no silence_end, FFmpeg considers
                    # silence to continue until EOF.
                    if not silence_ends:
                        completely_silent = True

                    # Otherwise check whether silence ends at/near EOF
                    elif float(silence_ends[-1]) >= duration - 0.1:
                        completely_silent = True

        if completely_silent:
            try:
                os.remove(temp_audio_path)
            except OSError:
                pass

            return {
                "has_audio": False,
                "audio_path": None
            }

        return {
            "has_audio": True,
            "audio_path": temp_audio_path
        }
    except Exception as e:
        try:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
        except OSError:
            pass
        return {
            "has_audio": False,
            "audio_path": None,
            "error": str(e)
        }

def transcribe_audio_large(audio_path):
    try:
        with open(audio_path, "rb") as f:
            result = groq_client.audio.transcriptions.create(
                file=("audio.wav", f.read()),
                model="whisper-large-v3-turbo",
                prompt="Specify context or spelling with punctuation",
            )
        return {
            "success": True,
            "transcription": result.text,
            "error": None
        }

    except FileNotFoundError:
        return {
            "success": False,
            "transcription": None,
            "error": f"Audio file not found: {audio_path}"
        }

    except Exception as e:
        return {
            "success": False,
            "transcription": None,
            "Actual_llm_error": f"Audio error:{e}"
        }
    
import uuid
def store_video_per_flow(collection_name,video_name,module_name, entry_point,credential,flow,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_flow called")
    for attempt in range(max_retries + 1):
        try:
            points = []
            document_id = str(uuid.uuid4())
            
            vector = embeddings.embed_query(video_name)
            payload = {
                "document_id": document_id,
                "video_name":video_name,
                "module_name": module_name,
                "entry_point": entry_point,   
                "credential":credential,
                "flow":flow,         
                "mongo_id":mongo_id,
            }
            points.append(
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                )
            )
            qdrant_client.upsert(collection_name=collection_name, points=points)
            return
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"end_to_end_image failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts with error : {e}"
                )

def data_selector_chunk(collection_name,video_name,all_module_name,all_module_name_flow,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_flow called")
    for attempt in range(max_retries + 1):
        try:
            points = []
            document_id = str(uuid.uuid4())
            chunk_id=-1
            vector = embeddings.embed_query(video_name)
            payload = {
                "document_id": document_id,
                "chunk_id":chunk_id,
                "video_name":video_name,
                "all_module_name":all_module_name,
                "all_module_name_flow": all_module_name_flow,
                "mongo_id":mongo_id,
            }
            points.append(
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                )
            )
            qdrant_client.upsert(collection_name=collection_name, points=points)
            return
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"end_to_end_image failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts with error : {e}"
                )


def e2e_system_user_prompt(data):

    SYSTEM_PROMPT = """
You are a QA test-flow analyst. You receive a JSON array of "modules" from a screen-recording analysis pipeline. Each module has this shape:

{
  "module_name": string,
  "entry_point_url": string,(Give the exact application url)(example:https://www.ikea.com/)
  "flow": array of strings (ordered steps; some lines are back-references like "User completes <Module Name>" instead of actual steps)
}

Your job: merge ALL modules into ONE single end-to-end flow, in the order the modules appear in the input.
Flow: Always make sure that the steps in each module should be analyze properly and then join it in the poper flow step by step(end to end flow)

Very important: Do not mix the sign up process and buying the product process example:  (sign up(allfieldfilling)->seraching->add cart->then filling dilivery details(allfielddilling))
Rules:
1. Output exactly ONE flow. Do not split into multiple flows.
2. Ignore/skip all back-reference lines ("User completes <module>", "User starts at the application entry point...") — they just point to modules that are already being merged in order, so they add nothing new.
3. Take every remaining literal step from every module's "flow" array, in order, and concatenate them into one "steps" list.
4. No step may appear twice in the final "steps" list. If a step is a genuine repeat, keep only the first occurrence.
5. Do not skip, shorten, merge, or paraphrase any literal step — copy it as-is.
7. "entry_point" = the entry_point_url of the first module. If none exists, null.
8. Never invent steps, URLs, or values not present in the source data.
9. Output ONLY valid JSON — no markdown fences, no commentary.

Output schema (strict):
{
  "end_to_end_flow": {
    "entry_point": string | null,
    "steps": [ string, ... ]
  }
}
"""

    USER_PROMPT = f"""These are my individual modules with their flows:

{json.dumps(data, indent=2)}"""

    return SYSTEM_PROMPT, USER_PROMPT


response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "e2e_flow_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "end_to_end_flow": {
                    "type": "object",
                    "properties": {
                        "entry_point": {
                            "type": "string",
                            "description": "The starting URL or entry point of the application. Use an empty string if unavailable."
                        },
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "Ordered list of end-to-end test steps."
                        }
                    },
                    "required": [
                        "entry_point",
                        "steps"
                    ],
                    "additionalProperties": False
                }
            },
            "required": [
                "end_to_end_flow"
            ],
            "additionalProperties": False
        }
    }
}



def e2e_llm_call(system_prompt, user_prompt):
    max_retries = 2
    retry_delay = 2
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"LLM request attempt {attempt + 1}/{max_retries + 1}")

            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
                max_completion_tokens=65000,
            )

            if response.usage:
                token_usage["prompt_tokens"] += response.usage.prompt_tokens
                token_usage["completion_tokens"] += response.usage.completion_tokens
                token_usage["total_tokens"] += response.usage.total_tokens

            return response.choices[0].message.content

        except Exception as e:
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}"
            )

            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.exception("Maximum retries reached.")
                raise LLMError(f"LLM request failed after retries: {e}") from e



def store_video_e2e(collection_name,video_name,e2e_entry_point,e2e_flow,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_flow called")
    for attempt in range(max_retries + 1):
        try:
            points = []
            document_id = str(uuid.uuid4())
            
            vector = embeddings.embed_query(video_name)
            payload = {
                "document_id": document_id,
                "chunk_type": "end to end",
                "FLOW":"end to end",
                "video_name":video_name,
                "e2e_entry_point": e2e_entry_point,
                "e2e_flow":e2e_flow,
                "mongo_id":mongo_id,
            }
            points.append(
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                )
            )
            qdrant_client.upsert(collection_name=collection_name, points=points)
            return
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"end_to_end_image failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts"
                )

def audio_video_relation(end_to_end_flow, audio_text):
    """
    end_to_end_flow: dict like { "entry_point": string | null, "steps": [ string, ... ] }
    audio_text: string
    """

    SYSTEM_PROMPT = """
You are a QA analyst validating whether narrated audio matches an observed screen-recording flow.

You receive:
1. An "end_to_end_flow" — the ordered, literal UI steps extracted from a screen recording.
2. An "audio_text" — the transcribed narration/commentary spoken during that same recording.

Your job: determine whether the audio_text is describing/related to the actions in the end_to_end_flow, or whether it is unrelated (e.g. off-topic conversation, unrelated narration, silence/noise transcribed as filler, or describing a completely different flow).

Rules:
1. Base your judgment ONLY on whether the audio content semantically corresponds to the steps in end_to_end_flow — do not judge grammar, audio quality, or completeness.
2. The audio does not need to describe every single step. Partial coverage that is clearly about the same flow/task still counts as related.
3. If the audio talks about a different task, a different application, or contains no meaningful connection to the steps, mark it as not related.
4. If audio_text is empty, null, or contains no meaningful content, mark it as not related.
5. Never invent steps or content not present in the source data.
6. Output ONLY valid JSON — no markdown fences, no commentary.

Output schema (strict):
{
  "related": true | false
}
"""

    USER_PROMPT = f"""Here is the end-to-end flow:

{json.dumps(end_to_end_flow, indent=2)}

Here is the audio transcript:

{audio_text}"""

    RESPONSE_FORMAT = {
        "type": "json_schema",
        "json_schema": {
            "name": "audio_video_relation",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "related": {
                        "type": "boolean"
                    }
                },
                "required": ["related"],
                "additionalProperties": False
            }
        }
    }

    return SYSTEM_PROMPT, USER_PROMPT, RESPONSE_FORMAT


def audio_related_checking(system_prompt, user_prompt,response_format):
    max_retries = 2
    retry_delay = 2
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"LLM request attempt {attempt + 1}/{max_retries + 1}")

            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
                max_completion_tokens=65000,
            )

            if response.usage:
                token_usage["prompt_tokens"] += response.usage.prompt_tokens
                token_usage["completion_tokens"] += response.usage.completion_tokens
                token_usage["total_tokens"] += response.usage.total_tokens

            audio_response=response.choices[0].message.content

            try:
                logger.info("Checking pydantic for the audio relation")
                if isinstance(audio_response,list) and len(audio_response)>0:
                    audio_response=audio_response[0]
                if isinstance(audio_response,str):
                    audio_response=AudioChecking.model_validate_json(audio_response)
                else:
                    audio_response=AudioChecking.model_validate(audio_response)
            except Exception as e:
                logger.info(f"pydantic fail to match json:{e}")

            return audio_response   
               
        except Exception as e:
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}"
            )

            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.exception("Maximum retries reached.")
                raise LLMError(f"LLM request failed after retries: {e}") from e


def store_video_audio(collection_name,video_name,video_audio,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_flow called")
    for attempt in range(max_retries + 1):
        try:
            points = []
            document_id = str(uuid.uuid4())
            
            vector = embeddings.embed_query(video_name)
            payload = {
                "document_id": document_id,
                "chunk_type": "video_audio",
                "video_name":video_name,
                "video_related_audio": video_audio,
                "mongo_id":mongo_id,
            }
            points.append(
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                )
            )
            qdrant_client.upsert(collection_name=collection_name, points=points)
            return
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"end_to_end_image failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts"
                )


class VideoUploadPreprocessPayload(BaseModel):
    video_name: List[str] = []
    license_id: str
    video_id: str
    storageType: Optional[List[str]] = None
    replace: bool
    user_id: str


def Video_ID_Normalization(attachment_id) -> tuple:
    
    if isinstance(attachment_id, str):
        return [attachment_id], None
    elif isinstance(attachment_id, list):
        return attachment_id, None
    else:
        return None, {
            "status": "failure",
            "responseCode": 400,
            "message": "attachment_id must be a string or list"
        }


def _video_download_headers(
    bearer_token,
    license_type,
    project_id,
    project_name,
    project_type,
) -> dict[str, str]:
    return {
        "Authorization": f"{bearer_token}",
        "licensetype": license_type,
        "projectid": project_id,
        "projectname": project_name,
        "projecttype": project_type,
    }


def fetch_video(
    file_id,
    bearer_token,
    license_type,
    project_id,
    project_name,
    project_type,
):
    base_url = os.getenv("base_url")
    url = f"{base_url}/optimize/v1/file/download/cloud/{file_id}"
    headers = _video_download_headers(
        bearer_token,
        license_type,
        project_id,
        project_name,
        project_type,
    )

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as e:
        logger.error(f"File fetch failed: {e}")
        return None


def fetch_video_to_file(
    file_id,
    dest_path,
    bearer_token,
    license_type,
    project_id,
    project_name,
    project_type,
) -> None:
    base_url = os.getenv("base_url")
    url = f"{base_url}/optimize/v1/file/download/cloud/{file_id}"
    headers = _video_download_headers(
        bearer_token,
        license_type,
        project_id,
        project_name,
        project_type,
    )

    response = requests.get(url, headers=headers, stream=True, timeout=300)
    response.raise_for_status()
    with open(dest_path, "wb") as dest:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
            if chunk:
                dest.write(chunk)


def _s3_name_variants(name: str) -> list[str]:
    variants: list[str] = []
    for value in (
        name,
        unquote(name),
        quote(name, safe=""),
        quote(name, safe="[](). "),
        name.replace(" ", "_"),
        name.replace(" ", "+"),
        name.replace(" ", "%20"),
    ):
        if value and value not in variants:
            variants.append(value)
    return variants


def build_video_s3_keys(
    license_id: str,
    project_id: str,
    *,
    video_name: str | None = None,
    extra_keys: list | None = None,
    user_id: str | None = None,
) -> list[str]:
    """S3 stores videos under User/{user_id}/aiChat/{video_name}."""
    prefix = (
        f"License/{license_id}/"
        f"Project/{project_id}/"
        f"User/{user_id}/"
        f"aiChat/"
    )
    object_names: list[str] = []
    if video_name:
        for variant in _s3_name_variants(str(video_name)):
            if variant not in object_names:
                object_names.append(variant)

    keys = [f"{prefix}{name}" for name in object_names]
    for key in extra_keys or []:
        if key and key not in keys:
            keys.append(key)
    return keys


class S3VideoFetcher:
    def __init__(self, s3_client, bucket_name, license_id, project_id, user_id=None):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.license_id = license_id
        self.project_id = project_id
        self.user_id = user_id

    def _prefix(self) -> str:
        return (
            f"License/{self.license_id}/"
            f"Project/{self.project_id}/"
            f"User/{self.user_id}/"
            f"aiChat/"
        )

    def fetch_by_key(self, s3_key: str) -> bytes:
        logger.info(f"Fetching from S3: s3://{self.bucket_name}/{s3_key}")
        file_obj = self.s3_client.get_object(
            Bucket=self.bucket_name,
            Key=s3_key,
        )
        return file_obj["Body"].read()

    def download_by_key(self, s3_key: str, dest_path: str) -> None:
        logger.info(f"Streaming S3 object to file: s3://{self.bucket_name}/{s3_key}")
        file_obj = self.s3_client.get_object(
            Bucket=self.bucket_name,
            Key=s3_key,
        )
        with open(dest_path, "wb") as dest:
            for chunk in file_obj["Body"].iter_chunks(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    dest.write(chunk)

    def _list_prefix_keys(self) -> list[str]:
        prefix = self._prefix()
        keys: list[str] = []
        paginator = self.s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            for obj in page.get("Contents") or []:
                key = obj.get("Key")
                if key:
                    keys.append(key)
        logger.info(
            "Listed %s object(s) under s3://%s/%s",
            len(keys),
            self.bucket_name,
            prefix,
        )
        return keys

    def _match_listed_key(self, listed: list[str], video_name: str | None, user_id: str | None) -> str | None:
        names = [unquote(video_name), video_name] if video_name else []
        names = [n for n in names if n]

        def basename(key: str) -> str:
            return unquote(key.rsplit("/", 1)[-1])

        for key in listed:
            base = basename(key)
            for name in names:
                if base == name or base.lower() == name.lower():
                    return key
        if user_id:
            for key in listed:
                if user_id in key and key.lower().endswith(".mp4"):
                    return key
        mp4s = [key for key in listed if key.lower().endswith(".mp4")]
        if video_name and mp4s:
            target = unquote(video_name).lower()
            for key in mp4s:
                if target in basename(key).lower() or basename(key).lower() in target:
                    return key
        if len(mp4s) == 1:
            return mp4s[0]
        return None

    def fetch_first_existing(
        self,
        s3_keys: list[str],
        *,
        video_name: str | None = None,
        user_id: str | None = None,
    ) -> bytes:
        from botocore.exceptions import ClientError

        last_error = None
        for s3_key in s3_keys:
            try:
                return self.fetch_by_key(s3_key)
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in {"NoSuchKey", "404"}:
                    logger.warning(f"S3 key not found, trying next: {s3_key}")
                    last_error = e
                    continue
                raise

        try:
            listed = self._list_prefix_keys()
            matched = self._match_listed_key(listed, video_name, user_id)
            if matched:
                logger.info("Matched video via S3 list: %s", matched)
                return self.fetch_by_key(matched)
            logger.error(
                "No matching video under prefix. Sample keys: %s",
                listed[:20],
            )
        except Exception:
            logger.exception("S3 prefix listing failed")

        raise last_error or FileNotFoundError("No S3 keys provided for video download")

    def fetch_first_existing_to_file(
        self,
        dest_path: str,
        s3_keys: list[str],
        *,
        video_name: str | None = None,
        user_id: str | None = None,
    ) -> None:
        from botocore.exceptions import ClientError

        last_error = None
        for s3_key in s3_keys:
            try:
                self.download_by_key(s3_key, dest_path)
                return
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in {"NoSuchKey", "404"}:
                    logger.warning(f"S3 key not found, trying next: {s3_key}")
                    last_error = e
                    continue
                raise

        try:
            listed = self._list_prefix_keys()
            matched = self._match_listed_key(listed, video_name, user_id)
            if matched:
                logger.info("Matched video via S3 list: %s", matched)
                self.download_by_key(matched, dest_path)
                return
            logger.error(
                "No matching video under prefix. Sample keys: %s",
                listed[:20],
            )
        except Exception:
            logger.exception("S3 prefix listing failed")

        raise last_error or FileNotFoundError("No S3 keys provided for video download")


class ApiVideoFetcher:
    def __init__(
        self,
        bearer_token,
        license_type,
        project_id,
        project_name,
        project_type,
    ):
        self.bearer_token = bearer_token
        self.license_type = license_type
        self.project_id = project_id
        self.project_name = project_name
        self.project_type = project_type

    async def fetch(self, file_id: str) -> bytes:
        logger.info(f"Fetching video via API: file_id={file_id}")
        file_bytes = fetch_video(
            file_id=file_id,
            bearer_token=self.bearer_token,
            license_type=self.license_type,
            project_id=self.project_id,
            project_name=self.project_name,
            project_type=self.project_type,
        )

        if not file_bytes:
            raise Exception(
                "Unable to process the uploaded file. Please upload a valid file"
            )

        return file_bytes

    async def fetch_to_file(self, file_id: str, dest_path: str) -> None:
        logger.info(f"Streaming video via API to file: file_id={file_id}")
        try:
            fetch_video_to_file(
                file_id=file_id,
                dest_path=dest_path,
                bearer_token=self.bearer_token,
                license_type=self.license_type,
                project_id=self.project_id,
                project_name=self.project_name,
                project_type=self.project_type,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"File fetch failed: {e}")
            raise Exception(
                "Unable to process the uploaded file. Please upload a valid file"
            ) from e