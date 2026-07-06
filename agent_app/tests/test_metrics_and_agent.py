import pandas as pd

import agent_app.agent as agent_module
from agent_app.agent import answer_question, select_tools
from agent_app.data_loader import DataBundle
from agent_app.metrics import (
    get_area_summary,
    get_ab_test_plan,
    get_behavior_funnel,
    get_comment_keywords,
    get_operation_matrix,
    get_price_band_analysis,
    get_rfm_behavior_differences,
    get_sales_forecast,
    get_semantic_linkage_analysis,
    get_user_path_analysis,
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


def sample_bundle():
    return DataBundle(
        behavior=sample_behavior_df(),
        rfm=sample_rfm_df(),
        comments=sample_comment_df(),
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


def test_agent_reports_model_unavailable_without_fake_analysis():
    bundle = DataBundle(
        behavior=sample_behavior_df(),
        rfm=sample_rfm_df(),
        comments=sample_comment_df(),
    )

    result = answer_question("评论里用户最关注什么？", bundle=bundle, llm_config={"api_key": ""})

    assert result["used_llm"] is False
    assert "comment_keywords" in result["tool_names"]
    assert "当前模型不可用" in result["answer"]
    assert "模板化运营结论" not in result["answer"]
    assert result["tool_results"]


def test_agent_uses_llm_planner_before_analyst(monkeypatch):
    bundle = DataBundle(
        behavior=sample_behavior_df(),
        rfm=sample_rfm_df(),
        comments=sample_comment_df(),
    )
    calls: list[str] = []

    def fake_chat_completion(messages, config, temperature=0.2):
        system = messages[0]["content"]
        calls.append(system)
        if "工具规划器" in system:
            return '{"tools":["price_band_analysis"],"reason":"问题询问价格带转化，需要价格带分析。","answer_intent":"diagnosis"}'
        return "50-100 价格带的转化表现更值得关注，因为样例中该价格带有浏览和购买。"

    monkeypatch.setattr(agent_module, "_chat_completion", fake_chat_completion)

    result = answer_question("哪个价格带转化率最高？", bundle=bundle, llm_config={"api_key": "valid-key"})

    assert result["used_llm"] is True
    assert result["tool_names"] == ["price_band_analysis"]
    assert result["answer"].startswith("50-100")
    assert result["tool_plan"]["used_llm"] is True
    assert len(calls) == 2


def test_user_path_analysis_calculates_common_paths_and_direct_purchase():
    result = get_user_path_analysis(sample_behavior_df())

    assert result["summary"]["direct_pv_buy_users"] == 1
    assert result["summary"]["converted_paths"] == 1
    assert result["path_table"][0]["path"] in {"浏览 > 加购", "浏览 > 购买"}
    assert result["dropoff_table"]
    assert "结构化全量行为数据" in result["scope_note"]


def test_operation_matrix_segments_category_by_traffic_and_conversion():
    behavior = pd.concat(
        [
            sample_behavior_df(),
            pd.DataFrame(
                [
                    {
                        "user_id": 3,
                        "goods_id": 103,
                        "category_id": 11,
                        "behavior": "pv",
                        "timestamp": "2024-05-03 10:00:00",
                        "date": "2024-05-03",
                        "hour": 10,
                        "address": "成都",
                        "device": "iPhone",
                        "sales": 0.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    result = get_operation_matrix(behavior, dimension="category_id")

    assert result["dimension"] == "category_id"
    assert result["matrix_table"]
    assert {"高流量低转化", "低流量高转化", "高流量高转化", "低流量低转化"}.issuperset(
        {row["quadrant"] for row in result["matrix_table"]}
    )
    assert result["chart_data"]


def test_price_band_analysis_uses_goods_price_for_all_behaviors_and_rfm_layers():
    result = get_price_band_analysis(sample_behavior_df(), sample_rfm_df())

    row = next(item for item in result["band_table"] if item["price_band"] == "50-100")
    assert row["pv"] == 1
    assert row["buys"] == 1
    assert row["conversion_rate"] == 1.0
    assert result["rfm_distribution"]
    assert "商品成交价中位数" in result["scope_note"]


def test_rfm_behavior_differences_compare_layer_conversion_and_preferences():
    result = get_rfm_behavior_differences(sample_behavior_df(), sample_rfm_df())

    labels = {row["label"] for row in result["layer_table"]}
    assert {"核心价值用户", "流失用户"}.issubset(labels)
    lost = next(row for row in result["layer_table"] if row["label"] == "流失用户")
    assert lost["purchase_rate"] == 1.0
    assert "结构化行为数据与 RFM 分层结果" in result["scope_note"]


def test_semantic_linkage_analysis_states_960_sample_scope(tmp_path):
    detail_path = tmp_path / "comment_semantic_result.csv"
    detail_path.write_text(
        "comment_hash,comment,sentiment,sentiment_score,aspects,negative_reasons,model,analyzed_at\n"
        "a,质量不好,负面,0.2,质量,做工问题,m,now\n"
        "b,物流慢,负面,0.2,物流,配送慢,m,now\n",
        encoding="utf-8",
    )
    behavior = pd.DataFrame(
        [
            {
                "user_id": 1,
                "goods_id": 101,
                "category_id": 11,
                "behavior": "buy",
                "timestamp": "2024-05-01 10:00:00",
                "date": "2024-05-01",
                "hour": 10,
                "address": "成都",
                "device": "iPhone",
                "price": 10,
                "amount": 1,
                "comment": "质量不好",
                "sales": 10.0,
            }
        ]
    )

    result = get_semantic_linkage_analysis(behavior, detail_path=detail_path)

    assert result["sample_size"] == 2
    assert "960 条去重评论样本" in result["scope_note"]
    assert result["aspect_table"][0]["aspect"] == "质量"
    assert result["linked_category_table"][0]["category_id"] == 11


def test_sales_forecast_returns_next_24_hours_with_limit_note():
    result = get_sales_forecast(sample_behavior_df())

    assert result["method"] in {"linear_regression_baseline", "moving_average_baseline"}
    assert len(result["forecast"]) == 24
    assert {"forecast_time", "predicted_sales"}.issubset(result["forecast"][0])
    assert "短期趋势辅助判断" in result["scope_note"]


def test_ab_test_plan_is_a_proposed_experiment_not_completed_result():
    result = get_ab_test_plan("针对浏览到加购流失高设计一个 A/B 测试方案", sample_behavior_df())

    assert result["status"] == "proposal"
    assert result["experiment_goal"]
    assert "已完成" not in result["limit_note"]
    assert any(metric["name"] == "浏览到加购转化率" for metric in result["metrics"])


def test_agent_selects_v6_tools_by_business_questions():
    checks = {
        "用户最常见的购买路径是什么？": "user_path_analysis",
        "哪些类目属于高流量低转化？": "operation_matrix",
        "质量问题主要集中在哪些类目？": "semantic_linkage",
        "核心价值用户和流失用户有什么行为差异？": "rfm_behavior_differences",
        "哪个价格带转化率最高？": "price_band_analysis",
        "未来 24 小时销售额趋势如何？": "sales_forecast",
        "针对质量问题设计一个运营实验方案": "ab_test_plan",
    }

    for question, tool in checks.items():
        assert tool in select_tools(question)


def test_agent_returns_trace_and_evidence_when_model_is_unavailable():
    result = answer_question(
        "给我数据概览",
        bundle=sample_bundle(),
        llm_config={"api_key": "", "model": "test-model", "base_url": "https://example.test"},
    )

    assert result["used_llm"] is False
    assert result["agent_trace"]["model_status"] == "missing_key"
    assert result["agent_trace"]["planned_tools"]
    assert result["evidence_summary"]
    assert result["agent_trace"]["evidence_summary"] == result["evidence_summary"]


def test_agent_includes_evidence_summary_in_analyst_prompt(monkeypatch):
    calls: list[str] = []

    def fake_chat(messages, config, temperature=0.2):
        content = messages[-1]["content"]
        calls.append(content)
        if "工具规划器" in messages[0]["content"] or "tools" not in content:
            return '{"tools":["data_overview"],"reason":"need overview","answer_intent":"overview"}'
        return "概览回答"

    monkeypatch.setattr("agent_app.agent._chat_completion", fake_chat)

    result = answer_question(
        "给我数据概览",
        bundle=sample_bundle(),
        llm_config={"api_key": "valid-key", "model": "test-model", "base_url": "https://example.test"},
    )

    assert result["used_llm"] is True
    assert result["agent_trace"]["planning_used_llm"] is True
    assert result["evidence_summary"]
    assert any("关键事实摘要" in item for item in calls)
