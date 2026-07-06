from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd
import requests

try:
    from .data_loader import DataBundle, load_data, load_llm_config
    from .metrics import (
        get_ab_test_plan,
        get_area_summary,
        get_behavior_funnel,
        get_comment_keywords,
        get_comment_semantic_summary,
        get_daily_trend,
        get_data_overview,
        get_device_conversion,
        get_hourly_trend,
        get_operation_matrix,
        get_price_band_analysis,
        get_rfm_behavior_differences,
        get_rfm_summary,
        get_sales_forecast,
        get_semantic_linkage_analysis,
        get_top_categories,
        get_user_path_analysis,
    )
    from .prompts import (
        ANALYST_SYSTEM_PROMPT,
        ANALYST_USER_PROMPT,
        TOOL_PLANNER_SYSTEM_PROMPT,
        TOOL_PLANNER_USER_PROMPT,
    )
    from .rag import answer_knowledge_question, should_use_rag
except ImportError:  # pragma: no cover - Streamlit script fallback
    from data_loader import DataBundle, load_data, load_llm_config
    from metrics import (
        get_ab_test_plan,
        get_area_summary,
        get_behavior_funnel,
        get_comment_keywords,
        get_comment_semantic_summary,
        get_daily_trend,
        get_data_overview,
        get_device_conversion,
        get_hourly_trend,
        get_operation_matrix,
        get_price_band_analysis,
        get_rfm_behavior_differences,
        get_rfm_summary,
        get_sales_forecast,
        get_semantic_linkage_analysis,
        get_top_categories,
        get_user_path_analysis,
    )
    from prompts import (
        ANALYST_SYSTEM_PROMPT,
        ANALYST_USER_PROMPT,
        TOOL_PLANNER_SYSTEM_PROMPT,
        TOOL_PLANNER_USER_PROMPT,
    )
    from rag import answer_knowledge_question, should_use_rag


ToolRunner = Callable[[DataBundle], Any]

AVAILABLE_TOOL_NAMES = {
    "data_overview",
    "behavior_funnel",
    "user_path_analysis",
    "operation_matrix",
    "comment_keywords",
    "comment_semantic",
    "semantic_linkage",
    "rfm_summary",
    "rfm_behavior_differences",
    "price_band_analysis",
    "hourly_trend",
    "daily_trend",
    "area_summary",
    "device_conversion",
    "top_categories",
    "sales_forecast",
    "ab_test_plan",
    "rag",
}

_TOOL_RESULT_CACHE: dict[tuple[str, int, int, int, str], Any] = {}


def select_tools(question: str) -> list[str]:
    text = question.lower()
    selected: list[str] = []

    def add(*names: str) -> None:
        for name in names:
            if name not in selected:
                selected.append(name)

    if any(k in text for k in ["概览", "总体", "摘要", "报告", "多少", "规模"]):
        add("data_overview")
    if any(k in text for k in ["漏斗", "转化", "流失", "浏览量高", "购买少", "购买低", "转化率"]):
        add("behavior_funnel")
    if any(k in text for k in ["购买路径", "常见路径", "路径流失", "直接购买", "从浏览到购买", "首次浏览到购买"]):
        add("user_path_analysis")
    if any(k in text for k in ["浏览", "购买少", "促销", "活动", "晚上", "高峰", "时间", "小时", "时段"]):
        add("hourly_trend")
    if any(k in text for k in ["日期", "每日", "趋势", "天"]):
        add("daily_trend")
    if any(k in text for k in ["未来 24", "未来24", "预测", "接下来", "可能上升", "可能下降"]):
        add("sales_forecast")
    if any(k in text for k in ["rfm", "分层", "价值用户", "核心", "优惠券", "召回", "留存", "流失用户"]):
        add("rfm_summary")
    if any(k in text for k in ["行为差异", "价格带偏好", "高潜力用户", "重点保持用户更偏好", "核心价值用户和流失用户"]):
        add("rfm_behavior_differences")
    if any(k in text for k in ["地区", "城市", "区域", "省", "销售额", "地域"]):
        add("area_summary")
    if any(k in text for k in ["设备", "手机", "iphone", "redmi", "安卓", "转化差异"]):
        add("device_conversion")
    if any(k in text for k in ["评论", "评价", "关键词", "关注", "词频", "问题"]):
        add("comment_keywords")
    if any(
        k in text
        for k in [
            "负面",
            "不满意",
            "差评",
            "情感",
            "语义",
            "方面",
            "原因",
            "质量",
            "物流",
            "价格",
            "服务",
            "包装",
            "售后",
            "体验",
        ]
    ):
        add("comment_semantic")
    if any(k in text for k in ["主要集中在哪些", "联动", "优先优化", "售后负面", "物流更严重", "质量问题"]):
        add("semantic_linkage")
    if any(k in text for k in ["品类", "类目", "商品类别"]):
        add("top_categories")
    if any(k in text for k in ["高流量低转化", "高流量高转化", "低流量高转化", "低流量低转化", "运营矩阵", "加大曝光", "详情页"]):
        add("operation_matrix")
    if any(k in text for k in ["价格带", "高客单价", "客单价", "价格区间"]):
        add("price_band_analysis")
    if any(k in text for k in ["a/b", "ab测试", "a/b 测试", "实验方案", "运营实验", "测试方案"]):
        add("ab_test_plan")
    if should_use_rag(question):
        add("rag")
    if any(k in text for k in ["摘要", "报告"]):
        add(
            "behavior_funnel",
            "rfm_summary",
            "hourly_trend",
            "area_summary",
            "device_conversion",
            "comment_keywords",
        )
    if not selected:
        add("data_overview", "behavior_funnel")
    return selected


def _tool_registry(
    semantic_summary_path: Any = None,
    question: str = "",
) -> dict[str, ToolRunner]:
    return {
        "data_overview": lambda bundle: get_data_overview(bundle.behavior, bundle.rfm, bundle.comments),
        "behavior_funnel": lambda bundle: get_behavior_funnel(bundle.behavior),
        "user_path_analysis": lambda bundle: get_user_path_analysis(bundle.behavior),
        "rfm_summary": lambda bundle: get_rfm_summary(bundle.rfm),
        "rfm_behavior_differences": lambda bundle: get_rfm_behavior_differences(bundle.behavior, bundle.rfm),
        "hourly_trend": lambda bundle: get_hourly_trend(bundle.behavior),
        "daily_trend": lambda bundle: get_daily_trend(bundle.behavior),
        "sales_forecast": lambda bundle: get_sales_forecast(bundle.behavior),
        "area_summary": lambda bundle: get_area_summary(bundle.behavior),
        "device_conversion": lambda bundle: get_device_conversion(bundle.behavior),
        "comment_keywords": lambda bundle: get_comment_keywords(bundle.comments),
        "comment_semantic": lambda bundle: get_comment_semantic_summary(summary_path=semantic_summary_path),
        "semantic_linkage": lambda bundle: get_semantic_linkage_analysis(bundle.behavior),
        "top_categories": lambda bundle: get_top_categories(bundle.behavior),
        "operation_matrix": lambda bundle: get_operation_matrix(bundle.behavior),
        "price_band_analysis": lambda bundle: get_price_band_analysis(bundle.behavior, bundle.rfm),
        "ab_test_plan": lambda bundle: get_ab_test_plan(question, bundle.behavior),
        "rag": lambda bundle: answer_knowledge_question(question),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.head(20).to_dict(orient="records")
    if isinstance(value, dict):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            converted[key] = item.head(20).to_dict(orient="records") if isinstance(item, pd.DataFrame) else item
        return converted
    return value


def run_tools(
    tool_names: list[str],
    bundle: DataBundle,
    semantic_summary_path: Any = None,
    question: str = "",
) -> dict[str, Any]:
    registry = _tool_registry(semantic_summary_path=semantic_summary_path, question=question)
    results: dict[str, Any] = {}
    cacheable_tools = {
        "data_overview",
        "behavior_funnel",
        "rfm_summary",
        "hourly_trend",
        "daily_trend",
        "area_summary",
        "device_conversion",
        "comment_keywords",
        "comment_semantic",
        "semantic_linkage",
        "top_categories",
        "operation_matrix",
        "price_band_analysis",
        "rfm_behavior_differences",
        "sales_forecast",
    }
    for name in tool_names:
        runner = registry.get(name)
        if runner:
            cache_key = (
                name,
                id(bundle.behavior),
                id(bundle.rfm),
                id(bundle.comments),
                str(semantic_summary_path),
            )
            if name in cacheable_tools and cache_key in _TOOL_RESULT_CACHE:
                results[name] = _TOOL_RESULT_CACHE[cache_key]
                continue
            result = runner(bundle)
            results[name] = result
            if name in cacheable_tools:
                _TOOL_RESULT_CACHE[cache_key] = result
    return results


def _format_number(value: Any) -> str:
    if isinstance(value, float):
        if 0 <= value <= 1:
            return f"{value:.2%}"
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _append_metric_evidence(tool_results: dict[str, Any], evidence: list[str]) -> None:
    overview = tool_results.get("data_overview")
    if isinstance(overview, dict):
        evidence.append(
            f"当前数据包含 {_format_number(overview.get('records', 0))} 条行为记录、"
            f"{_format_number(overview.get('users', 0))} 个用户，时间范围为 {overview.get('date_range', '未知')}。"
        )

    funnel = tool_results.get("behavior_funnel")
    if isinstance(funnel, pd.DataFrame) and not funnel.empty:
        buy_row = funnel[funnel["behavior"] == "buy"]
        if not buy_row.empty:
            evidence.append(f"购买相对浏览转化率为 {_format_number(float(buy_row.iloc[0]['pv_conversion_rate']))}。")

    rfm = tool_results.get("rfm_summary")
    if isinstance(rfm, pd.DataFrame) and not rfm.empty:
        top = rfm.iloc[0]
        evidence.append(
            f"RFM 人数最多的分层是 {top['label']}，用户数 {_format_number(int(top['user_count']))}，占比 {_format_number(float(top['percentage']))}。"
        )

    hourly = tool_results.get("hourly_trend")
    if isinstance(hourly, pd.DataFrame) and not hourly.empty:
        peak = hourly.sort_values("records", ascending=False).iloc[0]
        evidence.append(f"活跃峰值出现在 {int(peak['hour'])} 点，行为记录 {_format_number(int(peak['records']))} 条。")

    area = tool_results.get("area_summary")
    if isinstance(area, pd.DataFrame) and not area.empty:
        top = area.iloc[0]
        evidence.append(f"销售额最高地区是 {top['address']}，销售额 {_format_number(float(top['sales']))}。")

    device = tool_results.get("device_conversion")
    if isinstance(device, pd.DataFrame) and not device.empty:
        top = device.sort_values("conversion_rate", ascending=False).iloc[0]
        evidence.append(f"转化率最高设备是 {top['device']}，转化率 {_format_number(float(top['conversion_rate']))}。")

    comments = tool_results.get("comment_keywords")
    if isinstance(comments, pd.DataFrame) and not comments.empty:
        top_words = "、".join(comments.head(5)["word"].astype(str).tolist())
        evidence.append(f"评论高频关键词包括 {top_words}。")

    semantic = tool_results.get("comment_semantic")
    if isinstance(semantic, dict):
        if semantic.get("status") == "missing":
            evidence.append("语义分析结果尚未生成，当前无法回答负面方面占比和原因归因。")
        elif semantic.get("status") == "ready":
            aspect_summary = semantic.get("aspect_summary")
            sentiment_summary = semantic.get("sentiment_summary")
            negative_reasons = semantic.get("negative_reasons")
            if isinstance(aspect_summary, pd.DataFrame) and not aspect_summary.empty:
                top = aspect_summary.iloc[0]
                evidence.append(
                    f"负面更集中的方面是 {top['name']}，负面数 {_format_number(int(top['negative_count']))}，负面率 {_format_number(float(top['negative_rate']))}。"
                )
            if isinstance(sentiment_summary, pd.DataFrame) and not sentiment_summary.empty:
                parts = [
                    f"{row['name']} {_format_number(int(row['count']))} 条"
                    for _, row in sentiment_summary.iterrows()
                ]
                evidence.append("情感分布：" + "、".join(parts) + "。")
            if isinstance(negative_reasons, pd.DataFrame) and not negative_reasons.empty:
                reason = negative_reasons.iloc[0]
                evidence.append(f"最高频负面原因是 {reason['name']}，出现 {_format_number(int(reason['count']))} 次。")

    path = tool_results.get("user_path_analysis")
    if isinstance(path, dict):
        summary = path.get("summary") or {}
        if summary:
            evidence.append(
                f"路径样本 {_format_number(summary.get('path_instances', 0))} 个，路径购买转化率 "
                f"{_format_number(float(summary.get('path_conversion_rate', 0)))}，浏览后直接购买用户 "
                f"{_format_number(summary.get('direct_pv_buy_users', 0))} 个。"
            )

    matrix = tool_results.get("operation_matrix")
    if isinstance(matrix, dict):
        rows = matrix.get("matrix_table") or []
        risky = [row for row in rows if row.get("quadrant") == "高流量低转化"]
        if risky:
            top = risky[0]
            evidence.append(
                f"运营矩阵中存在高流量低转化对象 {top.get(matrix.get('dimension', 'category_id'))}，"
                f"PV {_format_number(top.get('pv', 0))}，转化率 {_format_number(float(top.get('conversion_rate', 0)))}。"
            )

    semantic_linkage = tool_results.get("semantic_linkage")
    if isinstance(semantic_linkage, dict) and semantic_linkage.get("status") == "ready":
        aspects = semantic_linkage.get("aspect_table") or []
        if aspects:
            top = aspects[0]
            evidence.append(
                f"评论语义联动基于 {semantic_linkage.get('sample_size', 0)} 条去重评论样本，"
                f"高频方面为 {top.get('aspect')}，负面数 {_format_number(top.get('negative_count', 0))}。"
            )

    rfm_diff = tool_results.get("rfm_behavior_differences")
    if isinstance(rfm_diff, dict):
        rows = rfm_diff.get("layer_table") or []
        if rows:
            top = rows[0]
            evidence.append(
                f"RFM 行为差异中人数最多分层为 {top.get('label')}，购买率 "
                f"{_format_number(float(top.get('purchase_rate', 0)))}，加购率 {_format_number(float(top.get('cart_rate', 0)))}。"
            )

    price_band = tool_results.get("price_band_analysis")
    if isinstance(price_band, dict):
        rows = price_band.get("band_table") or []
        if rows:
            top = sorted(rows, key=lambda row: row.get("conversion_rate", 0), reverse=True)[0]
            evidence.append(
                f"价格带分析中转化率最高区间为 {top.get('price_band')}，转化率 "
                f"{_format_number(float(top.get('conversion_rate', 0)))}，销售额 {_format_number(float(top.get('sales', 0)))}。"
            )

    forecast = tool_results.get("sales_forecast")
    if isinstance(forecast, dict):
        summary = forecast.get("summary") or {}
        if summary:
            evidence.append(
                f"未来 24 小时销售额基线预测趋势为 {summary.get('trend')}，预测销售额合计 "
                f"{_format_number(float(summary.get('next_24h_predicted_sales', 0)))}；该结果仅适合短期趋势辅助判断。"
            )

    ab_plan = tool_results.get("ab_test_plan")
    if isinstance(ab_plan, dict):
        baseline = ab_plan.get("baseline") or {}
        evidence.append(
            f"A/B 测试方案状态为 {ab_plan.get('status')}，基线 PV {_format_number(baseline.get('pv', 0))}，"
            f"浏览到加购转化率 {_format_number(float(baseline.get('pv_to_cart_rate', 0)))}；尚未执行真实实验。"
        )


def summarize_tool_results(tool_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Return compact business facts for the analyst prompt and API trace."""
    facts: list[dict[str, Any]] = []

    def add(label: str, value: Any, source: str, note: str = "") -> None:
        if value is None or value == "":
            return
        facts.append({"label": label, "value": value, "source": source, "note": note})

    overview = tool_results.get("data_overview")
    if isinstance(overview, dict):
        add("行为记录", overview.get("records"), "data_overview", "结构化历史行为数据")
        add("用户数", overview.get("users"), "data_overview", "结构化历史行为数据")
        add("商品数", overview.get("goods"), "data_overview", "结构化历史行为数据")
        add("时间范围", overview.get("date_range"), "data_overview", "不是实时数据")

    funnel = tool_results.get("behavior_funnel")
    if isinstance(funnel, pd.DataFrame) and not funnel.empty:
        buy_row = funnel[funnel["behavior"] == "buy"]
        if not buy_row.empty:
            add(
                "购买相对浏览转化率",
                _format_number(float(buy_row.iloc[0]["pv_conversion_rate"])),
                "behavior_funnel",
                "浏览到购买漏斗口径",
            )

    semantic = tool_results.get("comment_semantic")
    if isinstance(semantic, dict) and semantic.get("status") == "ready":
        add("语义样本规模", "960 条去重评论样本", "comment_semantic", "适合发现方向，不是全量评论统计")
        aspect_summary = semantic.get("aspect_summary")
        if isinstance(aspect_summary, pd.DataFrame) and not aspect_summary.empty:
            top = aspect_summary.iloc[0]
            add(
                "负面最高方面",
                f"{top.get('name')}，负面数 {_format_number(int(top.get('negative_count', 0)))}，负面率 {_format_number(float(top.get('negative_rate', 0)))}",
                "comment_semantic",
                "评论语义样本口径",
            )

    semantic_linkage = tool_results.get("semantic_linkage")
    if isinstance(semantic_linkage, dict) and semantic_linkage.get("status") == "ready":
        add("语义联动样本规模", f"{semantic_linkage.get('sample_size', 960)} 条去重评论样本", "semantic_linkage", "不是全量评论统计")
        aspects = semantic_linkage.get("aspect_table") or []
        if aspects:
            top = aspects[0]
            add(
                "高频评论问题",
                f"{top.get('aspect')}，负面数 {_format_number(top.get('negative_count', 0))}",
                "semantic_linkage",
                "按可关联样本统计",
            )

    path = tool_results.get("user_path_analysis")
    if isinstance(path, dict):
        summary = path.get("summary") or {}
        if summary:
            add("路径样本数", _format_number(summary.get("path_instances", 0)), "user_path_analysis", "用户行为路径口径")
            add("路径购买转化率", _format_number(float(summary.get("path_conversion_rate", 0))), "user_path_analysis")
            add("浏览后直接购买用户", _format_number(summary.get("direct_pv_buy_users", 0)), "user_path_analysis")

    matrix = tool_results.get("operation_matrix")
    if isinstance(matrix, dict):
        chart = matrix.get("chart_data") or []
        for row in chart:
            if row.get("quadrant") == "高流量低转化":
                add(
                    "高流量低转化规模",
                    f"{_format_number(row.get('count', 0))} 个对象，PV {_format_number(row.get('pv', 0))}",
                    "operation_matrix",
                    "按流量和转化率分象限",
                )
                break

    rfm_diff = tool_results.get("rfm_behavior_differences")
    if isinstance(rfm_diff, dict):
        rows = rfm_diff.get("layer_table") or []
        if rows:
            top = rows[0]
            add(
                "RFM 分层样本",
                f"{top.get('label')} 用户数 {_format_number(top.get('users', 0))}",
                "rfm_behavior_differences",
                "结构化行为数据与 RFM 分层结果",
            )

    price_band = tool_results.get("price_band_analysis")
    if isinstance(price_band, dict):
        rows = price_band.get("band_table") or []
        if rows:
            top = sorted(rows, key=lambda item: item.get("conversion_rate", 0), reverse=True)[0]
            add(
                "最高转化价格带",
                f"{top.get('price_band')}，转化率 {_format_number(float(top.get('conversion_rate', 0)))}",
                "price_band_analysis",
                price_band.get("bin_note", "按价格分箱统计"),
            )

    forecast = tool_results.get("sales_forecast")
    if isinstance(forecast, dict):
        summary = forecast.get("summary") or {}
        if summary:
            add(
                "未来 24 小时销售额趋势",
                f"{summary.get('trend')}，预测合计 {_format_number(float(summary.get('next_24h_predicted_sales', 0)))}",
                "sales_forecast",
                "短周期基线预测，只适合趋势辅助判断",
            )

    ab_plan = tool_results.get("ab_test_plan")
    if isinstance(ab_plan, dict):
        add("实验方案状态", ab_plan.get("status"), "ab_test_plan", "仅为基于历史诊断生成的实验方案，不是线上实验结论")
        baseline = ab_plan.get("baseline") or {}
        add("实验基线", f"PV {_format_number(baseline.get('pv', 0))}，浏览到加购 {_format_number(float(baseline.get('pv_to_cart_rate', 0)))}", "ab_test_plan")

    rag = tool_results.get("rag")
    if isinstance(rag, dict):
        add("RAG 来源数", len(rag.get("sources") or []), "rag", "只用于口径、背景和策略解释")

    return facts[:12]


def _build_agent_trace(
    plan: dict[str, Any],
    evidence_summary: list[dict[str, Any]],
    model_status: str,
) -> dict[str, Any]:
    return {
        "intent": str(plan.get("answer_intent") or "diagnosis"),
        "planned_tools": list(plan.get("tools") or []),
        "planning_reason": str(plan.get("reason") or ""),
        "planning_used_llm": bool(plan.get("used_llm")),
        "model_status": model_status,
        "evidence_summary": evidence_summary,
    }


def _rag_evidence(tool_results: dict[str, Any]) -> tuple[str, str]:
    rag = tool_results.get("rag")
    if not isinstance(rag, dict):
        return "", ""
    if rag.get("status") == "missing":
        return "- 知识库暂无相关内容。", rag.get("answer", "")

    sources = rag.get("sources") or []
    source_text = "\n".join(
        f"- {item.get('source')} / {item.get('heading')}" for item in sources[:3]
    )
    return source_text, rag.get("answer", "")


def _fallback_answer(question: str, tool_results: dict[str, Any]) -> str:
    evidence: list[str] = []
    _append_metric_evidence(tool_results, evidence)
    knowledge_sources, knowledge_answer = _rag_evidence(tool_results)

    evidence_text = "\n".join(f"- {item}" for item in evidence) or "- 当前工具未返回足够指标。"
    knowledge_section = ""
    if knowledge_answer:
        knowledge_section = f"\n\n知识库依据：\n{knowledge_sources}\n\n{knowledge_answer}"

    return f"""结论：
已根据固定分析工具和本地知识库回答“{question}”。当前未启用大模型解释层，因此返回模板化运营结论；所有数值均来自本地 CSV、已生成语义分析结果或知识库 Markdown。

数据依据：
{evidence_text}
{knowledge_section}

原因分析：
结构化数据问题由本地 metrics.py 工具计算；定义、含义、口径、字段、样本、范围和运营策略类问题由本地 RAG 检索知识库片段。若工具或知识库没有依据，应说明当前无法判断或知识库暂无相关内容。

运营建议：
优先基于真实指标定位问题，再结合知识库中的运营策略制定动作。涉及评论语义分析时，必须按知识库口径说明当前是 960 条去重评论样本，不是全量评论。"""


def _has_valid_api_key(config: dict[str, Any]) -> bool:
    api_key = str(config.get("api_key") or "").strip()
    return bool(api_key and "your_" not in api_key.lower() and "api_key_here" not in api_key.lower())


def _chat_completion(messages: list[dict[str, str]], config: dict[str, Any], temperature: float = 0.2) -> str:
    base_url = str(config.get("base_url") or "https://api.deepseek.com").rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": config.get("model") or "deepseek-v4-pro",
        "messages": messages,
        "temperature": temperature,
    }
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("planner response is not a JSON object")
    return value


def _normalize_planned_tools(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    selected: list[str] = []
    for item in value:
        name = str(item).strip()
        if name in AVAILABLE_TOOL_NAMES and name not in selected:
            selected.append(name)
    return selected[:4]


def _plan_tools_with_llm(question: str, config: dict[str, Any]) -> dict[str, Any]:
    content = _chat_completion(
        [
            {"role": "system", "content": TOOL_PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": TOOL_PLANNER_USER_PROMPT.format(question=question)},
        ],
        config,
        temperature=0.0,
    )
    plan = _extract_json_object(content)
    tools = _normalize_planned_tools(plan.get("tools"))
    if not tools:
        tools = select_tools(question)
    return {
        "tools": tools,
        "reason": str(plan.get("reason") or "模型根据问题意图选择了相关分析工具。"),
        "answer_intent": str(plan.get("answer_intent") or "diagnosis"),
        "used_llm": True,
    }


def _rag_sources_payload(tool_results: dict[str, Any]) -> list[dict[str, Any]]:
    rag = tool_results.get("rag")
    if isinstance(rag, dict):
        sources = rag.get("sources") or []
        if isinstance(sources, list):
            return sources[:5]
    return []


def _call_llm(
    question: str,
    tool_results: dict[str, Any],
    config: dict[str, Any],
    answer_intent: str = "diagnosis",
    evidence_summary: list[dict[str, Any]] | None = None,
) -> str:
    evidence_summary = evidence_summary or summarize_tool_results(tool_results)
    return _chat_completion(
        [
            {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": ANALYST_USER_PROMPT.format(
                    question=question,
                    answer_intent=answer_intent,
                    evidence_summary=json.dumps(evidence_summary, ensure_ascii=False, default=str),
                    tool_payload=json.dumps(
                        {key: _jsonable(value) for key, value in tool_results.items()},
                        ensure_ascii=False,
                        default=str,
                    ),
                    rag_sources=json.dumps(_rag_sources_payload(tool_results), ensure_ascii=False, default=str),
                ),
            },
        ],
        config,
        temperature=0.35,
    )


def answer_question(
    question: str,
    bundle: DataBundle | None = None,
    llm_config: dict[str, Any] | None = None,
    semantic_summary_path: Any = None,
) -> dict[str, Any]:
    data = bundle or load_data()
    config = llm_config if llm_config is not None else load_llm_config()

    if not _has_valid_api_key(config):
        tool_names = select_tools(question)
        tool_results = run_tools(
            tool_names,
            data,
            semantic_summary_path=semantic_summary_path,
            question=question,
        )
        evidence_summary = summarize_tool_results(tool_results)
        tool_plan = {
            "tools": tool_names,
            "reason": "模型不可用，暂时使用保守规则选择工具以便展示结构化结果。",
            "answer_intent": "diagnosis",
            "used_llm": False,
        }
        return {
            "answer": (
                "当前模型不可用，无法生成智能体分析回答。\n\n"
                "本轮已经完成必要的本地指标计算，右侧仍可查看工具结果；请配置有效的 "
                "`LLM_API_KEY` 后重新提问，系统会先由模型规划工具，再基于工具结果生成运营分析。"
            ),
            "tool_names": tool_names,
            "tool_results": tool_results,
            "used_llm": False,
            "tool_plan": tool_plan,
            "evidence_summary": evidence_summary,
            "agent_trace": _build_agent_trace(tool_plan, evidence_summary, "missing_key"),
            "error": "未配置有效 LLM_API_KEY，未生成模型分析回答。",
        }

    plan: dict[str, Any]
    try:
        plan = _plan_tools_with_llm(question, config)
    except Exception as exc:
        tool_names = select_tools(question)
        plan = {
            "tools": tool_names,
            "reason": f"模型工具规划失败，已使用保守规则选择工具。错误信息：{exc}",
            "answer_intent": "diagnosis",
            "used_llm": False,
        }

    tool_names = plan["tools"]
    tool_results = run_tools(
        tool_names,
        data,
        semantic_summary_path=semantic_summary_path,
        question=question,
    )
    evidence_summary = summarize_tool_results(tool_results)

    try:
        answer = _call_llm(
            question,
            tool_results,
            config,
            answer_intent=str(plan.get("answer_intent") or "diagnosis"),
            evidence_summary=evidence_summary,
        )
        return {
            "answer": answer,
            "tool_names": tool_names,
            "tool_results": tool_results,
            "used_llm": True,
            "tool_plan": plan,
            "evidence_summary": evidence_summary,
            "agent_trace": _build_agent_trace(plan, evidence_summary, "connected"),
            "error": "",
        }
    except Exception as exc:
        return {
            "answer": (
                "模型已完成工具规划和本地指标计算，但生成分析回答时失败。\n\n"
                "右侧仍可查看本轮工具结果。请检查模型服务、Key、模型名称或网络连接后重试。"
            ),
            "tool_names": tool_names,
            "tool_results": tool_results,
            "used_llm": False,
            "tool_plan": plan,
            "evidence_summary": evidence_summary,
            "agent_trace": _build_agent_trace(plan, evidence_summary, "analyst_failed"),
            "error": f"大模型分析回答失败，未生成模板化替代回答。错误信息：{exc}",
        }
