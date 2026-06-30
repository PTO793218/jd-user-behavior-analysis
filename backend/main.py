from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import database
from .schemas import ChatRequest, CreateSessionRequest, RagSearchRequest
from .services import (
    ambiguous_followup_response,
    build_context_summary,
    dumps_json,
    generate_session_report,
    get_overview_payload,
    get_semantic_summary_payload,
    is_followup_question,
    normalize_agent_result,
    rag_search,
    run_agent,
)


AgentRunner = Callable[[str, list[dict[str, str]] | None], dict]


def create_app(
    db_path: str | Path | None = None,
    agent_runner: AgentRunner | None = None,
) -> FastAPI:
    app = FastAPI(title="JD AI Operations Workbench API", version="4.0.0")
    resolved_db_path = Path(db_path or database.DEFAULT_DB_PATH)
    resolved_agent_runner = agent_runner or run_agent
    database.init_db(resolved_db_path)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/overview")
    def overview() -> dict:
        return get_overview_payload()

    @app.post("/api/sessions")
    def create_session(payload: CreateSessionRequest | None = None) -> dict:
        title = payload.title if payload else None
        return database.create_session(resolved_db_path, title=title)

    @app.get("/api/sessions")
    def sessions() -> list[dict]:
        return database.list_sessions(resolved_db_path)

    @app.get("/api/sessions/{session_id}")
    def session_detail(session_id: str) -> dict:
        detail = database.get_session_detail(resolved_db_path, session_id)
        if not detail:
            raise HTTPException(status_code=404, detail="session not found")
        return detail

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str) -> dict[str, bool]:
        deleted = database.delete_session(resolved_db_path, session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="session not found")
        return {"deleted": True}

    @app.post("/api/chat")
    def chat(payload: ChatRequest) -> dict:
        question = payload.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="question is required")

        if payload.session_id:
            session = database.get_session(resolved_db_path, payload.session_id)
            if not session:
                raise HTTPException(status_code=404, detail="session not found")
        else:
            session = database.create_session(resolved_db_path, title=question[:24])

        session_id = session["id"]
        context = database.recent_messages(resolved_db_path, session_id, limit=6)
        recent_tools = database.recent_tool_calls(resolved_db_path, session_id, limit=8)
        context_summary = build_context_summary(context, recent_tools)
        database.add_message(resolved_db_path, session_id, "user", question)

        if is_followup_question(question) and not context_summary:
            normalized = ambiguous_followup_response(question, session_id, context_summary=context_summary)
            assistant_message = database.add_message(
                resolved_db_path,
                session_id,
                "assistant",
                normalized["answer"],
            )
            return {
                "session_id": session_id,
                "message": assistant_message,
                "answer": normalized["answer"],
                "tools": normalized["tools"],
                "rag_sources": normalized["rag_sources"],
                "used_llm": normalized["used_llm"],
                "error": normalized["error"],
                "saved_tool_calls": [],
                "routing_explanation": normalized["routing_explanation"],
                "confidence": normalized["confidence"],
                "context_summary": normalized["context_summary"],
                "visual_payloads": normalized["visual_payloads"],
            }

        context_for_agent = context
        if context_summary:
            context_for_agent = [*context, {"role": "context", "content": context_summary}]

        raw_result = resolved_agent_runner(question, context_for_agent)
        raw_result["question"] = question
        normalized = normalize_agent_result(raw_result, context_summary=context_summary)
        assistant_message = database.add_message(
            resolved_db_path,
            session_id,
            "assistant",
            normalized["answer"],
        )

        saved_tool_calls = []
        for tool in normalized["tools"]:
            saved_tool_calls.append(
                database.add_tool_call(
                    resolved_db_path,
                    session_id,
                    assistant_message["id"],
                    tool["name"],
                    dumps_json(tool["result"]),
                )
            )

        return {
            "session_id": session_id,
            "message": assistant_message,
            "answer": normalized["answer"],
            "tools": normalized["tools"],
            "rag_sources": normalized["rag_sources"],
            "used_llm": normalized["used_llm"],
            "error": normalized["error"],
            "saved_tool_calls": saved_tool_calls,
            "routing_explanation": normalized["routing_explanation"],
            "confidence": normalized["confidence"],
            "context_summary": normalized["context_summary"],
            "visual_payloads": normalized["visual_payloads"],
        }

    @app.post("/api/sessions/{session_id}/report")
    def session_report(session_id: str) -> dict:
        detail = database.get_session_detail(resolved_db_path, session_id)
        if not detail:
            raise HTTPException(status_code=404, detail="session not found")
        return {
            "session_id": session_id,
            "report_markdown": generate_session_report(detail),
        }

    @get_semantic_summary_route(app)
    def semantic_summary() -> dict:
        return get_semantic_summary_payload()

    @app.post("/api/rag/search")
    def search_rag(payload: RagSearchRequest) -> dict:
        return rag_search(payload.query, top_k=payload.top_k)

    return app


def get_semantic_summary_route(app: FastAPI):
    return app.get("/api/semantic/summary")


app = create_app()
