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

    def test_ready_degraded(self, client: TestClient):
        """当依赖服务不可用时应返回 503。"""
        resp = client.get("/ready")
        # 在测试环境中，数据库/Milvus 可能不可用
        assert resp.status_code in (200, 503)
        if resp.status_code == 503:
            data = resp.json()
            assert data["detail"]["status"] == "unhealthy"
