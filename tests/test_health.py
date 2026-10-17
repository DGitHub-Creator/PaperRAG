"""健康检查端点测试。"""

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """测试 /health 和 /ready 端点。"""

    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_ready_all_healthy(self, client: TestClient, monkeypatch):
        """所有依赖可用时应返回 200。"""
        monkeypatch.setattr(
            "backend.api.health._check_db", lambda: (True, "connected")
        )
        monkeypatch.setattr(
            "backend.api.health._check_redis", lambda: (True, "connected")
        )
        monkeypatch.setattr(
            "backend.api.health._check_milvus", lambda: (True, "connected")
        )
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert all(c["status"] == "ok" for c in data["checks"].values())

    def test_ready_degraded(self, client: TestClient, monkeypatch):
        """任一依赖不可用时应返回 503。"""
        monkeypatch.setattr(
            "backend.api.health._check_db", lambda: (False, "disconnected: mock")
        )
        monkeypatch.setattr(
            "backend.api.health._check_redis", lambda: (True, "connected")
        )
        monkeypatch.setattr(
            "backend.api.health._check_milvus", lambda: (False, "timeout after 3s")
        )
        resp = client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["detail"]["status"] == "unhealthy"
        checks = data["detail"]["checks"]
        assert checks["database"]["status"] == "error"
        assert checks["redis"]["status"] == "ok"
        assert checks["milvus"]["status"] == "error"

    def test_ready_check_timeout_is_bounded(self, client: TestClient, monkeypatch):
        """单项检查超时应被 READY_CHECK_TIMEOUT 上限截断并返回 503。"""

        def _slow_check():
            import time

            time.sleep(10)
            return True, "connected"

        monkeypatch.setattr(
            "backend.api.health._check_db", lambda: (True, "connected")
        )
        monkeypatch.setattr(
            "backend.api.health._check_redis", lambda: (True, "connected")
        )
        monkeypatch.setattr("backend.api.health._check_milvus", _slow_check)

        import time

        start = time.perf_counter()
        resp = client.get("/ready")
        elapsed = time.perf_counter() - start

        assert resp.status_code == 503
        assert elapsed < 8  # 远小于慢检查的 10s
        data = resp.json()
        assert "timeout" in data["detail"]["checks"]["milvus"]["detail"]


def test_readiness_does_not_expose_database_connection_details(client, monkeypatch):
    from unittest.mock import MagicMock

    from backend.api import health

    database = MagicMock()
    database.execute.side_effect = RuntimeError("postgresql://admin:private-password@internal-host/database")
    monkeypatch.setattr(health, "SessionLocal", lambda: database)
    monkeypatch.setattr(health, "_check_redis", lambda: (True, "connected"))
    monkeypatch.setattr(health, "_check_milvus", lambda: (True, "connected"))
    response = client.get("/ready")
    assert response.status_code == 503
    assert "private-password" not in response.text
    assert "internal-host" not in response.text
    assert response.json()["detail"]["checks"]["database"]["detail"] == "unavailable"
    database.close.assert_called_once()
