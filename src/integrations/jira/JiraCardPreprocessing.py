import os, json
import requests
from requests.auth import HTTPBasicAuth
from io import BytesIO
from docx import Document as WordDocument
from langchain.schema.document import Document
from dotenv import load_dotenv
from typing import Dict, List, Optional
from docx.enum.text import WD_BREAK
import logging
from dotenv import load_dotenv
import uuid
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.storage import LocalFileStore
import asyncio
import httpx
from openai import AsyncOpenAI
from json_repair import repair_json
import base64
from src.processing.document import preprocess_file, enrich_document_content


load_dotenv()
os.environ["QDRANT_TELEMETRY_DISABLED"] = "1"
os.environ["LANGCHAIN_TELEMETRY_ENABLED"] = "false"

# Basic configuration (logs to console)
logging.basicConfig(
    level=logging.INFO,  # Minimum level to log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

doc__store = LocalFileStore("./docstore") 
class JiraDocGenerator:
    def __init__(self, email=None, api_token=None, domain=None):
        # Initialize with environment variables or passed parameters
        self.email = email 
        self.api_token = api_token 
        self.domain = domain
        self.auth = HTTPBasicAuth(self.email, self.api_token)
        self.headers = {"Accept": "application/json"}
        self.doc__store = doc__store

    async def authenticate(self) -> bool:
        """
        Verify the Jira API credentials by making a request to the 'myself' endpoint.
        """
        url = f"https://{self.domain}.atlassian.net/rest/api/3/myself"
        try:
            response = await asyncio.to_thread(
                requests.get, url, headers=self.headers, auth=self.auth, timeout=15.0
            )
            
            status_code = response.status_code
            if status_code == 200:
                return True
                
            try:
                error_json = response.json()
                error_msg = error_json.get("errorMessages", error_json.get("message", response.text))
                if isinstance(error_msg, list):
                    error_msg = ", ".join(error_msg)
            except Exception:
                error_msg = response.text

            if status_code == 401:
                raise PermissionError(f"Unauthorized: Invalid Jira API token or email. Error: {error_msg}")
            else:
                raise Exception(f"Jira authentication failed. Status Code: {status_code}. Error: {error_msg}")
        except requests.exceptions.RequestException as err:
            raise Exception(f"Failed to connect to Jira at {url}: {err}")

    async def _make_jira_request(self, url: str, params: dict = None, method: str = "GET", json_data: dict = None) -> dict:
        import time
        max_retries = 5
        base_delay = 2
        
        for attempt in range(max_retries):
            try:
                if method.upper() == "POST":
                    response = await asyncio.to_thread(
                        requests.post, url, headers=self.headers, auth=self.auth, json=json_data, params=params, timeout=30.0
                    )
                else:
                    response = await asyncio.to_thread(
                        requests.get, url, headers=self.headers, auth=self.auth, params=params, timeout=30.0
                    )
                
                # Handle Rate Limiting (429)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        wait_time = int(retry_after) + 1
                    else:
                        wait_time = base_delay * (2 ** attempt) # Exponential backoff
                    
                    logging.warning(f"Rate limit hit (429). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as err:
                status_code = err.response.status_code if err.response is not None else "Unknown"
                try:
                    error_json = err.response.json()
                    error_msg = error_json.get("errorMessages", error_json.get("message", err.response.text))
                    if isinstance(error_msg, list):
                        error_msg = ", ".join(error_msg)
                except Exception:
                    error_msg = err.response.text if err.response is not None else str(err)

                if status_code == 401:
                    logging.error(f"HTTP error occurred requesting {url} - Status Code: {status_code} - Error Message: {error_msg}")
                    raise PermissionError(f"Unauthorized: Invalid Jira API token or email. Error: {error_msg}")
                if status_code == 429:
                    retry_after = err.response.headers.get("Retry-After") if err.response is not None else None
                    wait_time = int(retry_after) + 1 if retry_after else base_delay * (2 ** attempt)
                    logging.warning(f"Rate limit hit (429) caught in exception. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                logging.error(f"HTTP error occurred requesting {url} - Status Code: {status_code} - Error Message: {error_msg}")
                return {}
            
            except Exception as err:
                logging.error(f"Error occurred requesting {url}: {err}")
                if attempt == max_retries - 1:
                    return {}
                await asyncio.sleep(1) # Small wait for other errors
        
        logging.error(f"Max retries exceeded for {url}")
        return {}

    async def _download_attachment(self, url: str) -> bytes:
        import time
        max_retries = 5
        base_delay = 2
        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    requests.get, url, auth=self.auth, timeout=30.0
                )
                
                # Handle Rate Limiting (429)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = int(retry_after) + 1 if retry_after else base_delay * (2 ** attempt)
                    print(f"[JIRA Download] Rate limit hit (429). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    logging.warning(f"Rate limit hit (429) when downloading attachment. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                    
                response.raise_for_status()
                return response.content
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"[JIRA Download] Failed to download {url} after {max_retries} attempts: {e}")
                    raise e
                wait_time = base_delay * (2 ** attempt)
                print(f"[JIRA Download] Error downloading, retrying in {wait_time}s... Error: {e}")
                logging.warning(f"Error downloading attachment, retrying in {wait_time}s... Error: {e}")
                await asyncio.sleep(wait_time)

    def _parse_adf_description(self, adf: dict) -> str:
        def extract_text(node):
            result = ""
            if isinstance(node, dict):
                node_type = node.get("type")
                content = node.get("content", [])
                if node_type == "text":
                    return node.get("text", "")
                elif node_type in ["paragraph", "heading"]:
                    line = "".join([extract_text(child) for child in content])
                    return line.strip() + "\n\n"
                elif node_type in ["bulletList", "orderedList"]:
                    return "".join([extract_text(child) for child in content])
                elif node_type == "listItem":
                    # Bullet or numbered list item
                    inner = "".join([extract_text(child) for child in content])
                    return f"- {inner.strip()}\n"
                elif node_type == "mediaSingle":
                    return ""  # skip images
                elif node_type == "inlineCard":
                    return node.get("attrs", {}).get("url", "") + "\n"
            elif isinstance(node, list):
                for child in node:
                    result += extract_text(child)
            return result

        return extract_text(adf).strip()


    async def fetch_issue_clean(self, issue_id: str) -> dict:
        issue_url = f"https://{self.domain}.atlassian.net/rest/api/3/issue/{issue_id}"
        data = await self._make_jira_request(issue_url, params=None)
        fields = data.get("fields", {})

        if fields == None:
            fields = {}

        if fields.get("description", {}) == None:
            fields["description"] = {}

        if fields.get("status", {}) == None:
            fields["status"] = {}

        if fields.get("project", {}) == None:
            fields["project"] = {}

        if fields.get("issuetype", {}) == None:
            fields["issuetype"] = {}

        if fields.get("reporter", {}) == None:
            fields["reporter"] = {}

        if fields.get("description", {}) == None:
            fields["description"] = {}

        # Fetch child issues using the recommended POST search endpoint
        child_issues = []
        try:
            # 1. Simplified JQL (Jira Cloud uses 'parent' for both Epics and Subtasks)
            jql = f'parent = "{issue_id}"'
            
            # 2. Use the standard search endpoint
            search_url = f"https://{self.domain}.atlassian.net/rest/api/3/search/jql"
            
            # 3. Pass JQL inside the JSON payload body instead of URL parameters
            payload = {
                "jql": jql,
                "maxResults": 50,  # Good practice to define pagination limits
                "fields": ["summary", "key"] # Only fetch what you actually need
            }
            
            search_data = await self._make_jira_request(search_url, method="POST", json_data=payload)
            
            if search_data and "issues" in search_data:
                child_issues = [{
                    "key": child.get("key"),
                    "summary": child.get("fields", {}).get("summary")
                } for child in search_data["issues"]]

        except Exception as e:
            print(f"Failed to fetch child issues: {e}")

        # Parse linked issues
        linked_issues = []
        for link in fields.get("issuelinks", []):
            direction = "outward" if "outwardIssue" in link else "inward"
            issue_obj = link.get(f"{direction}Issue", {})
            linked_issues.append({
                "type": link.get("type", {}).get("name"),
                "direction": direction,
                "key": issue_obj.get("key"),
                "summary": issue_obj.get("fields", {}).get("summary")
            })

        return {
            "Issue Key": data.get("key", ""),
            "Summary": fields.get("summary", ""),
            "Parent": None,  # 'parent' is not present in this issue
            "Status": fields.get("status", {}).get("name"),
            "Project": fields.get("project", {}).get("name"),
            "Type": fields.get("issuetype", {}).get("name"),
            "Priority": fields.get("priority", {}).get("name"),
            "Reporter": fields.get("reporter", {}).get("displayName"),
            "Resolution": (fields.get("resolution") or {}).get("name"),
            "Labels": fields.get("labels", []),
            "Remaining Estimate": fields.get("timeestimate"),
            "Time Spent": fields.get("timespent"),
            "Original Estimate": fields.get("timeoriginalestimate"),
            "Attachments": fields.get("attachment", []),
            "Epic Link": None,  # customfield_10101 not found
            "Fix Versions": [v["name"] for v in fields.get("fixVersions", [])],
            "Affects Versions": [v["name"] for v in fields.get("versions", [])],
            "Components": [c["name"] for c in fields.get("components", [])],
            "Votes": fields.get("votes", {}).get("votes"),
            "Description": self._parse_adf_description(fields.get("description", {}).get("content", [])),
            "Subtasks": [{
                            "key": s.get("key"),
                            "summary": s.get("fields", {}).get("summary")
                         } 
                         for s in fields.get("subtasks", [])
                         if s.get("fields") != None],
            "Linked Issues": linked_issues,
            "Child Issues": child_issues
        }

    def _process_attachment(
        self, attachment: Dict, issue_id: str, doc: Document
    ) -> None:
        """Saves the attachment in its original format to the issue folder."""
        file_url = attachment["content"]
        file_name = attachment["filename"]

        logging.info(f"\n📎 Saving attachment (as-is): {file_name}")

        try:
            # Define the issue-specific folder path
            output_dir = os.getenv("JIRA_STORAGE")
            issue_folder = os.path.join(output_dir, issue_id)
            os.makedirs(issue_folder, exist_ok=True)

            # Download the attachment
            print(f"[JIRA Download] Saving attachment '{file_name}' to issue folder...")
            content = self._download_attachment(file_url)

            # Save the file with original name/extension
            attachment_path = os.path.join(issue_folder, file_name)
            with open(attachment_path, "wb") as f:
                f.write(content)

            # Add a reference in the document
            doc.add_paragraph(f"Attachment saved: {file_name}")
            print(f"[JIRA Download] Successfully saved attachment: {file_name}")

        except Exception as e:
            print(f"[JIRA Download] Failed to save attachment {file_name}: {e}")
            logging.error(f"❌ Failed to download/save attachment: {str(e)}")
            doc.add_paragraph(f"Failed to save attachment: {file_name}")

    def _read_docx_from_bytes(self, bytes_data: bytes) -> str:
        """Extract text from DOCX file bytes."""
        doc = WordDocument(BytesIO(bytes_data))
        return "\n".join(para.text for para in doc.paragraphs)

    async def _process_attachments_hierarchical(
        self,
        issue_id: str,
        attachments: list,
        apiKey: str = None,
        serviceProvider: str = None,
        model: str = None,
        sa_info: dict = None,
        temp_dir: str = None,
        ticket_summary: str = "",
        resource: str = None,
        resourceId: str = None
    ) -> tuple[dict, int, int]:
        result = {
            "Documents": [],
            "Images": [],
            "Other Supported Files": []
        }
        total_ip_token = 0
        total_op_token = 0
        
        images_base64 = {}
        
        # Download all attachments in parallel
        async def download_one(att):
            f_url = att.get("content")
            f_name = att.get("filename")
            if not f_url or not f_name:
                return None
            try:
                print(f"[JIRA Processing] Downloading attachment '{f_name}' for ticket {issue_id}...")
                content = await self._download_attachment(f_url)
                return f_name, content
            except Exception as ex:
                print(f"[JIRA Processing] Error downloading '{f_name}' for ticket {issue_id}: {ex}")
                return None

        if attachments:
            image_exts = ['png', 'jpg', 'jpeg']
            filtered_attachments = []
            image_count = 0
            
            for att in attachments:
                f_name = att.get("filename", "")
                ext = f_name.split('.')[-1].lower() if '.' in f_name else ''
                
                if ext in image_exts:
                    if image_count < 10:
                        image_count += 1
                        filtered_attachments.append(att)
                    else:
                        print(f"[JIRA Processing] Skipped downloading image (limit reached): {f_name}")
                else:
                    # Always download non-image files
                    filtered_attachments.append(att)

            print(f"[JIRA Processing] Starting parallel downloads of {len(filtered_attachments)} attachments for ticket {issue_id}...")
            download_tasks = [download_one(att) for att in filtered_attachments]
            download_results = await asyncio.gather(*download_tasks)
        else:
            download_results = []
        
        # Process the downloaded contents sequentially (file operations, chunking, single-document summarization)
        for d_res in download_results:
            if not d_res:
                continue
            file_name, content = d_res
            ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
            
            try:
                if ext in ['docx', 'pdf', 'txt']:
                    extracted_text = ""
                    doc_summary = ""
                    
                    if apiKey and serviceProvider and model:
                        print(f"[JIRA Processing] Preprocessing document '{file_name}'...")
                        try:
                            extracted_text, imgs_ip_tokens, imgs_op_tokens = await preprocess_file(
                                file_data=content,
                                file_extension=ext,
                                serviceProvider=serviceProvider,
                                apiKey=apiKey,
                                model=model,
                                sa_info=sa_info,
                                resourceId=resourceId,
                                resource=resource,
                            )
                            total_ip_token += (imgs_ip_tokens or 0)
                            total_op_token += (imgs_op_tokens or 0)
                        except Exception as e:
                            print(f"[JIRA Processing] Error preprocessing document '{file_name}': {e}")
                            logging.error(f"Error preprocessing document {file_name}: {e}", exc_info=True)
                            extracted_text = ""
                        
                        if extracted_text and extracted_text.strip():
                            print(f"[JIRA Processing] Running AI summarization for document '{file_name}'...")
                            doc_summary, doc_ip_token, doc_op_token = await enrich_document_content(
                                full_text=extracted_text,
                                apiKey=apiKey,
                                resourceId=resourceId,
                                resource=resource,
                                serviceProvider=serviceProvider,
                                model=model,
                                sa_info=sa_info,
                                max_concurrent=3
                            )
                            total_ip_token += (doc_ip_token or 0)
                            total_op_token += (doc_op_token or 0)
                            print(f"[JIRA Processing] Summarized document '{file_name}' (Tokens: In={doc_ip_token}, Out={doc_op_token})")

                    else:
                        if ext == 'docx':
                            extracted_text = self._read_docx_from_bytes(content)
                        elif ext == 'pdf':
                            import PyPDF2
                            reader = PyPDF2.PdfReader(BytesIO(content))
                            extracted_text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
                        elif ext in ['txt', 'csv', 'md']:
                            extracted_text = content.decode('utf-8', errors='ignore')
                            
                    result["Documents"].append({
                        "File Name": file_name,
                        "File Type": ext.upper(),
                        "AI Summary": doc_summary if doc_summary else "No AI summary generated"
                    })
                    print(f"[JIRA Processing] Finished processing document attachment: {file_name}")
                    
                elif ext in ['png', 'jpg', 'jpeg']:
                    encoded = base64.b64encode(content).decode("utf-8")
                    images_base64[file_name] = encoded
                    print(f"[JIRA Processing] Staged image for combined analysis: {file_name}")
                    
                else:
                    result["Other Supported Files"].append({
                        "File Name": file_name,
                        "File Type": ext.upper() if ext else "UNKNOWN"
                    })
                    print(f"[JIRA Processing] Staged other file: {file_name}")
                    
            except Exception as e:
                print(f"[JIRA Processing] Error processing attachment {file_name} for ticket {issue_id}: {e}")
                logging.error(f"Error processing attachment {file_name} for ticket {issue_id}: {e}")
                
        # Handle images
        if images_base64:
            print(f"[JIRA Image Summarization] Starting combined analysis for {len(images_base64)} images on ticket {issue_id}...")
            try:
                img_summaries, img_in, img_out = await self.summarize_jira_image(
                    base64_images=images_base64,
                    ticket_summary=ticket_summary,
                    apiKey=apiKey,
                    serviceProvider=serviceProvider,
                    model=model,
                    sa_info=sa_info,
                    resource=resource,
                    resourceId=resourceId
                )
                total_ip_token += img_in
                total_op_token += img_out
                
                # Group relevant images by their common summaries to avoid duplicating the summary block!
                summary_groups = {}
                for img_name, img_summary in img_summaries.items():
                    if img_summary == "Discarded: irrelevant":
                        result["Images"].append({
                            "AI Image Summary": img_summary
                        })
                    else:
                        if img_summary not in summary_groups:
                            summary_groups[img_summary] = []
                        summary_groups[img_summary].append(img_name)
                
                # Append grouped entries
                for img_summary, img_names in summary_groups.items():
                    grouped_filenames = ", ".join(img_names)
                    result["Images"].append({
                        "AI Image Summary": img_summary
                    })
                    print(f"[JIRA Image Summarization] Added combined summary for group: [{grouped_filenames}]")
                    
            except Exception as e:
                print(f"[JIRA Image Summarization] Collective image summarization failed: {e}")
                logging.error(f"Failed to summarize images collectively: {e}")
                for img_name in images_base64.keys():
                    result["Images"].append({
                        "AI Image Summary": f"Failed to summarize image collectively: {str(e)}"
                    })
                
        return result, total_ip_token, total_op_token

    async def build_ticket_context(
        self,
        ticket_key: str,
        apiKey: str = None,
        serviceProvider: str = None,
        model: str = None,
        sa_info: dict = None,
        temp_dir: str = None,
        resource: str = None,
        resourceId: str = None,
        pre_fetched_fields: dict = None
    ) -> tuple[dict, int, int, dict]:
        fields = pre_fetched_fields if pre_fetched_fields is not None else await self.fetch_issue_clean(ticket_key)
        
        description_text = fields.get("Description", "")
        compressed_desc = await self.text_compress(
            text=description_text,
            apiKey=apiKey,
            serviceProvider=serviceProvider,
            model=model,
            sa_info=sa_info,
            resource=resource,
            resourceId=resourceId
        )
        
        jira_details = {
            "Jira Key": fields.get("Issue Key", ""),
            "Issue Type": fields.get("Type", ""),
            "Summary": fields.get("Summary", ""),
            "Description": compressed_desc
        }
        
        attachments_data = {}
        ip_tokens = 0
        op_tokens = 0
        try:
            attachments_data, ip_tokens, op_tokens = await self._process_attachments_hierarchical(
                issue_id=ticket_key,
                attachments=fields.get("Attachments", []),
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                sa_info=sa_info,
                temp_dir=temp_dir,
                ticket_summary=fields.get("Summary", ""),
                resource=resource,
                resourceId=resourceId
            )
        except Exception as e:
            print(f"[JIRA Processing] Error processing attachments for ticket {ticket_key}: {e}")
            logging.error(f"Error processing attachments for ticket {ticket_key}: {e}", exc_info=True)
        
        # Remove empty attachment lists natively
        clean_attachments = {k: v for k, v in attachments_data.items() if v}
        
        ticket_context = {
            "Jira Details": jira_details
        }
        
        if clean_attachments:
            ticket_context["Attachments"] = clean_attachments
        
        return ticket_context, ip_tokens, op_tokens, fields

    async def _generate_text_raw(
        self,
        serviceProvider: str,
        model: str,
        apiKey: str,
        system_prompt: str,
        user_prompt: str,
        sa_info: dict = None,
        temperature: float = 0.1,
        resource: str = None,
        resourceId: str = None
    ) -> str:
        """Helper to generate raw text from LLMs, bypassing JSON parsing logic of llm_client."""
        import logging
        if serviceProvider in ["DefaultFireFlink", "Groq"]:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=apiKey)
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature,
                "stream": False,
                "max_tokens": 32000,
            }
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content

        elif serviceProvider == 'OpenAi':
            from openai import AsyncOpenAI
            base_url = None
            if resourceId:
                if resource == 'openai':
                    base_url = f"https://api.openai.com/v1/"
                else:
                    base_url = f"https://{resourceId}.openai.azure.com/openai/v1/"
            
            client = AsyncOpenAI(api_key=apiKey, base_url=base_url)
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=1 if model in ["o4-mini-2025-04-16", "gpt-5-2025-08-07"] else temperature
            )
            return response.choices[0].message.content

        elif serviceProvider == 'Anthropic':
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=apiKey)
            
            output_config = None
            current_temperature = temperature
            max_tokens = 8192
            
            if model == "claude-haiku-4-5-20251001":
                max_tokens = 64000
            elif model in ["claude-sonnet-4-6", "claude-opus-4-6"]:
                max_tokens = 128000
                current_temperature = 1.0
                output_config = {"effort": "medium"}
            elif model == "claude-opus-4-8":
                max_tokens = 128000
                current_temperature = None
                output_config = {"effort": "medium"}
                
            extra_params = {}
            if output_config:
                extra_params["output_config"] = output_config
            if current_temperature is not None:
                extra_params["temperature"] = current_temperature
                
            async with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                **extra_params
            ) as stream:
                async for text in stream.text_stream:
                    pass
                final_message = await stream.get_final_message()
            return final_message.content[0].text

        elif serviceProvider == 'Azure_AI':
            from openai import AsyncOpenAI
            logging.info(f"_generate_text_raw: Entering Azure_AI service provider")
            if resource == "AzureFoundry":
                base_url = f"https://{resourceId}.services.ai.azure.com/openai/v1"
            else:
                base_url = f"https://{resourceId}.openai.azure.com/openai/v1/"
            logging.info(f"\033[93m_generate_text_raw base_url:{base_url}\033[0m")

            client = AsyncOpenAI(
                api_key=apiKey,
                base_url=base_url
            )
            response = await client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            content = response.choices[0].message.content
            if isinstance(content, list):
                content = content[0]
            if not content or not content.strip():
                raise ValueError("Empty response from Azure_AI model.")
            return content

        elif serviceProvider == 'Gemini':
            import google.generativeai as genai
            genai.configure(api_key=apiKey)
            client = genai.GenerativeModel(model)
            response = await client.generate_content_async(
                contents=[
                    {"role": "user", "parts": [{"text": system_prompt}]},
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": 32768
                }
            )
            return response.text

        elif serviceProvider == "gemini_enterprise":
            import json
            import vertexai
            from vertexai.generative_models import GenerativeModel
            from google.oauth2 import service_account
            
            if isinstance(sa_info, str):
                sa_info = json.loads(sa_info)
            credentials = service_account.Credentials.from_service_account_info(sa_info)
            vertexai.init(
                project=sa_info["project_id"],
                location="us-central1",
                credentials=credentials,
            )
            client = GenerativeModel(model)
            max_output_tokens = 8192 if model in ["publishers/meta/models/llama-3.3-70b-instruct-maas","publishers/google/models/gemini-2.0-flash-lite-001","publishers/google/models/gemini-2.0-flash-001"] else 32768
            response = await client.generate_content_async(
                contents=[
                    {"role": "user", "parts": [{"text": system_prompt}]},
                    {"role": "user", "parts": [{"text": user_prompt}]}
                ],
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens
                }
            )
            return response.text

        else:
            raise ValueError(f"Unsupported service provider for text compression: {serviceProvider}")

    async def text_compress(
        self, 
        text: str, 
        apiKey: str,
        serviceProvider: str = None,
        model: str = None,
        sa_info: dict = None,
        resource: str = None,
        resourceId: str = None
    ) -> str:
        """
        Compresses large text losslessly by chunking into 4000-word blocks.
        Each block is summarized independently to 650-850 words and then combined.
        """
        if not apiKey and not sa_info:
            return text
        
        words = text.split()
        original_word_count = len(words)
        print(f"[JIRA Processing] Checking compression for text length: {original_word_count} words.")
        
        if original_word_count <= 1000:
            print(f"[JIRA Processing] Text is under 1000 words ({original_word_count}). Skipping compression.")
            return text
            
        print(f"[JIRA Processing] Text is over 1000 words ({original_word_count}). Starting compression...")
            
        chunk_size = 4000
            
        chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
        
        final_summary_parts = []
        
        system_prompt = """
You are a lossless Jira context compressor for an AI-powered test case generation system.

Your objective is to maximize information density while preserving every detail that could influence manual or automated test case generation.

The input document exceeds 1000 words. Compress it into 650-850 words without changing its meaning.

STRICT REQUIREMENTS

Treat this as semantic compression, NOT summarization.

Preserve exactly:
- Functional requirements
- Non-functional requirements
- Business rules
- Acceptance criteria
- Preconditions
- Postconditions
- User journeys
- UI behavior
- APIs
- Data models
- Validation rules
- Permissions
- Error handling
- Edge cases
- Workflows
- Configuration
- Environment-specific behavior
- IDs, URLs, filenames, enums, constants, field names, labels
- Parent-child ticket relationships
- Attachment-derived information

Allowed transformations:
- Remove duplicate statements.
- Collapse repeated explanations.
- Convert paragraphs into compact bullets.
- Replace verbose language with concise equivalents.
- Merge overlapping descriptions without removing facts.
- Remove formatting noise.

Forbidden transformations:
- Summarization
- Generalization
- Omission of requirements
- Rewording that changes meaning
- Adding assumptions
- Inventing missing details

Every fact present in the source must remain recoverable from the compressed version.

Output only the compressed content (650-850 words).
"""

        for chunk in chunks:
            user_content = f"TEXT TO COMPRESS:\n{chunk}"
                
            try:
                content = await self._generate_text_raw(
                    serviceProvider=serviceProvider,
                    model=model,
                    apiKey=apiKey,
                    system_prompt=system_prompt,
                    user_prompt=user_content,
                    sa_info=sa_info,
                    temperature=0.1,
                    resource=resource,
                    resourceId=resourceId
                )
                    
                final_summary_parts.append(str(content))
            except Exception as e:
                logging.error(f"Error during batch compression chunk: {e}")
                print(f"[JIRA Processing] Failed compression chunk: {e}")
                # Fallback to appending raw chunk if compression fails to avoid data loss
                final_summary_parts.append(chunk)
                
        final_text = "\n\n".join(final_summary_parts)
        final_word_count = len(final_text.split())
        print(f"[JIRA Processing] Compression complete. Original: {original_word_count} words -> Final: {final_word_count} words.")
        return final_text

    async def summarize_jira_image(
        self,
        base64_images: dict,
        ticket_summary: str = "",
        apiKey: str = None,
        serviceProvider: str = None,
        model: str = None,
        sa_info: dict = None,
        resource: str = None,
        resourceId: str = None
    ) -> tuple[dict, int, int]:
        import os
        import json
        import logging
        from src.llm.client import ImageLLMClient

        # Setup parameters for LLMClient
        if serviceProvider == "DefaultFireFlink":
            provider_to_use = "OpenAi"
            key_to_use = os.getenv("OPENAI_API_KEY")
            model_to_use = "gpt-4.1-mini-2025-04-14"
            if not key_to_use:
                logging.error(
                    "OPENAI_API_KEY not found in environment variables for DefaultFireFlink."
                )
                return {
                    filename: "OPENAI_API_KEY not found in environment."
                    for filename in base64_images.keys()
                }, 0, 0
        else:
            if not apiKey and not sa_info:
                logging.error("Initial apiKey and sa_info are both missing.")
                return {
                    filename: "apiKey/sa_info not found in configuration."
                    for filename in base64_images.keys()
                }, 0, 0
            provider_to_use = serviceProvider if serviceProvider else "OpenAi"
            key_to_use = apiKey
            model_to_use = model if model else "gpt-4.1-mini-2025-04-14"

        print(f"\n[JIRA MTC Image Processing] Using Service Provider: {provider_to_use}, Model: {model_to_use}")

        jira_image_prompt = f"""You are a senior QA engineer analyzing screenshots attached to a Jira ticket. Extract key context to support test case generation.

    Ticket Summary Context: "{ticket_summary}"

    CRITICAL INSTRUCTIONS:
    1. First, evaluate if each image is relevant to the ticket summary or represents a software application/UI. If an image is irrelevant (e.g., a generic logo, a random picture, a system file icon, or not software-related), mark it as `is_relevant: false` in `relevance_assessment`.
    2. For all relevant images combined, describe a sequential user flow / chronological transition sequence in `combined_flow`.
    3. For all relevant images combined, generate a structured, consolidated summary under `combined_summary`.
    4. Only describe what is visibly present. Do not assume or hallucinate elements.
    """

        response_schema = {
            "type": "object",
            "properties": {
                "relevance_assessment": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "is_relevant": {"type": "boolean"},
                            "reason": {"type": "string"},
                        },
                        "required": ["filename", "is_relevant", "reason"],
                        "additionalProperties": False,
                    },
                },
                "combined_flow": {
                    "type": "string",
                    "description": "Sequential flow of the screens/images (e.g., Image A -> Image B -> Image C) explaining the user journey and actions triggering each transition.",
                },
                "combined_summary": {
                    "type": "object",
                    "properties": {
                        "screen_feature_context": {
                            "type": "string",
                            "description": "Identify the screen, page, or module shown and the application area they belong to.",
                        },
                        "ui_elements": {
                            "type": "string",
                            "description": "List the key visible components across all screens: buttons (label & state), input fields (name, value, placeholder), dropdowns, tables, modals, active navigation/tabs.",
                        },
                        "data_application_state": {
                            "type": "string",
                            "description": "Describe the current data entered or displayed, and the UI state (empty, loading, success, error, partial). Note toggle, checkbox, or radio button states.",
                        },
                        "error_validation_signals": {
                            "type": "string",
                            "description": "Quote any visible error messages, toast notifications, or inline validation text exactly. Describe broken layouts or misalignments.",
                        },
                        "inferred_requirement_or_bug": {
                            "type": "string",
                            "description": "Briefly state the user action or flow represented. Contrast expected vs. actual behavior if a bug is visible. Flag any ambiguities needing clarification.",
                        },
                    },
                    "required": [
                        "screen_feature_context",
                        "ui_elements",
                        "data_application_state",
                        "error_validation_signals",
                        "inferred_requirement_or_bug",
                    ],
                    "additionalProperties": False,
                },
            },
            "required": [
                "relevance_assessment",
                "combined_flow",
                "combined_summary",
            ],
            "additionalProperties": False,
        }

        image_items = list(base64_images.items())
        
        # We process all images (up to 10 max due to download limit) in a single chunk
        image_chunks = [image_items] if image_items else []
        
        result_summaries = {}

        async def process_chunk(chunk):
            if not chunk:
                return {}, 0, 0
            images = []
            user_prompt = "Please analyze the following images based on the provided instructions:\n"
            for filename, base64_img in chunk:
                user_prompt += f"- Image filename: {filename}\n"
                ext = filename.split(".")[-1].lower() if "." in filename else ""
                mime_type = {
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "gif": "image/gif",
                    "webp": "image/webp",
                }.get(ext, "image/png")

                images.append({
                    "mime_type": mime_type,
                    "data": base64_img
                })

            try:
                chunk_filenames = [f for f, _ in chunk]
                print(
                    f"[AI Vision] Sending parallel chunk of {len(chunk)} images to provider {provider_to_use} with model {model_to_use}: {chunk_filenames}..."
                )

                response_data, in_tokens, out_tokens = await ImageLLMClient.generate_async(
                    serviceProvider=provider_to_use,
                    model=model_to_use,
                    apiKey=key_to_use,
                    system_prompt=jira_image_prompt,
                    user_prompt=user_prompt,
                    images=images,
                    sa_info=sa_info,
                    resource=resource,
                    resourceId=resourceId,
                    temperature=0.1,
                    return_usage=True,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "image_summaries",
                            "strict": True,
                            "schema": response_schema,
                        },
                    }
                )

                # Ensure response_data is a dict (LLMClient generate_async returns dict when response_format is used)
                if isinstance(response_data, str):
                    try:
                        response_data = json.loads(response_data)
                    except json.JSONDecodeError:
                        try:
                            response_data = repair_json(response_data, return_objects=True)
                        except Exception as e:
                            logging.error(f"json_repair failed for image summarization: {e}")
                            response_data = {}
                
                # If the model wraps the object in a list, extract the first item
                if isinstance(response_data, list):
                    response_data = response_data[0] if len(response_data) > 0 else {}
                    
                if not isinstance(response_data, dict):
                    response_data = {}

                # Ensure a unique debug filename per chunk to prevent race conditions during concurrent execution
                safe_prefix = chunk_filenames[0].split(".")[0] if chunk_filenames else "chunk"
               
                relevance_assessment = response_data.get("relevance_assessment", [])
                combined_flow = response_data.get("combined_flow", "")
                combined_summary = response_data.get("combined_summary", {})

                relevance_map = {
                    item["filename"]: item["is_relevant"]
                    for item in relevance_assessment
                }
                relevant_chunk_filenames = [
                    fname for fname, _ in chunk if relevance_map.get(fname, True)
                ]

                if relevant_chunk_filenames:
                    combined_md = f"""**Combined Flow of Screens:**
    {combined_flow}

    **Screen / Feature Context**
    {combined_summary.get('screen_feature_context', '')}

    **UI Elements**
    {combined_summary.get('ui_elements', '')}

    **Data & Application State**
    {combined_summary.get('data_application_state', '')}

    **Error / Validation Signals**
    {combined_summary.get('error_validation_signals', '')}

    **Inferred Requirement or Bug**
    {combined_summary.get('inferred_requirement_or_bug', '')}"""
                else:
                    combined_md = "Discarded: irrelevant"

                res = {
                    fname: (
                        combined_md
                        if relevance_map.get(fname, True)
                        else "Discarded: irrelevant"
                    )
                    for fname, _ in chunk
                }
                return res, in_tokens, out_tokens
            except Exception as e:
                error_str = str(e)
                status_code = getattr(e, "responseCode", getattr(e, "status_code", 0))
                is_vision_error = (
                    "does not support vision" in error_str.lower()
                    or "must be a string" in error_str.lower()
                    or status_code in (400, 401, 403, 404, 422)
                    or "400" in error_str
                )

                if is_vision_error:
                    logging.warning(
                        f"[AI Vision] Model '{model_to_use}' does not support "
                        f"image inputs. Skipping image summarization for chunk: "
                        f"{[f for f, _ in chunk]}"
                    )
                    skip_reason = (
                        f"Image summarization skipped: model '{model_to_use}' "
                        f"does not support vision/image inputs."
                    )
                else:
                    logging.error(
                        f"Error calling LLM for Jira image summarization chunk: {e}"
                    )
                    skip_reason = f"Image summarization failed: {error_str}"

                res = {fname: skip_reason for fname, _ in chunk}
                return res, 0, 0

        chunk_tasks = [process_chunk(chunk) for chunk in image_chunks]
        completed_chunks = await asyncio.gather(*chunk_tasks)

        total_in = 0
        total_out = 0
        for chunk_result, chunk_in, chunk_out in completed_chunks:
            result_summaries.update(chunk_result)
            total_in += chunk_in
            total_out += chunk_out

        return result_summaries, total_in, total_out


async def jira_issues_fetch_utility(
    generator: JiraDocGenerator,
    domain: str,
    project_name: str,
    next_page_token: Optional[str] = None
):
    """
    Utility function to fetch Jira issues for a given project.
    Adapted to use JiraDocGenerator instead of JiraToolkit.
    """
    try:
        logging.info(f"Resolving project key for name: {project_name}")
        
        # Get project key by name
        projects_url = f"https://{domain}.atlassian.net/rest/api/3/project/search?query={project_name}"
        projects_response = await generator._make_jira_request(projects_url)
        projects = projects_response.get("values", [])
        
        project_key = None
        for p in projects:
            if p.get("name") == project_name:
                project_key = p.get("key")
                break
                
        if not project_key:
            return {
                "responseCode": 404,
                "message": f"Project with name '{project_name}' not found."
            }
            
        logging.info(f"Resolved project key: {project_key}")
        
        jql = f"project = {project_key} ORDER BY created DESC"
        search_url = f"https://{domain}.atlassian.net/rest/api/3/search/jql"
        payload = {
            "jql": jql,
            "maxResults": 5000,
            "fields": ["key"],
        }
        
        if next_page_token:
            payload["nextPageToken"] = next_page_token
            logging.info(f"Fetching next page with token: {next_page_token}")
            
        logging.info(f"Searching for issues with JQL: {jql}")
        
        try:
            search_response = await generator._make_jira_request(search_url, method="POST", json_data=payload)
        except Exception as e:
            logging.error(f"Jira returned error: {e}")
            return {
                "responseCode": 400,
                "message": "Failed to search for tickets",
                "error": str(e),
                "issues": []
            }
            
        issue_keys = [issue.get("key") for issue in search_response.get("issues", [])]
        total_issues = len(issue_keys)
        next_page_token = search_response.get("nextPageToken")
        is_last = search_response.get("isLast", True)
        
        logging.info(f"Found {len(issue_keys)} issues. Next page token: {next_page_token}. Is last page: {is_last}")
        
        return {
            "responseCode": 200,
            "issues": issue_keys,
            "next_page_token": next_page_token,
            "is_last": is_last,
            "message": "Successfully fetched issues",
            "total_issues": total_issues
        }
    except Exception as e:
        logging.exception("High-level error in jira_issues_fetch_utility")
        return {
            "responseCode": 500,
            "message": str(e)
        }