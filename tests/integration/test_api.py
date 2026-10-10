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
        pass


class TestStatsEndpoint:
    def test_get_stats_requires_admin(self, client):
        resp = client.get("/api/v1/stats/usage")
        assert resp.status_code == 401

    def test_reset_stats_requires_admin(self, client):
        resp = client.delete("/api/v1/stats/usage")
        assert resp.status_code == 401
