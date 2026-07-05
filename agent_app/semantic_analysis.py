from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

try:
    from .data_loader import PROCESSED_DATA_DIR, load_llm_config
except ImportError:  # pragma: no cover - direct script execution
    from data_loader import PROCESSED_DATA_DIR, load_llm_config


ASPECT_LABELS = ["质量", "物流", "价格", "服务", "包装", "售后", "体验"]
DETAIL_COLUMNS = [
    "comment_hash",
    "comment",
    "sentiment",
    "sentiment_score",
    "aspects",
    "negative_reasons",
    "model",
    "analyzed_at",
]
SUMMARY_COLUMNS = [
    "summary_type",
    "name",
    "count",
    "percentage",
    "avg_sentiment_score",
    "negative_count",
    "negative_rate",
]
INVALID_COMMENTS = {
    "",
    "无评论",
    "暂无评论",
    "默认好评",
    "此用户没有填写评论",
    "该用户觉得商品不错",
    "无",
    "没有评论",
    "null",
    "none",
    "nan",
}

DEFAULT_BEHAVIOR_CSV = PROCESSED_DATA_DIR / "jd_analysis_final.csv"
DEFAULT_DETAIL_CSV = PROCESSED_DATA_DIR / "comment_semantic_result.csv"
DEFAULT_SUMMARY_CSV = PROCESSED_DATA_DIR / "semantic_summary.csv"


def normalize_comment_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if text.lower() in INVALID_COMMENTS or text in INVALID_COMMENTS:
        return ""
    return text


def comment_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_unique_comments(df: pd.DataFrame, comment_col: str = "comment") -> pd.DataFrame:
    if comment_col not in df.columns:
        raise ValueError(f"输入数据缺少评论字段: {comment_col}")

    comments = df[comment_col].map(normalize_comment_text)
    result = pd.DataFrame({"comment": comments})
    result = result[result["comment"] != ""].drop_duplicates("comment").reset_index(drop=True)
    result.insert(0, "comment_hash", result["comment"].map(comment_hash))
    return result


def has_valid_api_key(config: dict[str, Any]) -> bool:
    api_key = str(config.get("api_key") or "").strip()
    return bool(api_key and "your_" not in api_key.lower() and "api_key_here" not in api_key.lower())


def load_existing_detail(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=DETAIL_COLUMNS)
    detail = pd.read_csv(path)
    for column in DETAIL_COLUMNS:
        if column not in detail.columns:
            detail[column] = ""
    return detail[DETAIL_COLUMNS].drop_duplicates("comment_hash", keep="last")


def _split_csv_values(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_values = value
    elif isinstance(value, tuple | set):
        raw_values = list(value)
    elif value is None or pd.isna(value):
        return []
    else:
        raw_values = re.split(r"[,，、;/；|]", str(value))
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _normalize_aspects(value: Any) -> str:
    values = []
    for item in _split_csv_values(value):
        if item in ASPECT_LABELS and item not in values:
            values.append(item)
    return ",".join(values)


def _normalize_reasons(value: Any) -> str:
    values = []
    for item in _split_csv_values(value):
        if item and item not in values:
            values.append(item[:40])
    return ",".join(values[:5])


def _normalize_sentiment(value: Any) -> str:
    text = str(value).strip()
    if text in {"正面", "中性", "负面"}:
        return text
    if "负" in text or "差" in text:
        return "负面"
    if "正" in text or "好" in text:
        return "正面"
    return "中性"


def _normalize_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(-1.0, min(1.0, score)), 4)


def aggregate_semantic_results(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    work = detail.copy()
    work["sentiment"] = work["sentiment"].map(_normalize_sentiment)
    work["sentiment_score"] = pd.to_numeric(work["sentiment_score"], errors="coerce").fillna(0.0)
    total = len(work)
    rows: list[dict[str, Any]] = []

    for sentiment, group in work.groupby("sentiment"):
        count = len(group)
        rows.append(
            {
                "summary_type": "sentiment",
                "name": sentiment,
                "count": count,
                "percentage": round(count / total, 4),
                "avg_sentiment_score": round(group["sentiment_score"].mean(), 4),
                "negative_count": int((group["sentiment"] == "负面").sum()),
                "negative_rate": round((group["sentiment"] == "负面").sum() / count, 4) if count else 0.0,
            }
        )

    exploded_aspects = []
    for _, row in work.iterrows():
        for aspect in _split_csv_values(row.get("aspects", "")):
            if aspect in ASPECT_LABELS:
                exploded_aspects.append(
                    {
                        "aspect": aspect,
                        "sentiment": row["sentiment"],
                        "sentiment_score": row["sentiment_score"],
                    }
                )
    aspect_df = pd.DataFrame(exploded_aspects)
    if not aspect_df.empty:
        for aspect, group in aspect_df.groupby("aspect"):
            count = len(group)
            negative_count = int((group["sentiment"] == "负面").sum())
            rows.append(
                {
                    "summary_type": "aspect",
                    "name": aspect,
                    "count": count,
                    "percentage": round(count / len(aspect_df), 4),
                    "avg_sentiment_score": round(group["sentiment_score"].mean(), 4),
                    "negative_count": negative_count,
                    "negative_rate": round(negative_count / count, 4) if count else 0.0,
                }
            )

    negative = work[work["sentiment"] == "负面"]
    reasons = []
    for value in negative.get("negative_reasons", pd.Series(dtype=str)):
        reasons.extend(_split_csv_values(value))
    if reasons:
        reason_counts = pd.Series(reasons).value_counts()
        for reason, count in reason_counts.items():
            rows.append(
                {
                    "summary_type": "negative_reason",
                    "name": reason,
                    "count": int(count),
                    "percentage": round(int(count) / len(reasons), 4),
                    "avg_sentiment_score": 0.0,
                    "negative_count": int(count),
                    "negative_rate": 1.0,
                }
            )

    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    return summary.sort_values(["summary_type", "count"], ascending=[True, False]).reset_index(drop=True)


def _semantic_prompt(batch: pd.DataFrame) -> list[dict[str, str]]:
    examples = batch[["comment_hash", "comment"]].rename(columns={"comment_hash": "id"}).to_dict(orient="records")
    system = (
        "你是电商评论语义分析器。只输出 JSON，不要输出解释文字。"
        "情感只能是 正面/中性/负面；sentiment_score 范围为 -1 到 1。"
        f"方面标签只能从 {ASPECT_LABELS} 中选择，可多选。"
        "negative_reasons 只在负面或中性偏负时填写，使用简短中文短语。"
    )
    user = {
        "任务": "分析每条评论的情感、情感分数、方面标签和负面原因。",
        "输出格式": {
            "results": [
                {
                    "id": "原 comment_hash",
                    "sentiment": "正面/中性/负面",
                    "sentiment_score": 0.0,
                    "aspects": ["质量"],
                    "negative_reasons": ["原因短语"],
                }
            ]
        },
        "评论": examples,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    data = json.loads(cleaned)
    if isinstance(data, dict):
        data = data.get("results") or data.get("data") or data.get("items") or []
    if not isinstance(data, list):
        raise ValueError("模型返回不是 JSON 数组")
    return [item for item in data if isinstance(item, dict)]


def call_llm_for_batch(batch: pd.DataFrame, config: dict[str, Any]) -> list[dict[str, Any]]:
    base_url = str(config.get("base_url") or "https://api.deepseek.com").rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": config.get("model") or "deepseek-v4-pro",
        "messages": _semantic_prompt(batch),
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = _extract_json_array(content)
    by_id = {str(item.get("id") or item.get("comment_hash")): item for item in parsed}

    rows = []
    analyzed_at = datetime.now().isoformat(timespec="seconds")
    for _, source in batch.iterrows():
        item = by_id.get(str(source["comment_hash"]), {})
        rows.append(
            {
                "comment_hash": source["comment_hash"],
                "comment": source["comment"],
                "sentiment": _normalize_sentiment(item.get("sentiment", "中性")),
                "sentiment_score": _normalize_score(item.get("sentiment_score", 0)),
                "aspects": _normalize_aspects(item.get("aspects", "")),
                "negative_reasons": _normalize_reasons(item.get("negative_reasons", "")),
                "model": config.get("model") or "",
                "analyzed_at": analyzed_at,
            }
        )
    return rows


def save_summary(detail: pd.DataFrame, summary_csv: Path) -> pd.DataFrame:
    summary = aggregate_semantic_results(detail)
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    return summary


def _log_progress(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[semantic] {message}", flush=True)


def run_semantic_analysis(
    input_csv: Path = DEFAULT_BEHAVIOR_CSV,
    detail_csv: Path = DEFAULT_DETAIL_CSV,
    summary_csv: Path = DEFAULT_SUMMARY_CSV,
    batch_size: int = 20,
    limit: int | None = None,
    prepare_only: bool = False,
    llm_config: dict[str, Any] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    source = pd.read_csv(input_csv, usecols=["comment"])
    unique_comments = extract_unique_comments(source)
    if limit is not None:
        unique_comments = unique_comments.head(limit)

    existing = load_existing_detail(detail_csv)
    existing_hashes = set(existing["comment_hash"].astype(str))
    pending = unique_comments[~unique_comments["comment_hash"].astype(str).isin(existing_hashes)]

    _log_progress(
        verbose,
        (
            f"prepared unique={len(unique_comments)}, cached={len(existing)}, "
            f"pending={len(pending)}, batch_size={batch_size}"
        ),
    )

    if prepare_only:
        return {
            "status": "prepared",
            "unique_comments": int(len(unique_comments)),
            "cached_comments": int(len(existing)),
            "pending_comments": int(len(pending)),
            "detail_csv": str(detail_csv),
            "summary_csv": str(summary_csv),
        }

    config = llm_config if llm_config is not None else load_llm_config()
    if not has_valid_api_key(config):
        if not existing.empty:
            save_summary(existing, summary_csv)
        _log_progress(verbose, "api key unavailable; skipped remote semantic analysis")
        return {
            "status": "api_unavailable",
            "message": "未配置有效 LLM_API_KEY，已跳过语义分析调用；第一版功能不受影响。",
            "unique_comments": int(len(unique_comments)),
            "cached_comments": int(len(existing)),
            "pending_comments": int(len(pending)),
        }

    detail_parts = [existing] if not existing.empty else []
    processed = 0
    total_batches = (len(pending) + batch_size - 1) // batch_size if len(pending) else 0
    _log_progress(verbose, f"start remote analysis batches={total_batches}")
    for batch_index, start in enumerate(range(0, len(pending), batch_size), start=1):
        batch = pending.iloc[start : start + batch_size]
        _log_progress(
            verbose,
            (
                f"batch {batch_index}/{total_batches} calling api, "
                f"comments={len(batch)}, processed_before={processed}"
            ),
        )
        rows = call_llm_for_batch(batch, config)
        batch_df = pd.DataFrame(rows, columns=DETAIL_COLUMNS)
        detail_parts.append(batch_df)
        current = pd.concat(detail_parts, ignore_index=True).drop_duplicates("comment_hash", keep="last")
        current.to_csv(detail_csv, index=False, encoding="utf-8-sig")
        save_summary(current, summary_csv)
        processed += len(batch_df)
        remaining = max(0, len(pending) - processed)
        _log_progress(
            verbose,
            (
                f"batch {batch_index}/{total_batches} saved, "
                f"processed_this_run={processed}, total_detail_rows={len(current)}, remaining_this_run={remaining}"
            ),
        )

    final_detail = pd.concat(detail_parts, ignore_index=True).drop_duplicates("comment_hash", keep="last") if detail_parts else existing
    if final_detail.empty:
        final_detail = pd.DataFrame(columns=DETAIL_COLUMNS)
        final_detail.to_csv(detail_csv, index=False, encoding="utf-8-sig")
    summary = save_summary(final_detail, summary_csv)
    _log_progress(
        verbose,
        f"completed processed_this_run={processed}, total_detail_rows={len(final_detail)}, summary_rows={len(summary)}",
    )
    return {
        "status": "completed",
        "unique_comments": int(len(unique_comments)),
        "cached_comments": int(len(existing)),
        "processed_comments": int(processed),
        "total_detail_rows": int(len(final_detail)),
        "summary_rows": int(len(summary)),
        "detail_csv": str(detail_csv),
        "summary_csv": str(summary_csv),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate semantic analysis results for JD comments.")
    parser.add_argument("--input", type=Path, default=DEFAULT_BEHAVIOR_CSV)
    parser.add_argument("--detail-output", type=Path, default=DEFAULT_DETAIL_CSV)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--prepare-only", action="store_true", help="Only count valid comments and cache state; do not call API.")
    parser.add_argument("--quiet", action="store_true", help="Do not print per-batch progress logs.")
    args = parser.parse_args()

    result = run_semantic_analysis(
        input_csv=args.input,
        detail_csv=args.detail_output,
        summary_csv=args.summary_output,
        batch_size=max(1, args.batch_size),
        limit=args.limit,
        prepare_only=args.prepare_only,
        verbose=not args.quiet,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
