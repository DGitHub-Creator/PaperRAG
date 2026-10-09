"""错误信封只剩一种形状（决策 K1/K4）。

P0-5 要让 Go 逐字复刻 Python 的错误响应，所以这里断言的是**键集合恰好等于
`{"detail"}`**，多一个键就红 —— 契约里"浏览器只读 detail"的前提得有用例兜住。
三类来源都覆盖：鉴权 401、结构校验（原 422，本文件）、全局限流 429（见
`test_rate_limit_enforcement.py`）。
"""


def _detail(resp):
    body = resp.json()
    assert set(body.keys()) == {"detail"}, f"出现第二种错误信封: {body}"
    assert isinstance(body["detail"], str), f"detail 不是字符串: {body}"
    return body["detail"]


class TestEnvelopeOnRealApp:
    def test_401_is_detail_string(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        _detail(resp)

    def test_missing_fields_are_400_not_422(self, client):
        """K4：FastAPI 默认 422 + detail 数组，降级为 400 + 字符串后 Go 才复刻得起。"""
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 400, resp.text
        detail = _detail(resp)
        assert "username" in detail and "password" in detail

    def test_wrong_field_type_is_400(self, client):
        resp = client.post("/api/v1/auth/login", json={"username": 1, "password": "x"})
        assert resp.status_code == 400
        _detail(resp)
