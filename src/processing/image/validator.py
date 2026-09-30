import io
import base64
import numpy as np
from PIL import Image

def is_blank_image_bytes(image_bytes: bytes, variance_threshold: int = 10) -> bool:
    """Check if image is blank/uniform using in-memory bytes (no disk I/O)."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        img_array = np.array(img)
        return img_array.var() < variance_threshold
    except Exception:
        # Treat unreadable / corrupted images as invalid
        return True

def validate_image_extension(ext: str) -> bool:
    """Check if extension is a supported image format."""
    return ext.lower() in {".png", ".jpg", ".jpeg"}

def image_to_base64_bytes(image_bytes: bytes) -> str:
    """In-memory variant of image_to_base64() — direct base64 encoding from bytes."""
    return base64.b64encode(image_bytes).decode("utf-8")
