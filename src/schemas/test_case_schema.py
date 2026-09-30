from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Union
import os

def build_license_id(license_id: str) -> str:
    env = os.getenv("PROFILE")

    if env:
        return f"optimize_{env}_{license_id}"

    return f"optimize_{license_id}"

class GeneratePromptRequest(BaseModel):
    input: str
    user_id: str
    project_id: str
    session_id: Optional[str] = None
    prompt_id: Optional[str] = None
    license_id: str
    input_type: Optional[str] = None
    count: int = 1
    script_type: Optional[str] = None
    file_name: Optional[str] = None
    file_content: Optional[str] = None
    is_modified: Optional[bool] = None
    session_name: Optional[str] = None
    prompt_type: str = "Web"
    summary : Optional[str ] = None
    input_info : Optional[List[str]] = None
    branch_id: Optional[str] = None
    summary: Optional[str] = None
    bearer_token: Optional[str] = None
    is_automation_steps: bool = False


class TerminateMtcGenerationRequest(BaseModel):
    prompt_id: str
    license_id: str
    session_id: Optional[str] = None
    unique_id: Optional[str] = None

class JiraPromptRequest(BaseModel):
    input: Optional[str] = ""
    user_id: str
    jira_ids: Optional[list] = None
    jira_instance_id: Optional[str] = None
    project_id: str
    session_id: Optional[str] = None
    prompt_id: Optional[str] = None
    license_id: str
    input_type: Optional[str] = None
    count: int = 1
    script_type: Optional[str] = None
    file_name: Optional[str] = None
    file_content: Optional[str] = None
    is_modified: Optional[bool] = None
    session_name: Optional[str] = None
    prompt_type: str = "Web"
    summary: Optional[str] = None
    input_info: Optional[List[str]] = None
    branch_id: Optional[str] = None
    ref_id: Any

class TempJiraPromptRequest(BaseModel):
    input: Optional[str] = ""
    user_id: str
    jira_ids: Optional[list] = None
    jira_instance_id: Optional[str] = None
    project_id: str
    session_id: Optional[str] = None
    prompt_id: Optional[str] = None
    license_id: str
    input_type: Optional[str] = None
    count: int = 1
    script_type: Optional[str] = None
    file_name: Optional[str] = None
    file_content: Optional[str] = None
    is_modified: Optional[bool] = None
    session_name: Optional[str] = None
    prompt_type: str = "Web"
    summary: Optional[str] = None
    input_info: Optional[List[str]] = None
    branch_id: Optional[str] = None
    ref_id: Optional[Any] = None
    is_automation_steps: bool = False

class DataPreprocessRequest(BaseModel):
    license_id: Optional[str] = None
    file_name: List[str] = []
    file_id: List[str] = []
    storageType: Optional[List[str]] = None
    replace: bool = False  
    
class BaseRequest(BaseModel):
    license_id: str

class UpdateTestCaseRequest(BaseRequest):
    id: str = Field (alias="_id")
    update_data: Dict[str, Any]

class DeleteTestCaseByIdRequest(BaseRequest):
    test_case_id: List[str]
    prompt_id: str
    count: Optional[int] = None
    prompt_unique_id: Optional[str] = None
    
class ClearAllRequest(BaseRequest):
    session_id: str
  
    
class CodeGenerationRequest(BaseModel):
    manualSteps: List[Dict]
    language: Optional[str] = None
    framework: Optional[str] = None

class DownloadTestCasesRequest(BaseModel):
    response: List[Dict[str, Any]]

class DeleteChunksRequest(BaseModel):
    license_id: str
    project_id: str
    file_name: str

class RefactoringUserPromptRequest(BaseModel):
    license_id: str
    roll_back: Optional[bool] = False

class PreprocessRequest(BaseModel):
    license_id: str
    file_name: str | List[str]
    apiKey: str
    model: str
    serviceProvider: str
    storageType: Optional[str] = "s3"
    file_id: Optional[List[str]] = None

class FigmaPreprocessRequest(BaseModel):
    file_id: str
    figma_access_token: str
    pages_name: List[str] = []
    license_id: str
    project_id: str
    instance_name: str
    replace: bool
    mongo_id:str
    instance_name_change:bool

class DeleteFigmaCollectionRequest(BaseModel):
    license_id: str
    project_id: str
    instance_name: str

class ImagePreprocessingRequest(BaseModel):
    user_id: str
    branch_id: str
    project_id: str
    license_id: str
    bearer_token: Optional[str] = None
    input: Optional[str] = ""
    session_id: Optional[str] = None
    prompt_id: Optional[str] = None
    input_type: Optional[str] = None
    script_type: Optional[str] = None
    is_modified: Optional[bool] = None
    session_name: Optional[str] = None
    image_content: Optional[str] = None

    count: int = 1
    prompt_type: str = "Web"

    # Pass attachment IDs instead of uploaded files
    attachment_ids: Optional[Any] = []
    summary: Optional[str] = None
    ref_id : Any
   
class FileUploadRequest(BaseModel):
    user_id: str
    license_id: str
    project_id: str
    branch_id: str
    session_id: Optional[str] = None
    session_name: Optional[str] = None
    prompt_id: Optional[str] = None
    ref_id: Optional[Any] = None
    input_type: str = "file"
    input: Optional[str] = ""
    prompt_type: str = "Web"
    count: int = 1
    file_name: Optional[str] = None
    summary: Optional[str] = None
    script_type: Optional[str] = None
    is_modified: Optional[Union[bool, str]] = None
    attachment_ids: Optional[Any] = []


class FigmaPromptRequest(BaseModel):
    input: str
    user_id: str
    project_id: str
    session_id: Optional[str] = None
    prompt_id: Optional[str] = None
    license_id: str
    input_type: Optional[str] = "figma"
    count: int = 1
    script_type: Optional[str] = None
    bearer_token: Optional[str] = None
    is_modified: Optional[bool] = None
    session_name: Optional[str] = None
    prompt_type: str = "Web"
    instance_name: Optional[str] = None
    page_name:Optional[List[str]] = []
    summary : Optional[str] = None
    input_info : Optional[List[str]] = None
    branch_id: Optional[str] = None
    ref_id: Any

class TempImagePreprocessingRequest(BaseModel):
    user_id: str
    branch_id: str
    project_id: str
    license_id: str
    bearer_token: Optional[str] = None
    input: Optional[str] = ""
    session_id: Optional[str] = None
    prompt_id: Optional[str] = None
    input_type: Optional[str] = None
    script_type: Optional[str] = None
    is_modified: Optional[bool] = None
    session_name: Optional[str] = None
    image_content: Optional[str] = None
    count: int = 1
    prompt_type: str = "Web"
    # Pass attachment IDs instead of uploaded files
    attachment_ids: Optional[Any] = []
    summary: Optional[str] = None
    ref_id : Optional[Any] = None
    is_automation_steps: bool = False

class TempFileUploadRequest(BaseModel):
    user_id: str
    license_id: str
    project_id: str
    branch_id: str
    session_id: Optional[str] = None
    session_name: Optional[str] = None
    prompt_id: Optional[str] = None
    ref_id: Optional[Any] = None
    input_type: str = "file"
    input: Optional[str] = ""
    prompt_type: str = "Web"
    count: int = 1
    file_name: Optional[str] = None
    attachment_ids: Optional[Any] = []
    summary: Optional[str] = None
    is_automation_steps: bool = False
    script_type: Optional[str] = None
    is_modified: Optional[Union[bool, str]] = None


class TempFigmaPromptRequest(BaseModel):
    input: str
    user_id: str
    project_id: str
    session_id: Optional[str] = None
    prompt_id: Optional[str] = None
    license_id: str
    input_type: Optional[str] = "figma"
    count: int = 1
    script_type: Optional[str] = None
    bearer_token: Optional[str] = None
    is_modified: Optional[bool] = None
    session_name: Optional[str] = None
    prompt_type: str = "Web"
    instance_name: Optional[str] = None
    page_name:Optional[List[str]] = []
    summary : Optional[str] = None
    input_info : Optional[List[str]] = None
    branch_id: Optional[str] = None
    ref_id: Optional[Any] = None
    is_automation_steps: bool = False

class FetchTicketsRequest(BaseModel):
    project_name: str
    company_domain: str
    jira_mail_id: str
    jira_api_token: str
    next_page_token: Optional[str] = None


class ProcessRequest(BaseModel):
    license_id: str
    instance_name: str
    project_name: str
    company_domain: str
    jira_mail_id: str
    jira_api_token: str
