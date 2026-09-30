"""Shared imports and names used by API route modules."""

import logging
from datetime import datetime, timezone
from io import BytesIO
import base64
from typing import Any, Dict, List, Optional, Union, Sequence
from urllib.parse import urlparse

import boto3
import cv2
import hvac
import numpy as np
import openpyxl
import pandas as pd
import requests
import tiktoken
from botocore.exceptions import ClientError
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient, QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, VectorParams
from toon import encode
from werkzeug.utils import secure_filename

from src.agents.helpers import update_ai_service_instance_token_usage
from src.agents.operations import AgentOperation
from src.config import get_ca_file, get_ck_file
from src.api.deps import (
    MAX_RETRIES,
    event_generator,
    get_collection,
    get_mongo_url,
    manualTestCase,
    manualTestCaseDoc,
    s3_client,
    serialize,
)
from src.core.exception import APIError, build_api_error, build_error_response
from src.core.generation_cancel import (
    GenerationCancelled,
    request_cancel,
    request_cancel_by_prompt,
)
from src.integrations.figma.cleaned_figma_data import cleaned_file_json
from src.integrations.figma.fetch_figma_data import FigmaAPIError, fetch_figma_frames
from src.integrations.figma.figma_mtc_gen import get_page_flow
from src.integrations.figma.image_user_story import Generate_User_Story
from src.integrations.figma.page_flow import (
    delete_points_by_source_replace,
    flow_of_pages,
    update_source_by_mongo_id,
)
from src.integrations.jira.JiraCardPreprocessing import (
    JiraDocGenerator,
    jira_issues_fetch_utility,
)
from src.integrations.jira.prompts import jira_scenario_generation
from src.llm.client import LLMClient
from src.persistence.document_processor import DocumentProcessor
from src.persistence.embeddings import EMBEDDINGS, get_embeddings,qdrant_client,qdrantAsyncClient
from src.persistence.temporary_mtc import (
    build_temporary_mtc_payload,
    converting_values_to_list_of_string,
    count_tokens,
)
from src.schemas.test_case_schema import (
    FetchTicketsRequest,
    ProcessRequest,
    ClearAllRequest,
    CodeGenerationRequest,
    DataPreprocessRequest,
    DeleteChunksRequest,
    DeleteFigmaCollectionRequest,
    DeleteTestCaseByIdRequest,
    DownloadTestCasesRequest,
    FigmaPreprocessRequest,
    FigmaPromptRequest,
    FileUploadRequest,
    GeneratePromptRequest,
    ImagePreprocessingRequest,
    JiraPromptRequest,
    PreprocessRequest,
    RefactoringUserPromptRequest,
    TempFigmaPromptRequest,
    TempFileUploadRequest,
    TempImagePreprocessingRequest,
    TempJiraPromptRequest,
    TerminateMtcGenerationRequest,
    UpdateTestCaseRequest,
    build_license_id,
)
from src.services.apiKeyValidator import validateApiKey
from src.services.main_processor import init_collection, process_document_to_modules
from src.services.module_extractor import moduleOptimizer
from src.services.aiDataSrcService import (normalizeFilesName,validateFileExtension,
    updateMongodbStatus,getSummaryId,
    getCollectionName,S3FileFetcher,ApiFileFetcher)
from src.services.processFile import (
    processSingleFile,
)
from src.processing.document import get_document_extractor, preprocess_file, enrich_document_content  # noqa: F401
from src.processing.image import (
    is_blank_image_bytes, 
    validate_image_extension, 
    detect_irrelevant_images, 
    summarize_images
)
from src.services.main_processor import init_collection, process_document_to_modules
from src.utils.helper import (
    delete_chunks_files,
    fetch_service_provider_instance,
    resolve_service_provider,
)
from src.utils.s3_container import (
    fetch_file,
    fetch_image,
    fetch_pdf_attachment,
    fetch_video_attachment,
)
from src.utils.helper_function import (
    CheckingsummaryPrompt,
    User_prompt,
    convert_to_openai_multimodal,
    extract_audio_from_video,
    extract_original_name,
    frame_variance_stats,
    generate_user_content_image_name,
    image_to_base64,
    is_blank_image,
    transcribe_audio,
    videoSummary,
)

from src.integrations.video import ensure_collection,extract_frames,analyze_video_frames,VideoAPIError,LLMError,ResponseParsingError,extract_audio_from_video_large,transcribe_audio_large,store_video_per_flow,data_selector_chunk,e2e_system_user_prompt,e2e_llm_call,E2EFlowResponse,store_video_e2e,audio_video_relation,audio_related_checking,store_video_audio,TempVideoPromptRequest,video_e2e_retrieval_temp,mongodb_license_inti,update_video_mongodb_status,VideoUploadPreprocessPayload,Video_ID_Normalization,S3VideoFetcher,ApiVideoFetcher,build_video_s3_keys,delete_points_of_videos,DeleteVideoCollectionRequest,VideoPromptRequest,get_the_collection,get_status_video

load_dotenv()
logger = logging.getLogger(__name__)
