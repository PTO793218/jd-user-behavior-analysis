from pathlib import Path

import pandas as pd

from agent_app.agent import answer_question, select_tools
from agent_app.data_loader import DataBundle
from agent_app.knowledge_base import chunk_markdown_text, load_knowledge_chunks
from agent_app.rag import answer_knowledge_question, retrieve, should_use_rag


def test_markdown_loader_chunks_by_heading_and_paragraph(tmp_path: Path):
    doc = tmp_path / "demo.md"
    doc.write_text(
        "# 项目说明\n\n## RFM 口径\n\nRFM 包含 Recency、Frequency、Monetary。\n\n第二段解释。\n",
        encoding="utf-8",
    )

    chunks = load_knowledge_chunks(tmp_path)

    assert chunks
    assert chunks[0].source == "demo.md"
    assert any(chunk.heading == "RFM 口径" for chunk in chunks)
    assert any("Recency" in chunk.content for chunk in chunks)


def test_chunk_markdown_keeps_heading_context():
    chunks = chunk_markdown_text(
        "# 文档\n\n## 行为漏斗\n\n浏览 pv -> 加购 cart -> 购买 buy。\n",
        source="metric.md",
    )

    assert chunks[0].heading == "文档"
    assert chunks[1].heading == "行为漏斗"
    assert chunks[2].heading == "行为漏斗"
    assert "浏览" in chunks[2].content


def test_retrieve_returns_relevant_top_k(tmp_path: Path):
    (tmp_path / "metric.md").write_text(
        "# 指标\n\n## RFM\n\nRFM 是用户价值模型。\n\n## 行为漏斗\n\n购买相对浏览转化率用于衡量转化。",
        encoding="utf-8",
    )

    chunks = load_knowledge_chunks(tmp_path)
    hits = retrieve("RFM 是什么含义？", chunks=chunks, top_k=2)

    assert hits[0].chunk.heading == "RFM"
    assert hits[0].score > 0


def test_answer_knowledge_question_requires_evidence(tmp_path: Path):
    (tmp_path / "semantic.md").write_text(
        "# 语义分析\n\n当前是 960 条去重评论样本，不是全量评论。",
        encoding="utf-8",
    )
    chunks = load_knowledge_chunks(tmp_path)

    answer = answer_knowledge_question("评论语义分析样本范围是什么？", chunks=chunks, top_k=3)
    miss = answer_knowledge_question("这个项目支持火星天气吗？", chunks=chunks, top_k=3)

    assert answer["status"] == "ready"
    assert "960 条去重评论样本" in answer["answer"]
    assert "不是全量评论" in answer["answer"]
    assert miss["status"] == "missing"
    assert "知识库暂无相关内容" in miss["answer"]


def test_agent_routes_rag_questions_and_preserves_metric_tools():
    assert should_use_rag("behavior 字段含义是什么？")
    assert "rag" in select_tools("behavior 字段含义是什么？")

    selected = select_tools("为什么浏览量高但购买少，这个转化率怎么计算？")
    assert "behavior_funnel" in selected
    assert "rag" in selected


def test_agent_can_answer_with_rag_without_breaking_data_tools():
    bundle = DataBundle(
        behavior=pd.DataFrame(
            [
                {
                    "user_id": 1,
                    "goods_id": 1,
                    "category_id": 1,
                    "behavior": "pv",
                    "timestamp": "2024-05-01 10:00:00",
                    "date": "2024-05-01",
                    "hour": 10,
                    "address": "成都",
                    "device": "iPhone",
                    "sales": 0,
                }
            ]
        ),
        rfm=pd.DataFrame([{"user_id": 1, "R": 1, "F": 1, "M": 1, "label": "流失用户"}]),
        comments=pd.DataFrame([{"word": "质量", "count": 2}]),
    )

    result = answer_question("RFM 是什么含义？", bundle=bundle, llm_config={"api_key": ""})

    assert "rag" in result["tool_names"]
    assert "rag" in result["tool_results"]
    assert "知识库依据" in result["answer"]
