import json
import os
from typing import Dict, List, Optional, Set
import os
from groq import Groq
from dotenv import load_dotenv
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
import json
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
VECTOR_SIZE = 768
import time
from qdrant_client.http.exceptions import UnexpectedResponse
from fastapi import HTTPException
# QDRANT_URL = "http://127.0.0.1:6333"
# embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")

# qdrant = QdrantClient(
#     url="http://103.182.210.230:30455",
#     timeout=60
# )
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    force=True   
)
logger = logging.getLogger(__name__)
token_usage = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
}

def load_figma_json(output_dir: str, file_id: str) -> Dict:
    file_path = os.path.join(output_dir, f"{file_id}.json")
    print("Loading Figma JSON:", file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# CANVAS (PAGE) RESOLUTION
# ============================================================
def get_canvas_by_id(figma_data: Dict, page_id: str) -> Dict:
    if "document" in figma_data:
        for child in figma_data["document"].get("children", []):
            if child.get("type") == "CANVAS" and child.get("id") == page_id:
                return child

    #this codition will pass
    if "nodes" in figma_data:
        node = figma_data["nodes"].get(page_id)
        if node and node.get("document", {}).get("type") == "CANVAS":
            return node["document"]

    raise ValueError(f"CANVAS with id {page_id} not found")



def get_main_frames(page: Dict) -> List[Dict]:
    return [
        n for n in page.get("children", [])
        if n.get("type") == "FRAME" and n.get("visible", True)
    ]

def order_frames_visually(frames: List[Dict]) -> List[Dict]:
    def sort_key(frame):
        bbox = frame.get("absoluteBoundingBox", {})
        return (bbox.get("y", 0), bbox.get("x", 0))
    return sorted(frames, key=sort_key)


def extract_label_and_type(node: Dict):
    if node.get("type") == "TEXT":
        return node.get("characters"), "TEXT", None

    name = (node.get("name") or "").lower()

    if name.startswith(("icon", "vector", "rectangle", "frame")):
        return "ICON", "ICON", node.get("absoluteBoundingBox")

    for child in node.get("children", []):
        label, t, _ = extract_label_and_type(child)
        if t == "TEXT":
            return label, "TEXT", None

    if node.get("children"):
        return "ICON", "ICON", node.get("absoluteBoundingBox")

    return node.get("name"), "COMPONENT", None


# ============================================================
# POSITION LOGIC
# ============================================================

def collect_text_nodes(node: Dict, texts: List[Dict]):
    if node.get("type") == "TEXT" and node.get("characters"):
        texts.append({
            "text": node["characters"],
            "bbox": node.get("absoluteBoundingBox")
        })
    for child in node.get("children", []):
        collect_text_nodes(child, texts)

def collect_interactions(
    page: Dict,
    frames: Dict[str, Dict],
    current_frame_id: Optional[str] = None,
    parent_type: Optional[str] = None
):
    if page.get("type") == "FRAME" and parent_type == "CANVAS":
        current_frame_id = page["id"]

    for interaction in page.get("interactions", []) or []:
        if not isinstance(interaction, dict):
            continue
        trigger = (interaction.get("trigger") or {}).get("type")

        for action in interaction.get("actions") or []:
            if not isinstance(action, dict):
                continue
            destination = action.get("destinationId")
            if not destination or current_frame_id not in frames:
                continue

            label, interaction_type, bbox = extract_label_and_type(page)

            frames[current_frame_id]["interactions"].append({
                "node_id": page.get("id"),
                "type": interaction_type,
                "component": page.get("name"),
                "label": label,
                "trigger": trigger,
                "navigation": action.get("navigation"),
                "destination_id": destination,
                "absoluteBoundingBox": bbox
            })

    for child in page.get("children", []):
        collect_interactions(child, frames, current_frame_id, page.get("type"))


def build_flow_from_start(
    start_id: str,
    frames: Dict[str, Dict],
    frame_name_map: Dict[str, str],
    node_map
) -> Dict[str, object]:

    def resolve_label(interaction: Dict, node_map: Dict[str, Dict]) -> str:
        GENERIC = {"group", "frame", "icon", "vector", "rectangle", "ellipse"}

        def clean(v):
            return v.strip() if isinstance(v, str) else None

        def is_valid(name):
            return name and name.lower() not in GENERIC and not name.startswith("fi_")

        def find_child_label(node):
            text_candidates = []
            other_candidates = []

            for child in node.get("children", []):
                name = clean(child.get("name"))
                if not name:
                    continue

                child_type = child.get("type", "")

                # PRIORITY 1 — text nodes
                if child_type == "TEXT":
                    text_candidates.append(name)

                # PRIORITY 2 — meaningful non-shape names
                elif child_type not in {"VECTOR", "ELLIPSE", "RECTANGLE", "LINE"}:
                    other_candidates.append(name)

                # recursive search
                nested = find_child_label(child)
                if nested:
                    text_candidates.append(nested)

            if text_candidates:
                return text_candidates[0]

            if other_candidates:
                return other_candidates[0]

            return None


        node_id = interaction.get("node_id")
        node = node_map.get(node_id)

        # 1 explicit label
        label = clean(interaction.get("label"))
        if is_valid(label):
            return label

        # 2 node name
        name = clean(interaction.get("name"))
        if is_valid(name):
            return name

        # 3 search children
        if node:
            found = find_child_label(node)
            if found:
                return found

        # 4 component name
        comp = clean(interaction.get("component"))
        if is_valid(comp):
            return comp

        return "Icon"

    visited: Set[str] = set()
    stack = [start_id]

    sentences: List[str] = []
    frame_names: Set[str] = set()
    seen_sentences: Set[str] = set()  # prevents duplicates

    while stack:
        current = stack.pop()

        if current in visited:
            continue
        visited.add(current)

        current_frame = frames.get(current)
        if not current_frame:
            continue

        source_name = current_frame.get("name", "UNKNOWN")

        for interaction in current_frame.get("interactions", []):
            dest = interaction.get("destination_id")
            dest_name = frame_name_map.get(dest, "UNKNOWN")

            frame_names.update(filter(None, [source_name, dest_name]))

            label = resolve_label(interaction, node_map)


            trigger = interaction.get("trigger", "ACTION")
            navigation = interaction.get("navigation", "NAVIGATE")
            component = interaction.get("component", "UNKNOWN")

            sentence = (
                f'From {source_name}, by {trigger} on "{label}" '
                f'(component: {component}, label: {label}), '
                f'the user {navigation} to {dest_name}.'
            )

            # avoid duplicates
            if sentence not in seen_sentences:
                sentences.append(sentence)
                seen_sentences.add(sentence)

            # DFS traversal
            if dest in frames and dest not in visited:
                stack.append(dest)

    return {
        "sentences": sentences,
        "frame_names": frame_names
    }

single_flow_data="flow_data.json"
# ============================================================
# EXTRACT FLOWS FROM PAGE
# ============================================================
def extract_flow(page: Dict, node_map: Dict) -> Dict[str, Dict]:
    ordered_frames = order_frames_visually(get_main_frames(page))

    frames = {}
    for f in ordered_frames:
        texts: List[Dict] = []
        collect_text_nodes(f, texts)
        frames[f["id"]] = {
            "name": f.get("name"),
            "bbox": f.get("absoluteBoundingBox"),
            "interactions": [],
            "texts": texts
        }

    frame_name_map = {f["id"]: f.get("name") for f in ordered_frames}
    collect_interactions(page, frames)

    flows = {}
    flow_starting_points = page.get("flowStartingPoints", [])

    if flow_starting_points:
        for entry in flow_starting_points:
            start_id = entry.get("nodeId")
            flow_name = entry.get("name", start_id)
            if start_id in frames:
                flows[flow_name] = build_flow_from_start(
                    start_id, frames, frame_name_map, node_map
                )
    else:
        logger.info("No flowStartingPoints found — falling back to heuristic detection")

        # frames that are never a destination = likely entry points
        destination_ids = {
            interaction.get("destination_id")
            for f in frames.values()
            for interaction in f["interactions"]
            if interaction.get("destination_id")
        }
        candidate_starts = [fid for fid in frames if fid not in destination_ids]

        # fully cyclic graph or no interactions at all -> just use the first frame visually
        if not candidate_starts and ordered_frames:
            candidate_starts = [ordered_frames[0]["id"]]

        for start_id in candidate_starts:
            flow_name = frames[start_id]["name"] or start_id
            result = build_flow_from_start(start_id, frames, frame_name_map, node_map)
            if result["sentences"]:          # only keep it if it actually produced navigation
                flows[flow_name] = result

        # last resort: page has frames but zero interactions anywhere —
        # still emit something so image names / page summary aren't skipped downstream
        if not flows and frames:
            flows["Static_Page_Flow"] = {
                "sentences": [
                    f'The page contains screen "{f["name"]}" with no defined navigation interactions.'
                    for f in frames.values() if f.get("name")
                ],
                "frame_names": {f["name"] for f in frames.values() if f.get("name")}
            }

    print("✌️"*10)
    print(flows)
    print("✌️"*10)
    return flows
    
def generate_flow_summary(flow_name, sentences, frame_names):
    flow_json_str = json.dumps(sentences, indent=2)
    frame_str = json.dumps(frame_names, indent=2)
    prompt =f"""You are a senior UX navigation analyst specializing in reconstructing user flows from raw navigation logs.
Your job is to transform raw navigation events into a structured narrative summary that accurately describes how a user moves through the product interface.
You are provided 2 things:
flow_name:{flow_name}
flow_json :{flow_json_str}
The provided data represents navigation actions extracted from a Figma prototype.

CRITICAL OBJECTIVE:
Reconstruct the complete navigation flows while preserving every screen, transition, and interaction exactly as provided.

**IMPORTANT** Here properly give here on which page(page_name) by clicking on which button,link,text.. user is navigated to which page(page_name)
Note: Keep the page_name as it is do not change
IMPORTANT RULES:

1. Flow Reconstruction
- Identify logical navigation chains from the events.
- A flow begins at a natural entry screen and ends when a terminal screen or loop occurs.
- Multiple independent flows may exist inside the same dataset.

2. Multiple Flows Handling (VERY IMPORTANT)
- If multiple distinct flows exist, you MUST separate them.
- Complete the full navigation of the first flow from start to finish.
- Only after completing the first flow should you begin describing the next flow.
- Never mix steps from different flows.

3. Navigation Integrity
- Every screen transition must be preserved.
- Do not remove any screen that appears in the data.
- Do not skip intermediate screens.

4. UI Elements
- Preserve all button names, icons, components, and feature names exactly as written.
- Do not rename or paraphrase screen names.
- Do not modify image or component identifiers.

5. Deduplication
- If the same transition appears multiple times, consolidate it logically.
- Avoid repeating identical transitions unnecessarily.

6. Writing Style
- Write in natural readable paragraph format.
- Do not use bullet points.
- Do not number steps.
- Do not add explanations.
- Do not add headings.

7. Content Limits
- The output must remain concise but complete.
- Do not omit any navigation possibility.
- Do not invent any new transitions.

8. Strict Accuracy
- Only use the information present in the input.
- Do not assume behavior that is not explicitly described.

**IMPORTANT** : If the partricular flow already exist avoid duplicate flows in same flow
FINAL OUTPUT REQUIREMENTS:
Produce a compact narrative describing each full navigation flow sequentially.
Each flow must be described completely before the next flow begins.

This are the image name {frame_str} do not change it 
The result should read like a technical UX documentation paragraph describing the navigation behavior of the interface.
"""
    max_retries = 2
    retry_delay = 2
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": "You are a UX flow documentation assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=65000
            )
            if response.usage:
                token_usage["prompt_tokens"] += response.usage.prompt_tokens
                token_usage["completion_tokens"] += response.usage.completion_tokens
                token_usage["total_tokens"] += response.usage.total_tokens
            content = response.choices[0].message.content
            print("this---------content------",content)
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

def all_flow_summary(all_summary):

    system_prompt = """You are a senior UX flow architect specializing in reconstructing a single, coherent end-to-end user journey from multiple individual page-level flow summaries.

INPUT CONTEXT:
You will receive several flow summaries, each describing navigation within one Figma page. These summaries may contain overlapping transitions, partial flows, or unrelated fragments.

YOUR TASK:
Combine these individual page flows into ONE single, connected, end-to-end user journey — the longest and most logically complete path through the product, from initial entry to final completion/exit.

STRICT RULES:

1. Single Flow Only
   - Output exactly ONE continuous flow. Do not output multiple separate flows.
   - If multiple candidate flows exist, select and connect the ones that form the longest coherent journey. Discard fragments that don't connect to this main journey.

2. No Invention
   - Only use transitions, screens, and actions explicitly present in the provided summaries.
   - Do not infer, assume, or imagine any transition, screen, or button that isn't stated.
   - If a transition is marked UNKNOWN or ambiguous, exclude it rather than guessing.

3. One Action Per Screen
   - Each screen in the final flow must show exactly ONE navigation action (one click/tap leading to the next screen).
   - Do not describe multiple possible actions from the same screen (e.g. "click X, or alternatively click Y").

4. No Duplicates
   - Do not repeat the same screen-to-screen transition more than once.
   - If the same transition appears in multiple input summaries, include it only once in the output.

5. Flow Boundaries
   - Start the journey at the natural entry point (app launch, login, or landing screen — whichever is present in the data).
   - End the journey at a natural terminal point (confirmation, closing screen, or last reachable screen in the connected chain).

6. Preserve Exact Names
   - Keep all page names, button names, and labels exactly as written in the input. Do not paraphrase or rename them.

7. Writing Style
   - Write as a single flowing paragraph of technical UX documentation.
   - No bullet points, no numbering, no headings, no extra commentary.
   - State clearly: "On [page_name], clicking [element_name] navigates to [page_name]" style phrasing, chained sequentially.

OUTPUT:
Return only the final single consolidated end-to-end flow paragraph. Nothing else — no preamble, no explanation of your reasoning."""

    user_prompt = f"""Below are individual page-level navigation flow summaries extracted from a Figma prototype. Reconstruct the single longest end-to-end user journey from these, following the system rules exactly.

FLOW SUMMARIES:
{all_summary}"""

    max_retries = 2
    retry_delay = 2
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=65000,
            )

            if response.usage:
                token_usage["prompt_tokens"] += response.usage.prompt_tokens
                token_usage["completion_tokens"] += response.usage.completion_tokens
                token_usage["total_tokens"] += response.usage.total_tokens
            print("////////////////",response.choices[0].message.content)
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

def convert_sets(obj):
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: convert_sets(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets(i) for i in obj]
    else:
        return obj
    

from collections import Counter
import re

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


import uuid

def store_flow_individual(collection_name, page_name, individual_flow_summary, instance_name,flow_name,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_flow called")
    for attempt in range(max_retries + 1):
        try:
    
            print("Summary length:", len(individual_flow_summary))
            print("Flow name:", flow_name)

            points = []
            document_id = str(uuid.uuid4())
            # next_chunk_id = get_next_chunk_id(collection_name)

            vector = embeddings.embed_query(individual_flow_summary)
            print("Vector length:", len(vector))
            payload = {
                "document_id": document_id,
                "individual_flow_page_name": page_name,
                "individual_flow": flow_name,            
                "source": instance_name,
                "mongo_id":mongo_id,
                "Individual_FlowSummary":individual_flow_summary
            }
            print("Payload size:", len(str(payload)))
            print(payload)
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
                    f"store_flow failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts"
                )
        

def store_end_to_end(collection_name, page_name, entier_page_summary, instance_name,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_flow called")
    for attempt in range(max_retries + 1):
        try:
            points = []
            document_id = str(uuid.uuid4())
            # next_chunk_id = get_next_chunk_id(collection_name)

            vector = embeddings.embed_query(entier_page_summary)
            payload = {
                "document_id": document_id,
                "entier_page_summary_page_name": page_name,
                "entier_page_summary": entier_page_summary,            
                "source": instance_name, 
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
                    f"store_end_to_end failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts"
                )

        

# here we are storing qdrant the images name in the page
def end_to_end_image(collection_name, page_name,individual_page_image, instance_name,embeddings,qdrant_client,mongo_id):
    max_retries = 2
    retry_delay = 3
    print("🟢 store_flow called")
    for attempt in range(max_retries + 1):
        try:
            points = []
            document_id = str(uuid.uuid4())
            # next_chunk_id = get_next_chunk_id(collection_name)
            individual_page_image_list = sorted(list(individual_page_image))
            vector = embeddings.embed_query(" ".join(individual_page_image_list))
            payload = {
                "document_id": document_id,
                "individual_page_name_for_images": page_name,
                "individual_page_image": individual_page_image_list,            
                "source": instance_name, 
                "mongo_id":mongo_id,
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
                    f"end_to_end_image failed "
                    f"(attempt {attempt + 1}/{max_retries + 1}): "
                    f"{type(e).__name__}: {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.exception(
                    f"store_story failed after {max_retries + 1} attempts"
                )
        

def flow_of_pages(OUTPUT_DIR: str, file_id: str, page_ids: List[str],collection_name,instance_name,embeddings,qdrant_client,mongo_id):

    try:
        ensure_collection(collection_name,qdrant_client)
    except Exception as e:
        logger.exception(f"Error for qdrant initialization : {e}")
        raise

    figma_data = load_figma_json(OUTPUT_DIR, file_id)
    file_name=figma_data.get('name')
    print(file_name)
    for page_id in page_ids:
        page = get_canvas_by_id(figma_data, page_id)
        print(f"\nProcessing page: {page.get('name')}\n")

        page_name = page.get("name", "UNKNOWN_PAGE")
        print("Processing page:", page_name)

        node_map = {}
        def index_nodes(node):
            node_map[node["id"]] = node
            for c in node.get("children", []):
                index_nodes(c)
        index_nodes(page)

        print("extract the flow started")
        flows = extract_flow(page,node_map)
        flows = convert_sets(flows)
        
        page_dir = os.path.join(OUTPUT_DIR, page_name)
        #if does not exist create it
        os.makedirs(page_dir, exist_ok=True)

        #there create one file
        json_flow_summary = os.path.join(page_dir, f"summary_{page_name}.txt")

        global_frames: Set[str] = set()
        flows_json: Dict[str, List[str]] = {}

        for flow_name, data in flows.items():
            flows_json[flow_name] = {
                "sentences": data["sentences"],
                "frame_names": list(data["frame_names"])
            }
            global_frames.update(data["frame_names"])
            
        # this 2 we are storing a json
        final_json = {
            "flows": flows_json,
            "frame_names": (list(global_frames))
        }
        print(global_frames)
        print(len(global_frames))
        with open(json_flow_summary, "w", encoding="utf-8") as f:
                f.write(f"This are the images name for all flows")
                f.write(str(global_frames)+ "\n\n")

        #this is storing the image 
        # names
        try:
            logger.info(f"Storing the end to end images name")
            print("HERE WE ARE STORING THE IMAGE NAMES....")
            end_to_end_image(collection_name=collection_name, page_name=page_name, individual_page_image=global_frames, instance_name=instance_name,embeddings=embeddings,qdrant_client=qdrant_client,mongo_id=mongo_id)
        except Exception as e:
            logger.exception(f"Error in Qdrant image name storing : {e}")
            raise
        all_flow_name=[]
        for flow_name in final_json["flows"].keys():
            all_flow_name.append(flow_name)

        #now we are storing the flow name in the page
        with open(json_flow_summary, "a", encoding="utf-8") as f:
            f.write(f"This are the flow name for the page")
            f.write(str(all_flow_name)+ "\n\n")

        #created empty list
        all_summary=""
        all_summary += "This are the images name for all flows"
        all_summary += str(global_frames) + "\n\n"
        all_summary += "This are the flow name for all flows"
        all_summary += str(all_flow_name) + "\n\n"

        for flow_name, flow_data in final_json["flows"].items():
            sentences = flow_data["sentences"]
            frame_names = flow_data["frame_names"]
            try:
                logger.info(f"Generating the individual flow summary by llm")
                summary = generate_flow_summary(flow_name, sentences, frame_names)
                if not summary:
                    logger.error(f"Failed to generate summary for flow {flow_name}")
                    continue
                summary = summary.replace("\\n", "\n").replace("\\t", "\t")
                summary = re.sub(r'\n\s*\n+', '\n', summary).strip()
            except Exception as e:
                logger.exception(f"Error for get the individual summary: {e}")

            with open(json_flow_summary, "a", encoding="utf-8") as f:
                f.write(f"\n--- {flow_name} FLOW ---\n")
                f.write(summary + "\n\n")
            all_summary += f"\n--- {flow_name} FLOW ---\n"
            all_summary += summary + "\n\n"
            #individual flow summary
            try:
                logger.info(f"Storing individual flow summary in Qdrant")
                print("HERE WE HAVE STORED INDIVIDUAL FLOW")
                store_flow_individual(collection_name=collection_name, page_name=page_name, individual_flow_summary=summary, instance_name=instance_name,flow_name=flow_name,embeddings=embeddings,qdrant_client=qdrant_client,mongo_id=mongo_id)
            except Exception as e:
                logger.exception(f"Error in Qdrant individual flow summary : {e}")
                raise
            print(f"✅ Appended summary for {flow_name}")
        try:
            logger.info(f"Generating summary for eniter page e2e")
            end_to_end_flow=all_flow_summary(all_summary)
            if not end_to_end_flow:
                logger.error(f"Failed to generate end-to-end flow for {page_name}")
                continue

        except Exception as e:
            logger.exception(f"Error for generating individual summary by llm : {e}")
            raise
        try:
            print("HERE WE ARE STORING E2E FLOW")
            store_end_to_end(collection_name=collection_name, page_name=page_name,entier_page_summary=end_to_end_flow, instance_name=instance_name,embeddings=embeddings,qdrant_client=qdrant_client,mongo_id=mongo_id)
        except Exception as e:
            logger.exception(f"Error in Qdrant entier page summary e2e: {e}")
            raise
        print(f"✅ Appended all flow summary for {page_name}")

    return token_usage


from qdrant_client.models import Distance, VectorParams,Filter, FieldCondition, MatchValue
def delete_points_by_source_replace(instance_name,collection_name,qdrant_client,mongo_id):

    try:
        # Check if collection exists
        collections = qdrant_client.get_collections().collections
        existing = [c.name for c in collections]

        if collection_name not in existing:
            return {
                "responseCode": 404,
                "responseObject": None,
                "message": f"Collection '{collection_name}' does not exist"
            }

        # Delete points where payload["source"] == instance_name
        delete_filter = Filter(
            must=[
                FieldCondition(
                    key="mongo_id",
                    match=MatchValue(value=mongo_id)
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
                "deleted_source": instance_name
            },
            "message": f"{instance_name} deleted successfully."
        }

    except Exception:
        raise RuntimeError(
            f"Failed to delete source '{instance_name}' from collection '{collection_name}'"
        )


from qdrant_client.models import Filter, FieldCondition, MatchValue


def update_source_by_mongo_id(collection_name,qdrant_client,mongo_id,new_instance_name):
    try:
        # Check if collection exists
        collections = qdrant_client.get_collections().collections
        existing = [c.name for c in collections]

        if collection_name not in existing:
            return {
                "responseCode": 404,
                "responseObject": None,
                "message": f"Collection '{collection_name}' does not exist"
            }

        # Filter points by mongo_id
        update_filter = Filter(
            must=[
                FieldCondition(
                    key="mongo_id",
                    match=MatchValue(value=mongo_id)
                )
            ]
        )

        points, _ = qdrant_client.scroll(
            collection_name=collection_name,
            scroll_filter=update_filter,
            with_payload=True,
            with_vectors=False,
            limit=1
        )

        if not points:
            return {
                "responseCode": 404,
                "responseObject": None,
                "message": f"No points found for mongo_id '{mongo_id}'"
            }
        previous_source = points[0].payload.get("source")
        
        # Update payload
        qdrant_client.set_payload(
            collection_name=collection_name,
            payload={
                "source": new_instance_name
            },
            points=update_filter
        )
        
        return previous_source

    except Exception as e:
        raise RuntimeError(
            f"Failed to update source for mongo_id '{mongo_id}' in collection '{collection_name}'. Error: {str(e)}"
        )