
import os
import json
import re

UNWANTED_KEYS = {
    'background', 'fills', 'strokes', 'backgroundColor',
    'cornerRadius', 'cornerSmoothing',
    'strokeWeight', 'strokeAlign', 'opacity', 'blendMode',
    'styles', 'gradientStops', 'gradientHandlePositions',
    'itemSpacing',
    'paddingLeft', 'paddingRight', 'paddingTop', 'paddingBottom',
    'absoluteBoundingBox', 'absoluteRenderBounds', 'constraints',
    'layoutAlign', 'layoutGrow', 'layoutMode',
    'layoutSizingHorizontal', 'layoutSizingVertical',
    'preserveRatio', 'clipsContent',
    'primaryAxisAlignItems', 'counterAxisAlignItems',
    'primaryAxisSizingMode', 'counterAxisSizingMode',
    'layoutWrap',
    'fontFamily', 'fontWeight', 'fontSize', 'lineHeight',
    'letterSpacing', 'paragraphSpacing',
    'textAlignHorizontal', 'textAlignVertical',
    'textAutoResize', 'textDecoration', 'textCase',
    'characterStyleOverrides', 'styleOverrideTable',
    'style', 'overriddenFields', 'effects'
}

def find_frame(file_json, page_id):
    if isinstance(file_json, dict):
        if (file_json.get("type") == "CANVAS" and (file_json.get("id") == page_id or file_json.get("name") == page_id)):     
            return file_json
        for v in file_json.values():
            found = find_frame(v, page_id)
            if found:
                return found     
    elif isinstance(file_json, list):
        for item in file_json:
            found = find_frame(item, page_id)
            if found:
                return found
    return None

def build_frame_map(page_json, frame_map=None):
    if frame_map is None: 
        frame_map = {}
    if isinstance(page_json, dict):
        if page_json.get("type") == "FRAME" and "id" in page_json and "name" in page_json:
            frame_map[page_json["id"]] = {"name": page_json["name"]}
        for v in page_json.values():
            build_frame_map(v, frame_map)

    elif isinstance(page_json, list):
        for i in page_json:
            build_frame_map(i, frame_map)
    return frame_map


def build_node_index(page_json, node_index=None):
    if node_index is None:
        node_index = {}
    if isinstance(page_json, dict):
        node_id = page_json.get("id")
        if node_id:
            node_index[node_id] = page_json
        for v in page_json.values():
            build_node_index(v, node_index)
    elif isinstance(page_json, list):
        for i in page_json:
            build_node_index(i, node_index)
    return node_index


def extract_page_frame_header(node):
    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type"),
    }

def sanitize(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", name) 
    name = name.strip().rstrip(".")            
    return name

def get_children(node):
    return node.get("children", []) if isinstance(node, dict) else []

def collect_text_nodes(node, texts=None):
    if texts is None:
        texts = []
    if isinstance(node, dict):
        if node.get("type") == "TEXT":
            txt = node.get("characters", "").strip()
            if txt:
                texts.append(txt)
        for v in node.values():
            collect_text_nodes(v, texts)
    elif isinstance(node, list):
        for i in node:
            collect_text_nodes(i, texts)
    return texts

def get_bbox(node):
    return node.get("absoluteBoundingBox", {}) or {}

def find_position_reference(node, ancestors):
    nb = get_bbox(node)
    for p in reversed(ancestors):
        pb = get_bbox(p)
        if pb.get("width", 0) > nb.get("width", 0) * 3:
            return p
    return None

def classify_position(node, parent):
    nb, pb = get_bbox(node), get_bbox(parent)
    if not pb.get("width") or not pb.get("height"):
        return "absolute"

    x = (nb["x"] - pb["x"]) / pb["width"]
    y = (nb["y"] - pb["y"]) / pb["height"]

    v = "top" if y < 0.33 else "bottom" if y > 0.66 else "center"
    h = "left" if x < 0.33 else "right" if x > 0.66 else "center"
    return f"{v}_{h}"

GENERIC_ICON_NAMES = {"vector", "frame", "group", ""}
def extract_icon_name(node, ancestors):
    for n in [node] + list(reversed(ancestors)):
        name = n.get("name", "").strip()
        lname = name.lower()
        if lname not in GENERIC_ICON_NAMES and not lname.startswith("frame"):
            return name.split("/")[-1]
    return "icon"

ICON_MIN_SIZE = 8
ICON_MAX_SIZE = 32
def extract_static_icon(node, path, ancestors):
    if node.get("type") != "FRAME":
        return None

    children = get_children(node)
    if len(children) != 1:
        return None

    child = children[0]
    if child.get("type") not in {"VECTOR", "BOOLEAN_OPERATION"}:
        return None

    if collect_text_nodes(node):
        return None

    bbox = get_bbox(child)
    w, h = bbox.get("width", 0), bbox.get("height", 0)
    if not (ICON_MIN_SIZE <= w <= ICON_MAX_SIZE and ICON_MIN_SIZE <= h <= ICON_MAX_SIZE):
        return None

    position = "absolute"
    if (p := find_position_reference(node, ancestors)):
        position = classify_position(node, p)

    return {
        "name": extract_icon_name(node, ancestors),
        "path": path,
        "position": position
    }

def node_or_descendant_matches(node, keywords, max_depth=2, depth=0):
    if not isinstance(node, dict) or depth > max_depth:
        return False
    name = node.get("name", "").lower()
    if any(k in name for k in keywords):
        return True
    return any(
        node_or_descendant_matches(c, keywords, max_depth, depth + 1)
        for c in get_children(node)
    )

HOVER_TRIGGER_TYPES = {"ON_HOVER", "MOUSE_ENTER", "MOUSE_LEAVE"}

def has_on_hover_interaction(node):
    for i in node.get("interactions", []):
        trigger = i.get("trigger", {})
        if isinstance(trigger, dict) and trigger.get("type") in HOVER_TRIGGER_TYPES:
            return True
    return False


def has_descendant_hover_interaction(node, max_depth=2, depth=0):
    if not isinstance(node, dict) or depth > max_depth:
        return False
    if has_on_hover_interaction(node):
        return True
    return any(
        has_descendant_hover_interaction(c, max_depth, depth + 1)
        for c in get_children(node)
    )

HOVER_NAME_HINTS = {"hover", "hovered", "overlay", "menu", "tooltip"}
def is_hover_container(node):
    return (
        node_or_descendant_matches(node, HOVER_NAME_HINTS)
        or has_descendant_hover_interaction(node)
    )

def get_interaction_target_ids(node):
    """Any node ids this node's interactions/transitions point to."""
    targets = set()
    tid = node.get("transitionNodeID")
    if tid:
        targets.add(tid)
    for i in node.get("interactions", []):
        for action in i.get("actions", []):
            if isinstance(action, dict):
                dest = action.get("destinationId")
                if dest:
                    targets.add(dest)
    return targets

def collect_linked_options(node, node_index):
    """Resolve any interaction/transition targets and pull their text
    options too -- this is what makes option detection work for widgets
    whose real option list lives on a different node than the trigger."""
    if not node_index:
        return []
    linked = []
    for target_id in get_interaction_target_ids(node):
        target_node = node_index.get(target_id)
        if target_node:
            linked.extend(collect_text_nodes(target_node))
    return linked

MIN_MENU_OPTIONS = 2
DEBUG = True
BLACKLIST_LABELS = {
    "edit", "delete", "create", "cancel",
    "open", "--", "search"
}
def extract_hover_menu(node, path, node_index=None):

    if not is_hover_container(node):
        return None
    own_options = collect_text_nodes(node)
    linked_options = collect_linked_options(node, node_index)
    options = list(dict.fromkeys(own_options + linked_options))

    if len(options) < MIN_MENU_OPTIONS:
        if DEBUG:
            print(f"[hover] reject '{node.get('name')}' -> only {len(options)} text option(s) (own+linked), need {MIN_MENU_OPTIONS}")
        return None

    label = options[0]
    if label.lower() in BLACKLIST_LABELS:
        if DEBUG:
            print(f"[hover] reject '{node.get('name')}' -> first option '{label}' is blacklisted")
        return None

    if DEBUG:
        print(f"[hover] ACCEPT '{node.get('name')}' -> options={options} (linked={bool(linked_options)})")

    return {
        "role": "hover_menu",
        "interaction": "on_hover",
        # "label": label,
        "options": options,
        "path": path,
        "confidence": 0.95 if has_on_hover_interaction(node) else 0.75
    }

def extract_label(node):
    texts = collect_text_nodes(node)
    return texts[0] if texts else node.get("name", "Unknown")

DROPDOWN_NAME_HINTS = {"dropdown", "select", "chevron", "arrow"}
def extract_dropdown_menu(node, path, node_index=None):

    if not node_or_descendant_matches(node, DROPDOWN_NAME_HINTS):
        if DEBUG:
            pass
            # print(f"[dropdown] reject '{node.get('name')}' -> no dropdown-like name in node or children")
        return None

    own_options = collect_text_nodes(node)
    linked_options = collect_linked_options(node, node_index)
    options = list(dict.fromkeys(own_options + linked_options))

    if len(options) < MIN_MENU_OPTIONS:
        if DEBUG:
            # print(f"[dropdown] reject '{node.get('name')}' -> only {len(options)} text option(s) (own+linked), need {MIN_MENU_OPTIONS}")
            pass
        return None

    label = extract_label(node)
    if label.lower() in BLACKLIST_LABELS:
        if DEBUG:
            pass
            # print(f"[dropdown] reject '{node.get('name')}' -> label '{label}' is blacklisted")
        return None

    if DEBUG:
        #  print(f"[dropdown] ACCEPT '{node.get('name')}' -> options={options} (linked={bool(linked_options)})")
        pass
    return {
        "role": "dropdown",
        "interaction": "on_click",
        # "label": label,
        "options": options,
        "path": path,
        "confidence": 0.9
    }


MAX_TREE_DEPTH = 12
def clean_and_detect(individual_frame, frame_id_name=None, depth=0, path="", ancestors=None, node_index=None):
    if depth > MAX_TREE_DEPTH:
        return None, None, None, []
    
    if ancestors is None:
        ancestors = []

    if isinstance(individual_frame, dict):
        cleaned = {}
        icons = []

        if individual_frame.get("type") == "FRAME":

            cleaned["header"] = extract_page_frame_header(individual_frame)

        name = individual_frame.get("name", "")

        current_path = f"{path} / {name}" if path else name

        new_ancestors = ancestors + [individual_frame]

        child_hover = None
        child_dropdown = None

        for c in get_children(individual_frame):
            cleaned_child, h, d, child_icons = clean_and_detect(
                c, frame_id_name, depth + 1, current_path, new_ancestors, node_index
            )
            if cleaned_child:
                cleaned.setdefault("children", []).append(cleaned_child)

            icons.extend(child_icons)

            if h:
                child_hover = h
            if d:
                child_dropdown = d

        # 2️⃣ ICON DETECTION (NEW)
        if (icon := extract_static_icon(individual_frame, current_path, ancestors)):
            icons.append(icon)

        # 3️⃣ CURRENT NODE DETECTION (ONLY IF NO CHILD WON)
        hover = None
        dropdown = None

        if not child_hover:
            hover = extract_hover_menu(individual_frame, current_path, node_index)
        if not child_dropdown:
            dropdown = extract_dropdown_menu(individual_frame, current_path, node_index)

        # 4️⃣ CLEAN KEYS (RESTORED destinationFrame LOGIC)
        for k, v in individual_frame.items():
            if k in UNWANTED_KEYS or k == "children":
                continue

            if k == "interactions":
                cleaned_interactions = []
                for interaction in v:
                    interaction_cleaned = dict(interaction)

                    if frame_id_name and "actions" in interaction_cleaned:
                        for action in interaction_cleaned.get("actions", []):
                            if not isinstance(action, dict):
                                continue

                            if "destinationId" in action:
                                dest_id = action["destinationId"]
                                action["destinationFrame"] = (
                                    frame_id_name.get(dest_id, {}).get("name")
                                )


                    cleaned_interactions.append(interaction_cleaned)

                cleaned["interactions"] = cleaned_interactions
            else:
                cleaned[k] = v

        # 5️⃣ ATTACH SEMANTIC INFO
        if hover and not child_hover:
            if icons:
                hover["icons"] = icons
            cleaned["hoverMenu"] = hover

        if dropdown and not child_dropdown:
            cleaned["dropdownMenu"] = dropdown

        return cleaned, hover or child_hover, dropdown or child_dropdown, icons

    elif isinstance(individual_frame, list):
        cleaned_list = []
        icons = []

        for i in individual_frame:
            cleaned_i, _, _, child_icons = clean_and_detect(
                i, frame_id_name, depth, path, ancestors, node_index
            )
            if cleaned_i:
                cleaned_list.append(cleaned_i)
            icons.extend(child_icons)

        return cleaned_list, None, None, icons

    return individual_frame, None, None, []



def _contains_key(node, key):
    """Small helper used only for the summary print (FIX: see below)."""
    if isinstance(node, dict):
        if key in node:
            return True
        return any(_contains_key(v, key) for v in node.values())
    if isinstance(node, list):
        return any(_contains_key(i, key) for i in node)
    return False


FORCE_OVERWRITE = True
def cleaned_file_json(OUTPUT_DIR, FILE_ID, Page_ID):
    file_path = os.path.join(OUTPUT_DIR, f"{FILE_ID}.json")
    print(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        file_json = json.load(f)

    for page_id in Page_ID:
        print("this is page id",page_id)
        page_json = find_frame(file_json, page_id)
        if not page_json:
            print("no page going for next")
            continue 

        frame_id_name = build_frame_map(page_json)
        print("frame name id extracted")
        node_index = build_node_index(page_json)
   
        page_header = extract_page_frame_header(page_json )
        page_name = sanitize(page_header["name"])
       
        page_dir = os.path.join(OUTPUT_DIR, page_name)
        os.makedirs(page_dir, exist_ok=True)


        cleaned_children = []
        for individual_frame in page_json.get("children", []):
            cleaned_child, h, d, child_icons = clean_and_detect(individual_frame, frame_id_name, node_index=node_index)
    
            if cleaned_child:
                cleaned_children.append(cleaned_child)

        cleaned_page = {
            "page": page_header,
            "children": cleaned_children
        }
    
        n_hover = sum(1 for f in cleaned_children if _contains_key(f, "hoverMenu"))
        n_dropdown = sum(1 for f in cleaned_children if _contains_key(f, "dropdownMenu"))
        print(f"\n[{page_header['name']}] frames={len(cleaned_children)} "
              f"hoverMenus_found={n_hover} dropdownMenus_found={n_dropdown}")

        json_path = os.path.join(page_dir, f"{page_name}.json")
        if os.path.exists(json_path) and not FORCE_OVERWRITE:
            print(f"⏭️ Skipping existing file: {json_path}")
        else:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(cleaned_page, f, indent=2, ensure_ascii=True)
            print(f"✅ Saved → {json_path}")

    
   
