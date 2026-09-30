import logging
from typing import Tuple, Any

from src.utils.helper_function import videoSummary
from toon import encode

logger = logging.getLogger(__name__)

async def summarize_images(
    image_content: list,
    serviceProvider: str,
    apiKey: str,
    model: str,
    sa_info: Any = None,
    resource: str = None,
    resourceId: str = None,
) -> Tuple[str, int, int]:
    """
    Summarize image content using LLM vision.
    Returns (encoded_summary_text, input_tokens, output_tokens).
    """
    try:
        imageContent, input_token, output_token = await videoSummary(
            image_content, 
            True, 
            serviceProvider=serviceProvider, 
            apiKey=apiKey, 
            model=model, 
            sa_info=sa_info, 
            resource=resource, 
            resourceId=resourceId
        )
        imageContent.pop("is_valid_software_video", None)
        
        encoded_content = encode(imageContent)
        return encoded_content, input_token, output_token
    except Exception as e:
        logger.error(f"Error in summarize_images: {e}")
        raise e
