"""API 端点集成测试 —— 健康检查、认证边界、统计。"""


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_ready_returns_503_without_services(self, client):
        # /ready tries to connect to DB/Redis/Milvus, all unavailable
        resp = client.get("/ready")
        assert resp.status_code == 503


class TestAuthUnauthenticated:
    def test_me_unauthenticated(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_refresh_unauthenticated(self, client):
        pass


class TestStatsEndpoint:
    def test_get_stats_requires_admin(self, client):
        resp = client.get("/api/v1/stats/usage")
        assert resp.status_code == 401

    def test_reset_stats_requires_admin(self, client):
        resp = client.delete("/api/v1/stats/usage")
        assert resp.status_code == 401
