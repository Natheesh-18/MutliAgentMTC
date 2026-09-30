from typing import Any, Dict, List, Optional
# from src.api.runtime import *  # noqa: F401,F403
import os , uuid , logging
from docling.datamodel.document import PictureItem, TableItem
from src.persistence.document_processor import DocumentProcessor
from src.persistence.embeddings import EMBEDDINGS, qdrant_client
# from src.api.deps import manualTestCase
from src.core.exception import build_api_error
from io import BytesIO
import base64
from dotenv import load_dotenv
load_dotenv()
from groq import Groq
from openai import OpenAI
api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=api_key)

manualTestCaseDoc = DocumentProcessor(
    embeddings=EMBEDDINGS,
    qdrant_host=os.getenv("QDRANT_HOST"),
    qdrant_port=os.getenv("QDRANT_PORT"),
)

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
SUMMARY_NAMESPACE_NAME = "GLOBAL_SUMMARY"
_openai_client = None

def getOpenaiClient():
    global _openai_client

    if _openai_client is None:
        _openai_client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
    return _openai_client

def getLicenseIdMod(env: Optional[str], license_id: str) -> str:
    """Build the modified license_id used for MongoDB updates."""
    return f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"

def getCollectionName(env: Optional[str], license_id: str, project_id: str) -> str:
    """Build the Qdrant collection name."""
    return f"ff_cloud_{env}_{license_id}_{project_id}" if env else f"ff_cloud_{license_id}_{project_id}"

def getSummaryId(collection_name: str) -> str:
    """
    Generate a deterministic UUID for the global summary point.
    Includes collection_name to avoid collisions across collections.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{SUMMARY_NAMESPACE_NAME}:{collection_name}"))

def updateMongodbStatus(
    env: Optional[str],
    license_id: str,
    project_id: str,
    file_name: str,
    status: str
) -> None:
    """
    Update MongoDB processing status for a file.
    Swallows exceptions to avoid breaking the main flow on DB errors.
    """
    try:
        _lid = getLicenseIdMod(env, license_id)
        processor = DocumentProcessor(
            embeddings=manualTestCaseDoc.embeddings,
            qdrant_host=os.getenv("QDRANT_HOST"),
            qdrant_port=os.getenv("QDRANT_PORT")
        )
        processor.update_mongodb_status(
            license_id=_lid,
            project_id=project_id,
            file_name=file_name,
            status=status
        )
        logger.info(f"MongoDB status set to '{status}' for: {file_name}")
    except Exception as e:
        logger.error(f"MongoDB status update error for {file_name}: {e}", exc_info=True)

class FileFetcher:
    """Abstract base for fetching file bytes."""
    async def fetch(self, file_name: str, **kwargs) -> bytes:
        raise NotImplementedError

class S3FileFetcher(FileFetcher):
    """Fetch files from AWS S3."""
    def __init__(self, s3_client, bucket_name: str, license_id: str, project_id: str):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.license_id = license_id
        self.project_id = project_id

    async def fetch(self, file_name: str, **kwargs) -> bytes:
        s3_key = f"License/{self.license_id}/Project/{self.project_id}/aiMl/Root/DEFAULT_AIML_FLD/{file_name}"
        logger.info(f"Fetching from S3: s3://{self.bucket_name}/{s3_key}")
        file_obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
        return file_obj["Body"].read()

class ApiFileFetcher(FileFetcher):
    """Fetch files via manualTestCase API."""
    def __init__(self, bearer_token: str, license_type: str, project_id: str, project_name: str, project_type: str):
        self.bearer_token = bearer_token
        self.license_type = license_type
        self.project_id = project_id
        self.project_name = project_name
        self.project_type = project_type

    async def fetch(self, file_name: str, file_id: str, **kwargs) -> bytes:
        logger.info(f"Fetching file via API: {file_name} (id={file_id})")
        file_bytes = manualTestCase.fetch_file(
            file_id=file_id,
            bearer_token=self.bearer_token,
            license_type=self.license_type,
            project_id=self.project_id,
            project_name=self.project_name,
            project_type=self.project_type
        )
        if not file_bytes:
            raise Exception("Unable to process the uploaded file. Please upload a valid file")
        return file_bytes

def validateFileExtension(file_name: str) -> Optional[str]:
    """Returns error message if extension is invalid, else None."""
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"Unsupported file type: {ext}"
    return None

def normalizeFilesName(file_names) -> tuple:
    """
    Normalize file_names to a list.
    Returns (list_of_names, error_response_dict_or_None)
    """
    if isinstance(file_names, str):
        return [file_names], None
    elif isinstance(file_names, list):
        return file_names, None
    else:
        return None, {
            "status": "failure",
            "responseCode": 400,
            "message": "file_name must be a string or list"
        }

def encodeImageAsBase64(image) -> str:
    """Convert a PIL Image object to a Base64 encoded string."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def summarizeImage(image, apiKey, model, serviceProvider, maxReTries):
    systemPrompt="""You are an expert QA UI and workflow analyst.

You will be provided with a screenshot of ONE of the following:
- A web/mobile application UI screen, OR
- A flowchart / workflow / process / sequence diagram.

## Step 1 — Classify the Image
First, silently determine the image type:
- TYPE_UI → Predominantly interactive UI elements (buttons, inputs, forms, tables, menus, dialogs)
- TYPE_FLOW → Predominantly nodes, connectors, arrows, decision diamonds, swim lanes, or process boxes
- TYPE_LOGO → Only branding, decorative, or cosmetic content with NO interactive/functional elements

---

## If TYPE_LOGO → Return exactly an empty string: ""
Do NOT generate any output. No explanation, no observations, nothing.

---

## If TYPE_UI → Output the following (max 180 words total):

1. **Screen Purpose** — Only if clearly inferable from visible headings or labels.

2. **Visible UI Elements:**
   - Label/Name | Element Type (button, input, dropdown, table, icon, link, toggle, checkbox, radio, tab, modal/popup, dialog, tooltip, toast/snackbar, overlay, accordion, carousel, badge, chip, progress bar, etc.) | Position | Visible State (enabled, disabled, selected, empty, filled, error, loading, hidden/collapsed, etc.)

   **Position format:**
   - Default: coarse zone (top/bottom/left/right/center, or combinations like top-right, bottom-left).
   - **If duplicate/ambiguous elements exist on the same screen** (e.g., two "Login" buttons, two "Submit" icons), disambiguate using a **relative anchor** to a nearby, uniquely-identifiable element:
     - Format: `[zone] — [relative position] [reference element]`
     - Examples:
       - "Login button — below 'Email' input field"
       - "Login button — top-right, beside 'Sign Up' link"
       - "Close icon — top-right corner of modal, above 'Cancel' button"
       - "Submit button — under 'Terms & Conditions' checkbox"
   - Only use a reference element if it is itself unambiguous (unique label/type on screen). Do not chain multiple relative references.

3. **Visible User Inputs Extraction:**
   - For each input field, extract any visible placeholder text, default values, or pre-filled content that could be relevant for testing.
   - Field name - Visible placeholder/default/pre-filled value (if any) - Visible validation rules or hints (e.g., "Must be 8 characters", "Enter a valid email", etc.)

4. **Possible User Actions** — Strictly based on visible interactive elements only.

5. **Test-Relevant Observations** — Visible validations, placeholders, default values, error messages, state indicators, and any **overlays/popups/modals/toasts** present at time of capture (include their trigger state if visible, e.g., "error toast visible after failed submit").

6. **Missing or Unclear Information** — Cropped, blurred, ambiguous, or partially hidden UI areas (including elements partially covered by an open modal/dropdown/keyboard).

**Rules:**
- Do NOT include standalone logos, brand marks, or decorative icons unless inside a clickable control.
- Do NOT assume business logic, backend behavior, or hidden workflows.
- Do NOT hallucinate labels, states, or actions.
- Do NOT invent a reference element that isn't visibly present — if no unique anchor exists, fall back to the coarse zone only.
- Strictly stay within 180 words.

---

## If TYPE_FLOW → Output the following (no word limit — depth and accuracy are priority):

1. **Diagram Purpose** — Inferred strictly from visible titles, headings, or node labels.

2. **Visible Nodes/Elements:**
   - Label (exact visible text)|Type (process, decision, start, end, swimlane, connector, annotation, etc.) | Position | State/Style (e.g., filled, bordered, directional)
3. **Visible Connections:**
   - From → To | Arrow direction | Connector label (if any)

4. **Flow Paths — All Distinct Paths Traced:**
   - Trace every visible path from start to end, including branches at decision nodes.
   - Label each path clearly (e.g., Path A: Happy path, Path B: Error/alternate path).

5. **Decision Points:**
   - List each decision node, its visible condition labels (Yes/No, True/False, custom labels), and the resulting branches.

6. **Test-Relevant Observations:**
   - Loop-backs, parallel flows, merge points, visible counters/percentages/statuses, annotated conditions.

7. **Missing or Unclear Information:**
   - Cropped nodes, illegible text, ambiguous arrow directions, disconnected elements.

**Rules:**
- Do NOT assume steps not shown by visible arrows or connectors.
- Do NOT infer business logic beyond what the diagram explicitly shows.
- If text in a node is partially visible, state it as "[partially visible: ...]".
- Prioritize completeness and traceability over brevity for flow diagrams.
"""

    try:
        base64_image = encodeImageAsBase64(image)
        data_url = f"data:image/png;base64,{base64_image}"
        messages = [
            {
                "role": "system",
                "content": systemPrompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe the meaningful content of this image in a concise and factual manner. Include important text, UI elements, diagrams, tables, or other information that may be relevant to understanding the document."
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        }
                    }
                ]
            }
        ]

        for attempts in range(maxReTries):
            try:
                openaiClient = getOpenaiClient()
                resp = openaiClient.chat.completions.create(
                    model="gpt-4.1-mini-2025-04-14",
                    messages=messages
                )

                content = (
                    resp.choices[0].message.content.strip()
                    if resp.choices[0].message.content
                    else ""
                )

                input_tokens = (
                    resp.usage.prompt_tokens
                    if resp.usage
                    else 0
                )

                output_tokens = (
                    resp.usage.completion_tokens
                    if resp.usage
                    else 0
                )

                return content, input_tokens, output_tokens

            except Exception as e:
                logging.error(f"Error in image LLM call: {e}")
                if attempts == maxReTries - 1:
                    raise build_api_error(e, serviceProvider)

    except Exception as e:
        logging.error(f"Error summarizing image: {e}")
        raise

def preprocessDocumentWithImagesTables(docling_document, apiKey, model, serviceProvider):
    """
    Processes only images and tables while preserving all other
    Docling-generated Markdown exactly as it is.
    """
    try:
        image_placeholder = "DOCLINGIMAGEPLACEHOLDER"
        processed_text = docling_document.export_to_markdown(image_placeholder=image_placeholder)

        images = []
        tables = []

        for item, _level in docling_document.iterate_items():
            if isinstance(item, PictureItem):
                image = item.get_image(docling_document)
                if image:
                    images.append(image)
                else:
                    logging.warning("Unable to extract image from Docling document")

            elif isinstance(item, TableItem):
                table_markdown = item.export_to_markdown(doc=docling_document)
                if table_markdown and table_markdown.strip():
                    tables.append(table_markdown.strip())

        # Replace image placeholders
        for image in images:
            image_summary, _, _ = summarizeImage(
                image, apiKey, model, serviceProvider="DefaultFireFlink", maxReTries=2
            )
            if image_summary and image_summary.strip():
                replacement = f"<ImageSummary>\n{image_summary.strip()}\n</ImageSummary>"
            else:
                replacement = ""
            processed_text = processed_text.replace(image_placeholder, replacement, 1)

        # Wrap tables
        for table_markdown in tables:
            replacement = f"<TabularColumn>\n{table_markdown}\n</TabularColumn>"
            processed_text = processed_text.replace(table_markdown, replacement, 1)

        return processed_text

    except Exception as e:
        logging.error(f"Error preprocessing document with images/tables: {e}")
        raise
