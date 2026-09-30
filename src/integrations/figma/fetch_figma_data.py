import os
import requests
import json
import re
import time

def sanitize(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", name) 
    name = name.strip().rstrip(".")            
    return name

class FigmaAPIError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(message)

def handle_figma_response(res, context=""):
    if res.status_code == 200:
        return

    if res.status_code == 403:
        raise FigmaAPIError(403, f"Invalid or expired Figma access token.")
    elif res.status_code == 404:
        raise FigmaAPIError(404, f"Figma file not found. Verify the File ID and try again.")
    elif res.status_code == 429:
        raise FigmaAPIError(429, f"Request limit exceeded. Please try again later.")
    else:
        try:
            err_detail = res.json().get("err", res.text)
        except Exception:
            err_detail = res.text
        raise FigmaAPIError(res.status_code, f"Figma API error: {err_detail}. {context}")


def fetch_figma_frames(file_id, figma_token, page_ids,instance_name):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ENTIER_FOLDER = os.path.join(BASE_DIR, "FIGMA_ENTIER")
    OUTPUT_DIR = os.path.join(ENTIER_FOLDER, file_id + "_" + instance_name)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    headers = {"X-Figma-Token": figma_token}

    # 1. FETCH JSON
    url = f"https://api.figma.com/v1/files/{file_id}/nodes"
    params = {"ids": ",".join(page_ids)}

    res = requests.get(url, headers=headers, params=params)
    handle_figma_response(res, context=f"file_id={file_id}")

    data = res.json()

    # save json
    with open(os.path.join(OUTPUT_DIR, file_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("JSON saved")

    # 2. LOOP THROUGH ALL PAGES
    for pid in page_ids:
        if pid not in data["nodes"]:
            print(f"Page {pid} not found in response")
            continue
        
        page_json = data["nodes"][pid]["document"]
        page_name = sanitize(page_json["name"])
        page_folder = os.path.join(OUTPUT_DIR, page_name)
        os.makedirs(page_folder, exist_ok=True)

        # 3. COLLECT FRAME IDS
        frame_map = {}
        for child in page_json["children"]:
            if child["type"] == "FRAME":
                frame_map[child["id"]] = sanitize(child["name"])

        frame_ids = list(frame_map.keys())
        print("this are the images:",frame_map)
        print("Frames found:", len(frame_ids))

        # 4. FETCH FRAME IMAGES
        batch_size = 50
        image_urls = {}

        for i in range(0, len(frame_ids), batch_size):
            batch = frame_ids[i:i + batch_size]

            # now lets exatract the images base on the id
            img_url = f"https://api.figma.com/v1/images/{file_id}"

            params = {
                "ids": ",".join(batch),
                "format": "png"
            }

            r = requests.get(img_url, headers=headers, params=params)
            r.raise_for_status()

            image_urls.update(r.json()["images"])
            time.sleep(1)

        # 5. DOWNLOAD IMAGES
        for node_id, url in image_urls.items():

            if not url:
                continue
            name = frame_map[node_id]
            safe_id = node_id.replace(":", "_")
            path = os.path.join(page_folder, f"{safe_id}_{name}.png")
            img = requests.get(url).content
            with open(path, "wb") as f:
                f.write(img)

        print("Done. Images saved in:", page_folder)

    return OUTPUT_DIR
