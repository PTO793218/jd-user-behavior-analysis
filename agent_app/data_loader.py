from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent


@dataclass(frozen=True)
class DataPaths:
    behavior_csv: Path = PROJECT_ROOT / "jd_analysis_final.csv"
    rfm_csv: Path = PROJECT_ROOT / "jd_rfm_result.csv"
    comment_csv: Path = PROJECT_ROOT / "comment_word_freq.csv"


@dataclass
class DataBundle:
    behavior: pd.DataFrame
    rfm: pd.DataFrame
    comments: pd.DataFrame


def _parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_llm_config(env_path: Path | None = None) -> dict[str, Any]:
    """Read OpenAI-compatible LLM settings, preferring agent_app/.env."""
    env_values = _parse_env_file(env_path or APP_DIR / ".env")

    def pick(name: str, default: str = "") -> str:
        return env_values.get(name) or os.environ.get(name, default)

    return {
        "provider": pick("LLM_PROVIDER", "deepseek"),
        "api_key": pick("LLM_API_KEY", ""),
        "base_url": pick("LLM_BASE_URL", "https://api.deepseek.com"),
        "model": pick("LLM_MODEL", "deepseek-v4-pro"),
        "thinking_enabled": pick("LLM_THINKING_ENABLED", "false").lower() == "true",
        "reasoning_effort": pick("LLM_REASONING_EFFORT", "medium"),
    }


def _require_columns(df: pd.DataFrame, columns: set[str], file_name: str) -> None:
    missing = columns.difference(df.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"{file_name} 缺少必要字段: {missing_text}")


def _normalize_behavior_df(df: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        df,
        {"user_id", "goods_id", "behavior", "timestamp", "date", "hour"},
        "jd_analysis_final.csv",
    )
    normalized = df.copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="coerce")
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce").dt.date
    normalized["hour"] = pd.to_numeric(normalized["hour"], errors="coerce").fillna(0).astype(int)

    for column in ["price", "amount", "sales"]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0.0)

    for column in ["address", "device", "behavior"]:
        if column in normalized.columns:
            normalized[column] = normalized[column].fillna("未知").astype(str)
    return normalized


def _normalize_rfm_df(df: pd.DataFrame) -> pd.DataFrame:
    _require_columns(df, {"user_id", "R", "F", "M", "label"}, "jd_rfm_result.csv")
    normalized = df.copy()
    for column in ["R", "F", "M"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0)
    normalized["label"] = normalized["label"].fillna("未分层").astype(str)
    return normalized


def _normalize_comment_df(df: pd.DataFrame) -> pd.DataFrame:
    _require_columns(df, {"word", "count"}, "comment_word_freq.csv")
    normalized = df.copy()
    normalized["word"] = normalized["word"].fillna("").astype(str)
    normalized["count"] = pd.to_numeric(normalized["count"], errors="coerce").fillna(0).astype(int)
    return normalized


@lru_cache(maxsize=1)
def load_data(
    behavior_csv: str | None = None,
    rfm_csv: str | None = None,
    comment_csv: str | None = None,
) -> DataBundle:
    paths = DataPaths(
        behavior_csv=Path(behavior_csv) if behavior_csv else DataPaths.behavior_csv,
        rfm_csv=Path(rfm_csv) if rfm_csv else DataPaths.rfm_csv,
        comment_csv=Path(comment_csv) if comment_csv else DataPaths.comment_csv,
    )

    behavior = pd.read_csv(paths.behavior_csv)
    rfm = pd.read_csv(paths.rfm_csv)
    comments = pd.read_csv(paths.comment_csv)

    return DataBundle(
        behavior=_normalize_behavior_df(behavior),
        rfm=_normalize_rfm_df(rfm),
        comments=_normalize_comment_df(comments),
    )


def get_duckdb_connection(bundle: DataBundle | None = None):
    """Register current dataframes as read-only DuckDB tables."""
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("缺少 duckdb 依赖，请先执行 pip install -r agent_app/requirements.txt") from exc

    data = bundle or load_data()
    con = duckdb.connect(database=":memory:", read_only=False)
    con.register("jd_behavior", data.behavior)
    con.register("jd_rfm", data.rfm)
    con.register("comment_word_freq", data.comments)
    return con
