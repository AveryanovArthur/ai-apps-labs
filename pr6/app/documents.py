import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DOCS_DIR = Path(__file__).parent.parent / "docs"

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "600"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))


@dataclass
class Chunk:
    """Фрагмент документа — одиниця індексування й пошуку."""

    text: str
    source: str
    metadata: dict = field(default_factory=dict)


def parse_front_matter(raw: str) -> tuple[dict, str]:
    """Відокремити блок метаданих від тексту документа."""
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    metadata: dict = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body = "\n".join(lines[i + 1:]).lstrip("\n")
            return metadata, body
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()
    return {}, raw


def load_documents(docs_dir: Path = DOCS_DIR) -> list[tuple[str, dict, str]]:
    """Прочитати всі документи колекції."""
    documents = []
    for path in sorted(docs_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        metadata, body = parse_front_matter(path.read_text(encoding="utf-8"))
        documents.append((path.name, metadata, body))
    return documents


def split(text: str, source: str, metadata: dict) -> list[Chunk]:
    """Поділити текст документа на фрагменти з урахуванням заголовків та розміру."""
    chunks: list[Chunk] = []
    lines = text.splitlines()

    current_heading = ""
    current_buffer: list[str] = []

    def flush_buffer(buffer: list[str], heading: str):
        full_text = "\n".join(buffer).strip()
        if not full_text:
            return

        chunk_meta = dict(metadata)
        if heading:
            chunk_meta["heading"] = heading

        if len(full_text) > CHUNK_SIZE:
            step = CHUNK_SIZE - CHUNK_OVERLAP if CHUNK_SIZE > CHUNK_OVERLAP else CHUNK_SIZE
            for start in range(0, len(full_text), step):
                sub_text = full_text[start : start + CHUNK_SIZE].strip()
                if sub_text:
                    sub_meta = dict(chunk_meta)
                    chunks.append(Chunk(text=sub_text, source=source, metadata=sub_meta))
        else:
            chunks.append(Chunk(text=full_text, source=source, metadata=chunk_meta))

    for line in lines:
        if line.startswith("#"):
            if current_buffer:
                flush_buffer(current_buffer, current_heading)
                current_buffer = []
            current_heading = line.lstrip("#").strip()
        current_buffer.append(line)

    if current_buffer:
        flush_buffer(current_buffer, current_heading)

    return chunks


def load_chunks(docs_dir: Path = DOCS_DIR) -> list[Chunk]:
    """Прочитати колекцію й повернути всі її фрагменти."""
    chunks: list[Chunk] = []
    for source, metadata, body in load_documents(docs_dir):
        chunks.extend(split(body, source, metadata))
    return chunks