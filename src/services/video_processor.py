"""Video download and preprocessing pipeline used by the Kafka worker."""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Optional

from src.api.deps import manualTestCaseDoc, s3_client
from src.config import logger
from src.integrations.video import (
    ApiVideoFetcher,
    E2EFlowResponse,
    LLMError,
    ResponseParsingError,
    S3VideoFetcher,
    build_video_s3_keys,
    delete_points_of_videos,
    VideoAPIError,
    VIDEO_FRAME_BATCH_SIZE,
    analyze_video_frame_batches,
    audio_related_checking,
    audio_video_relation,
    data_selector_chunk,
    e2e_llm_call,
    e2e_system_user_prompt,
    ensure_collection,
    extract_audio_from_video_large,
    iter_frame_batches,
    store_video_audio,
    store_video_e2e,
    store_video_per_flow,
    transcribe_audio_large,
    update_video_mongodb_status,
)
from src.persistence.embeddings import qdrant_client
from src.services.video_job_result import VideoJobResult
from src.utils.helper_function import frame_variance_stats

INVALID_VIDEO_MESSAGE = "Please upload a valid software application recording"
GENERIC_FAIL_MESSAGE = "Failed to Process the video"


def _permanent_fail(
    _lid,
    video_id: str,
    message: str,
    *,
    failure_code: str,
) -> VideoJobResult:
    update_video_mongodb_status(
        _lid=_lid,
        video_id=video_id,
        status="Failed",
        message=message,
    )
    return VideoJobResult(
        success=False,
        retriable=False,
        message=message,
        failure_code=failure_code,
    )


def _retriable_fail(message: str, *, failure_code: str) -> VideoJobResult:
    return VideoJobResult(
        success=False,
        retriable=True,
        message=message,
        failure_code=failure_code,
    )


async def download_video_from_job(job: dict[str, Any]) -> tuple[str, str]:
    """Download the video to a temp file. Returns (video_path, temp_dir)."""
    video_name = job["video_name"]
    if isinstance(video_name, list) and video_name:
        video_name = video_name[0]
    storage_type = job.get("storage_type") or "cloudS3"
    local_path = job.get("local_path")

    temp_dir = tempfile.mkdtemp(prefix="video_")
    video_path = os.path.join(temp_dir, video_name)

    try:
        if local_path and os.path.exists(local_path):
            shutil.copyfile(local_path, video_path)
            return video_path, temp_dir

        if storage_type == "cloudS3":
            bucket_name = os.getenv("BUCKET_NAME")
            fetcher = S3VideoFetcher(
                s3_client,
                bucket_name,
                job["license_id"],
                job["project_id"],
                job.get("user_id"),
            )
            s3_keys = list(job.get("s3_keys") or [])
            if job.get("s3_key") and job["s3_key"] not in s3_keys:
                s3_keys.insert(0, job["s3_key"])
            s3_keys.extend(
                build_video_s3_keys(
                    job["license_id"],
                    job["project_id"],
                    video_name=video_name,
                    user_id=job.get("user_id"),
                )
            )
            seen = set()
            unique_keys = []
            for key in s3_keys:
                if key and key not in seen:
                    seen.add(key)
                    unique_keys.append(key)
            fetcher.fetch_first_existing_to_file(
                video_path,
                unique_keys,
                video_name=video_name,
                user_id=job.get("user_id"),
            )
        else:
            fetcher = ApiVideoFetcher(
                job.get("bearer_token"),
                job.get("license_type"),
                job["project_id"],
                job.get("project_name"),
                job.get("project_type"),
            )
            file_ids = list(job.get("file_id") or [])
            if not file_ids:
                job_video_id = job.get("video_id")
                if job_video_id:
                    file_ids = [job_video_id]
            if not file_ids:
                raise RuntimeError("On-prem video download missing file id")

            for file_id in file_ids:
                await fetcher.fetch_to_file(file_id, video_path)
            if not os.path.exists(video_path):
                raise RuntimeError("On-prem video download returned empty content")

        return video_path, temp_dir
    except Exception:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise


async def process_video_background(
    _lid,
    video_id,
    video_name,
    video_path,
    temp_dir,
    collection_name,
) -> VideoJobResult:
    audio_result = None
    audio_output = None
    try:
        try:
            logger.info("Initilizing the embeddings of qdrant taking global")
            embeddings = manualTestCaseDoc.embeddings
            logger.info("Qrant initlizing completed")
        except Exception:
            logger.exception("Fail to initialize embeddings")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="embeddings_init",
            )

        try:
            logger.info("initilizing the collection in the qdrant")
            ensure_collection(collection_name, qdrant_client)
        except Exception as e:
            logger.error(f"Fail to initilize the collection in qdrant:{e}")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="qdrant_collection",
            )

        try:
            logger.info("Checking if video is blank (streaming frame batches)")
            stds: list[float] = []
            for batch in iter_frame_batches(video_path, batch_size=100):
                stds.extend(frame_variance_stats(batch))
            if not stds or all(s < 3.0 for s in stds):
                logger.info("IT IS BLANK VIDEO")
                return _permanent_fail(
                    _lid,
                    video_id,
                    INVALID_VIDEO_MESSAGE,
                    failure_code="blank_video",
                )
        except Exception:
            logger.exception("Blank video check failed")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="blank_check",
            )

        try:
            logger.info(
                "Started analyzing the video in batches of %s frame(s)",
                VIDEO_FRAME_BATCH_SIZE,
            )
            response = analyze_video_frame_batches(
                iter_frame_batches(video_path, batch_size=VIDEO_FRAME_BATCH_SIZE)
            )
            response = response.model_dump()
            logger.info(
                "Frame analysis completed with %s module(s)",
                len(response.get("modules", [])),
            )
        except VideoAPIError:
            return _permanent_fail(
                _lid,
                video_id,
                INVALID_VIDEO_MESSAGE,
                failure_code="invalid_video",
            )
        except LLMError:
            logger.exception("LLM frame analysis failed")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="llm_frame_analysis",
            )
        except ResponseParsingError:
            logger.exception("Frame analysis response parsing failed")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="frame_response_parse",
            )
        except Exception:
            logger.exception("Unexpected error during frame analysis")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="frame_analysis",
            )

        try:
            logger.info("Audio extraction started")
            audio_result = extract_audio_from_video_large(video_path)
            logger.info(f"Audio extraction result: {audio_result}")
        except Exception as e:
            logger.exception(f"Audio extraction failed: {str(e)}")
            audio_result = {"has_audio": False, "audio_path": None}

        try:
            logger.info("Aduio passing to wisper model")
            if audio_result and audio_result.get("has_audio") and audio_result.get("audio_path"):
                logger.info("Audio detected. Sending to Whisper")
                audio_path = audio_result["audio_path"]
                audio_output = transcribe_audio_large(audio_path)
                logger.info("Whisper transcription completed")
            else:
                logger.info("No audio found in video")
        except Exception as e:
            logger.exception(f"WISPER LLM FAIL ERROR: {str(e)}")

        all_module_name = []
        all_module_name_flow = []
        for per_module in response["modules"]:
            module_name = per_module["module_name"]
            all_module_name.append(module_name)
            entry_point = per_module["entry_point_url"]
            credential = per_module["credentials"]
            flow = per_module["flow"]

            module_name_flow = {
                "module_name": module_name,
                "flow": flow,
            }
            all_module_name_flow.append(module_name_flow)

            try:
                logger.info("storing data per flow in the qdrant")
                store_video_per_flow(
                    collection_name,
                    video_name,
                    module_name,
                    entry_point,
                    credential,
                    flow,
                    embeddings,
                    qdrant_client,
                    video_id,
                )
                logger.info("ended storing data per flow in the qdrant")
            except Exception:
                logger.exception("Failed storing per-flow data in Qdrant")
                return _retriable_fail(
                    GENERIC_FAIL_MESSAGE,
                    failure_code="qdrant_per_flow",
                )

        try:
            logger.info("Storing the data selector chunk in the qdrant")
            data_selector_chunk(
                collection_name,
                video_name,
                all_module_name,
                all_module_name_flow,
                embeddings,
                qdrant_client,
                video_id,
            )
            logger.info("Ended Storing the data selector chunk in the qdrant")
        except Exception:
            logger.exception("Failed storing data selector chunk in Qdrant")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="qdrant_selector",
            )

        try:
            logger.info("creating content for e2e flow")
            response.pop("is_valid_video", None)
            for i, module in enumerate(response.get("modules", [])):
                if i != 0:
                    module.pop("entry_point_url", None)
        except Exception as e:
            logger.warning(f"Not able to create data for e2e flow:{e}")

        logger.info("Creating e2e scenarios")
        system_prompt, user_prompt = e2e_system_user_prompt(response)

        try:
            logger.info("Starting LLM call for e2e scenario")
            e2e_response = e2e_llm_call(system_prompt, user_prompt)
        except LLMError:
            logger.exception("E2E LLM call failed")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="llm_e2e",
            )

        try:
            if isinstance(e2e_response, list) and len(e2e_response) > 0:
                e2e_response = e2e_response[0]
            if isinstance(e2e_response, str):
                e2e_response = E2EFlowResponse.model_validate_json(e2e_response)
            else:
                e2e_response = E2EFlowResponse.model_validate(e2e_response)
        except Exception:
            logger.exception("Invalid response schema from LLM for e2e")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="e2e_response_parse",
            )

        e2e_response = e2e_response.model_dump()
        e2e_entry_point = e2e_response["end_to_end_flow"]["entry_point"]
        e2e_flow = e2e_response["end_to_end_flow"]["steps"]

        try:
            logger.info("Storing e2e flow in the qdrant")
            store_video_e2e(
                collection_name,
                video_name,
                e2e_entry_point,
                e2e_flow,
                embeddings,
                qdrant_client,
                video_id,
            )
        except Exception:
            logger.exception("Failed storing e2e flow in Qdrant")
            return _retriable_fail(
                GENERIC_FAIL_MESSAGE,
                failure_code="qdrant_e2e",
            )

        try:
            if audio_output is not None:
                logger.info("checking if the audio is related to the video or not")
                SYSTEM_PROMPT, USER_PROMPT, RESPONSE_FORMAT = audio_video_relation(
                    e2e_response, audio_output
                )
                audio_response = audio_related_checking(
                    SYSTEM_PROMPT, USER_PROMPT, RESPONSE_FORMAT
                )
                logger.info("audio related to video or not:", audio_response)

                if audio_response.related:
                    logger.info("Storing auido in Qdrant")
                    store_video_audio(
                        collection_name,
                        video_name,
                        audio_output["transcription"],
                        embeddings,
                        qdrant_client,
                        video_id,
                    )
                    logger.info("Audio stored successfully")
        except Exception as e:
            logger.warning(f"Fail to check the audio related to video or not:{e}")

        logger.info("Successfully Preprocessing completed")
        update_video_mongodb_status(
            _lid=_lid,
            video_id=video_id,
            status="Processed",
            message="Video processed successfully.",
        )
        return VideoJobResult(
            success=True,
            retriable=False,
            message="Video processed successfully.",
        )

    except Exception:
        logger.exception("Unexpected error in video background processing")
        return _retriable_fail(
            GENERIC_FAIL_MESSAGE,
            failure_code="unexpected",
        )

    finally:
        if (
            audio_result is not None
            and audio_result.get("audio_path")
            and os.path.exists(audio_result["audio_path"])
        ):
            try:
                os.remove(audio_result["audio_path"])
            except Exception as e:
                logger.warning(f"Failed to delete temp audio: {e}")

        if temp_dir is not None and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to delete temp directory: {e}")


def _cleanup_partial_qdrant_on_retry(job: dict[str, Any]) -> None:
    retry_count = int(job.get("retry_count") or 0)
    if retry_count < 1:
        return

    collection_name = job.get("collection_name")
    video_id = job.get("video_id")
    video_name = job.get("video_name")
    if isinstance(video_name, list) and video_name:
        video_name = video_name[0]
    if not collection_name or not video_id:
        return

    try:
        logger.info(
            "Retry attempt %s: clearing existing Qdrant points for video_id=%s",
            retry_count,
            video_id,
        )
        delete_points_of_videos(collection_name, qdrant_client, video_id, video_name)
    except Exception:
        logger.exception(
            "Failed to clear Qdrant points before retry for video_id=%s",
            video_id,
        )


async def process_video_job(job: dict[str, Any]) -> VideoJobResult:
    _lid = job["_lid"]
    video_id = job["video_id"]
    video_name = job["video_name"]
    collection_name = job["collection_name"]
    video_path: Optional[str] = None
    temp_dir: Optional[str] = None

    _cleanup_partial_qdrant_on_retry(job)

    try:
        video_path, temp_dir = await download_video_from_job(job)
        return await process_video_background(
            _lid,
            video_id,
            video_name,
            video_path,
            temp_dir,
            collection_name,
        )
    except FileNotFoundError:
        logger.exception("Video file not found for video_id=%s", video_id)
        return _permanent_fail(
            _lid,
            video_id,
            GENERIC_FAIL_MESSAGE,
            failure_code="video_not_found",
        )
    except Exception:
        logger.exception("Video job failed before/during download for video_id=%s", video_id)
        if temp_dir is not None and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return _retriable_fail(
            GENERIC_FAIL_MESSAGE,
            failure_code="download",
        )
