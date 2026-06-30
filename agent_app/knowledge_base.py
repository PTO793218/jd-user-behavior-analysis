from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from .data_loader import PROJECT_ROOT
except ImportError:  # pragma: no cover - direct script fallback
    from data_loader import PROJECT_ROOT


DEFAULT_KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge_base"


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    heading: str
    content: str
    index: int


def _clean_line(line: str) -> str:
    return line.strip()


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s+", line.strip()))


def _heading_text(line: str) -> str:
    return re.sub(r"^#{1,6}\s+", "", line.strip()).strip()


def _paragraphs(lines: list[str]) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = _clean_line(line)
        if not stripped:
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        current.append(stripped)
    if current:
        paragraphs.append("\n".join(current).strip())
    return paragraphs


def chunk_markdown_text(text: str, source: str) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    heading = Path(source).stem
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        for paragraph in _paragraphs(buffer):
            chunks.append(
                KnowledgeChunk(
                    source=source,
                    heading=heading,
                    content=paragraph,
                    index=len(chunks),
                )
            )
        buffer = []

    for raw_line in text.splitlines():
        if _is_heading(raw_line):
            flush()
            heading = _heading_text(raw_line)
            chunks.append(
                KnowledgeChunk(
                    source=source,
                    heading=heading,
                    content=heading,
                    index=len(chunks),
                )
            )
        else:
            buffer.append(raw_line)
    flush()
    return [chunk for chunk in chunks if chunk.content.strip()]


def load_markdown_documents(knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR) -> dict[str, str]:
    if not knowledge_dir.exists():
        return {}
    documents: dict[str, str] = {}
    for path in sorted(knowledge_dir.rglob("*.md")):
        documents[path.name] = path.read_text(encoding="utf-8")
    return documents


@lru_cache(maxsize=4)
def _load_knowledge_chunks_cached(knowledge_dir_text: str) -> tuple[KnowledgeChunk, ...]:
    knowledge_dir = Path(knowledge_dir_text)
    chunks: list[KnowledgeChunk] = []
    for source, text in load_markdown_documents(knowledge_dir).items():
        chunks.extend(chunk_markdown_text(text, source=source))
    return tuple(chunks)


def load_knowledge_chunks(knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR) -> list[KnowledgeChunk]:
    return list(_load_knowledge_chunks_cached(str(knowledge_dir.resolve())))
