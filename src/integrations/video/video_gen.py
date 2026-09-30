from pydantic import BaseModel,Field
from typing import Optional,Any
from qdrant_client.models import Filter,FieldCondition,MatchValue
from src.persistence.mongo_client import get_sync_client
from src.api.runtime import *


class TempVideoPromptRequest(BaseModel):
    input: str
    user_id: str
    project_id: str
    license_id: str
    input_type: Optional[str] = "video"
    count: int = 1
    prompt_type: str = "Web"
    summary : Optional[str] = None
    branch_id: Optional[str] = None
    ref_id: Optional[Any] = None
    is_automation_steps: bool = False
    file_name: str

async def video_e2e_retrieval_temp(video_name,collection_name,q_client):
    e2e_flow=[]
    search_filter = Filter(
        must=[
            FieldCondition(
                key="video_name",
                match=MatchValue(value=video_name),
            ),
            FieldCondition(
                key="chunk_type",
                match=MatchValue(value="end to end"),
            ),
        ]
    )
    results, _ = q_client.scroll(
        collection_name=collection_name,
        scroll_filter=search_filter,
        with_payload=True,
        limit=1,
    )
    if not results:
        return None
    payload = results[0].payload or {}
    e2e=payload.get("e2e_flow")
    e2e_flow.append({
        "end_to_end_flow_of_video":e2e
    })
    return e2e_flow


async def mongodb_license_inti(license_id,env=None):
    _lid = f"optimize_{env}_{license_id}" if env else f"optimize_{license_id}"
    return _lid

def load_video_collection(license_id):
    client = get_sync_client()
    db = client[license_id]
    collection = db["ai_video_data_sources"]
    return collection

def update_video_mongodb_status(_lid,video_id,status,message):
    collection = load_video_collection(_lid)
    video_id = video_id.strip().strip('"').strip("'")
    record = {
        "status": status,
        "message": message
        }
        
    collection.update_one(
            {"videoId": video_id},  
            {"$set": record},          
            )

def get_the_collection(_lid):
    collection = load_video_collection(_lid)
    return collection
    

def get_status_video(collection):
    cursor = collection.find(
        {},
        {
            "_id": 0,
            "videoId": 1,
            "fileName": 1,
            "projectId": 1,
            "status": 1
        }
    )
    return cursor



async def handle_user_input_for_video_process(
        self,
        user_input: str,
        session_id: str,
        session_name,
        count,
        license_id,
        project_id,
        bearer_token,
        prompt_id,
        user_id,
        input_type,
        script_type,
        is_modified,
        user_input_tokens,
        template_id,
        unique_id,
        dateTime,
        original_template,
        template,
        apiKey=None,
        serviceProvider=None,
        model=None,
        prompt_type=None,
        sa_info=None,
        resourceId=None,
        resource=None,
        env=None,
        video_process_name=None,
        request_time_for_storing_1_tc_in_MD=None,
        return_generated_payload=False,
        branch_id=None,
    ):
        if env:
            mongoDb_license_id = f"optimize_{env}_{license_id}"
        else:
            mongoDb_license_id = f"optimize_{license_id}"

        try:
            if env :
                COLLECTION_NAME = f"ff_cloud_{env}_video_{license_id}_{project_id}"
            else :
                COLLECTION_NAME = f"ff_cloud_video_{license_id}_{project_id}"
            agent_operstion = AgentOperation(
                json_template=template, 
                user_input=user_input,
                collection_name=COLLECTION_NAME,
                embeddings=self.embeddings,
                qdrant_client=AsyncQdrantClient(qdrant_host, port=qdrant_port, https=False),
                # qdrant_client=qdrant_client,
                session_id=session_id, 
                session_name=session_name,
                prompt_id=prompt_id,
                user_id=user_id,
                input_type=input_type,
                script_type=script_type,
                is_modified=is_modified,
                user_input_tokens=user_input_tokens,
                template_id=template_id,
                unique_id=unique_id,
                dateTime=dateTime,
                original_template=original_template,
                bearer_token=bearer_token,
                branch_id=branch_id,            
                count=count,
                memory=True, 
                is_jira=False,
                is_image =False,
                is_file =False,
                is_video=False,
                is_figma=False,
                is_video_process=True,
                apiKey=apiKey,
                serviceProvider=serviceProvider,
                model=model,
                prompt_type=prompt_type,
                sa_info=sa_info,
                resourceId=resourceId,
                resource=resource,
                env=env,
                video_process_name=video_process_name,
                license_id=license_id,
                project_id=project_id,
                return_generated_payload=return_generated_payload,
            )
            result = await agent_operstion.async_lang_graph_builder(
                apiKey,
                serviceProvider,
                model,
                sa_info,
                request_time_for_storing_1_tc_in_MD,
                return_generated_payload=return_generated_payload
            )
            
            # If no test cases were generated at all, raise an exception to record the failure in MongoDB
            if agent_operstion._total_testcase_count == 0:
                raise ValueError("Unable to generate manual test cases. Please try again.")
            
            return result
            
        except Exception as e:
            self.save_generation_error(
                unique_id=unique_id,
                error=e,
                license_id=mongoDb_license_id,
                service_provider=serviceProvider
            )




def delete_points_of_videos(collection_name,qdrant_client,mongo_id,video_name):
    try:
        # Check if collection exists
        mongo_id = mongo_id.strip('"')
        collections = qdrant_client.get_collections().collections
        existing = [c.name for c in collections]
        print("this are the existing collections:",existing)

        if collection_name not in existing:
            return {
                "responseCode": 404,
                "responseObject": None,
                "message": f"Collection '{collection_name}' does not exist"
            }

        # Delete points where payload["source"] == instance_name
        delete_filter = Filter(
            should=[
                FieldCondition(
                    key="mongo_id",
                    match=MatchValue(value=mongo_id)
                ),
                FieldCondition(
                    key="mongo_id",
                    match=MatchValue(value=f'"{mongo_id}"')
                )
            ]
        )

        qdrant_client.delete(
            collection_name=collection_name,
            points_selector=delete_filter
        )

        return {
            "responseCode": 200,
            "responseObject": {
                "collection_name": collection_name,
                "video_name":video_name
            },
        }

    except Exception:
        raise RuntimeError(
            f"Failed to delete source '{video_name}' from collection '{collection_name}'"
        )

class DeleteVideoCollectionRequest(BaseModel):
    license_id: str
    project_id: str
    video_id: str


async def video_flow_selector(video_name,collection_name, q_client):
    print("coming inside function")
    structured_modules = []
    search_filter = Filter(
        must=[
            FieldCondition(
                key="chunk_id",
                match=MatchValue(value=-1)
                        ),
            FieldCondition(
                key="video_name",
                match=MatchValue(value=video_name)
            )
        ]
    )
    results, _ = await q_client.scroll(
        collection_name=collection_name,
        scroll_filter=search_filter,
        with_payload=True,
        limit=1,      
    )
    if results:
        payload = results[0].payload or {}
        module_names = payload.get("all_module_name", [])
        module_flows = payload.get("all_module_name_flow", [])

        structured_modules.append(f"This are all module names:{module_names}")
        # print("...............",structured_modules)
        # for module in module_flows:
        #     structured_modules.append(
        #         f"This is the module with its flow: "
        #         f"module_name={module['module_name']}, "
        #         f"flow={module['flow']}"
        #     )
        print("...............",structured_modules)
        for module in module_flows:
            structured_modules.append({
                "module_name": module["module_name"],
                "flow": module["flow"]
            })

    return structured_modules,module_names


def video_data_selector(flow_selector_chunk: str, user_query: str):

    systemPrompt = f"""
You are a structured data extraction assistant, here you are acting as a ROUTER that selects the relevant module name(s) from the provided FlowSelectorChunk based on the user query only.
You do not have any prior knowledge of modules, flows, or business logic beyond what is explicitly given in the FlowSelectorChunk.

There are exactly THREE possible outcomes. Decide which ONE applies, in this order:

**Task 0 — Explicit End-to-End Query**
    - Applies when the user query EXPLICITLY asks for an end-to-end / e2e test case, with no specific module/screen/content reference.
    - Trigger phrases (case-insensitive, and their obvious variants/misspellings): "end to end", "end-to-end", "endtoend", "e2e".
    - Examples: "generate end to end test case for video", "generate e2e test case for video", "generate e2e test case", "create an end-to-end test case for the video".
    THEN you MUST:
        1. Leave "module_name" as an empty list: []
        2. Set "end to end" as true
        3. Set "all_flow" as false
        4. Do NOT attempt to guess, infer, or select any module in this case.
        5. Do NOT perform Task 1 or Task 2 — stop here and return the JSON object as described.

**Task 1 — Specific Module Query**
    - Applies when a content word/phrase (after removing boilerplate) matches module content in the FlowSelectorChunk (e.g., "login", "sign up", "checkout", "product search").
        - Examples: "generate test case for login video", "generate end to end test case for flipkart video" etc (which will contain a word)
        By using that word identify exact flow to which it belongs
    THEN you MUST:
        1. Identify the exact module_name(s) from the FlowSelectorChunk whose flow content matches the content word(s).
        2. Give the EXACT module name as it appears in the FlowSelectorChunk — do NOT change, rephrase, abbreviate, or alter a single character.
        3. If more than one module is relevant, include all of them in "module_name".
        4. Set "end to end" as false.
        5. Set "all_flow" as false.
        6. Do NOT invent or guess a module that is not present in the FlowSelectorChunk.
        7. If the content word does not genuinely map to any module, fall back to Task 0 if the query explicitly said end-to-end/e2e, otherwise fall back to Task 2.

**Task 2 — Generic Query (no e2e keyword, no specific module)**
    - Applies when the query does NOT contain an explicit end-to-end/e2e trigger phrase AND, after removing boilerplate words, there is no specific module/screen/content reference left.
    - Examples: "generate test case for video", "generate test cases", "generate test case".
    THEN you MUST:
        1. Leave "module_name" as an empty list: []
        2. Set "end to end" as false
        3. Set "all_flow" as true
        4. Do NOT attempt to guess, infer, or select any module in this case.

**HOW TO TELL A REAL CONTENT WORD FROM NOISE (do this check BEFORE matching)**
    Before treating any word/phrase from the user query as a content word for Task 1, check how it distributes across the FlowSelectorChunk's modules:
        - If the word/phrase appears in the flow text of ONLY ONE module, or a small minority of modules (i.e., it distinguishes that module from the others) → it IS a valid content word. Proceed with Task 1.
        - If the word/phrase appears in the flow text of MOST or ALL modules (e.g., because it's the name of the application/website/product under test, which naturally gets mentioned everywhere — in URLs, step descriptions, etc.) → it carries NO discriminating power and must be treated as boilerplate/noise, exactly like the word "video". Fall back to Task 0 (if an explicit e2e/end-to-end phrase was used) or Task 2 (otherwise).
    This check is dynamic — perform it fresh against whatever FlowSelectorChunk is given. Do NOT rely on a fixed list of "known" app names; determine it by literally checking word distribution across the modules' flow arrays each time.
    Reasoning pattern:
        1. First check the query for an explicit end-to-end/e2e trigger phrase — note this separately, it does NOT get stripped as ordinary boilerplate; it decides between Task 0 and Task 2 later.
        2. Extract candidate content words from the query (strip generic request words like "generate", "test case", "for", "video", "create", "a", "the", etc., and also strip the end-to-end/e2e trigger phrase itself once noted).
        3. For each candidate word, scan every module's flow list in the FlowSelectorChunk and count in how many DISTINCT modules it appears.
        4. Keep only candidate words that appear in a small subset of modules (distinctive). Discard candidate words appearing in nearly all modules (non-distinctive/app-name-like).
        5. If distinctive candidate word(s) remain → Task 1, matching to the module(s) whose flow content contains them.
        6. If no distinctive candidate words remain:
            a. If an explicit end-to-end/e2e trigger phrase was present → Task 0.
            b. Otherwise → Task 2.

**IMPORTANT RULES**
    - Completely analyze the FlowSelectorChunk to understand which flow content belongs to which module_name before deciding.
    - Do NOT include explanations, reasoning, markdown, or any other text — output the JSON object only.
    - Exactly one of "end to end" / "all_flow" may be true at once, and both must be false whenever "module_name" is non-empty (Task 1). Never set both "end to end" and "all_flow" to true.
    - Preserve the exact module_name string (including capitalization, spacing, and punctuation) exactly as it appears in the FlowSelectorChunk.
    - The presence of the word "video" anywhere in the user_query is NEVER by itself a reason to choose Task 0 or Task 2 over Task 1 — it is boilerplate, not content.
"""

    userPrompt = f"""
FLOW SELECTOR CHUNK:
{flow_selector_chunk}

USER REQUEST:
{user_query}

### FINAL OUTPUT
Return ONLY the JSON object.
### FINAL OUTPUT
Return ONLY the JSON object.
{{
  "module_name": [<string>, ...],
  "end to end": <boolean>,
  "all_flow": <boolean>
}}
"""
    responseFormat = {
        "type": "json_schema",
        "json_schema": {
            "name": "module_video_router",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "end to end": {
                        "type": "boolean"
                    },
                    "all_flow": {
                        "type": "boolean"
                    }
                },
                "required": ["module_name", "end to end", "all_flow"],
                "additionalProperties": False
            }
        }
    }
    return systemPrompt, userPrompt, responseFormat


class ModuleVideoRouterResponse(BaseModel):
    module_name: List[str]
    end_to_end: bool = Field(alias="end to end")
    all_flow: bool


async def video_e2e_retrieval(video_name,collection_name,q_client):
    e2e_flow=[]
    search_filter = Filter(
        must=[
            FieldCondition(
                key="video_name",
                match=MatchValue(value=video_name),
            ),
            FieldCondition(
                key="chunk_type",
                match=MatchValue(value="end to end"),
            ),
        ]
    )
    results, _ = await q_client.scroll(
        collection_name=collection_name,
        scroll_filter=search_filter,
        with_payload=True,
        limit=1,
    )
    if not results:
        return None
    payload = results[0].payload or {}
    e2e=payload.get("e2e_flow")
    e2e_url=payload.get("e2e_entry_point")
    e2e_flow.append({
        "entry_point":e2e_url,
        "end_to_end_flow":e2e
    })
    return e2e_flow



async def video_flow_retrieval(video_name,collection_name,q_client,module_name):
    summary_flow=[]
    search_filter = Filter(
        must=[
            FieldCondition(
                key="video_name",
                match=MatchValue(value=video_name),
            ),
            FieldCondition(
                key="module_name",
                match=MatchValue(value=module_name),
            ),
        ]
    )
    results, _ = await q_client.scroll(
        collection_name=collection_name,
        scroll_filter=search_filter,
        with_payload=True,
        limit=1,
    )
    if not results:
        return None
    payload = results[0].payload or {}
    flow=payload.get("flow")
    credential=payload.get("credential")
    summary_flow.append({
        "flow_name":module_name,
        "credential":credential,
        "flow":flow
    })
    return summary_flow


class VideoPromptRequest(BaseModel):
    input: str
    user_id: str
    project_id: str
    session_id: Optional[str] = None
    prompt_id: Optional[str] = None
    license_id: str
    input_type: Optional[str] = "video"
    count: int = 1
    script_type: Optional[str] = None
    session_name: Optional[str] = None
    prompt_type: str = "Web"
    summary : Optional[str] = None
    branch_id: Optional[str] = None
    ref_id: Any


async def video_audio_retrieval(video_name,collection_name,q_client):
    audio_flow=[]
    search_filter = Filter(
        must=[
            FieldCondition(
                key="video_name",
                match=MatchValue(value=video_name),
            ),
            FieldCondition(
                key="chunk_type",
                match=MatchValue(value="video_audio"),
            ),
        ]
    )
    results, _ = await q_client.scroll(
        collection_name=collection_name,
        scroll_filter=search_filter,
        with_payload=True,
        limit=1,
    )
    if not results:
        return None
    payload = results[0].payload or {}
    audio_txt=payload.get("video_related_audio")
    audio_flow.append({
        "audio_flow":audio_txt
    })
    return audio_flow