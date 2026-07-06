from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_app.agent import answer_question, summarize_tool_results  # noqa: E402
from agent_app.data_loader import load_data, load_llm_config  # noqa: E402
from agent_app.metrics import (  # noqa: E402
    get_behavior_funnel,
    get_comment_semantic_summary,
    get_data_overview,
    get_daily_trend,
    get_rfm_summary,
)
from agent_app.rag import answer_knowledge_question  # noqa: E402
from agent_app.semantic_analysis import DEFAULT_DETAIL_CSV  # noqa: E402


SEMANTIC_SCOPE_NOTE = "评论语义分析当前基于 960 条去重评论样本，不是全量评论。"

FOLLOWUP_KEYWORDS = ["那", "这个", "该", "应该", "具体", "怎么做", "怎么办", "原因", "优先", "哪个"]
EXPLICIT_TOPIC_KEYWORDS = [
    "RFM",
    "rfm",
    "质量",
    "物流",
    "价格",
    "服务",
    "包装",
    "售后",
    "体验",
    "评论",
    "语义",
    "漏斗",
    "转化",
    "浏览",
    "购买",
    "地区",
    "设备",
    "小时",
    "时间",
    "趋势",
    "路径",
    "矩阵",
    "价格带",
    "预测",
    "实验",
    "A/B",
    "ab",
]


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.head(80).to_dict(orient="records")
    if isinstance(value, pd.Series):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def dumps_json(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, default=str)


def loads_json(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def semantic_sample_count() -> int:
    if DEFAULT_DETAIL_CSV.exists():
        try:
            return int(len(pd.read_csv(DEFAULT_DETAIL_CSV, usecols=["comment_hash"])))
        except Exception:
            return 960
    return 0


def model_status_payload() -> dict[str, Any]:
    config = load_llm_config()
    api_key = str(config.get("api_key") or "").strip()
    configured = bool(api_key and "your_" not in api_key.lower() and "api_key_here" not in api_key.lower())
    return {
        "configured": configured,
        "status": "connected" if configured else "missing_key",
        "model": config.get("model") or "",
        "base_url": config.get("base_url") or "",
        "provider": config.get("provider") or "OpenAI-compatible",
    }


def get_overview_payload() -> dict[str, Any]:
    bundle = load_data()
    overview = _jsonable(get_data_overview(bundle.behavior, bundle.rfm, bundle.comments))
    funnel = _jsonable(get_behavior_funnel(bundle.behavior))
    daily = _jsonable(get_daily_trend(bundle.behavior).tail(14))
    rfm = _jsonable(get_rfm_summary(bundle.rfm).head(10))

    overview["semantic_sample_count"] = semantic_sample_count()
    overview["semantic_scope_note"] = SEMANTIC_SCOPE_NOTE
    overview["model_status"] = model_status_payload()
    overview["charts"] = {
        "behavior_funnel": funnel,
        "daily_trend": daily,
        "rfm_summary": rfm,
        "behavior_counts": _jsonable(overview.get("behavior_counts", [])),
    }
    return overview


def get_semantic_summary_payload() -> dict[str, Any]:
    result = _jsonable(get_comment_semantic_summary())
    result["semantic_sample_count"] = semantic_sample_count()
    result["semantic_scope_note"] = SEMANTIC_SCOPE_NOTE
    return result


def run_agent(
    question: str,
    context: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    context = context or []
    routed_question = question
    if is_followup_question(question):
        context_text = "\n".join(
            item["content"]
            for item in context[-3:]
            if item.get("role") == "context" and item.get("content")
        )
        if context_text:
            routed_question = f"{question}\n\n追问上下文摘要：\n{context_text[:800]}"
    result = answer_question(routed_question)
    result["question"] = question
    return result


def is_followup_question(question: str) -> bool:
    text = question.strip()
    return any(keyword in text for keyword in FOLLOWUP_KEYWORDS) and not any(
        keyword in text for keyword in EXPLICIT_TOPIC_KEYWORDS
    )


def build_context_summary(
    messages: list[dict[str, str]],
    tool_calls: list[dict[str, Any]],
    max_turns: int = 3,
) -> str:
    if not messages and not tool_calls:
        return ""

    recent_messages = messages[-max_turns * 2 :]
    user_questions = [item["content"] for item in recent_messages if item.get("role") == "user"]
    assistant_answers = [item["content"] for item in recent_messages if item.get("role") == "assistant"]
    tools = [item.get("tool_name", "") for item in tool_calls[-8:] if item.get("tool_name")]
    unique_tools = list(dict.fromkeys(tools))

    parts: list[str] = []
    if user_questions:
        parts.append("上一轮/最近问题：" + " | ".join(user_questions[-max_turns:]))
    if assistant_answers:
        parts.append("上一轮回答摘要：" + re.sub(r"\s+", " ", assistant_answers[-1])[:220])
    if unique_tools:
        parts.append("上一轮工具结果：" + "、".join(unique_tools))
    if tool_calls:
        last_tool = tool_calls[-1]
        preview = str(loads_json(str(last_tool.get("result_json", ""))))[:260]
        parts.append(f"最近关注对象：{last_tool.get('tool_name')} -> {preview}")
    return "\n".join(parts)


def routing_explanation(question: str, tool_names: list[str], context_summary: str = "") -> str:
    text = f"{question}\n{context_summary}"
    reasons: list[str] = []

    def add(reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)

    if "data_overview" in tool_names:
        add("问题涉及概览、总体规模、多少、摘要或报告，因此调用 data_overview。")
    if "behavior_funnel" in tool_names:
        add("问题涉及漏斗、转化、流失、浏览高购买少，因此调用 behavior_funnel。")
    if "user_path_analysis" in tool_names:
        add("问题涉及购买路径、直接购买或路径流失，因此调用 user_path_analysis。")
    if "rfm_summary" in tool_names:
        add("问题涉及 RFM、用户分层、价值用户、召回或留存，因此调用 rfm_summary。")
    if "rfm_behavior_differences" in tool_names:
        add("问题涉及不同 RFM 用户层的行为差异、类目偏好或价格带偏好，因此调用 rfm_behavior_differences。")
    if "hourly_trend" in tool_names:
        add("问题涉及时间、小时、高峰、活动或促销时段，因此调用 hourly_trend。")
    if "daily_trend" in tool_names:
        add("问题涉及日期、每日或趋势变化，因此调用 daily_trend。")
    if "sales_forecast" in tool_names:
        add("问题涉及未来 24 小时、销售额预测或上升下降判断，因此调用 sales_forecast。")
    if "area_summary" in tool_names:
        add("问题涉及地区、城市、区域或销售额，因此调用 area_summary。")
    if "device_conversion" in tool_names:
        add("问题涉及设备、手机型号或终端转化差异，因此调用 device_conversion。")
    if "comment_keywords" in tool_names:
        add("问题涉及评论、评价、关键词或用户关注点，因此调用 comment_keywords。")
    if "comment_semantic" in tool_names:
        add("问题命中负面、不满意、差评、情感、方面、质量、物流、价格、服务、包装、售后或体验，因此调用 comment_semantic。")
    if "semantic_linkage" in tool_names:
        add("问题涉及评论语义问题在商品或类目维度的集中情况，因此调用 semantic_linkage。")
    if "top_categories" in tool_names:
        add("问题涉及品类、类目或商品类别，因此调用 top_categories。")
    if "operation_matrix" in tool_names:
        add("问题涉及高流量低转化、加大曝光、详情页优化或运营矩阵，因此调用 operation_matrix。")
    if "price_band_analysis" in tool_names:
        add("问题涉及价格带、客单价或不同价格区间转化，因此调用 price_band_analysis。")
    if "ab_test_plan" in tool_names:
        add("问题涉及 A/B 测试、实验方案或运营实验设计，因此调用 ab_test_plan。")
    if "rag" in tool_names:
        add("问题命中 RFM、定义、含义、口径、字段、为什么、样本、范围或运营策略，因此调用 rag 检索项目知识库。")
    if context_summary and is_followup_question(question):
        add("本轮是省略主语的追问，因此合并最近 3 轮会话和上一轮工具结果作为上下文。")

    if not reasons:
        add("未命中更细工具规则，使用默认数据概览和行为漏斗保证回答基于真实数据。")
    return "\n".join(f"- {reason}" for reason in reasons)


def confidence_for_result(
    tool_names: list[str],
    tool_results: dict[str, Any],
    error: str = "",
) -> dict[str, str]:
    error_note = "；大模型调用失败，本轮回答使用本地降级模板生成" if error else ""
    if not tool_names:
        return {"level": "低", "reason": "缺少可用工具结果，只能给出有限方向性说明。"}

    rag_result = tool_results.get("rag")
    if isinstance(rag_result, dict) and rag_result.get("status") == "missing":
        return {"level": "低", "reason": f"知识库未检索到足够相关片段，当前依据不足{error_note}。"}

    if any(name == "comment_semantic" for name in tool_names):
        return {"level": "中", "reason": f"结论基于已生成的 960 条去重评论语义样本，适合发现方向但不是全量评论统计{error_note}。"}

    if any(name == "semantic_linkage" for name in tool_names):
        return {"level": "中", "reason": f"评论联动基于 960 条去重评论语义样本，并只关联能匹配到行为记录的评论，适合发现方向但不是全量评论统计{error_note}。"}

    if any(name == "sales_forecast" for name in tool_names):
        return {"level": "中", "reason": f"销售额预测使用短周期小时级历史数据和简单基线模型，只适合短期趋势辅助判断{error_note}。"}

    if any(name == "ab_test_plan" for name in tool_names):
        return {"level": "中", "reason": f"A/B 测试内容是基于历史诊断生成的实验方案，不代表已经执行或得到线上实验结论{error_note}。"}

    if any(name == "rag" for name in tool_names):
        structured = [name for name in tool_names if name != "rag"]
        if structured:
            return {"level": "中", "reason": f"回答同时使用结构化数据工具和知识库片段，口径解释可靠但含业务解读{error_note}。"}
        return {"level": "中", "reason": f"回答基于本地 Markdown 知识库片段，不直接重新计算结构化指标{error_note}。"}

    return {"level": "高", "reason": f"回答来自 metrics.py 固定工具的确定性统计结果{error_note}。"}


def visual_payloads_for_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for tool in tools:
        name = tool["name"]
        result = tool.get("result")
        if name == "data_overview" and isinstance(result, dict):
            counts = result.get("behavior_counts")
            if isinstance(counts, list):
                payloads.append(
                    {
                        "tool_name": name,
                        "type": "bar",
                        "title": "行为类型分布",
                        "data": counts,
                        "x_key": "name",
                        "y_key": "count",
                    }
                )
            else:
                payloads.append(
                    {
                        "tool_name": name,
                        "type": "metric_cards",
                        "title": "数据概览指标",
                        "data": [
                            {"name": "行为记录", "value": result.get("records", 0)},
                            {"name": "用户数", "value": result.get("users", 0)},
                            {"name": "商品数", "value": result.get("goods", 0)},
                            {"name": "RFM 用户", "value": result.get("rfm_users", 0)},
                            {"name": "语义样本", "value": result.get("semantic_sample_count", semantic_sample_count())},
                        ],
                    }
                )
        elif name == "behavior_funnel" and isinstance(result, list):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "bar",
                    "title": "行为漏斗",
                    "data": result,
                    "x_key": "name",
                    "y_key": "count",
                }
            )
        elif name == "rfm_summary" and isinstance(result, list):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "bar",
                    "title": "RFM 用户分层",
                    "data": result,
                    "x_key": "label",
                    "y_key": "user_count",
                }
            )
        elif name == "hourly_trend" and isinstance(result, list):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "line",
                    "title": "小时行为趋势",
                    "data": result,
                    "x_key": "hour",
                    "y_key": "records",
                }
            )
        elif name == "user_path_analysis" and isinstance(result, dict):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "table",
                    "title": "用户购买路径",
                    "data": result.get("path_table") or [],
                    "columns": [
                        {"key": "path", "label": "路径"},
                        {"key": "path_count", "label": "次数"},
                        {"key": "users", "label": "用户数"},
                        {"key": "conversion_rate", "label": "转化率"},
                    ],
                }
            )
            payloads.append(
                {
                    "tool_name": name,
                    "type": "table",
                    "title": "关键流失路径",
                    "data": result.get("dropoff_table") or [],
                    "columns": [
                        {"key": "name", "label": "流失停留行为"},
                        {"key": "dropoff_count", "label": "流失路径数"},
                        {"key": "dropoff_rate", "label": "占比"},
                    ],
                }
            )
        elif name == "operation_matrix" and isinstance(result, dict):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "matrix",
                    "title": "类目/商品运营矩阵",
                    "data": result.get("matrix_table") or [],
                    "columns": [
                        {"key": result.get("dimension") or "category_id", "label": "对象"},
                        {"key": "pv", "label": "PV"},
                        {"key": "buys", "label": "购买"},
                        {"key": "conversion_rate", "label": "转化率"},
                        {"key": "quadrant", "label": "象限"},
                        {"key": "suggestion", "label": "建议"},
                    ],
                }
            )
        elif name == "semantic_linkage" and isinstance(result, dict):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "table",
                    "title": "评论语义问题分布",
                    "data": result.get("aspect_table") or [],
                    "columns": [
                        {"key": "aspect", "label": "问题方面"},
                        {"key": "count", "label": "样本数"},
                        {"key": "negative_count", "label": "负面数"},
                        {"key": "negative_rate", "label": "负面率"},
                    ],
                }
            )
        elif name == "rfm_behavior_differences" and isinstance(result, dict):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "table",
                    "title": "RFM 分层行为差异",
                    "data": result.get("layer_table") or [],
                    "columns": [
                        {"key": "label", "label": "用户层"},
                        {"key": "users", "label": "用户数"},
                        {"key": "cart_rate", "label": "加购率"},
                        {"key": "purchase_rate", "label": "购买率"},
                        {"key": "avg_price", "label": "均价"},
                    ],
                }
            )
        elif name == "price_band_analysis" and isinstance(result, dict):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "bar",
                    "title": "价格带转化率",
                    "data": result.get("chart_data") or [],
                    "x_key": "price_band",
                    "y_key": "conversion_rate",
                }
            )
            payloads.append(
                {
                    "tool_name": name,
                    "type": "table",
                    "title": "价格带明细",
                    "data": result.get("band_table") or [],
                    "columns": [
                        {"key": "price_band", "label": "价格带"},
                        {"key": "pv", "label": "浏览"},
                        {"key": "buys", "label": "购买"},
                        {"key": "sales", "label": "销售额"},
                        {"key": "conversion_rate", "label": "转化率"},
                    ],
                }
            )
        elif name == "sales_forecast" and isinstance(result, dict):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "line",
                    "title": "未来 24 小时销售额预测",
                    "data": result.get("forecast") or [],
                    "x_key": "forecast_time",
                    "y_key": "predicted_sales",
                }
            )
        elif name == "ab_test_plan" and isinstance(result, dict):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "plan",
                    "title": "A/B 测试方案摘要",
                    "data": [
                        {
                            "experiment_goal": result.get("experiment_goal"),
                            "hypothesis": result.get("hypothesis"),
                            "groups": result.get("groups") or [],
                            "metrics": result.get("metrics") or [],
                            "traffic_split": result.get("traffic_split"),
                            "observation_period": result.get("observation_period"),
                            "success_criteria": result.get("success_criteria"),
                            "limit_note": result.get("limit_note"),
                        }
                    ],
                }
            )
        elif name == "comment_semantic" and isinstance(result, dict):
            sentiment = result.get("sentiment_summary")
            aspect = result.get("aspect_summary")
            if isinstance(sentiment, list):
                payloads.append(
                    {
                        "tool_name": name,
                        "type": "bar",
                        "title": "评论情绪分布",
                        "data": sentiment,
                        "x_key": "name",
                        "y_key": "count",
                    }
                )
            if isinstance(aspect, list):
                payloads.append(
                    {
                        "tool_name": name,
                        "type": "bar",
                        "title": "方面负面率排行",
                        "data": aspect,
                        "x_key": "name",
                        "y_key": "negative_rate",
                    }
                )
        elif name == "rag" and isinstance(result, dict):
            payloads.append(
                {
                    "tool_name": name,
                    "type": "references",
                    "title": "RAG 来源片段",
                    "data": result.get("sources") or [],
                }
            )
    return payloads


def normalize_agent_result(raw: dict[str, Any], context_summary: str = "") -> dict[str, Any]:
    tool_results = raw.get("tool_results") or {}
    tool_names = raw.get("tool_names") or list(tool_results.keys())
    tools = [
        {"name": name, "result": _jsonable(tool_results.get(name))}
        for name in tool_names
        if name in tool_results
    ]

    rag_sources: list[dict[str, Any]] = []
    rag_result = tool_results.get("rag")
    if isinstance(rag_result, dict):
        rag_sources = _jsonable(rag_result.get("sources") or [])

    answer = str(raw.get("answer") or "")
    if ("comment_semantic" in tool_names or "semantic_linkage" in tool_names) and "960" not in answer:
        answer = f"{answer}\n\n注意：{SEMANTIC_SCOPE_NOTE}"

    routing = routing_explanation(str(raw.get("question") or ""), tool_names, context_summary=context_summary)
    tool_plan = raw.get("tool_plan")
    if isinstance(tool_plan, dict) and tool_plan.get("reason"):
        prefix = "- 模型工具规划：" if tool_plan.get("used_llm") else "- 保底工具规划："
        routing = f"{prefix}{tool_plan.get('reason')}\n{routing}"
    confidence = confidence_for_result(tool_names, tool_results, error=raw.get("error") or "")
    visual_payloads = visual_payloads_for_tools(tools)
    evidence_summary = raw.get("evidence_summary")
    if not isinstance(evidence_summary, list):
        evidence_summary = summarize_tool_results(tool_results)
    agent_trace = raw.get("agent_trace")
    if not isinstance(agent_trace, dict):
        tool_plan = raw.get("tool_plan") if isinstance(raw.get("tool_plan"), dict) else {}
        agent_trace = {
            "intent": tool_plan.get("answer_intent") or "diagnosis",
            "planned_tools": tool_names,
            "planning_reason": tool_plan.get("reason") or "",
            "planning_used_llm": bool(tool_plan.get("used_llm")),
            "model_status": "connected" if raw.get("used_llm") else "unavailable",
            "evidence_summary": evidence_summary,
        }
    else:
        agent_trace = {**agent_trace, "evidence_summary": agent_trace.get("evidence_summary") or evidence_summary}

    return {
        "answer": answer,
        "tools": tools,
        "rag_sources": rag_sources,
        "used_llm": bool(raw.get("used_llm")),
        "error": raw.get("error") or "",
        "routing_explanation": routing,
        "confidence": confidence,
        "context_summary": context_summary,
        "visual_payloads": visual_payloads,
        "evidence_summary": evidence_summary,
        "agent_trace": agent_trace,
    }


def rag_search(query: str, top_k: int = 3) -> dict[str, Any]:
    return _jsonable(answer_knowledge_question(query, top_k=top_k))


def ambiguous_followup_response(question: str, session_id: str, context_summary: str = "") -> dict[str, Any]:
    answer = (
        "结论：当前问题缺少明确分析对象，暂时无法判断应该优先优化哪个环节。\n"
        "数据依据：本轮没有可复用的上一轮工具结果，也未指定质量、物流、RFM、漏斗、地区或设备等对象。\n"
        "原因分析：这是省略主语的追问，需要依赖上一轮上下文；当前会话没有足够上下文。\n"
        "运营建议：请补充要比较或优化的对象，例如“质量和物流应该优先优化哪个？”或“漏斗里哪一步优先优化？”。"
    )
    return {
        "session_id": session_id,
        "answer": answer,
        "tools": [],
        "rag_sources": [],
        "used_llm": False,
        "error": "",
        "routing_explanation": "- 本轮问题是省略主语的追问，但当前会话没有可用上下文，因此不调用数据工具，避免编造结论。",
        "confidence": {"level": "低", "reason": "缺少明确分析对象和上一轮上下文，当前数据不足以判断。"},
        "context_summary": context_summary,
        "visual_payloads": [],
        "evidence_summary": [],
        "agent_trace": {
            "intent": "clarification",
            "planned_tools": [],
            "planning_reason": "追问缺少可复用上下文，未调用数据工具。",
            "planning_used_llm": False,
            "model_status": "not_called",
            "evidence_summary": [],
        },
    }


def generate_session_report(detail: dict[str, Any]) -> str:
    session = detail["session"]
    messages = detail["messages"]
    tool_calls = detail["tool_calls"]

    questions = [message["content"] for message in messages if message["role"] == "user"]
    answers = [message["content"] for message in messages if message["role"] == "assistant"]
    tools = list(dict.fromkeys(call["tool_name"] for call in tool_calls))

    rag_sources: list[str] = []
    tool_lines: list[str] = []
    saved_tool_results: dict[str, Any] = {}
    for call in tool_calls:
        payload = loads_json(call["result_json"])
        saved_tool_results[call["tool_name"]] = payload
        tool_lines.append(f"- `{call['tool_name']}`：{str(payload)[:240]}")
        if call["tool_name"] == "rag" and isinstance(payload, dict):
            for source in payload.get("sources") or []:
                rag_sources.append(f"- {source.get('source')} / {source.get('heading')}")
    evidence_lines = [
        f"- {item.get('label')}：{item.get('value')}（来源：`{item.get('source')}`；{item.get('note') or '本地工具结果'}）"
        for item in summarize_tool_results(saved_tool_results)
    ]
    tool_chain_lines = [f"- `{name}`" for name in tools]

    latest_answer = answers[-1] if answers else "当前会话尚无 Agent 回答。"
    semantic_note = ""
    if "comment_semantic" in tools or "语义" in "\n".join(questions) or "评论" in "\n".join(questions):
        semantic_note = f"\n- {SEMANTIC_SCOPE_NOTE}"

    return "\n".join(
        [
            "# 京东用户行为分析报告",
            "",
            f"- 会话：{session['title']}",
            f"- 生成范围：当前 SQLite 会话内的 {len(questions)} 个用户问题和 {len(tool_calls)} 次工具调用。",
            "",
            "## 分析问题",
            "\n".join(f"- {question}" for question in questions) or "- 暂无问题。",
            "",
            "## 关键结论",
            latest_answer,
            "",
            "## Agent 工具链路",
            "\n".join(tool_chain_lines) if tool_chain_lines else "- 本会话未保存工具调用记录。",
            "",
            "## 关键证据摘要",
            "\n".join(evidence_lines) if evidence_lines else "- 当前会话工具结果不足以抽取稳定证据摘要，请查看原始工具结果。",
            "",
            "## 数据依据",
            "\n".join(tool_lines) if tool_lines else "- 暂无结构化工具结果。",
            "",
            "## RAG/知识库依据",
            "\n".join(rag_sources) if rag_sources else "- 本会话未调用 RAG，或未返回知识库来源片段。",
            "",
            "## 运营建议",
            "- 优先围绕已调用工具中的高风险环节制定运营动作。",
            "- 若结论来自评论语义分析，应先做小范围验证，再扩展到全量运营策略。",
            "",
            "## 风险与限制",
            "- 报告只基于当前会话中已经产生的问题、回答、工具调用和 RAG 来源。",
            "- 结构化指标来自本地 CSV 和 metrics.py 固定工具，不代表实时京东数据。",
            semantic_note or "- 未涉及评论语义分析时，不使用语义样本推断全量评论。",
        ]
    )
