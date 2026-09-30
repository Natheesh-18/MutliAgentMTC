import os
import uuid
import re
from llama_index.core import Document
from llama_index.core.schema import TextNode, BaseNode
from typing import List,Sequence
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter,NodeParser


# --- CONFIGURATION ---
# INPUT_DIR = "./input_documents"
OUTPUT_FILE = "chunks_output.txt"
TARGET_TOKENS = 512
MAX_SINGLE_BLOCK_TOKENS = 1024

class ProductionHierarchyChunker(NodeParser):
    def _clean_text(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    def _is_strictly_bold(self, line: str) -> bool:
        """Detects if a line is just bold text (Docling's typical header output)."""
        return bool(re.match(r'^\s*\*\*(.*?)\*\*\s*$', line))

    def _preprocess_document(self, text: str) -> str:
        """
        Logic to determine which processing method to use.
        """
        lines = text.splitlines()
        
        # STAGE 1: Check for existing Markdown headers
        has_md_headers = any(line.strip().startswith('#') for line in lines)
        if has_md_headers:
            print(">>> METHOD WORKING: Standard Heading Detection (Stage 1)")
            return text

        # STAGE 2: Check for Bold lines to promote
        has_bold = any(self._is_strictly_bold(line) for line in lines)
        if has_bold:
            print(">>> METHOD WORKING: Bold Promotion Detection (Stage 2)")
            processed_lines = []
            for line in lines:
                if self._is_strictly_bold(line):
                    header_content = line.replace("**", "").strip()
                    processed_lines.append(f"# {header_content}") 
                else:
                    processed_lines.append(line)
            return "\n".join(processed_lines)
        
        # STAGE 3: Fallback to Flat Text
        print(">>> METHOD WORKING: Flat Text (Stage 3) - No Headers or Bold found")
        return text

    def _parse_nodes(self, nodes: Sequence[BaseNode], **kwargs) -> List[BaseNode]:
        merged_nodes = []
        current_chunk_text = ""
        current_tokens = 0
        current_metadata = {}
        chunk_index = 0

        for node in nodes:
            content = self._clean_text(node.get_content())
            if not content: continue
            
            node_tokens = len(content) // 4
            if current_tokens + node_tokens > TARGET_TOKENS:
                if current_chunk_text:
                    merged_nodes.append(self._create_node(current_chunk_text, current_metadata, chunk_index))
                    chunk_index += 1
                current_chunk_text = content
                current_tokens = node_tokens
                current_metadata = node.metadata.copy()
            else:
                current_chunk_text = (current_chunk_text + "\n\n" + content) if current_chunk_text else content
                current_tokens += node_tokens
                current_metadata.update(node.metadata)

        if current_chunk_text:
            merged_nodes.append(self._create_node(current_chunk_text, current_metadata, chunk_index))
        return merged_nodes

    def _create_node(self, text, metadata, index):
        file_name = metadata.get('file_name', 'document')
        # Calculate tokens for the final text block
        est_tokens = len(text) // 4
        
        # --- MODIFIED LINE BELOW ---
        # Removed "SECTION" and added "Token Size"
        final_text = f"--- Chunk Token Size: {est_tokens} ---\n\n{text}"
        
        readable_id = f"{file_name}_chunk_{index+1}".replace(" ", "_")
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, readable_id))
        
        return TextNode(
            id_=point_id,
            text=final_text.strip(),
            metadata={
                "file_name": file_name,
                "token_size": est_tokens
            }
        )
