from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

try:
    from .knowledge_base import KnowledgeChunk, load_knowledge_chunks
except ImportError:  # pragma: no cover - direct script fallback
    from knowledge_base import KnowledgeChunk, load_knowledge_chunks


RAG_INTENT_KEYWORDS = [
    "定义",
    "含义",
    "口径",
    "字段",
    "为什么",
    "怎么理解",
    "样本",
    "范围",
    "运营策略",
    "使用边界",
    "是什么",
    "什么意思",
    "RFM",
    "sentiment_score",
    "语义分析",
    "行为漏斗",
]


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: KnowledgeChunk
    score: float


def should_use_rag(question: str) -> bool:
    text = question.lower()
    return any(keyword.lower() in text for keyword in RAG_INTENT_KEYWORDS)


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-zA-Z0-9_]+", lowered))
    chinese_terms = set(re.findall(r"[\u4e00-\u9fff]{2,}", lowered))
    grams = {
        lowered[index : index + size]
        for size in (2, 3)
        for index in range(0, max(0, len(lowered) - size + 1))
        if re.search(r"[\u4e00-\u9fffA-Za-z0-9_]", lowered[index : index + size])
    }
    return words | chinese_terms | grams


def _score(question: str, chunk: KnowledgeChunk) -> float:
    query_tokens = _tokens(question)
    haystack = f"{chunk.source} {chunk.heading} {chunk.content}"
    chunk_tokens = _tokens(haystack)
    if not query_tokens or not chunk_tokens:
        return 0.0

    overlap = query_tokens & chunk_tokens
    if not overlap:
        return 0.0

    exact_bonus = 0.0
    question_lower = question.lower()
    haystack_lower = haystack.lower()
    for keyword in RAG_INTENT_KEYWORDS:
        if keyword.lower() in question_lower and keyword.lower() in haystack_lower:
            exact_bonus += 2.0

    heading_bonus = 1.5 if any(token in _tokens(chunk.heading) for token in query_tokens) else 0.0
    length_penalty = math.log(max(len(chunk.content), 20), 10)
    return round((len(overlap) + exact_bonus + heading_bonus) / length_penalty, 4)


def retrieve(
    question: str,
    chunks: list[KnowledgeChunk] | None = None,
    top_k: int = 3,
    min_score: float = 0.1,
) -> list[RetrievedChunk]:
    knowledge_chunks = chunks if chunks is not None else load_knowledge_chunks()
    hits = [
        RetrievedChunk(chunk=chunk, score=_score(question, chunk))
        for chunk in knowledge_chunks
    ]
    hits = [hit for hit in hits if hit.score >= min_score]
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:top_k]


def _format_sources(hits: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [
        {
            "source": hit.chunk.source,
            "heading": hit.chunk.heading,
            "content": hit.chunk.content,
            "score": hit.score,
        }
        for hit in hits
    ]


def answer_knowledge_question(
    question: str,
    chunks: list[KnowledgeChunk] | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    hits = retrieve(question, chunks=chunks, top_k=top_k)
    if not hits:
        return {
            "status": "missing",
            "answer": "结论：知识库暂无相关内容。\n知识库依据：未检索到足够相关的项目知识片段。\n解释：该问题可能超出当前项目背景、字段字典、指标定义、语义分析说明和运营策略文档范围。\n使用边界：请改问项目数据字段、指标口径、RFM、行为漏斗、评论语义分析样本或运营策略相关问题。",
            "sources": [],
        }

    source_lines = []
    explanation_parts = []
    for index, hit in enumerate(hits, start=1):
        source_lines.append(f"{index}. {hit.chunk.source} / {hit.chunk.heading}")
        explanation_parts.append(hit.chunk.content)

    answer = (
        "结论：可基于项目知识库回答该问题，以下解释只来自检索到的 Markdown 片段。\n"
        "知识库依据：\n"
        + "\n".join(source_lines)
        + "\n解释：\n"
        + "\n\n".join(explanation_parts)
        + "\n使用边界：RAG 只用于解释项目背景、字段含义、指标口径、样本说明和运营策略；结构化数据指标仍由本地 metrics.py 工具计算，不用 RAG 查询 75 万行 CSV。"
    )

    if any("语义" in hit.chunk.content or "semantic" in hit.chunk.source for hit in hits):
        answer += "\n注意：涉及评论语义分析时，当前口径是 960 条去重评论样本，不是全量评论。"

    return {
        "status": "ready",
        "answer": answer,
        "sources": _format_sources(hits),
    }
