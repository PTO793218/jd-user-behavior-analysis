from pathlib import Path

import pandas as pd

from agent_app.agent import answer_question, select_tools
from agent_app.data_loader import DataBundle
from agent_app.semantic_analysis import (
    ASPECT_LABELS,
    aggregate_semantic_results,
    extract_unique_comments,
    normalize_comment_text,
    _normalize_reasons,
)


def test_extract_unique_comments_filters_invalid_and_deduplicates():
    df = pd.DataFrame(
        {
            "comment": [
                "无评论",
                "",
                None,
                "  物流很慢，包装破损  ",
                "物流很慢，包装破损",
                "质量不错",
            ]
        }
    )

    comments = extract_unique_comments(df)

    assert comments["comment"].tolist() == ["物流很慢，包装破损", "质量不错"]
    assert comments["comment_hash"].is_unique


def test_normalize_comment_text_rejects_placeholder_values():
    assert normalize_comment_text(" 无评论 ") == ""
    assert normalize_comment_text("暂无评论") == ""
    assert normalize_comment_text(" 质量很好 ") == "质量很好"


def test_aggregate_semantic_results_counts_sentiment_aspects_and_reasons():
    detail = pd.DataFrame(
        [
            {
                "comment_hash": "1",
                "comment": "物流慢",
                "sentiment": "负面",
                "sentiment_score": -0.8,
                "aspects": "物流,服务",
                "negative_reasons": "配送慢",
            },
            {
                "comment_hash": "2",
                "comment": "质量好",
                "sentiment": "正面",
                "sentiment_score": 0.7,
                "aspects": "质量",
                "negative_reasons": "",
            },
            {
                "comment_hash": "3",
                "comment": "包装坏了",
                "sentiment": "负面",
                "sentiment_score": -0.6,
                "aspects": "包装",
                "negative_reasons": "包装破损",
            },
        ]
    )

    summary = aggregate_semantic_results(detail)

    aspect_rows = summary[summary["summary_type"] == "aspect"].set_index("name")
    sentiment_rows = summary[summary["summary_type"] == "sentiment"].set_index("name")

    assert "物流" in aspect_rows.index
    assert aspect_rows.loc["物流", "negative_count"] == 1
    assert sentiment_rows.loc["负面", "count"] == 2
    assert set(ASPECT_LABELS).issuperset({"质量", "物流", "价格", "服务", "包装", "售后", "体验"})


def test_normalize_reasons_accepts_model_json_arrays():
    assert _normalize_reasons(["配送慢", "包装破损"]) == "配送慢,包装破损"


def test_agent_routes_semantic_comment_questions():
    selected = select_tools("负面评论主要集中在哪些方面，质量和物流哪个更严重？")

    assert "comment_semantic" in selected
    assert "python" not in selected
    assert "sql" not in selected


def test_agent_reports_missing_semantic_file_without_breaking_v1(tmp_path: Path):
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
                    "comment": "无评论",
                }
            ]
        ),
        rfm=pd.DataFrame([{"user_id": 1, "R": 1, "F": 1, "M": 1, "label": "流失用户"}]),
        comments=pd.DataFrame([{"word": "质量", "count": 2}]),
    )

    missing_summary = tmp_path / "semantic_summary.csv"
    result = answer_question(
        "用户最不满意什么？",
        bundle=bundle,
        llm_config={"api_key": ""},
        semantic_summary_path=missing_summary,
    )

    assert result["used_llm"] is False
    assert "comment_semantic" in result["tool_names"]
    assert "当前模型不可用" in result["answer"]
    assert result["tool_results"]["comment_semantic"]["status"] == "missing"
    assert "语义分析结果尚未生成" in result["tool_results"]["comment_semantic"]["message"]
