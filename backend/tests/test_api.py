from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend import services
from backend.main import create_app


def fake_agent_runner(question: str, context: list[dict[str, str]] | None = None) -> dict:
    tool_results = {
        "data_overview": {
            "records": 10,
            "users": 3,
            "goods": 4,
            "rfm_users": 3,
            "semantic_sample_count": 960,
        }
    }
    if "RFM" in question or "口径" in question:
        tool_results["rag"] = {
            "status": "ready",
            "answer": "RFM 是基于最近一次消费、消费频次和消费金额的分层口径。",
            "sources": [
                {
                    "source": "metric_definitions.md",
                    "heading": "RFM",
                    "content": "RFM 用于用户价值分层。",
                    "score": 2.5,
                }
            ],
        }
    return {
        "answer": "结论：测试回答\n数据依据：来自固定工具\n原因分析：测试原因\n运营建议：测试建议",
        "tool_names": list(tool_results.keys()),
        "tool_results": tool_results,
        "used_llm": False,
        "error": "",
    }


def client(tmp_path) -> TestClient:
    db_path = tmp_path / "workbench.sqlite3"
    app = create_app(db_path=db_path, agent_runner=fake_agent_runner)
    return TestClient(app)


def test_health(tmp_path):
    response = client(tmp_path).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_session_lifecycle(tmp_path):
    api = client(tmp_path)

    created = api.post("/api/sessions", json={"title": "测试会话"})
    assert created.status_code == 200
    session = created.json()
    assert session["title"] == "测试会话"

    listed = api.get("/api/sessions")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == session["id"]

    detail = api.get(f"/api/sessions/{session['id']}")
    assert detail.status_code == 200
    assert detail.json()["session"]["id"] == session["id"]

    deleted = api.delete(f"/api/sessions/{session['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_chat_persists_messages_and_tool_calls(tmp_path):
    api = client(tmp_path)
    session_id = api.post("/api/sessions", json={"title": "问数"}).json()["id"]

    chat = api.post("/api/chat", json={"session_id": session_id, "question": "给我数据概览"})
    assert chat.status_code == 200
    payload = chat.json()
    assert payload["session_id"] == session_id
    assert payload["tools"][0]["name"] == "data_overview"

    detail = api.get(f"/api/sessions/{session_id}").json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert len(detail["tool_calls"]) == 1
    assert json.loads(detail["tool_calls"][0]["result_json"])["records"] == 10


def test_chat_returns_rag_sources(tmp_path):
    api = client(tmp_path)
    chat = api.post("/api/chat", json={"question": "RFM 的口径是什么"})

    assert chat.status_code == 200
    payload = chat.json()
    assert payload["rag_sources"][0]["source"] == "metric_definitions.md"
    assert any(tool["name"] == "rag" for tool in payload["tools"])


def test_overview_shape(tmp_path):
    api = client(tmp_path)
    response = api.get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert {"records", "users", "goods", "rfm_users", "semantic_sample_count"}.issubset(payload)


def test_chat_returns_routing_explanation_confidence_and_visual_payloads(tmp_path):
    api = client(tmp_path)
    response = api.post("/api/chat", json={"question": "RFM 的口径是什么"})

    assert response.status_code == 200
    payload = response.json()
    assert "routing_explanation" in payload
    assert "RFM" in payload["routing_explanation"]
    assert payload["confidence"]["level"] in {"高", "中", "低"}
    assert payload["confidence"]["reason"]
    assert any(item["tool_name"] == "data_overview" for item in payload["visual_payloads"])


def test_followup_uses_recent_context_and_tool_results(tmp_path):
    captured: dict[str, object] = {}

    def runner(question: str, context: list[dict[str, str]] | None = None) -> dict:
        captured["question"] = question
        captured["context"] = context or []
        return fake_agent_runner(question, context)

    db_path = tmp_path / "context.sqlite3"
    api = TestClient(create_app(db_path=db_path, agent_runner=runner))
    session_id = api.post("/api/sessions", json={"title": "追问"}).json()["id"]

    api.post("/api/chat", json={"session_id": session_id, "question": "质量和物流哪个问题更严重"})
    followup = api.post("/api/chat", json={"session_id": session_id, "question": "那应该优先优化哪个？"})

    assert followup.status_code == 200
    payload = followup.json()
    assert "上一轮" in payload["context_summary"]
    assert "data_overview" in payload["context_summary"]
    assert any(item["role"] == "context" for item in captured["context"])


def test_ambiguous_followup_without_context_returns_low_confidence(tmp_path):
    api = client(tmp_path)
    response = api.post("/api/chat", json={"question": "那应该优先优化哪个？"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["confidence"]["level"] == "低"
    assert "补充" in payload["answer"]
    assert payload["tools"] == []


def test_report_generation_uses_session_messages_tools_and_sources(tmp_path):
    api = client(tmp_path)
    session_id = api.post("/api/sessions", json={"title": "报告"}).json()["id"]
    api.post("/api/chat", json={"session_id": session_id, "question": "RFM 的口径是什么"})

    response = api.post(f"/api/sessions/{session_id}/report")

    assert response.status_code == 200
    markdown = response.json()["report_markdown"]
    for heading in ["# 京东用户行为分析报告", "## 分析问题", "## 关键结论", "## 数据依据", "## RAG/知识库依据", "## 运营建议", "## 风险与限制"]:
        assert heading in markdown
    assert "metric_definitions.md" in markdown


def test_run_agent_does_not_append_context_for_standalone_questions(monkeypatch):
    captured: dict[str, str] = {}

    def fake_answer_question(question: str):
        captured["question"] = question
        return {
            "answer": "ok",
            "tool_names": ["comment_semantic"],
            "tool_results": {"comment_semantic": {"status": "ready"}},
            "used_llm": False,
            "error": "",
        }

    monkeypatch.setattr(services, "answer_question", fake_answer_question)

    services.run_agent(
        "质量和物流哪个问题更严重",
        context=[
            {"role": "user", "content": "RFM 是什么含义？"},
            {"role": "assistant", "content": "地区、设备、漏斗、RFM、评论关键词都可以分析。"},
        ],
    )

    assert captured["question"] == "质量和物流哪个问题更严重"
