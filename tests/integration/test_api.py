"""API 端点集成测试 —— 健康检查、认证边界、统计。"""


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_ready_returns_503_without_services(self, client, monkeypatch):
        # /ready tries to connect to DB/Redis/Milvus, all unavailable
        #
        # 依赖项是探针的边界：这里显式把三项检查置为不可达，才能在"服务其实都在跑"的
        # 环境（dev.py up 之后的容器栈）里确定性地复现"无服务"语义。
        # 原实现直接假定宿主上没有服务，P0-0 起栈成功后该断言必失败（实测 200）。
        from backend.api import health

        monkeypatch.setattr(health, "_check_db", lambda: (False, "disconnected: test"))
        monkeypatch.setattr(health, "_check_redis", lambda: (False, "disconnected: test"))
        monkeypatch.setattr(health, "_check_milvus", lambda: (False, "disconnected: test"))

        resp = client.get("/ready")
        assert resp.status_code == 503
        checks = resp.json()["detail"]["checks"]
        assert checks["database"]["status"] == "error"
        assert checks["redis"]["status"] == "error"
        assert checks["milvus"]["status"] == "error"


class TestAuthUnauthenticated:
    def test_me_unauthenticated(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_refresh_unauthenticated(self, client):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid"})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid or expired refresh token"}


class TestStatsEndpoint:
    def test_get_stats_requires_admin(self, client):
        resp = client.get("/api/v1/stats/usage")
        assert resp.status_code == 401

    def test_reset_stats_requires_admin(self, client):
        resp = client.delete("/api/v1/stats/usage")
        assert resp.status_code == 401


class TestSessionTrace:
    def test_invalid_historical_trace_preserves_all_messages(self, app, client, monkeypatch, caplog):
        from types import SimpleNamespace
        from backend.api import sessions
        from backend.core.auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="alice")
        records = [
            {"type": "ai", "content": "old answer", "timestamp": "2026-10-16T00:00:00", "rag_trace": {"query": "private-raw-value"}},
            {"type": "ai", "content": "new answer", "timestamp": "2026-10-16T00:00:01", "rag_trace": {
                "tool_used": True, "tool_name": "search_knowledge_base", "query": "q", "unknown_internal_key": "private-raw-value",
                "citations": [{"source_label": "Source 1", "supported": True, "chunk_id": "c1"}],
            }},
        ]
        monkeypatch.setattr(sessions, "get_conversation_storage", lambda: SimpleNamespace(get_session_messages=lambda user, sid: records))
        response = client.get("/api/v1/sessions/history")
        assert response.status_code == 200
        messages = response.json()["messages"]
        assert [message["content"] for message in messages] == ["old answer", "new answer"]
        assert messages[0]["rag_trace"] is None
        assert messages[1]["rag_trace"]["citations"][0]["chunk_id"] == "c1"
        assert "unknown_internal_key" not in messages[1]["rag_trace"]
        assert "历史消息追踪格式不兼容" in caplog.text
        assert "private-raw-value" not in caplog.text
