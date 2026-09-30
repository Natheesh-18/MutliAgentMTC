"""Lazy HuggingFace embeddings and Qdrant connection constants."""
import logging
import os

import torch
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient, AsyncQdrantClient

load_dotenv()
logger = logging.getLogger(__name__)

try:
    torch.set_num_threads(4)
except Exception:
    pass

QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_PORT = os.getenv("QDRANT_PORT")
# qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT,https=False, check_compatibility=False,timeout=60.0)
# qdrantAsyncClient = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT,https=False, check_compatibility=False,timeout=60.0)

QDRANT_URL = f"{QDRANT_HOST}:{QDRANT_PORT}"

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    check_compatibility=False,
    timeout=60.0,
)

qdrantAsyncClient = AsyncQdrantClient(
    url=QDRANT_URL,
    check_compatibility=False,
    timeout=60.0,
)

_EMBEDDINGS = None

def get_embeddings():
    global _EMBEDDINGS
    if _EMBEDDINGS is None:
        _EMBEDDINGS = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True, "batch_size": 64},
        )
    return _EMBEDDINGS


class _EmbeddingsProxy:
    def __getattr__(self, name):
        return getattr(get_embeddings(), name)


EMBEDDINGS = _EmbeddingsProxy()
