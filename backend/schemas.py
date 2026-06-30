from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str | None = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str | None = None


class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=3, ge=1, le=8)


class ToolPayload(BaseModel):
    name: str
    result: Any

