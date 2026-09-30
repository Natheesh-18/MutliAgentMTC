"""Shared imports for AgentOperation mixins."""
import asyncio
import json
import logging
import os
import pathlib
import re
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from groq import Groq
from json_repair import repair_json
from langgraph.graph import END, StateGraph
from pydantic import AliasChoices, BaseModel, Field, ValidationError
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, VectorParams
from toon import encode

from src.agents.helpers import (
    get_manual_test_case,
    recover_completed_test_cases,
    token_usage,
    update_ai_service_instance_token_usage,
)
from src.agents.models import (
    CollectionNotFoundError,
    E2EImageResponse,
    FlowImageResponse,
    RAGQueryResponse,
    State,
    TestCaseCountResponse,
    TestCaseResponse,
    TestCaseType,
)
from src.agents.memory import AgentMemoryOperation
from src.agents.prompts import (
    FallBackScenarioSuggestion,
    FallBackScenarioSuggestionFigma,
    FigmaScenarioSuggestion,
    FileScenarioSuggestion,
    Generate_image_for_e2e,
    Generate_required_flow_img,
    GenericUserquery,
    ImageScenarioSuggestion,
    ScenarioSuggestion,
    Test_Count_Prompt,
    attachmentFollowUpPrompt,
    dataSelectorPrompt,
    followUpPrompt,
    genericFollowup,
    nonPreprocessedFileAndroidMtc,
    nonPreprocessedFileIosMtc,
    nonPreprocessedFileWebMobileMtc,
    nonPreprocessedFileWebMtc,
    promptReconstructor,
    GenericScenarioSuggestion,
    GenericFallBackScenarioSuggestion,
    Merge_EndToEnd_Audio_Prompt
)
from src.agents.summary import SummaryCreation
from src.core.exception import APIError, build_api_error
from src.core.generation_cancel import (
    GenerationCancelled,
    check_cancelled,
    is_cancelled,
    mark_cancelled_from_mongo,
    register_job,
    request_cancel,
    unregister_job,
)
from src.integrations.figma.figma_mtc_gen import (
    get_page_flow,
    retrive_chunk,
    retrive_e2e,
    retrive_e2e_image,
    retrive_flow,
)
from src.integrations.web_search import qdrant_is_sufficient, web_search_fallback_or_raise
from src.integrations.jira.prompts import jira_scenario_generation
from src.llm.client import LLMClient
from src.services.promptMapping import PromptRouter
from src.utils.create_dynamic_pydentic_model import create_dynamic_model
from src.utils.key_corrector import KeyCorrector
from src.persistence.post_response import process_llm_response, process_llm_results

from src.integrations.video.video_gen import video_flow_selector,video_data_selector,ModuleVideoRouterResponse,video_e2e_retrieval,video_flow_retrieval,video_audio_retrieval
from src.agents.prompts import Videoe2eScenarioSuggestion,VideoflowScenarioSuggestion,VideoallflowScenarioSuggestion,FallBackScenarioSuggestionVideo
load_dotenv()
logger = logging.getLogger(__name__)
