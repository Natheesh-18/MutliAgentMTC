import os
from io import BytesIO
from flask import Flask, request, jsonify
import boto3
from botocore.exceptions import ClientError
import hvac
import logging
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from langchain_community.vectorstores import Qdrant
from langchain_community.document_loaders import PyPDFLoader, UnstructuredWordDocumentLoader, TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv
import json
from langchain_experimental.text_splitter import SemanticChunker
from charset_normalizer import from_path

from src.persistence.mongo_client import get_sync_client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
load_dotenv()
app = Flask(__name__)

# S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)


class DocumentProcessor:
    def __init__(self, embeddings, qdrant_host, qdrant_port):
        self.embeddings = embeddings
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.env = os.getenv("PROFILE")

    def load_files_collection(self, license_id, project_id):
        """Return the ``{project_id}_files`` collection for *license_id*."""
        client = get_sync_client()
        db = client[license_id]
        collection = db[f"{project_id}_files"]
        return collection

    def load_figma_collection(self, license_id, project_id):
        """Return the ``{project_id}_figma_instances`` collection for *license_id*."""
        client = get_sync_client()
        db = client[license_id]
        collection = db[f"{project_id}_figma_instances"]
        return collection
    
    def split_documents(self, file_data):
        """
        Hybrid splitting: first semantically, then recursively for large chunks.
        Keeps metadata and adds 'chunk_id' for ordering.
        """
        embedding_model = self.embeddings
        print("Splitting documents using semantic + recursive chunking...")

        semantic_splitter = SemanticChunker(embedding_model)
        recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
            separators=["\n\n", "\n", " "]
        )

        final_documents = []
        chunk_counter = 0

        # Process each document in the list
        for doc in file_data:
            # Semantic splitter expects a list of documents
            semantic_chunks = semantic_splitter.split_documents([doc])

            for sem_chunk in semantic_chunks:
                text = sem_chunk.page_content.strip()

                if len(text) < 100:
                    continue

                # Recursively split if too big, else keep as is
                if len(text) > 500:
                    sub_chunks = recursive_splitter.split_text(text)
                else:
                    sub_chunks = [text]

                for sub_text in sub_chunks:
                    sub_text = sub_text.strip()
                    if len(sub_text) < 100:
                        continue

                    metadata = sem_chunk.metadata.copy()
                    metadata["source"] = os.path.basename(metadata.get("source", "unknown"))
                    metadata["chunk_id"] = chunk_counter
                    final_documents.append(Document(page_content=sub_text, metadata=metadata))
                    chunk_counter += 1

        print(f"Created {len(final_documents)} final chunks")
        return final_documents
 
    def update_mongodb_status(self, license_id, project_id, file_name, status):
        """Update project-specific MongoDB collection with status."""
        collection = self.load_files_collection(license_id, project_id)
        record = {
        "file_name": file_name,
        "status": status,

        }
        collection.update_one(
        {"name": file_name},  
        {"$set": record},          
        upsert=True                
        )

        print(f"🟢 MongoDB ({license_id}/{project_id}_files) updated for {file_name}: {status}")

    def update_figma_mongodb_status(self, license_id, project_id, mongo_id,instance_name, status):
        """Update project-specific MongoDB collection with status."""
        collection = self.load_figma_collection(license_id,project_id)
        record = {
        "state": status,
        }
        collection.update_one(
        {"_id": mongo_id},  
        {"$set": record},          
        upsert=True                
        )

        print(f"🟢 MongoDB ({license_id}/{project_id}_files) updated for {instance_name}: {status}")

    def get_figma_instance_name(self, license_id, project_id, mongo_id):
        
        """
        Fetch the 'name' of a Figma instance using its MongoDB _id.
        """
        collection = self.load_figma_collection(license_id, project_id)

        document = collection.find_one(
            {"_id": mongo_id},
            {"name": 1, "_id": 0}  # Only fetch the name field
        )

        if document:
            return document.get("name")

        return None