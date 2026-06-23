"""API 文档端点集成测试 —— 上传、删除、列表、增量导入的鉴权边界。"""


class TestDocumentEndpointsAuth:
    def test_list_documents_requires_auth(self, client):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 401

    def test_upload_requires_auth(self, client):
        resp = client.post("/api/v1/documents/upload")
        assert resp.status_code in (401, 422)

    def test_delete_requires_auth(self, client):
        resp = client.delete("/api/v1/documents/test.pdf")
        assert resp.status_code == 401

    def test_async_delete_requires_auth(self, client):
        resp = client.delete("/api/v1/documents/delete/async/test.pdf")
        assert resp.status_code == 401

    def test_ingest_requires_auth(self, client):
        resp = client.post("/api/v1/documents/ingest", json={"directory": "/tmp"})
        assert resp.status_code == 401

    def test_upload_jobs_requires_auth(self, client):
        resp = client.get("/api/v1/documents/upload/jobs")
        assert resp.status_code == 401

    def test_upload_job_by_id_requires_auth(self, client):
        resp = client.get("/api/v1/documents/upload/jobs/fake-id")
        assert resp.status_code == 401

    def test_delete_job_by_id_requires_auth(self, client):
        resp = client.get("/api/v1/documents/delete/jobs/fake-id")
        assert resp.status_code == 401


class TestCacheEndpointAuth:
    def test_cache_clear_requires_auth(self, client):
        resp = client.post("/api/v1/cache/clear")
        assert resp.status_code == 401


class TestStatsEndpointAuth:
    def test_stats_requires_auth(self, client):
        resp = client.get("/api/v1/stats/usage")
        assert resp.status_code == 401
