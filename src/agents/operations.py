"""AgentOperation facade.

Generation logic lives in agents/mixins/. Call sites keep using AgentOperation
and recover_completed_test_cases from this module.
"""
import asyncio
from typing import Any, Optional

from groq import Groq

from src.agents.helpers import (
    extract_summary,
    get_manual_test_case,
    recover_completed_test_cases,
    token_usage,
    update_ai_service_instance_token_usage,
)
from src.agents.mixins.generate import GenerateMixin
from src.agents.mixins.graph import GraphMixin
from src.agents.mixins.payload import PayloadMixin
from src.agents.mixins.session import SessionMixin
from src.agents.mixins.support import SupportMixin
from src.agents.mixins.type_pipeline import TypePipelineMixin
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
from src.utils.create_dynamic_pydentic_model import create_dynamic_model
from src.utils.key_corrector import KeyCorrector

__all__ = [
    "AgentOperation",
    "CollectionNotFoundError",
    "E2EImageResponse",
    "FlowImageResponse",
    "RAGQueryResponse",
    "State",
    "TestCaseCountResponse",
    "TestCaseResponse",
    "TestCaseType",
    "extract_summary",
    "get_manual_test_case",
    "recover_completed_test_cases",
    "token_usage",
    "update_ai_service_instance_token_usage",
]


class AgentOperation(
    PayloadMixin,
    SessionMixin,
    SupportMixin,
    TypePipelineMixin,
    GenerateMixin,
    GraphMixin,
):
    def __init__(
        self,
        # 1. Tenant & Context
        user_id,
        license_id,
        project_id,
        branch_id,
        env,
        # 2. Session & Prompt IDs
        session_id,
        session_name,
        prompt_id,
        unique_id,
        dateTime,
        # 3. Template
        json_template,
        original_template,
        template_id,
        # 4. Input & Generation Controls
        input_type: str,
        user_input: str,
        user_input_tokens,
        prompt_type: str,
        script_type,
        count,
        is_modified,
        # 5. Modality Flags & Execution
        memory: bool,
        is_file: bool,
        is_jira: bool,
        is_image: bool,
        is_video: bool,
        is_figma: bool,
        # 6. AI Model / Provider
        apiKey: str,
        serviceProvider: str,
        model: str,
        sa_info,
        resourceId: str,
        resource: str,
        # 7. Qdrant & Vector Setup (Optional / Modality-specific)
        collection_name: Optional[str] = None,
        embeddings: Optional[Any] = None,
        qdrant_client: Optional[Any] = None,
        bearer_token: Optional[str] = None,
        # 8. Modality-Specific Content & Token Data (Optional)
        file_name: Optional[str] = None,
        file_content: Optional[Any] = None,
        context_summary: Optional[str] = None,
        chatContext: Optional[str] = None,
        images_path: Optional[Any] = None,
        image_content: Optional[str] = None,
        Image_Input_token: Optional[int] = None,
        Image_Output_token: Optional[int] = None,
        video_name: Optional[str] = None,
        video_content: Optional[Any] = None,
        Input_Token_Video: Optional[int] = None,
        Output_Token_Video: Optional[int] = None,
        page_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        Jira_Input_token: Optional[int] = None,
        Jira_Output_token: Optional[int] = None,
        return_generated_payload: bool = False,
    ):
        # 1. Tenant & Context
        self.user_id = user_id
        self.license_id = license_id
        self.project_id = project_id
        self.branch_id = branch_id
        self.env = env

        # 2. Session & Prompt IDs
        self.session_id = session_id
        self.session_name = session_name
        self.prompt_id = prompt_id
        self.unique_id = unique_id
        self.dateTime = dateTime

        # 3. Template & Models
        self.json_template = json_template
        self.original_template = original_template
        self.template_id = template_id
        self.key_corrector = KeyCorrector(json_template)
        self.TopLevelModel = create_dynamic_model("TestCases", json_template)

        # 4. Input & Generation Controls
        self.input_type = input_type
        self.user_input = user_input
        self.user_input_tokens = user_input_tokens
        self.prompt_type = prompt_type
        self.script_type = script_type
        self.count = count
        self.is_modified = is_modified
        self.input = input if input is not None else []

        # 5. Modality Flags & Execution
        self.memory = memory
        self.is_file = is_file
        self.is_jira = is_jira
        self.is_image = is_image
        self.is_video = is_video
        self.is_figma = is_figma

        # 6. AI Model / Provider
        self.apikey = apiKey
        self.serviceProvider = serviceProvider
        self.model = model
        self.sa_info = sa_info
        self.resourceId = resourceId
        self.resource = resource
        self.clientgroq = Groq(api_key=apiKey) if apiKey else None

        # 7. Qdrant & Vector Setup
        self.collection_name = collection_name
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client

        # 8. Modality-Specific Content & Token Data
        self.file_name = file_name
        self.file_content = file_content
        self.context_summary = context_summary
        self.chatContext = chatContext
        self.images_path = images_path
        self.image_content = image_content
        self.Image_Input_token = Image_Input_token
        self.Image_Output_token = Image_Output_token
        self.video_name = video_name
        self.Input_Token_Video = Input_Token_Video
        self.Output_Token_Video = Output_Token_Video
        self.page_name = page_name
        self.instance_name = instance_name
        self.Jira_Input_token = Jira_Input_token
        self.Jira_Output_token = Jira_Output_token
        self.return_generated_payload = return_generated_payload

        # 9. Internal State & Counters
        self.counter_ref = [1]
        self.counter_lock = asyncio.Lock()
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_testcase_count = 0
        self._cancel_finalized = False
        self._follow_up = None
