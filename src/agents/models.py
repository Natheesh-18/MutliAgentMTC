"""Pydantic models and errors used by agent generation."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TestCaseResponse(BaseModel):
    filesName: Optional[List[str]] = None
    testCaseType: List[str]
    count: int = 0



class TestCaseType(BaseModel):
    type: str
    count: int


class TestCaseCountResponse(BaseModel):
    count: int = 0
    testCaseTypes: List[TestCaseType] = Field(default_factory=list)


class CollectionNotFoundError(Exception):
    pass


class RAGQueryResponse(BaseModel):
    rag_queries: Dict[str, List[str]]


class FlowImageResponse(BaseModel):
    FlowName: List[str] = []
    Images: List[str] = []
    end_to_end: List[str] = []


class E2EImageResponse(BaseModel):
    Images: List[str] = []


class State(BaseModel):
    messages: List[Dict] = []
    raw_testcases: Optional[Dict] = None
    corrected_testcases: Optional[Dict] = None
    validated_testcases: Optional[Any] = None
    correction_log: List[Dict] = []
    summary: Optional[str] = None
    error: Optional[Any] = None
    llm_warning: dict | None = None
    context_summary: Optional[str] = None
