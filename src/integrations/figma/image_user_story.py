
import os
from toon import encode
import base64
import uuid
from dotenv import load_dotenv
from groq import Groq
from qdrant_client.http import models as qmodels
from typing import Dict, List, Optional
load_dotenv()
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    force=True   
)
logger = logging.getLogger(__name__)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)
MODEL_NAME_1 = "qwen/qwen3.6-27b"
VECTOR_SIZE = 768
token_usage = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
}

def find_frame_by_name(node, target_name):
    if isinstance(node, dict):
        if node.get("name") == target_name:
            return node
        for v in node.values():
            found = find_frame_by_name(v, target_name)
            if found:
                return found

    elif isinstance(node, list):
        for item in node:
            found = find_frame_by_name(item, target_name)
            if found:
                return found
    return None

def extract_text(node: Dict) -> Optional[str]:
    if node.get("type") == "TEXT":
        return node.get("characters")

    for child in node.get("children", []):
        text = extract_text(child)
        if text:
            return text

    return None

def collect_frames(node: Dict, frames: Dict[str, Dict]):

    if node.get("type") == "FRAME":
        frames[node["id"]] = {
            "id": node["id"],
            "name": node.get("name"),
            "interactions": []
        }

    for child in node.get("children", []):
        collect_frames(child, frames)

def collect_interactions(
    node: Dict,
    frames: Dict[str, Dict],
    current_frame_id: Optional[str] = None,
    parent_type: Optional[str] = None
):
    if node.get("type") == "FRAME" and parent_type == "CANVAS":
        current_frame_id = node.get("id")
    for interaction in node.get("interactions") or []:
        if not isinstance(interaction, dict):
            continue
        trigger = (interaction.get("trigger") or {}).get("type")
        for action in interaction.get("actions") or []:
            if not isinstance(action, dict):
                continue
            destination = action.get("destinationId")
            if destination and current_frame_id in frames:
                frames[current_frame_id]["interactions"].append({
                    "component": node.get("name"),
                    "label": extract_text(node),
                    "trigger": trigger,
                    "navigation": action.get("navigation"),
                    "destination_id": destination
                })

    for child in node.get("children") or []:
        if isinstance(child, dict):
            collect_interactions(
                child,
                frames,
                current_frame_id,
                node.get("type")
            )

def extract_flow(page_json: Dict) -> List[Dict]:
    frames: Dict[str, Dict] = {}
    canvas = {
        "id": page_json["page"]["id"],
        "name": page_json["page"]["name"],
        "type": "CANVAS",
        "children": page_json.get("children", [])
    }

    collect_frames(canvas, frames)
    
    frame_name_map = {fid: f["name"] for fid, f in frames.items()}
    collect_interactions(canvas, frames)

    flow = []
    for frame in frames.values():
        for interaction in frame["interactions"]:
            flow.append({
                "from_screen": frame["name"],
                "component": interaction["component"],
                "label": interaction["label"],
                "trigger": interaction["trigger"],
                "navigation": interaction["navigation"],
                "destinationFrame": frame_name_map.get(
                    interaction["destination_id"],
                    "UNKNOWN"
                )
            })

    return flow


def create_prototype_flow(node_id: str, page_json: str) -> None:
    full_flow = extract_flow(page_json)

    as_source = []
    as_destination = []

    for entry in full_flow:
        if entry.get("from_screen") == node_id:
            as_source.append(entry)

        if entry.get("destinationFrame") == node_id:
            as_destination.append(entry)

    output = [{
        "as_source": as_source,
        "as_destination": as_destination
    }]

    return output

import time
def summarize_toon_with_grok(toon_output: str, flow_output: str, page_name: str,image_name: str) -> str:

    SYSTEM_PROMPT = """
You are a UI/UX interpretation assistant.

You will be given a cleaned Figma JSON (toon format) representing a single image/screen of a Figma page in Figma Design.
Your task is to analyze and describe all UI elements and interactions in a clear, structured summary format.
This is the image name :{image_name} it belongs
and this is a page_name : {page_name} from figma

Core Responsibilities
1. Dropdown-focused analysis (HIGH PRIORITY)
    For each dropdown element:
        State the name/label of the dropdown
        Describe what happens when the dropdown is clicked
        List all options that appear
        If selecting an option triggers navigation or action, describe it clearly

2. Hover interaction handling
    Identify if hovermenu states exist
    if hovermenu is present, describe:
        give the options that appear on hover
        do not miss any of the hovermenu 

3. Click & navigation flow
    Describe what happens when an element is clicked
    Clearly explain:
        Which element is clicked
        What action occurs
        Which destination frame/screen it navigates to
    If no navigation occurs, state the resulting UI change instead

4. Interaction flow summary
    here from the json flow of pages u will get the flow of pages connection it will contain as_source and as_destination
    {flow_output}
    Use this to accurately describe the navigation flow between different screens
    -1. from navigate to i.e as_source (from_screen to destinationFrame)
    -2. navigated from i.e as_destination (from_screen to destinationFrame)

Output Format Requirements
    Output must be in summary format
    Do not include raw JSON
    Do not assume behavior not present in the JSON
    Be precise, concise, and UI-focused

note : do not mention shape elements like rectangles, circles, lines etc.
        do not mention any element which is not interactive in nature.
        do not give repeated information.
        in one if u have give information about an element then do not give information about the same element again in another section.
        make sure the summary is small and concise.
do not give the summary big in size.
"""
    user_prompt = f"""Here is the page name to which this image belongs to:{page_name}\n\nHere is the name of the image:{image_name}\n\nHere is the TOON data:\n\n{toon_output}\n\nHere is the json flow data:\n\n{flow_output}"""

    max_retries = 2
    retry_delay = 2
    for attempt in range(max_retries + 1):
        try:
            response = groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=65000,
            )

            if response.usage:
                token_usage["prompt_tokens"] += response.usage.prompt_tokens
                token_usage["completion_tokens"] += response.usage.completion_tokens
                token_usage["total_tokens"] += response.usage.total_tokens

            return response.choices[0].message.content
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}). "
                    f"Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                f"Request failed after {max_retries + 1} attempts.")
    
def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def analyze_ui_image(image_path: str, ui_summary: str, page_name: str, image_name: str, flow_frame_node: str):
    """Send image + UI summary to Groq Maverick and get a concise narrative QA summary"""

    image_b64 = encode_image(image_path)
    print("encoding done")

    prompt = f"""
You are a Senior QA Analyst. You must describe this UI screen as a SHORT STORY — a natural, flowing narrative a QA tester could read once and fully understand the screen. Not bullet points, not a report. Tell it like you're walking someone through the screen in one breath.

You must combine TWO sources of truth:
SOURCE A — THE IMAGE (visual layout, visible elements, text)
SOURCE B — UI SUMMARY (Figma metadata: dropdown options, hover states, click actions, navigation)

UI SUMMARY (Source B):
{ui_summary}

FLOW NODE DATA (source/destination frames): {flow_frame_node}

MERGE RULE: The image shows what's visually present but not hidden states. The UI Summary reveals hidden behavior (dropdown options, hover states) the image can't show. Weave both into one coherent narrative — do not describe them separately or say "according to the summary."

SPECIAL CASE
If this is a splash screen (first screen shown on app open, typically just a logo), output only:
"SPLASH SCREEN — {page_name}"
and stop.

OTHERWISE, write ONE short narrative with this shape:

Start with: PAGE: {page_name} | IMAGE: {image_name} | FEATURE: <2-5 word feature name>

Then, in story form, cover in this order focus on flow(still as flowing prose, not headers):
1. Where the user arrives from and where this screen can take them next (use the flow node data — name the source/destination frame naturally, e.g. "arriving here after tapping Login on the Home screen").
2. Every element on the screen, introduced as the user's eye would naturally move over it (top to bottom) — every input field, button, link, checkbox, dropdown, label, and error/helper text must be named individually with its state (e.g. "the Password field, which is empty by default and masks input") — do not skip any element for the sake of brevity, but describe each in one short clause, not a paragraph.
3. Dropdown options and hover behaviors woven in naturally at the point where that element is mentioned (e.g. "hovering over the profile icon reveals a menu with Logout and Settings").
4. What happens when the user interacts — key actions and system responses (validation, redirect, error states) — told as a brief sequence of events, not a full step-by-step walkthrough.
Note : do not repeat the ui elements name right it step by step like a flow.
HARD RULES:
- One paragraph, at most.
-Never Mention the backgroup ,color and all
- Every element must still be individually named somewhere in the story — compress the SENTENCES, not the ELEMENT COVERAGE.
- No assumptions unsupported by either source.
- No headers, no bullets, no lists — pure narrative prose after the PAGE/IMAGE/FEATURE line.
- Do not merge unrelated features into this story.
- Plain text only.
"""
    max_retries = 2
    retry_delay = 2
    for attempt in range(max_retries + 1):
        try:
            response = groq_client.chat.completions.create(
                model=MODEL_NAME_1,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.2,
                max_tokens=500
            )
            if response.usage:
                token_usage["prompt_tokens"] += response.usage.prompt_tokens
                token_usage["completion_tokens"] += response.usage.completion_tokens
                token_usage["total_tokens"] += response.usage.total_tokens

            return response.choices[0].message.content
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"Request failed (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}. Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"Request failed after {max_retries + 1} attempts."
                )

def ensure_collection(collection_name,qdrant_client):
    existing = [c.name for c in qdrant_client.get_collections().collections]
    if collection_name not in existing:
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=VECTOR_SIZE,
                distance=qmodels.Distance.COSINE
            )
        )

def get_next_chunk_id(collection_name,qdrant_client):
    points, _ = qdrant_client.scroll(
        collection_name=collection_name,
        limit=10000,
        with_payload=True
    )

    max_chunk_id = 0
    for point in points:
        payload = point.payload or {}
        if "chunk_id" in payload:
            try:
                cid = int(payload["chunk_id"])
                max_chunk_id = max(max_chunk_id, cid)
            except Exception:
                pass

    return max_chunk_id + 1


def store_image_story(collection_name,page_name,image_name,story_chunks,instance_name,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_story called")
    for attempt in range(max_retries + 1):
        try:
            print("Type of story_chunks:", type(story_chunks))
            print("story_chunks length:", len(story_chunks))

            points = []
            document_id = str(uuid.uuid4())
            next_chunk_id = get_next_chunk_id(collection_name,qdrant_client)

            for i, chunk in enumerate(story_chunks, start=1):
                vector = embeddings.embed_query(chunk)
                payload = {
                    "document_id": document_id,
                    "page_name": page_name,
                    "image_name": image_name,
                    "page_image": f"This {image_name} belongs to this {page_name}",
                    "text": chunk,
                    "source": instance_name,
                    "mongo_id":mongo_id,
                    "chunk_id": next_chunk_id + i - 1
                }

                points.append(
                    qmodels.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload=payload
                    )
                )

            qdrant_client.upsert(collection_name=collection_name, points=points)
            return
        
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"store_story failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts"
                )
        
def store_imagename_flowname_flow(collection_name, page_name, flow_text, instance_name,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_flow called")
    for attempt in range(max_retries + 1):
        try:
            points = []
            document_id = str(uuid.uuid4())
            # next_chunk_id = get_next_chunk_id(collection_name)

            vector = embeddings.embed_query(flow_text)
            payload = {
                "document_id": document_id,
                "FlowName": page_name,            
                "source": instance_name,
                "FlowSummary":flow_text,
                "mongo_id":mongo_id
            }

            points.append(
                qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload
                )
            )

        
            qdrant_client.upsert(
                collection_name=collection_name,
                points=points
            )
            return

        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"store_flow failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts"
                ) 
        
def extract_node_id_from_image(image_name: str) -> str:
    parts = image_name.split("_")
    if len(parts) < 2:
        return None
    return f"{parts[0]}:{parts[1]}"

def find_frame_by_id(node, target_id):
    if isinstance(node, dict):
        if node.get("id") == target_id:
            return node

        for child in node.get("children", []):
            result = find_frame_by_id(child, target_id)
            if result:
                return result

    elif isinstance(node, list):
        for item in node:
            result = find_frame_by_id(item, target_id)
            if result:
                return result

    return None

processed_images = []
import json
def Generate_User_Story(output_dir: str, collection_name: str, instance_name: str,embeddings,qdrant_client,mongo_id):
    try:
        logger.info(f"Initilizing the qdrant collection")
        ensure_collection(collection_name,qdrant_client)
    except Exception as e:
        logger.exception(f"Error in Qdrant initilization : {e}")
        raise
 
    for folder in os.listdir(output_dir):       
        folder_path = os.path.join(output_dir, folder)

        if not os.path.isdir(folder_path):
            continue  
        print("this is folder_path:",folder_path) 

        files = os.listdir(folder_path)
        print("this is file:",files)

        json_files = [f for f in files if f.lower().endswith(".json")]
        
        if not json_files:
            continue
        
        page_name = os.path.splitext(json_files[0])[0]

        json_path = os.path.join(folder_path, json_files[0])
        with open(json_path, "r", encoding="utf-8") as f:
            page_json = json.load(f)

        for file in files:
            if not file.lower().endswith(".png"):
                continue
            raw_image_name = os.path.splitext(file)[0]

            node_id = extract_node_id_from_image(raw_image_name)
            if not node_id:
                print(f"❌ Could not extract node_id from {raw_image_name}")
                continue

            frame_node = find_frame_by_id(page_json, node_id)
            if not frame_node:
                print(f"❌ No frame found for node_id {node_id}")
                continue

            image_path = os.path.join(folder_path, file)
            image_name = frame_node.get("name")
            
            processed_images.append({
                "page_name": page_name,
                "image_name": image_name
            })
            print(f"\n🖼 Image: {image_name} | Page: {page_name}")                                  
            print(f"✅ Frame JSON found for image {image_name}")
             
            flow_frame_node = create_prototype_flow(image_name, page_json)
            if not flow_frame_node:
                print(f"❌ No frame found for image {image_name}")
                continue
            try:
                toon_output = encode(frame_node)
                print("✅ Toon encoding successful.")
                try:
                    logger.info(f"Summarizing the json of page")   
                    summary = summarize_toon_with_grok(toon_output,flow_frame_node,page_name,image_name)
                    if not summary:
                        logger.error(f"Failed to generate summary for {image_name}")
                        continue
                except Exception as e:
                    logger.exception(f"Error for summarizing the json of page : {e}")
                    
                try:
                    logger.info(f"Generating the user story for the image")
                    user_story = analyze_ui_image(
                        image_path=image_path,
                        ui_summary=summary,
                        page_name=page_name,
                        image_name=image_name,
                        flow_frame_node=flow_frame_node
                    )
                    if not user_story:
                        logger.error(f"Failed to generate user story for {image_name}")
                        continue
                except Exception as e:
                    logger.exception(f"Error for generating the user story for the image : {e}")
                    continue
                    
                # print("👍"*10)
                # print("this is image:",image_name)
                # print("this is it summar:",user_story)
                # print("👍"*10)
                clean_image_name = image_name.strip()
                
                print("HERE WE ARE STORING IMAGE USER STORY")
                store_image_story(collection_name, page_name, clean_image_name, [user_story], instance_name,embeddings,qdrant_client,mongo_id)
                
                # storing summary generated by versatile in folder
                # summary_path = os.path.join(folder_path, f"{raw_image_name}_summary.txt")
                # with open(summary_path, "w", encoding="utf-8") as f:
                #     f.write(summary)
                    
                # storing user story of image by maverick model in folder
                # user_story_path = os.path.join(folder_path, f"qwen_model_{raw_image_name}_user_story.txt")
                # with open(user_story_path, "w", encoding="utf-8") as f:
                #     f.write(user_story)
                
            except Exception as e:
                print(f"❌ Error processing {image_name}: {e}")
            
        flow_text = None
        for file in files:
            if file.lower().endswith(".txt") and file.startswith("summary_"):
                flow_path = os.path.join(folder_path, file)
                with open(flow_path, "r", encoding="utf-8") as f:
                    flow_text = f.read().strip()
                    
        if flow_text:
            #storing the page flow in qdrant
            print("HERE WERE ARE STORING IMAGE FLOWNAME FLOW")
            store_imagename_flowname_flow(collection_name, page_name, flow_text, instance_name,embeddings,qdrant_client,mongo_id) 
        else:
            print(f"No flow text found for page {page_name}")    

    return {
        "processed_images": processed_images,
        "token_usage": token_usage
    }


      
