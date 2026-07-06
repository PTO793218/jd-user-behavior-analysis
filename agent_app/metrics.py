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


def _records(df: pd.DataFrame, limit: int = 50) -> list[dict[str, Any]]:
    return df.head(limit).to_dict(orient="records")


def _ensure_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="coerce")
    return normalized.dropna(subset=["timestamp"])


def _price_enriched_behavior(df: pd.DataFrame) -> pd.DataFrame:
    behavior = df.copy()
    if "price" not in behavior.columns:
        behavior["price"] = 0.0
    behavior["price"] = pd.to_numeric(behavior["price"], errors="coerce").fillna(0.0)
    if "sales" in behavior.columns and "amount" in behavior.columns:
        sales = pd.to_numeric(behavior["sales"], errors="coerce").fillna(0.0)
        amount = pd.to_numeric(behavior["amount"], errors="coerce").fillna(0.0)
        derived_price = sales.divide(amount.where(amount > 0)).fillna(0.0)
        behavior.loc[behavior["price"] <= 0, "price"] = derived_price[behavior["price"] <= 0]
    elif "sales" in behavior.columns:
        sales = pd.to_numeric(behavior["sales"], errors="coerce").fillna(0.0)
        behavior.loc[behavior["price"] <= 0, "price"] = sales[behavior["price"] <= 0]
    bought_price = (
        behavior[(behavior["behavior"] == "buy") & (behavior["price"] > 0)]
        .groupby("goods_id")["price"]
        .median()
    )
    behavior["effective_price"] = behavior["goods_id"].map(bought_price).fillna(behavior["price"])
    return behavior


def _assign_price_band(price: float) -> str:
    if price < 50:
        return "0-50"
    if price < 100:
        return "50-100"
    if price < 200:
        return "100-200"
    if price < 500:
        return "200-500"
    return "500+"


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


def get_user_path_analysis(df: pd.DataFrame | None = None, top_n: int = 12) -> dict[str, Any]:
    behavior = _ensure_timestamp(_behavior_df(df))
    behavior = behavior[behavior["behavior"].isin(BEHAVIOR_LABELS)].copy()
    if behavior.empty:
        return {
            "summary": {},
            "path_table": [],
            "dropoff_table": [],
            "interval_table": [],
            "chart_data": [],
            "scope_note": "结构化全量行为数据为空，无法计算用户路径。",
        }

    first_seen = behavior.groupby(["user_id", "goods_id", "behavior"])["timestamp"].min().unstack()
    for column in BEHAVIOR_LABELS:
        if column not in first_seen.columns:
            first_seen[column] = pd.NaT
    first_seen = first_seen.reset_index()

    behavior_order = {"pv": 0, "cart": 1, "fav": 2, "buy": 3}
    path_rows: list[dict[str, Any]] = []
    for row in first_seen[["user_id", "goods_id", "pv", "cart", "fav", "buy"]].itertuples(index=False, name=None):
        user_id, goods_id, pv_time, cart_time, fav_time, buy_time = row
        raw_steps = [("pv", pv_time), ("cart", cart_time), ("fav", fav_time), ("buy", buy_time)]
        steps = [
            (code, ts)
            for code, ts in raw_steps
            if pd.notna(ts) and (pd.isna(buy_time) or ts <= buy_time)
        ]
        if not steps:
            continue
        steps = sorted(steps, key=lambda item: (item[1], behavior_order[item[0]]))
        codes = [code for code, _ in steps]
        path_rows.append(
            {
                "user_id": user_id,
                "goods_id": goods_id,
                "path": " > ".join(BEHAVIOR_LABELS.get(code, code) for code in codes),
                "last_behavior": codes[-1],
                "converted": "buy" in codes,
            }
        )

    path_df = pd.DataFrame(path_rows)
    if path_df.empty:
        return {
            "summary": {},
            "path_table": [],
            "dropoff_table": [],
            "interval_table": [],
            "chart_data": [],
            "scope_note": "结构化全量行为数据没有可识别路径。",
        }

    path_table = (
        path_df.groupby("path", as_index=False)
        .agg(path_count=("path", "size"), users=("user_id", "nunique"), converted_count=("converted", "sum"))
        .sort_values(["path_count", "converted_count"], ascending=False)
    )
    path_table["conversion_rate"] = path_table.apply(
        lambda row: _safe_rate(row["converted_count"], row["path_count"]), axis=1
    )

    interval_df = first_seen[["pv", "buy"]].rename(columns={"pv": "pv_time", "buy": "buy_time"}).dropna()
    interval_df = interval_df[interval_df["buy_time"] >= interval_df["pv_time"]]
    intervals = ((interval_df["buy_time"] - interval_df["pv_time"]).dt.total_seconds() / 3600).round(2)

    dropoff_df = path_df[~path_df["converted"]].copy()
    dropoff_table = pd.DataFrame(columns=["last_behavior", "name", "dropoff_count", "dropoff_rate"])
    if not dropoff_df.empty:
        dropoff_table = (
            dropoff_df.groupby("last_behavior", as_index=False)
            .agg(dropoff_count=("last_behavior", "size"))
            .sort_values("dropoff_count", ascending=False)
        )
        dropoff_table["name"] = dropoff_table["last_behavior"].map(BEHAVIOR_LABELS).fillna(dropoff_table["last_behavior"])
        dropoff_table["dropoff_rate"] = dropoff_table["dropoff_count"].apply(lambda value: _safe_rate(value, len(path_df)))

    interval_table = pd.DataFrame(
        [
            {
                "metric": "首次浏览到购买平均间隔",
                "hours": round(float(intervals.mean()), 2) if not intervals.empty else 0.0,
                "sample_paths": len(intervals),
            },
            {
                "metric": "首次浏览到购买中位间隔",
                "hours": round(float(intervals.median()), 2) if not intervals.empty else 0.0,
                "sample_paths": len(intervals),
            },
        ]
    )

    summary = {
        "path_instances": int(len(path_df)),
        "converted_paths": int(path_df["converted"].sum()),
        "path_conversion_rate": _safe_rate(path_df["converted"].sum(), len(path_df)),
        "direct_pv_buy_users": int(path_df[path_df["path"] == "浏览 > 购买"]["user_id"].nunique()),
        "avg_hours_from_first_pv_to_buy": float(interval_table.iloc[0]["hours"]),
    }
    return {
        "summary": summary,
        "path_table": _records(path_table, top_n),
        "dropoff_table": _records(dropoff_table, top_n),
        "interval_table": _records(interval_table),
        "chart_data": _records(path_table[["path", "path_count", "conversion_rate"]], top_n),
        "scope_note": "路径分析基于结构化全量行为数据，按 user_id + goods_id 统计各行为首次出现时间，并按时间形成浏览、加购、收藏、购买路径；静态历史数据不代表实时路径。",
    }


def get_operation_matrix(
    df: pd.DataFrame | None = None,
    dimension: str = "category_id",
    top_n: int = 30,
) -> dict[str, Any]:
    behavior = _behavior_df(df)
    dimension = dimension if dimension in {"category_id", "goods_id"} else "category_id"
    if dimension not in behavior.columns:
        return {
            "dimension": dimension,
            "summary": {},
            "matrix_table": [],
            "chart_data": [],
            "scope_note": f"结构化全量行为数据缺少 {dimension} 字段。",
        }

    grouped = (
        behavior.groupby(dimension, as_index=False)
        .agg(
            records=("behavior", "size"),
            users=("user_id", "nunique"),
            pv=("behavior", lambda s: int((s == "pv").sum())),
            cart=("behavior", lambda s: int((s == "cart").sum())),
            fav=("behavior", lambda s: int((s == "fav").sum())),
            buys=("behavior", lambda s: int((s == "buy").sum())),
            sales=("sales", "sum"),
        )
    )
    grouped["conversion_rate"] = grouped.apply(lambda row: _safe_rate(row["buys"], row["pv"]), axis=1)
    traffic_threshold = float(grouped["pv"].median()) if not grouped.empty else 0.0
    positive_conversion = grouped[grouped["conversion_rate"] > 0]["conversion_rate"]
    conversion_threshold = float(positive_conversion.median()) if not positive_conversion.empty else 0.0

    def quadrant(row: pd.Series) -> str:
        high_traffic = row["pv"] >= traffic_threshold
        high_conversion = row["conversion_rate"] >= conversion_threshold if conversion_threshold > 0 else row["conversion_rate"] > 0
        if high_traffic and high_conversion:
            return "高流量高转化"
        if high_traffic and not high_conversion:
            return "高流量低转化"
        if not high_traffic and high_conversion:
            return "低流量高转化"
        return "低流量低转化"

    suggestions = {
        "高流量高转化": "保持曝光和库存稳定，优先沉淀为标杆商品/类目。",
        "高流量低转化": "优先检查详情页、价格、评价和促销承接，减少流量浪费。",
        "低流量高转化": "适合加大曝光、搜索推荐和活动资源，验证放量能力。",
        "低流量低转化": "谨慎投入，先做选品、价格或内容基础优化。",
    }
    grouped["quadrant"] = grouped.apply(quadrant, axis=1)
    grouped["suggestion"] = grouped["quadrant"].map(suggestions)
    grouped["sales"] = grouped["sales"].round(2)
    sorted_table = grouped.sort_values(["quadrant", "pv", "conversion_rate"], ascending=[True, False, False])
    quadrant_counts = (
        grouped.groupby("quadrant", as_index=False)
        .agg(items=("quadrant", "size"), pv=("pv", "sum"), buys=("buys", "sum"), sales=("sales", "sum"))
    )
    quadrant_counts["sales"] = quadrant_counts["sales"].round(2)

    return {
        "dimension": dimension,
        "summary": {
            "traffic_threshold_pv_median": round(traffic_threshold, 2),
            "conversion_threshold_median": round(conversion_threshold, 4),
            "items": int(len(grouped)),
        },
        "matrix_table": _records(sorted_table, top_n),
        "chart_data": _records(quadrant_counts),
        "scope_note": f"运营矩阵基于结构化全量行为数据，流量口径为 PV，转化口径为购买数/PV；高低阈值使用当前 {dimension} 的中位数。",
    }


def get_semantic_linkage_analysis(
    df: pd.DataFrame | None = None,
    detail_path: Any = None,
    top_n: int = 20,
) -> dict[str, Any]:
    behavior = _behavior_df(df)
    detail_csv = pd.io.common.stringify_path(detail_path or DEFAULT_DETAIL_CSV)
    if not pd.io.common.file_exists(detail_csv):
        return {
            "status": "missing",
            "sample_size": 0,
            "aspect_table": [],
            "reason_table": [],
            "linked_category_table": [],
            "linked_goods_table": [],
            "scope_note": "评论语义分析结果文件不存在；不会自动重跑语义分析。",
        }

    detail = pd.read_csv(detail_csv)
    sample_size = int(len(detail))
    for column in ["aspects", "negative_reasons", "comment", "sentiment"]:
        if column not in detail.columns:
            detail[column] = ""

    def explode_counts(column: str, name: str) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for _, row in detail.iterrows():
            values = [item.strip() for item in str(row.get(column, "")).split(",") if item.strip()]
            for value in values:
                rows.append({name: value, "sentiment": row.get("sentiment", "")})
        if not rows:
            return pd.DataFrame(columns=[name, "count", "negative_count", "negative_rate"])
        exploded = pd.DataFrame(rows)
        result = (
            exploded.groupby(name, as_index=False)
            .agg(count=(name, "size"), negative_count=("sentiment", lambda s: int((s == "负面").sum())))
        )
        result["negative_rate"] = result.apply(lambda row: _safe_rate(row["negative_count"], row["count"]), axis=1)
        priority = {"质量": 0, "售后": 1, "物流": 2, "价格": 3, "包装": 4, "体验": 5, "服务": 6}
        result["_priority"] = result[name].map(priority).fillna(99)
        result = result.sort_values(["negative_count", "count", "_priority", name], ascending=[False, False, True, True])
        result = result.drop(columns=["_priority"])
        return result

    aspect_table = explode_counts("aspects", "aspect")
    reason_table = explode_counts("negative_reasons", "reason")

    linked = pd.DataFrame()
    if "comment" in behavior.columns:
        comment_map = detail[["comment", "sentiment", "aspects", "negative_reasons"]].dropna(subset=["comment"])
        linked = behavior.merge(comment_map, on="comment", how="inner")
        linked = linked[linked["comment"].astype(str).str.strip().ne("无评论")]

    def linked_table(dimension: str) -> pd.DataFrame:
        if linked.empty or dimension not in linked.columns:
            return pd.DataFrame(columns=[dimension, "linked_comments", "negative_comments", "top_aspects", "top_reasons"])
        rows: list[dict[str, Any]] = []
        for value, group in linked.groupby(dimension):
            aspects: list[str] = []
            reasons: list[str] = []
            for item in group["aspects"].fillna("").astype(str):
                aspects.extend([part.strip() for part in item.split(",") if part.strip()])
            for item in group["negative_reasons"].fillna("").astype(str):
                reasons.extend([part.strip() for part in item.split(",") if part.strip()])
            rows.append(
                {
                    dimension: value,
                    "linked_comments": int(group["comment"].nunique()),
                    "negative_comments": int((group["sentiment"] == "负面").sum()),
                    "negative_rate": _safe_rate((group["sentiment"] == "负面").sum(), len(group)),
                    "top_aspects": "、".join(pd.Series(aspects).value_counts().head(3).index.tolist()) if aspects else "",
                    "top_reasons": "、".join(pd.Series(reasons).value_counts().head(3).index.tolist()) if reasons else "",
                }
            )
        return pd.DataFrame(rows).sort_values(["negative_comments", "linked_comments"], ascending=False)

    return {
        "status": "ready",
        "sample_size": sample_size,
        "aspect_table": _records(aspect_table, top_n),
        "reason_table": _records(reason_table, top_n),
        "linked_category_table": _records(linked_table("category_id"), top_n),
        "linked_goods_table": _records(linked_table("goods_id"), top_n),
        "scope_note": "评论语义联动基于现有 960 条去重评论样本，适合发现质量、物流、售后、价格、包装等方向，不是全量评论统计；商品/类目联动仅统计能通过评论文本匹配到行为记录的样本。",
    }


def get_rfm_behavior_differences(
    behavior_df: pd.DataFrame | None = None,
    rfm_df: pd.DataFrame | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    behavior = _price_enriched_behavior(_behavior_df(behavior_df))
    rfm = _rfm_df(rfm_df)
    merged = behavior.merge(rfm[["user_id", "label"]], on="user_id", how="inner")
    if merged.empty:
        return {
            "layer_table": [],
            "category_preference": [],
            "price_preference": [],
            "scope_note": "结构化行为数据与 RFM 分层结果没有可匹配用户。",
        }

    merged["price_band"] = merged["effective_price"].apply(_assign_price_band)
    layer = (
        merged.groupby("label", as_index=False)
        .agg(
            users=("user_id", "nunique"),
            records=("behavior", "size"),
            pv=("behavior", lambda s: int((s == "pv").sum())),
            cart=("behavior", lambda s: int((s == "cart").sum())),
            fav=("behavior", lambda s: int((s == "fav").sum())),
            buys=("behavior", lambda s: int((s == "buy").sum())),
            sales=("sales", "sum"),
            avg_price=("effective_price", "mean"),
        )
    )
    layer["cart_rate"] = layer.apply(lambda row: _safe_rate(row["cart"], row["pv"]), axis=1)
    layer["purchase_rate"] = layer.apply(lambda row: _safe_rate(row["buys"], row["pv"]), axis=1)
    layer["sales"] = layer["sales"].round(2)
    layer["avg_price"] = layer["avg_price"].round(2)

    category_preference = pd.DataFrame()
    if "category_id" in merged.columns:
        category_preference = (
            merged.groupby(["label", "category_id"], as_index=False)
            .agg(records=("behavior", "size"), buys=("behavior", lambda s: int((s == "buy").sum())), sales=("sales", "sum"))
            .sort_values(["label", "records"], ascending=[True, False])
        )
        category_preference["sales"] = category_preference["sales"].round(2)

    price_preference = (
        merged.groupby(["label", "price_band"], as_index=False)
        .agg(records=("behavior", "size"), buys=("behavior", lambda s: int((s == "buy").sum())), sales=("sales", "sum"))
        .sort_values(["label", "records"], ascending=[True, False])
    )
    price_preference["sales"] = price_preference["sales"].round(2)

    return {
        "layer_table": _records(layer.sort_values("users", ascending=False), top_n),
        "category_preference": _records(category_preference, top_n),
        "price_preference": _records(price_preference, top_n),
        "scope_note": "RFM 行为差异基于结构化行为数据与 RFM 分层结果按 user_id 关联，转化率为购买数/PV，价格带使用商品成交价中位数补齐。",
    }


def get_price_band_analysis(
    behavior_df: pd.DataFrame | None = None,
    rfm_df: pd.DataFrame | None = None,
    top_n: int = 30,
) -> dict[str, Any]:
    behavior = _price_enriched_behavior(_behavior_df(behavior_df))
    behavior = behavior[behavior["effective_price"] > 0].copy()
    if behavior.empty:
        return {
            "band_table": [],
            "rfm_distribution": [],
            "chart_data": [],
            "scope_note": "当前行为数据无法从成交记录推断商品价格带。",
        }
    behavior["price_band"] = behavior["effective_price"].apply(_assign_price_band)
    band_order = ["0-50", "50-100", "100-200", "200-500", "500+"]
    band = (
        behavior.groupby("price_band", as_index=False)
        .agg(
            records=("behavior", "size"),
            users=("user_id", "nunique"),
            pv=("behavior", lambda s: int((s == "pv").sum())),
            cart=("behavior", lambda s: int((s == "cart").sum())),
            fav=("behavior", lambda s: int((s == "fav").sum())),
            buys=("behavior", lambda s: int((s == "buy").sum())),
            sales=("sales", "sum"),
        )
    )
    band["conversion_rate"] = band.apply(lambda row: _safe_rate(row["buys"], row["pv"]), axis=1)
    band["cart_or_fav_rate"] = band.apply(lambda row: _safe_rate(row["cart"] + row["fav"], row["pv"]), axis=1)
    band["sales"] = band["sales"].round(2)
    band["sort_key"] = band["price_band"].apply(lambda value: band_order.index(value) if value in band_order else 99)
    band = band.sort_values("sort_key").drop(columns=["sort_key"])

    distribution = pd.DataFrame()
    rfm = _rfm_df(rfm_df)
    if not rfm.empty:
        merged = behavior.merge(rfm[["user_id", "label"]], on="user_id", how="left")
        distribution = (
            merged.groupby(["price_band", "label"], as_index=False)
            .agg(records=("behavior", "size"), buys=("behavior", lambda s: int((s == "buy").sum())), sales=("sales", "sum"))
            .sort_values(["price_band", "records"], ascending=[True, False])
        )
        distribution["sales"] = distribution["sales"].round(2)

    return {
        "band_table": _records(band, top_n),
        "rfm_distribution": _records(distribution, top_n),
        "chart_data": _records(band[["price_band", "pv", "buys", "sales", "conversion_rate"]], top_n),
        "scope_note": "价格带口径为固定区间 0-50、50-100、100-200、200-500、500+；浏览、加购、收藏记录使用同商品成交价中位数补齐价格，适合做历史转化对比。",
    }


def get_sales_forecast(df: pd.DataFrame | None = None, horizon: int = 24) -> dict[str, Any]:
    behavior = _ensure_timestamp(_behavior_df(df))
    if behavior.empty:
        return {
            "method": "moving_average_baseline",
            "actual_tail": [],
            "forecast": [],
            "summary": {"trend": "数据不足"},
            "scope_note": "行为数据时间戳为空，无法生成销售额预测。",
        }
    hourly = (
        behavior.set_index("timestamp")
        .resample("h")["sales"]
        .sum()
        .reset_index()
        .rename(columns={"timestamp": "time", "sales": "sales"})
    )
    hourly["sales"] = hourly["sales"].fillna(0.0)
    last_time = hourly["time"].max()
    future_times = pd.date_range(last_time + pd.Timedelta(hours=1), periods=horizon, freq="h")

    if len(hourly) >= 3:
        x = pd.Series(range(len(hourly)), dtype="float64")
        y = hourly["sales"].astype(float)
        slope = float(x.cov(y) / x.var()) if x.var() else 0.0
        intercept = float(y.mean() - slope * x.mean())
        preds = [max(0.0, round(intercept + slope * (len(hourly) + step), 2)) for step in range(horizon)]
        method = "linear_regression_baseline"
    else:
        baseline = float(hourly["sales"].tail(3).mean()) if not hourly.empty else 0.0
        preds = [round(max(0.0, baseline), 2) for _ in range(horizon)]
        method = "moving_average_baseline"

    first_half = sum(preds[: max(1, horizon // 2)])
    second_half = sum(preds[max(1, horizon // 2) :])
    if second_half > first_half * 1.05:
        trend = "上升"
    elif second_half < first_half * 0.95:
        trend = "下降"
    else:
        trend = "平稳"

    forecast = [
        {"forecast_time": time.strftime("%Y-%m-%d %H:%M:%S"), "predicted_sales": float(value)}
        for time, value in zip(future_times, preds)
    ]
    actual_tail = hourly.tail(24).copy()
    actual_tail["time"] = actual_tail["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    actual_tail["sales"] = actual_tail["sales"].round(2)

    return {
        "method": method,
        "actual_tail": _records(actual_tail),
        "forecast": forecast,
        "summary": {
            "trend": trend,
            "next_24h_predicted_sales": round(sum(preds), 2),
            "last_observed_hour": last_time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "scope_note": "销售额预测基于小时级历史销售额聚合和简单基线模型，仅适合短期趋势辅助判断；当前数据周期较短，不应包装成长期经营预测。",
    }


def get_ab_test_plan(question: str = "", df: pd.DataFrame | None = None) -> dict[str, Any]:
    behavior = _behavior_df(df)
    funnel = get_behavior_funnel(behavior)
    by_behavior = funnel.set_index("behavior") if not funnel.empty else pd.DataFrame()
    pv_count = int(by_behavior.loc["pv", "count"]) if not by_behavior.empty and "pv" in by_behavior.index else 0
    cart_count = int(by_behavior.loc["cart", "count"]) if not by_behavior.empty and "cart" in by_behavior.index else 0
    buy_count = int(by_behavior.loc["buy", "count"]) if not by_behavior.empty and "buy" in by_behavior.index else 0
    pv_to_cart = _safe_rate(cart_count, pv_count)
    pv_to_buy = _safe_rate(buy_count, pv_count)

    text = question.lower()
    is_quality = any(keyword in text for keyword in ["质量", "售后", "物流", "包装", "评论", "负面"])
    if is_quality:
        goal = "降低评论语义样本中高频负面问题带来的购买顾虑"
        hypothesis = "如果在详情页和售后承诺中前置问题解释、质检说明或服务保障，用户信任感提升，浏览到加购/购买转化会改善。"
        variant = "B 组在详情页增加质量/物流/售后保障模块、典型问题解释和客服入口；A 组保持当前页面。"
        primary_metric = "购买转化率"
        guardrail = "负面评论率、退款/售后咨询量、客服响应压力"
    else:
        goal = "降低浏览到加购阶段的流失"
        hypothesis = "如果在高流量低转化商品或类目中强化首屏卖点、价格利益点和加购提醒，浏览到加购转化率会提升。"
        variant = "B 组展示强化卖点、限时利益点和醒目的加购按钮；A 组保持当前承接页。"
        primary_metric = "浏览到加购转化率"
        guardrail = "购买转化率、客单价、跳出率、投诉或负面反馈"

    return {
        "status": "proposal",
        "experiment_goal": goal,
        "baseline": {
            "pv": pv_count,
            "cart": cart_count,
            "buy": buy_count,
            "pv_to_cart_rate": pv_to_cart,
            "pv_to_buy_rate": pv_to_buy,
            "data_source": "结构化全量行为数据历史统计",
        },
        "hypothesis": hypothesis,
        "groups": [
            {"group": "A 组", "design": "保持当前商品/类目页面或运营策略，作为对照组。"},
            {"group": "B 组", "design": variant},
        ],
        "metrics": [
            {"name": primary_metric, "role": "核心指标", "success_rule": "B 组相对 A 组有稳定提升，并通过预设显著性或业务阈值。"},
            {"name": "购买转化率", "role": "结果指标", "success_rule": "不能因加购提升而明显牺牲最终购买。"},
            {"name": guardrail, "role": "护栏指标", "success_rule": "不能出现明显恶化。"},
        ],
        "traffic_split": "建议用户级随机分流 50%/50%，同一 user_id 在实验周期内保持固定分组，避免跨组污染。",
        "observation_period": "建议至少覆盖完整周内高低峰，当前历史数据周期较短时先做小流量试验，再扩大流量。",
        "success_criteria": "实验结束后比较 A/B 两组核心指标、结果指标和护栏指标；只有指标达标且风险可控，才进入放量。",
        "risk_controls": [
            "实验前冻结口径，明确曝光、加购、购买、销售额和评论语义样本的计算方式。",
            "监控库存、价格、活动资源变化，避免外部因素污染实验结论。",
            "该模块只生成实验方案，不能输出已经完成实验的结论。",
        ],
        "limit_note": "这是基于历史数据诊断生成的 A/B 测试方案建议，实验尚未执行，不能替代实验后的统计检验。",
    }
