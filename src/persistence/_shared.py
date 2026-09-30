"""Shared imports for Prompt mixins. Keeps mixin files free of import duplication."""
import ast
import asyncio
import base64
import copy
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import boto3
import cv2
import hvac
import numpy as np
import pandas as pd
import requests
import tiktoken
from botocore.exceptions import ClientError
from bson import ObjectId
from dotenv import load_dotenv
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.vectorstores import Qdrant
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pymongo import ReturnDocument
from PyPDF2 import PdfReader
from qdrant_client import AsyncQdrantClient, QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, VectorParams
from requests.auth import HTTPBasicAuth
from toon import encode
from werkzeug.utils import secure_filename

from src.agents.operations import AgentOperation
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
from src.persistence.embeddings import (
    EMBEDDINGS,
    QDRANT_HOST,
    QDRANT_PORT,
    get_embeddings,
)
from src.persistence.qdrant_client_provider import (
    get_async_qdrant_client,
    get_sync_qdrant_client,
)
from src.persistence.temporary_mtc import converting_values_to_list_of_string
from src.schemas.test_case_schema import build_license_id
from src.services.apiKeyValidator import validateApiKey
from src.processing.document import enrich_document_content
from src.services.main_processor import init_collection, process_document_to_modules
from src.utils.helper import (
    delete_chunks_files,
    fetch_image,
    fetch_pdf_attachment,
    fetch_service_provider_instance,
    fetch_video_attachment,
    resolve_service_provider,
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

load_dotenv()
logger = logging.getLogger(__name__)

# python-docx Document (same name as langchain Document in the original file)
from docx import Document
from jira import JIRA
