from dataclasses import dataclass, field
from pathlib import Path
import re

# Безпечний імпорт конфігурації
try:
    import config
    DOCS_DIR = Path(getattr(config, "DOCS_DIR", "docs"))
    CHUNK_SIZE = getattr(config, "CHUNK_SIZE", 500)
    CHUNK_OVERLAP = getattr(config, "CHUNK_OVERLAP", 50)
except ImportError:
    DOCS_DIR = Path("docs")
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50


@dataclass
class Chunk:
    text: str
    source: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Document:
    text: str
    source: str
    metadata: dict = field(default_factory=dict)


def load_documents(docs_dir: Path | str = DOCS_DIR) -> list[Document]:
    """Завантаження всіх документів (.md, .txt) із директорії docs_dir."""
    docs_path = Path(docs_dir)
    documents: list[Document] = []

    if not docs_path.exists():
        return documents

    for file_path in sorted(docs_path.glob("**/*")):
        if file_path.is_file() and file_path.suffix.lower() in [".md", ".txt"]:
            try:
                text = file_path.read_text(encoding="utf-8")
                metadata = {"title": file_path.stem}

                # Зчитування YAML-frontmatter (якщо є вгорі файлу між ---)
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    if len(parts) >= 3:
                        fm_text = parts[1]
                        text = parts[2].strip()
                        for line in fm_text.splitlines():
                            if ":" in line:
                                k, v = line.split(":", 1)
                                metadata[k.strip()] = v.strip().strip("\"'")

                documents.append(
                    Document(
                        text=text,
                        source=file_path.name,
                        metadata=metadata,
                    )
                )
            except Exception as e:
                print(f"Помилка зчитання файлу {file_path}: {e}")

    return documents


def split(
    text_or_doc, source: str = "", metadata: dict | None = None
) -> list[Chunk]:
    """Розбиття документа на фрагменти з додаванням контексту заголовків."""
    if hasattr(text_or_doc, "text"):
        text = text_or_doc.text
        source = getattr(text_or_doc, "source", source)
        metadata = getattr(text_or_doc, "metadata", metadata or {})
    else:
        text = str(text_or_doc)
        metadata = metadata or {}

    chunks: list[Chunk] = []
    sections = text.split("\n## ")

    for i, sec in enumerate(sections):
        if not sec.strip():
            continue

        header = ""
        content = sec
        if i > 0:
            lines = sec.split("\n", 1)
            header = lines[0].strip()
            content = lines[1] if len(lines) > 1 else ""

        doc_title = metadata.get("title", source)
        context_prefix = f"Документ: {doc_title}"
        if header:
            context_prefix += f" | Розділ: {header}"

        full_text = f"{context_prefix}\n\n{content.strip()}"

        if len(full_text) <= CHUNK_SIZE:
            chunk_meta = dict(metadata)
            if header:
                chunk_meta["heading"] = header
            chunks.append(
                Chunk(text=full_text, source=source, metadata=chunk_meta)
            )
        else:
            start = 0
            sub_idx = 1
            body = content.strip()
            while start < len(body):
                end = start + CHUNK_SIZE
                part = body[start:end]
                c_text = f"{context_prefix}\n\n{part}"

                chunk_meta = dict(metadata)
                if header:
                    chunk_meta["heading"] = header
                chunk_meta["part"] = sub_idx

                chunks.append(
                    Chunk(text=c_text, source=source, metadata=chunk_meta)
                )
                start += CHUNK_SIZE - CHUNK_OVERLAP
                sub_idx += 1

    return chunks


def load_chunks(docs_dir: Path | str = DOCS_DIR) -> list[Chunk]:
    """Завантажує всі документи та розбиває їх на фрагменти (чанки)."""
    docs = load_documents(docs_dir)
    all_chunks: list[Chunk] = []
    for doc in docs:
        all_chunks.extend(split(doc))
    return all_chunks