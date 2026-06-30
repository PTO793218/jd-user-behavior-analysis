import pandas as pd

from agent_app.agent import answer_question, select_tools
from agent_app.data_loader import DataBundle
from agent_app.metrics import (
    get_area_summary,
    get_behavior_funnel,
    get_comment_keywords,
    get_data_overview,
    get_device_conversion,
    get_rfm_summary,
)


def sample_behavior_df():
    return pd.DataFrame(
        [
            {
                "user_id": 1,
                "goods_id": 101,
                "category_id": 11,
                "behavior": "pv",
                "timestamp": "2024-05-01 10:00:00",
                "date": "2024-05-01",
                "hour": 10,
                "address": "成都",
                "device": "iPhone",
                "sales": 0.0,
            },
            {
                "user_id": 1,
                "goods_id": 101,
                "category_id": 11,
                "behavior": "cart",
                "timestamp": "2024-05-01 10:05:00",
                "date": "2024-05-01",
                "hour": 10,
                "address": "成都",
                "device": "iPhone",
                "sales": 0.0,
            },
            {
                "user_id": 2,
                "goods_id": 102,
                "category_id": 12,
                "behavior": "pv",
                "timestamp": "2024-05-02 21:00:00",
                "date": "2024-05-02",
                "hour": 21,
                "address": "重庆",
                "device": "Redmi",
                "sales": 0.0,
            },
            {
                "user_id": 2,
                "goods_id": 102,
                "category_id": 12,
                "behavior": "buy",
                "timestamp": "2024-05-02 21:30:00",
                "date": "2024-05-02",
                "hour": 21,
                "address": "重庆",
                "device": "Redmi",
                "sales": 99.0,
            },
        ]
    )


def sample_rfm_df():
    return pd.DataFrame(
        [
            {"user_id": 1, "R": 1, "F": 3, "M": 199.0, "label": "核心价值用户"},
            {"user_id": 2, "R": 9, "F": 1, "M": 20.0, "label": "流失用户"},
        ]
    )


def sample_comment_df():
    return pd.DataFrame(
        [
            {"word": "质量", "count": 15},
            {"word": "物流", "count": 10},
        ]
    )


def test_overview_uses_real_columns_and_ranges():
    overview = get_data_overview(sample_behavior_df(), sample_rfm_df(), sample_comment_df())

    assert overview["records"] == 4
    assert overview["users"] == 2
    assert overview["goods"] == 2
    assert overview["date_range"] == "2024-05-01 至 2024-05-02"
    assert overview["rfm_users"] == 2


def test_behavior_funnel_calculates_counts_and_rates():
    funnel = get_behavior_funnel(sample_behavior_df())
    by_behavior = funnel.set_index("behavior")

    assert by_behavior.loc["pv", "count"] == 2
    assert by_behavior.loc["cart", "count"] == 1
    assert by_behavior.loc["buy", "pv_conversion_rate"] == 0.5


def test_rfm_area_device_and_keywords_are_structured():
    rfm = get_rfm_summary(sample_rfm_df())
    area = get_area_summary(sample_behavior_df())
    device = get_device_conversion(sample_behavior_df())
    keywords = get_comment_keywords(sample_comment_df(), top_n=1)

    assert set(["label", "user_count", "percentage", "suggestion"]).issubset(rfm.columns)
    assert area.iloc[0]["sales"] == 99.0
    assert device.set_index("device").loc["Redmi", "conversion_rate"] == 0.5
    assert keywords.iloc[0]["word"] == "质量"


def test_agent_selects_fixed_tools_without_freeform_code_execution():
    selected = select_tools("为什么浏览量高但购买少，哪一步流失严重？")

    assert "behavior_funnel" in selected
    assert "hourly_trend" in selected
    assert "python" not in selected
    assert "sql" not in selected


def test_agent_returns_template_answer_when_llm_is_unavailable():
    bundle = DataBundle(
        behavior=sample_behavior_df(),
        rfm=sample_rfm_df(),
        comments=sample_comment_df(),
    )

    result = answer_question("评论里用户最关注什么？", bundle=bundle, llm_config={"api_key": ""})

    assert result["used_llm"] is False
    assert "comment_keywords" in result["tool_names"]
    assert "结论" in result["answer"]
    assert "数据依据" in result["answer"]
    assert "原因分析" in result["answer"]
    assert "运营建议" in result["answer"]
