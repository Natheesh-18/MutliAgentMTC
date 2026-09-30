"""Prompt facade.

The original 3,500-line class is split into mixins under persistence/mixins/.
Call sites keep using Prompt / manualTestCase with the same method names.
"""
import os

from langchain_groq import ChatGroq

from src.persistence.embeddings import (
    EMBEDDINGS,
    QDRANT_HOST,
    QDRANT_PORT,
    get_embeddings,
)
from src.persistence.qdrant_client_provider import get_sync_qdrant_client
from src.persistence.mixins.codegen import CodeGenerationMixin
from src.persistence.mixins.crud import PromptCrudMixin
from src.persistence.mixins.generation_status import GenerationStatusMixin
from src.persistence.mixins.handlers import GenerationHandlersMixin
from src.persistence.mixins.media import MediaAnalysisMixin
from src.persistence.mixins.mongo import MongoCollectionsMixin
from src.persistence.mixins.qdrant_docs import QdrantDocumentsMixin
from src.persistence.mixins.writes import PromptWritesMixin
from src.persistence.temporary_mtc import (
    build_temporary_mtc_payload,
    converting_values_to_list_of_string,
    count_tokens,
    is_temporary_verification_step,
    remove_temporary_verification_steps,
    sanitize_temporary_mtc_step_inputs,
    should_keep_step_input,
    summary_has_input_fields,
)
from src.schemas.test_case_schema import FetchTicketsRequest, ProcessRequest

__all__ = [
    "Prompt",
    "EMBEDDINGS",
    "FetchTicketsRequest",
    "ProcessRequest",
    "build_temporary_mtc_payload",
    "converting_values_to_list_of_string",
    "count_tokens",
    "get_embeddings",
    "is_temporary_verification_step",
    "get_sync_qdrant_client",
    "remove_temporary_verification_steps",
    "sanitize_temporary_mtc_step_inputs",
    "should_keep_step_input",
    "summary_has_input_fields",
]


class Prompt(
    MongoCollectionsMixin,
    QdrantDocumentsMixin,
    GenerationStatusMixin,
    PromptWritesMixin,
    GenerationHandlersMixin,
    PromptCrudMixin,
    CodeGenerationMixin,
    MediaAnalysisMixin,
):
    def __init__(self, model_name: str):
        self._embeddings = None
        self.llm = ChatGroq(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name=model_name,
        )
        self.mtc_collection = os.getenv("mtc_collection_name")
        self.mtc_user_data_db_name = os.getenv("mtc_dataBase")
        self.user_prompt_details_collection = os.getenv(
            "user_prompt_details_collection"
        )
        self.user_prompt_collection = os.getenv("user_prompt_collection")
        self.base_url = os.getenv("base_url")
        self.file_path = os.getenv("file_path")
        self.auth_mtc_collection = os.getenv("mtc_auth_collection_name")
        self.qdrant_collection = self.load_collection_qdrant()
        self.session_info = {}
        self.jira_collection_db = os.getenv("jira_collection")
        self.qdrant_client = get_sync_qdrant_client()
        self.code_generation_payload = os.getenv("code_generation_payload")
        self.license_auth_collection = os.getenv("license_auth_collection")
        self.auth_license_collection = self.load_auth_collection()
        self.valid_input = None

    @property
    def embeddings(self):
        return EMBEDDINGS
