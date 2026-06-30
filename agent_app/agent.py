from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd
import requests

try:
    from .data_loader import DataBundle, load_data, load_llm_config
    from .metrics import (
        get_area_summary,
        get_behavior_funnel,
        get_comment_keywords,
        get_comment_semantic_summary,
        get_daily_trend,
        get_data_overview,
        get_device_conversion,
        get_hourly_trend,
        get_rfm_summary,
        get_top_categories,
    )
    from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
    from .rag import answer_knowledge_question, should_use_rag
except ImportError:  # pragma: no cover - Streamlit script fallback
    from data_loader import DataBundle, load_data, load_llm_config
    from metrics import (
        get_area_summary,
        get_behavior_funnel,
        get_comment_keywords,
        get_comment_semantic_summary,
        get_daily_trend,
        get_data_overview,
        get_device_conversion,
        get_hourly_trend,
        get_rfm_summary,
        get_top_categories,
    )
    from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
    from rag import answer_knowledge_question, should_use_rag


ToolRunner = Callable[[DataBundle], Any]


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
    if any(k in text for k in ["浏览", "购买少", "促销", "活动", "晚上", "高峰", "时间", "小时", "时段"]):
        add("hourly_trend")
    if any(k in text for k in ["日期", "每日", "趋势", "天"]):
        add("daily_trend")
    if any(k in text for k in ["rfm", "分层", "价值用户", "核心", "优惠券", "召回", "留存", "流失用户"]):
        add("rfm_summary")
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
    if any(k in text for k in ["品类", "类目", "商品类别"]):
        add("top_categories")
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
        "rfm_summary": lambda bundle: get_rfm_summary(bundle.rfm),
        "hourly_trend": lambda bundle: get_hourly_trend(bundle.behavior),
        "daily_trend": lambda bundle: get_daily_trend(bundle.behavior),
        "area_summary": lambda bundle: get_area_summary(bundle.behavior),
        "device_conversion": lambda bundle: get_device_conversion(bundle.behavior),
        "comment_keywords": lambda bundle: get_comment_keywords(bundle.comments),
        "comment_semantic": lambda bundle: get_comment_semantic_summary(summary_path=semantic_summary_path),
        "top_categories": lambda bundle: get_top_categories(bundle.behavior),
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
    for name in tool_names:
        runner = registry.get(name)
        if runner:
            results[name] = runner(bundle)
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


def _call_llm(question: str, tool_names: list[str], tool_results: dict[str, Any], config: dict[str, Any]) -> str:
    base_url = str(config.get("base_url") or "https://api.deepseek.com").rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": config.get("model") or "deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    question=question,
                    tool_names=", ".join(tool_names),
                    tool_payload=json.dumps({k: _jsonable(v) for k, v in tool_results.items()}, ensure_ascii=False, default=str),
                ),
            },
        ],
        "temperature": 0.2,
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


def answer_question(
    question: str,
    bundle: DataBundle | None = None,
    llm_config: dict[str, Any] | None = None,
    semantic_summary_path: Any = None,
) -> dict[str, Any]:
    data = bundle or load_data()
    config = llm_config if llm_config is not None else load_llm_config()
    tool_names = select_tools(question)
    tool_results = run_tools(
        tool_names,
        data,
        semantic_summary_path=semantic_summary_path,
        question=question,
    )

    if not _has_valid_api_key(config):
        return {
            "answer": _fallback_answer(question, tool_results),
            "tool_names": tool_names,
            "tool_results": tool_results,
            "used_llm": False,
            "error": "未配置有效 LLM_API_KEY，已使用模板化降级回答。",
        }

    try:
        answer = _call_llm(question, tool_names, tool_results, config)
        return {
            "answer": answer,
            "tool_names": tool_names,
            "tool_results": tool_results,
            "used_llm": True,
            "error": "",
        }
    except Exception as exc:
        return {
            "answer": _fallback_answer(question, tool_results),
            "tool_names": tool_names,
            "tool_results": tool_results,
            "used_llm": False,
            "error": f"大模型调用失败，已使用本地模板化回答。错误信息：{exc}",
        }
