import re
from typing import List

SPLIT_STRATEGIES = [
    r'\n(?=#{1,2}\s)',
    r'\n(?=#{3,4}\s)',
    r'\n{2,}',
    r'\n(?=(?:\d+\.|\*|-)\s)',
    r'(?<=[.!?])\s+',
    r'\s+',
]


def clean_text(chunk: str) -> str:
    if not chunk:
        return ""

    # Remove trailing/leading whitespaces on each line and drop empty blank lines
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    text = "\n".join(lines)

    # Collapse multiple consecutive horizontal spaces to a single space
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def chunk_text(
    text: str,
    max_chars: int = 20000,
    overlap_chars: int = 500,
    level: int = 0
) -> List[str]:
    
    cleaned_text = clean_text(text)
    if not cleaned_text:
        return []

    # If the text already fits comfortably within the 20,000 budget, return it directly
    if len(cleaned_text) <= max_chars:
        return [cleaned_text]

    # If we have exhausted all natural split boundaries, use hard windowing
    if level >= len(SPLIT_STRATEGIES):
        chunks = []
        step = max(1, max_chars - overlap_chars)
        for i in range(0, len(cleaned_text), step):
            slice_text = clean_text(cleaned_text[i:i + max_chars])
            if slice_text:
                chunks.append(slice_text)
        return chunks

    pattern = SPLIT_STRATEGIES[level]
    parts = re.split(pattern, cleaned_text)

    chunks = []
    buffer = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue

        separator = "\n\n" if level <= 2 else " "
        candidate = f"{buffer}{separator}{part}" if buffer else part

        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            if buffer:
                opt_buf = clean_text(buffer)
                if len(opt_buf) <= max_chars:
                    chunks.append(opt_buf)
                else:
                    chunks.extend(chunk_text(opt_buf, max_chars, overlap_chars, level + 1))

            # Handle the oversized single part that couldn't fit in the buffer
            if len(part) > max_chars:
                chunks.extend(chunk_text(part, max_chars, overlap_chars, level + 1))
                buffer = ""
            else:
                buffer = part

    if buffer:
        opt_buf = clean_text(buffer)
        if len(opt_buf) <= max_chars:
            chunks.append(opt_buf)
        else:
            chunks.extend(chunk_text(opt_buf, max_chars, overlap_chars, level + 1))

    # Final pass: ensure every returned chunk is clean and non-empty
    return [clean_text(c) for c in chunks if clean_text(c)]
