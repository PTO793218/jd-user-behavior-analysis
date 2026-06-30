from __future__ import annotations

from typing import Any

import pandas as pd

try:
    from .data_loader import load_data
    from .semantic_analysis import DEFAULT_DETAIL_CSV, DEFAULT_SUMMARY_CSV
except ImportError:  # pragma: no cover - Streamlit script fallback
    from data_loader import load_data
    from semantic_analysis import DEFAULT_DETAIL_CSV, DEFAULT_SUMMARY_CSV


BEHAVIOR_LABELS = {
    "pv": "浏览",
    "cart": "加购",
    "fav": "收藏",
    "buy": "购买",
}

RFM_SUGGESTIONS = {
    "核心价值用户": "重点维护，提供会员权益、新品优先购和高价值复购激励。",
    "重点保持用户": "保持触达频率，结合近期浏览和购买偏好推送个性化活动。",
    "重点发展用户": "提升购买频次，可通过组合优惠、满减券和关联推荐促进转化。",
    "重点挽留用户": "设置召回券和限时权益，优先验证价格敏感型促销。",
    "一般价值用户": "采用低成本自动化触达，持续观察活跃和复购变化。",
    "一般保持用户": "通过内容推荐和轻促销维持关系，避免过度补贴。",
    "一般发展用户": "加强商品匹配和新客任务，引导形成第二次购买。",
    "流失用户": "使用召回活动和原因调查，优先识别价格、体验或需求变化。",
}


def _safe_rate(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _behavior_df(df: pd.DataFrame | None = None) -> pd.DataFrame:
    return df if df is not None else load_data().behavior


def _rfm_df(df: pd.DataFrame | None = None) -> pd.DataFrame:
    return df if df is not None else load_data().rfm


def _comment_df(df: pd.DataFrame | None = None) -> pd.DataFrame:
    return df if df is not None else load_data().comments


def get_data_overview(
    behavior_df: pd.DataFrame | None = None,
    rfm_df: pd.DataFrame | None = None,
    comment_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    behavior = _behavior_df(behavior_df)
    rfm = _rfm_df(rfm_df)
    comments = _comment_df(comment_df)

    dates = pd.to_datetime(behavior["date"], errors="coerce").dropna()
    if dates.empty:
        date_range = "未知"
    else:
        date_range = f"{dates.min().date()} 至 {dates.max().date()}"

    behavior_counts = (
        behavior["behavior"].value_counts().rename_axis("behavior").reset_index(name="count")
    )
    behavior_counts["name"] = behavior_counts["behavior"].map(BEHAVIOR_LABELS).fillna(
        behavior_counts["behavior"]
    )

    return {
        "records": int(len(behavior)),
        "users": int(behavior["user_id"].nunique()),
        "goods": int(behavior["goods_id"].nunique()),
        "categories": int(behavior["category_id"].nunique()) if "category_id" in behavior else 0,
        "date_range": date_range,
        "behavior_types": sorted(behavior["behavior"].dropna().unique().tolist()),
        "behavior_counts": behavior_counts,
        "rfm_users": int(rfm["user_id"].nunique()),
        "comment_keywords": int(len(comments)),
    }


def get_behavior_funnel(df: pd.DataFrame | None = None) -> pd.DataFrame:
    behavior = _behavior_df(df)
    counts = behavior["behavior"].value_counts().to_dict()
    pv_count = int(counts.get("pv", 0))
    rows: list[dict[str, Any]] = []
    previous_count: int | None = None

    for stage, behavior_code in enumerate(["pv", "cart", "fav", "buy"], start=1):
        count = int(counts.get(behavior_code, 0))
        previous_rate = None if previous_count is None else _safe_rate(count, previous_count)
        rows.append(
            {
                "stage": stage,
                "behavior": behavior_code,
                "name": BEHAVIOR_LABELS[behavior_code],
                "count": count,
                "previous_conversion_rate": previous_rate,
                "pv_conversion_rate": _safe_rate(count, pv_count),
                "loss_rate_from_previous": None
                if previous_rate is None
                else round(1 - previous_rate, 4),
            }
        )
        previous_count = count

    return pd.DataFrame(rows)


def get_rfm_summary(df: pd.DataFrame | None = None) -> pd.DataFrame:
    rfm = _rfm_df(df)
    total = len(rfm)
    if total == 0:
        return pd.DataFrame(columns=["label", "user_count", "percentage", "avg_R", "avg_F", "avg_M", "suggestion"])

    summary = (
        rfm.groupby("label", as_index=False)
        .agg(user_count=("user_id", "nunique"), avg_R=("R", "mean"), avg_F=("F", "mean"), avg_M=("M", "mean"))
        .sort_values("user_count", ascending=False)
    )
    summary["percentage"] = (summary["user_count"] / total).round(4)
    for column in ["avg_R", "avg_F", "avg_M"]:
        summary[column] = summary[column].round(2)
    summary["suggestion"] = summary["label"].map(RFM_SUGGESTIONS).fillna(
        "结合活跃度、频次和消费金额设计差异化触达策略。"
    )
    return summary


def get_hourly_trend(df: pd.DataFrame | None = None) -> pd.DataFrame:
    behavior = _behavior_df(df)
    grouped = (
        behavior.groupby("hour", as_index=False)
        .agg(records=("behavior", "size"), users=("user_id", "nunique"), buys=("behavior", lambda s: int((s == "buy").sum())), sales=("sales", "sum"))
        .sort_values("hour")
    )
    grouped["conversion_rate"] = grouped.apply(lambda row: _safe_rate(row["buys"], row["records"]), axis=1)
    grouped["sales"] = grouped["sales"].round(2)
    return grouped


def get_daily_trend(df: pd.DataFrame | None = None) -> pd.DataFrame:
    behavior = _behavior_df(df).copy()
    behavior["date"] = pd.to_datetime(behavior["date"], errors="coerce").dt.date
    grouped = (
        behavior.groupby("date", as_index=False)
        .agg(records=("behavior", "size"), users=("user_id", "nunique"), buys=("behavior", lambda s: int((s == "buy").sum())), sales=("sales", "sum"))
        .sort_values("date")
    )
    grouped["conversion_rate"] = grouped.apply(lambda row: _safe_rate(row["buys"], row["records"]), axis=1)
    grouped["sales"] = grouped["sales"].round(2)
    return grouped


def get_area_summary(df: pd.DataFrame | None = None, top_n: int = 15) -> pd.DataFrame:
    behavior = _behavior_df(df)
    grouped = (
        behavior.groupby("address", as_index=False)
        .agg(records=("behavior", "size"), users=("user_id", "nunique"), buys=("behavior", lambda s: int((s == "buy").sum())), sales=("sales", "sum"))
        .sort_values(["sales", "records"], ascending=False)
        .head(top_n)
    )
    grouped["conversion_rate"] = grouped.apply(lambda row: _safe_rate(row["buys"], row["records"]), axis=1)
    grouped["avg_order_value"] = grouped.apply(lambda row: round(row["sales"] / row["buys"], 2) if row["buys"] else 0.0, axis=1)
    grouped["sales"] = grouped["sales"].round(2)
    return grouped


def get_device_conversion(df: pd.DataFrame | None = None) -> pd.DataFrame:
    behavior = _behavior_df(df)
    grouped = (
        behavior.groupby("device", as_index=False)
        .agg(records=("behavior", "size"), users=("user_id", "nunique"), buys=("behavior", lambda s: int((s == "buy").sum())), sales=("sales", "sum"))
        .sort_values("records", ascending=False)
    )
    grouped["conversion_rate"] = grouped.apply(lambda row: _safe_rate(row["buys"], row["records"]), axis=1)
    grouped["sales"] = grouped["sales"].round(2)
    return grouped


def get_comment_keywords(df: pd.DataFrame | None = None, top_n: int = 20) -> pd.DataFrame:
    comments = _comment_df(df)
    result = comments.sort_values("count", ascending=False).head(top_n).copy()
    total = result["count"].sum()
    result["percentage"] = result["count"].apply(lambda value: _safe_rate(value, total))
    return result.reset_index(drop=True)


def get_comment_semantic_summary(
    summary_path: str | None = None,
    detail_path: str | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    summary_csv = pd.io.common.stringify_path(summary_path or DEFAULT_SUMMARY_CSV)
    detail_csv = pd.io.common.stringify_path(detail_path or DEFAULT_DETAIL_CSV)

    if not pd.io.common.file_exists(summary_csv):
        return {
            "status": "missing",
            "message": "语义分析结果尚未生成，请先运行 python agent_app/semantic_analysis.py。",
            "summary_path": summary_csv,
            "detail_path": detail_csv,
            "sentiment_summary": pd.DataFrame(),
            "aspect_summary": pd.DataFrame(),
            "negative_reasons": pd.DataFrame(),
            "negative_examples": pd.DataFrame(),
        }

    summary = pd.read_csv(summary_csv)
    sentiment = summary[summary["summary_type"] == "sentiment"].sort_values("count", ascending=False)
    aspects = summary[summary["summary_type"] == "aspect"].sort_values(
        ["negative_count", "negative_rate", "count"], ascending=False
    )
    reasons = summary[summary["summary_type"] == "negative_reason"].sort_values("count", ascending=False)

    examples = pd.DataFrame()
    if pd.io.common.file_exists(detail_csv):
        detail = pd.read_csv(detail_csv)
        if not detail.empty and "sentiment" in detail.columns:
            examples = detail[detail["sentiment"] == "负面"].head(top_n).copy()
            keep_columns = [
                column
                for column in ["comment", "sentiment", "sentiment_score", "aspects", "negative_reasons"]
                if column in examples.columns
            ]
            examples = examples[keep_columns]

    return {
        "status": "ready",
        "message": "语义分析结果已加载。",
        "summary_path": summary_csv,
        "detail_path": detail_csv,
        "sentiment_summary": sentiment.head(top_n).reset_index(drop=True),
        "aspect_summary": aspects.head(top_n).reset_index(drop=True),
        "negative_reasons": reasons.head(top_n).reset_index(drop=True),
        "negative_examples": examples.reset_index(drop=True),
    }


def get_top_categories(df: pd.DataFrame | None = None, top_n: int = 10) -> pd.DataFrame:
    behavior = _behavior_df(df)
    if "category_id" not in behavior.columns:
        return pd.DataFrame(columns=["category_id", "records", "users", "buys", "sales"])
    grouped = (
        behavior.groupby("category_id", as_index=False)
        .agg(records=("behavior", "size"), users=("user_id", "nunique"), buys=("behavior", lambda s: int((s == "buy").sum())), sales=("sales", "sum"))
        .sort_values(["sales", "records"], ascending=False)
        .head(top_n)
    )
    grouped["conversion_rate"] = grouped.apply(lambda row: _safe_rate(row["buys"], row["records"]), axis=1)
    grouped["sales"] = grouped["sales"].round(2)
    return grouped
