from __future__ import annotations

import pandas as pd
import streamlit as st

from agent import answer_question
from data_loader import get_duckdb_connection, load_data, load_llm_config
from metrics import (
    get_area_summary,
    get_behavior_funnel,
    get_comment_keywords,
    get_comment_semantic_summary,
    get_data_overview,
    get_device_conversion,
    get_hourly_trend,
    get_rfm_summary,
)
from rag import answer_knowledge_question
from sample_questions import SAMPLE_QUESTIONS
from ui_state import QUESTION_INPUT_KEY, get_current_question, set_question_from_sample


st.set_page_config(page_title="京东用户行为分析 Agent", page_icon="JD", layout="wide")


@st.cache_data(show_spinner="正在加载本地 CSV 数据...")
def cached_data():
    return load_data()


def show_dataframe_chart(name: str, value):
    if isinstance(value, dict):
        if name == "rag":
            if value.get("status") == "missing":
                st.info(value.get("answer", "知识库暂无相关内容。"))
            return

        if value.get("status") == "missing":
            st.info(value.get("message", "语义分析结果尚未生成。"))
            return
        if "aspect_summary" in value:
            aspect = value.get("aspect_summary")
            sentiment = value.get("sentiment_summary")
            reasons = value.get("negative_reasons")
            if isinstance(sentiment, pd.DataFrame) and not sentiment.empty:
                st.subheader("情感分布")
                st.bar_chart(sentiment.set_index("name")["count"])
            if isinstance(aspect, pd.DataFrame) and not aspect.empty:
                st.subheader("方面负面数")
                st.bar_chart(aspect.set_index("name")["negative_count"])
            if isinstance(reasons, pd.DataFrame) and not reasons.empty:
                st.subheader("负面原因")
                st.bar_chart(reasons.set_index("name")["count"])
            return

        behavior_counts = value.get("behavior_counts")
        if isinstance(behavior_counts, pd.DataFrame) and not behavior_counts.empty:
            st.subheader("行为类型分布")
            st.bar_chart(behavior_counts.set_index("name")["count"])
        return

    if not isinstance(value, pd.DataFrame) or value.empty:
        st.info("该工具没有返回可展示的表格数据。")
        return

    chart_columns = {
        "behavior_funnel": ("name", "count", "行为漏斗"),
        "rfm_summary": ("label", "user_count", "RFM 用户分层"),
        "hourly_trend": ("hour", "records", "小时活跃趋势"),
        "daily_trend": ("date", "records", "每日活跃趋势"),
        "area_summary": ("address", "sales", "地区销售额"),
        "device_conversion": ("device", "conversion_rate", "设备转化率"),
        "comment_keywords": ("word", "count", "评论关键词"),
        "top_categories": ("category_id", "sales", "高销售额类目"),
    }
    chart = chart_columns.get(name)
    if chart:
        x_col, y_col, title = chart
        if x_col in value.columns and y_col in value.columns:
            st.subheader(title)
            st.bar_chart(value.set_index(x_col)[y_col])


def show_rag_sources(rag_result: dict):
    sources = rag_result.get("sources") or []
    if not sources:
        return
    st.subheader("参考片段")
    for index, source in enumerate(sources, start=1):
        with st.expander(f"{index}. {source['source']} / {source['heading']}  score={source['score']}"):
            st.write(source["content"])


def show_tool_results(tool_results: dict):
    for name, value in tool_results.items():
        expanded = name in {"behavior_funnel", "rfm_summary", "comment_semantic", "rag"}
        with st.expander(f"工具结果：{name}", expanded=expanded):
            show_dataframe_chart(name, value)
            if name == "rag" and isinstance(value, dict):
                st.markdown(value.get("answer", ""))
                show_rag_sources(value)
                continue

            if isinstance(value, pd.DataFrame):
                st.dataframe(value, use_container_width=True)
            elif isinstance(value, dict):
                for key, item in value.items():
                    if isinstance(item, pd.DataFrame) and not item.empty:
                        st.caption(key)
                        st.dataframe(item, use_container_width=True)
                simple_items = {k: v for k, v in value.items() if not isinstance(v, pd.DataFrame)}
                st.json(simple_items)


def main():
    st.title("京东用户行为分析 Agent")

    try:
        bundle = cached_data()
        overview = get_data_overview(bundle.behavior, bundle.rfm, bundle.comments)
    except Exception as exc:
        st.error(f"数据加载失败：{exc}")
        st.stop()

    llm_config = load_llm_config()
    if not llm_config.get("api_key") or "your_" in str(llm_config.get("api_key")).lower():
        st.info("当前未检测到有效 LLM_API_KEY，问答会使用本地模板化降级回答，图表和指标仍来自真实数据。")

    cards = st.columns(5)
    cards[0].metric("行为记录", f"{overview['records']:,}")
    cards[1].metric("用户数", f"{overview['users']:,}")
    cards[2].metric("商品数", f"{overview['goods']:,}")
    cards[3].metric("类目数", f"{overview['categories']:,}")
    cards[4].metric("RFM 用户", f"{overview['rfm_users']:,}")
    st.caption(f"数据时间范围：{overview['date_range']}")

    semantic = get_comment_semantic_summary()

    with st.sidebar:
        st.header("示例问题")
        for index, sample in enumerate(SAMPLE_QUESTIONS):
            if st.button(sample, key=f"sample_{index}", use_container_width=True):
                set_question_from_sample(st.session_state, sample)
        st.divider()
        st.header("分析能力")
        st.write("数据概览、行为漏斗、RFM 分层、小时/日期趋势、地区销售、设备转化、评论关键词、评论语义分析、项目知识库 RAG。")
        if semantic["status"] == "ready":
            st.success("评论语义结果已加载")
        else:
            st.warning("评论语义结果尚未生成")
            st.code("python agent_app\\semantic_analysis.py", language="powershell")
        try:
            con = get_duckdb_connection(bundle)
            table_count = con.execute("select count(*) from jd_behavior").fetchone()[0]
            con.close()
            st.caption(f"DuckDB 已注册内存表 jd_behavior：{table_count:,} 行")
        except Exception as exc:
            st.caption(f"DuckDB 未启用：{exc}")

    tab_ask, tab_dashboard, tab_semantic, tab_rag = st.tabs(
        ["自然语言问数", "固定分析看板", "评论语义分析", "项目知识库 RAG"]
    )

    with tab_ask:
        get_current_question(st.session_state, SAMPLE_QUESTIONS[0])
        question = st.text_area("请输入业务问题", key=QUESTION_INPUT_KEY, height=90)
        if st.button("开始分析", type="primary"):
            if not question.strip():
                st.warning("请输入一个业务问题。")
            else:
                with st.spinner("正在选择工具并计算真实指标..."):
                    result = answer_question(question.strip(), bundle=bundle, llm_config=llm_config)
                if result["error"]:
                    st.warning(result["error"])
                st.markdown(result["answer"])
                st.caption("已调用工具：" + "、".join(result["tool_names"]))
                show_tool_results(result["tool_results"])

    with tab_dashboard:
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("行为漏斗")
            funnel = get_behavior_funnel(bundle.behavior)
            st.bar_chart(funnel.set_index("name")["count"])
            st.dataframe(funnel, use_container_width=True)

            st.subheader("小时活跃趋势")
            hourly = get_hourly_trend(bundle.behavior)
            st.line_chart(hourly.set_index("hour")["records"])

            st.subheader("评论关键词")
            keywords = get_comment_keywords(bundle.comments, top_n=15)
            st.bar_chart(keywords.set_index("word")["count"])

        with col_right:
            st.subheader("RFM 用户分层")
            rfm = get_rfm_summary(bundle.rfm)
            st.bar_chart(rfm.set_index("label")["user_count"])
            st.dataframe(rfm, use_container_width=True)

            st.subheader("地区销售额")
            area = get_area_summary(bundle.behavior, top_n=10)
            st.bar_chart(area.set_index("address")["sales"])

            st.subheader("设备转化率")
            device = get_device_conversion(bundle.behavior)
            st.bar_chart(device.set_index("device")["conversion_rate"])

    with tab_semantic:
        st.subheader("评论语义分析")
        if semantic["status"] == "missing":
            st.warning(semantic["message"])
            st.code("python agent_app\\semantic_analysis.py --batch-size 20", language="powershell")
        else:
            show_dataframe_chart("comment_semantic", semantic)
            st.info("语义分析口径：当前是 960 条去重评论样本，不是全量评论。")
            for key in ["sentiment_summary", "aspect_summary", "negative_reasons", "negative_examples"]:
                value = semantic.get(key)
                if isinstance(value, pd.DataFrame) and not value.empty:
                    st.caption(key)
                    st.dataframe(value, use_container_width=True)

    with tab_rag:
        st.subheader("项目知识库 RAG")
        rag_question = st.text_input("请输入项目知识问题", value="RFM 是什么含义？")
        top_k = st.slider("参考片段数量", min_value=1, max_value=5, value=3)
        if st.button("检索知识库"):
            result = answer_knowledge_question(rag_question.strip(), top_k=top_k)
            st.markdown(result["answer"])
            show_rag_sources(result)


if __name__ == "__main__":
    main()
