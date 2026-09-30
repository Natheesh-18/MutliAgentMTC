import json
import logging
import re
from typing import Dict, List, Any, Tuple

from json_repair import repair_json

from src.llm.client import ImageLLMClient
from src.utils.helper_function import (
    generate_user_content_image_name,
    convert_to_openai_multimodal
)
from src.processing.image.validator import image_to_base64_bytes
from src.processing.image.prompts import irrelevant_image_detection_prompt

logger = logging.getLogger(__name__)


async def IrrelevantImageDetector(
    user_content, PROMPT, json_structure_image_schema,
    serviceProvider=None, apiKey=None, model=None,
    sa_info=None, resource=None, resourceId=None
):
    """
    Analyse each labelled image and classify it as valid UI or invalid.
    Returns (result_dict, input_tokens, output_tokens).
    """
    userPrompt = """Analyze each labeled image (e.g., img_1, img_2).
        Check if the image contains ANY of the following UI elements:
        - A browser or browser URL bar
        - Any app screen, modal, popup, login form, or dialog box
        - Any button, input field, menu, or navigation element
        - Any CAPTCHA, image grid selector, or puzzle embedded in an app
        - Any real-world photo or object embedded INSIDE a software UI

        Only mark an image as INVALID if it has absolutely ZERO software UI elements.
        Return a strictly valid JSON response."""

    if serviceProvider in ["Anthropic", "Gemini", "gemini_enterprise", "Groq"]:
        userPrompt += """
        EXPECTED JSON FORMAT:
        {
            "content": {
                "img_1": {
                    "imageName": "Home Page"
                },
                "img_2": {
                    "imageName": "Signup Page"
                },
                "img_3": {
                    "imageName": "Login Page"
                }
            },
            "invalidImages": []
        }
        """

    # Extract images and text labels from user_content for ImageLLMClient
    images = []
    text_parts = []
    for item in user_content:
        if item.get("type") == "text":
            text_parts.append(item["text"])
        elif item.get("type") == "image_url":
            # Pass the full data-URL; ImageLLMClient handles all formats
            images.append(item["image_url"]["url"])

    # Append the analysis user prompt
    text_parts.append(userPrompt)
    combined_user_prompt = "\n".join(text_parts)

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "json_structure_image",
            "schema": json_structure_image_schema
        }
    }

    logger.info(f"IrrelevantImageDetector: using ImageLLMClient with provider={serviceProvider}, model={model}")

    try:
        data, input_tokens, output_tokens = await ImageLLMClient.generate_async(
            serviceProvider=serviceProvider,
            model=model,
            apiKey=apiKey,
            system_prompt=PROMPT,
            user_prompt=combined_user_prompt,
            images=images,
            sa_info=sa_info,
            resource=resource,
            resourceId=resourceId,
            response_format=response_format,
            return_usage=True,
        )
    except Exception as e:
        logger.error(f"Error in IrrelevantImageDetector with model {model}: {str(e)}")
        raise e

    # Ensure data is a dict (ImageLLMClient already parses JSON via parse_json_response)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = repair_json(data, return_objects=True)

    if not isinstance(data, dict):
        raise ValueError("Failed to parse valid JSON from the model response.")

    logger.info(f"IrrelevantImageDetector result: {len(data.get('content', {}))} valid, {len(data.get('invalidImages', []))} invalid")
    return data, input_tokens, output_tokens


async def detect_irrelevant_images(
    images_data: List[Dict[str, Any]],
    user_input: str,
    serviceProvider: str,
    apiKey: str,
    model: str,
    sa_info: Any = None,
    resource: str = None,
    resourceId: str = None,
) -> Tuple[list, List[str], int, int]:
    """
    Takes in-memory images_data [{filename, bytes}], builds base64 user content,
    runs IrrelevantImageDetector, and returns (image_content, valid_images, input_tokens, output_tokens).
    """
    Image_Input_token = 0
    Image_Output_token = 0

    # 1. Base64 encode images from bytes
    base64_images = {}
    for img_info in images_data:
        filename = img_info["filename"]
        file_bytes = img_info["bytes"]
        base64_img = image_to_base64_bytes(file_bytes)
        base64_images[filename] = base64_img

    # 2. Generate user content & image names
    userContent, imageNames = generate_user_content_image_name(base64_images)
    
    # 3. Call IrrelevantImageDetector
    Prompt, jsonSchema = irrelevant_image_detection_prompt(user_input)
    
    try:
        result, det_in_t, det_out_t = await IrrelevantImageDetector(
            userContent, 
            Prompt, 
            jsonSchema, 
            serviceProvider=serviceProvider, 
            apiKey=apiKey, 
            model=model, 
            sa_info=sa_info, 
            resource=resource, 
            resourceId=resourceId
        )
        Image_Input_token += det_in_t
        Image_Output_token += det_out_t
    except Exception as e:
        logger.error(f"Error in IrrelevantImageDetector: {str(e)}")
        raise e

    # 4. Filter out invalid images
    irelevant_images = result.get("invalidImages", [])
    invalid_real_files = {imageNames[img] for img in irelevant_images if img in imageNames}
    
    valid_images = [img["filename"] for img in images_data if img["filename"] not in invalid_real_files]
    
    if not valid_images:
        raise ValueError("Uploaded image is not a valid application screenshot.Please upload relevant images.")

    skip_next = False
    filtered_content = []
    for item in userContent:
        if item["type"] == "input_text" and any(f"ScreenName: {img}" in item["text"] for img in irelevant_images):
            skip_next = True
            continue
        if skip_next and item["type"] == "image_url":
            skip_next = False
            continue
        filtered_content.append(item)
    userContent = filtered_content
    
    for item in userContent:
        if item["type"] == "text":
            for img_key, data in result.get("content", {}).items():
                if img_key in imageNames:
                    item["text"] = item["text"].replace(f"ScreenName: {img_key}", f"ScreenName: {data['imageName']}")
                    
    # 5. Convert to OpenAI multimodal format
    image_content = convert_to_openai_multimodal(userContent)
    
    return image_content, valid_images, Image_Input_token, Image_Output_token
