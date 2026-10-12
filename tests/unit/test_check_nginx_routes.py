"""`scripts/check_nginx_routes.py` 的判定单测（X2 / Y4 的 mock 级证据）。

这个脚本的价值全在"改坏了会被抓到"，所以每条规则都给一个合规输入和一个篡改输入。
今天跑真仓库的 `nginx.conf` 是**故意不过**的（`/api/` 还指向 Python），
那属于现场状态，不属于这里的解析与判定逻辑。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.check_nginx_routes import (  # noqa: E402
    check_compose,
    check_nginx,
    location_path,
    parse_upstreams,
    proxy_host,
    resolve,
    strip_comments,
)

GOOD = """
upstream go_api {
    server go-api:8080;   # 唯一公开入口
}
server {
    listen 80;
    location /api/ {
        proxy_pass http://go_api;
    }
    location / {
        root /usr/share/nginx/html;
    }
}
"""


def _bad(text: str) -> list[str]:
    return check_nginx(text)[0]


class TestParsing:
    def test_upstream_and_locations_are_paired_through_the_upstream_name(self):
        assert parse_upstreams(GOOD) == {"go_api": ["go-api:8080"]}
        assert check_nginx(GOOD) == ([], [])

    def test_comment_stripping_keeps_hash_inside_quotes(self):
        assert "#" in strip_comments('add_header X "a#b";')
        assert "#" not in strip_comments("location /api/ { # 注释\n proxy_pass http://x; }")

    @pytest.mark.parametrize(
        "spec,expected",
        [("= /health", "/health"), ("/api/v1/ws/", "/api/v1/ws/"), ("~* \\.js$", "\\.js$")],
    )
    def test_location_modifier_is_not_part_of_the_path(self, spec, expected):
        assert location_path(spec) == expected

    @pytest.mark.parametrize(
        "target,expected",
        [("http://backend", "backend"), ("http://backend:8000/", "backend"),
         ("https://go-api.internal/api", "go-api.internal")],
    )
    def test_proxy_host_drops_scheme_port_and_path(self, target, expected):
        assert proxy_host(target) == expected


class TestRules:
    def test_api_prefix_pointing_at_python_is_a_violation(self):
        text = GOOD.replace("server go-api:8080;", "server backend:8000;")
        errors, _ = check_nginx(text)
        assert any("违反 R1" in e for e in errors), errors

    def test_api_prefix_must_be_proxied_at_all(self):
        """`/api/` 里只发静态根 = 请求不会到 Go，也是违反，不是"没匹配到所以通过"。"""
        text = GOOD.replace("proxy_pass http://go_api;", "root /usr/share/nginx/html;")
        assert any("没有 proxy_pass" in e for e in _bad(text))

    def test_direct_ai_core_route_is_caught(self):
        text = GOOD + "\nlocation /internal/ {\n    proxy_pass http://ai-core:8001;\n}\n"
        errors, _ = check_nginx(text)
        assert any("R2" in e for e in errors)
        assert any("R3" in e for e in errors), "同一条 location 同时踩了 R2 与 R3，两条都要报"

    def test_ai_core_hidden_behind_an_upstream_is_still_caught(self):
        """"加一个 upstream 名字叫 api，里面偷偷指 ai-core"是这条规则要防的真实绕法。"""
        text = """
upstream api_pool { server go-api:8080; server ai-core:8001; }
server { location /api/ { proxy_pass http://api_pool; } }
"""
        assert any("R2" in e for e in _bad(text))

    def test_internal_location_without_ai_core_host_is_still_rejected(self):
        text = """
upstream go_api { server go-api:8080; }
server { location /internal/v1/ { proxy_pass http://go_api; } }
"""
        assert any("R3" in e for e in _bad(text))

    def test_non_api_probe_route_is_a_note_not_a_violation(self):
        """X2 的 expect 只管 `/api/` 与 ai-core；根路径探针还指着 Python 时给提示，不冒充判定。

        真仓库的 `location = /health` 就是这种形状——把它算成违反会让脚本第一天就红成
        一堆原因，把真正要先修的 R1 淹掉；完全不管又是放过，所以取"提示"这一档。
        """
        text = """
server {
    location = /health { proxy_pass http://backend:8000; }
    location /api/     { proxy_pass http://go-api:8080; }
}
"""
        errors, notes = check_nginx(text)
        assert errors == [], errors
        assert any("/health" in n for n in notes), notes

    def test_unparseable_config_fails_closed(self):
        assert any("没解析出任何 location" in e for e in _bad("server { listen 80; }"))

    def test_resolve_reports_multi_host_upstreams_instead_of_picking_one(self):
        ups = {"pool": ["go-api:8080", "ai-core:8001"]}
        assert resolve("http://pool", ups).startswith("多个(")


class TestComposeRule:
    def test_missing_ai_core_service_is_a_note(self):
        """服务还不存在（P0-8 的活）不能算违反，否则这条规则在 P0-8 之前永远报假警。"""
        errors, notes = check_compose({"services": {"postgres": {}}})
        assert errors == []
        assert any("还没有" in n for n in notes)

    def test_published_host_port_is_a_violation(self):
        errors, _ = check_compose({"services": {"ai-core": {"ports": ["8001:8001"]}}})
        assert any("R4" in e for e in errors)

    def test_host_network_mode_is_a_violation(self):
        errors, _ = check_compose({"services": {"ai-core": {"network_mode": "host"}}})
        assert any("R4" in e for e in errors)

    def test_internal_only_service_passes(self):
        assert check_compose({"services": {"ai-core": {"expose": ["8001"]}}})[0] == []


def test_shipped_nginx_config_fails_for_the_recorded_reason():
    """真仓库现在的配置必须**失败在 R1**（`/api/` 还指向 backend）。

    如果哪天它变成 pass，说明 P0-8 已经把 upstream 切到 Go —— 那时这条用例该被
    改成断言 pass，而不是留着当"脚本永远红"的借口。
    """
    text = (Path(__file__).resolve().parents[2] / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    errors, notes = check_nginx(text)
    assert any("违反 R1" in e and "backend" in e for e in errors), (errors, notes)
    assert not any("R2" in e for e in errors), "今天没有任何路由指向 ai-core，R2 本就该过"
