"""反向代理路由机检（X2「Go 是唯一公开入口」＋ Y4「ai-core 只内网可达」）。

为什么要有这个脚本：X2/Y4 原来只有 `not_run`，因为**没有可判定的命令**。
"Go 是唯一公开入口"这句话靠人读 `nginx.conf` 是保不住的——加一条 location、
改一个 upstream 就可能把内部面暴露出去，而且改的人不会知道这违反了哪条原则。
这里把 `progress.json` 里 X2 与 Y4 的 `expect` 逐字变成判定：

  R1  所有 `/api/` 前缀的 location，其 `proxy_pass` 必须解析到 `go-api`
  R2  任何 location 都不得把流量交给 `ai-core`（含经 upstream 间接指向）
  R3  nginx 里不得出现 `/internal` 前缀的 location（内部面对浏览器不可见）
  R4  prod compose 里的应用服务不得发布宿主端口（入口只有 nginx）
  R5  dev compose 里不得出现应用服务（2026-10-13 定案「容器只跑中间件」）

只做静态判定，不发请求：它能在没有 Docker 的机器上告诉你"配置写错了"，
但**不能**证明运行中的 nginx 行为与配置一致——那半截要真起栈，所以 X2 的 level
仍是 e2e，本脚本 exit 0 只是它的必要条件。

R4 与 R5 按**形态**分判，这是 P0-8 里容易写错的一处：源码形态下 dev compose 里
本来就不该有 `ai-core`/`backend`，把它们当"服务不存在"吞成提示，那条规则就永远找不到
对象（空规则比红规则危险）；而 prod 是全栈容器，应用服务必须存在，只是不许开端口。
R1 在 2026-10-15 之前一直红（`/api/` 指向 Python 的 `backend`），那是 P0-8 的活，不是脚本缺陷。

用法：
    uv run python scripts/check_nginx_routes.py [路径...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NGINX_CONF = ROOT / "nginx" / "nginx.conf"
COMPOSE_FILE = ROOT / "docker-compose.yml"
PROD_COMPOSE_FILE = ROOT / "docker-compose.prod.yml"

GO_UPSTREAM = "go-api"
AI_CORE = "ai-core"
API_PREFIX = "/api"

#: compose 里属于"应用"的服务名。Python 那条在 compose 里叫 `backend`（历史名，
#: 目录也不改回去——见 `AGENTS.md §7` 的「不 `git mv backend → ai-core`」），
#: 但它在 R4 里的角色就是 ai-core，所以两个名字都要认，否则改个服务名就能绕过端口隔离。
APP_SERVICES = ("backend", "ai-core", "go-api", "go-worker", "nginx")

#: prod 里**唯一**允许发布宿主端口的应用服务。R4 判的是"内部面不对外"，不是"谁都不许监听"：
#: 把 nginx 也算进去等于要求部署形态里没有任何入口，那是一条永远不可能满足的规则。
PUBLIC_ENTRY = "nginx"

UPSTREAM_BLOCK_RE = re.compile(r"\bupstream\s+(?P<name>\S+)\s*\{")
LOCATION_BLOCK_RE = re.compile(r"\blocation\s+(?P<spec>[^{};]+?)\s*\{")
PROXY_PASS_RE = re.compile(r"\bproxy_pass\s+(?P<target>[^;\s]+)\s*;")
SERVER_DIRECTIVE_RE = re.compile(r"\bserver\s+(?P<addr>[^;\s]+)\s*;")


def strip_comments(text: str) -> str:
    """去掉 `#` 行注释，但不动引号里的 `#`（nginx 的值里出现 `#` 是合法的）。"""
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _block_body(text: str, open_brace_at: int) -> str:
    """从 `{` 的下标取到与之配对的 `}` 之间的内容（花括号嵌套要配对）。"""
    depth = 0
    for j in range(open_brace_at, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_at + 1 : j]
    raise ValueError("花括号不配对，无法解析 nginx 配置")


def parse_upstreams(text: str) -> dict[str, list[str]]:
    """`{upstream 名: [server 地址]}`。"""
    body = strip_comments(text)
    out: dict[str, list[str]] = {}
    for m in UPSTREAM_BLOCK_RE.finditer(body):
        block = _block_body(body, m.end() - 1)
        out[m.group("name")] = [s.group("addr") for s in SERVER_DIRECTIVE_RE.finditer(block)]
    return out


def parse_locations(text: str) -> list[tuple[str, str | None]]:
    """`[(location spec, proxy_pass 目标或 None)]`，按出现顺序。"""

    body = strip_comments(text)
    out: list[tuple[str, str | None]] = []
    for m in LOCATION_BLOCK_RE.finditer(body):
        block = _block_body(body, m.end() - 1)
        p = PROXY_PASS_RE.search(block)
        out.append((m.group("spec").strip(), p.group("target") if p else None))
    return out


def proxy_host(target: str) -> str:
    """`http://backend` → `backend`；去掉 scheme、端口与路径。

    nginx 里 `proxy_pass http://name/` 与 `http://name:8000/x` 的"打给谁"都由这一段决定，
    后面的路径只影响转发的 URI，不影响入口归属，所以判定只看它。
    """
    host = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", target)
    host = host.split("/", 1)[0]
    return host.rsplit(":", 1)[0] if ":" in host else host


def location_path(spec: str) -> str:
    """`= /health` → `/health`；`/api/v1/ws/` → 原样。修饰符（`=`/`~`/`^~`）不是路径的一部分。"""
    parts = spec.split(None, 1)
    if len(parts) == 2 and parts[0] in {"=", "~", "~*", "^~", "@"}:
        return parts[1]
    return spec


def resolve(target: str, upstreams: dict[str, list[str]]) -> str:
    """把 `proxy_pass` 目标解析成**真正的后端主机名**：upstream 名 → 它唯一的 server 主机。

    一个 upstream 指向多台机器时返回 `多个(go-api, go-api2)`，让调用方自己判——
    "把 backend 换成一个包含 ai-core 的 upstream"就是这种绕法，不能让它蒙过去。
    """
    host = proxy_host(target)
    servers = upstreams.get(host)
    if servers is None:
        return host
    hosts = sorted({proxy_host(s) for s in servers})
    if len(hosts) == 1:
        return hosts[0]
    return f"多个({', '.join(hosts)})"


def check_nginx(text: str) -> tuple[list[str], list[str]]:
    """返回 `(错误, 提示)`。错误就是 R1–R3；提示是脚本判定不了但值得看一眼的东西。"""
    errors: list[str] = []
    notes: list[str] = []
    upstreams = parse_upstreams(text)
    locations = parse_locations(text)
    if not locations:
        errors.append("没解析出任何 location——配置形状不认识，宁可报错也不要空过")
        return errors, notes

    for spec, target in locations:
        path = location_path(spec)
        where = f"location {spec}"
        if target is None:
            if path.startswith(API_PREFIX):
                errors.append(f"{where}：`{API_PREFIX}/` 下的 location 没有 proxy_pass，请求不会到达任何后端")
            continue

        backend = resolve(target, upstreams)
        if path.startswith("/internal"):
            errors.append(f"{where}：把内部面（`/internal`）暴露给了浏览器，违反 R3")
        if backend == AI_CORE or (backend.startswith("多个") and AI_CORE in backend):
            errors.append(f"{where} → {backend}：`ai-core` 不得成为公开入口的代理目标，违反 R2")
        elif path.startswith(API_PREFIX) and backend != GO_UPSTREAM:
            errors.append(f"{where} → {backend}：`{API_PREFIX}/` 必须指向 `{GO_UPSTREAM}`（当前是 {backend}），违反 R1")
        elif not path.startswith(API_PREFIX) and backend != GO_UPSTREAM:
            notes.append(f"{where} → {backend}：不在 `/api/` 前缀下，X2 的字面判定管不到它，但它仍不是 Go")

    for name, servers in upstreams.items():
        if not servers:
            notes.append(f"upstream {name} 没有 server，引用它的 location 会在运行时 502")
    return errors, notes


def check_compose(data: Any, *, dev: bool) -> tuple[list[str], list[str]]:
    """按**形态**判 compose。dev 与 prod 不是"好配置与坏配置"，是两种都合法的拓扑。

    dev（源码形态）判 R5：容器里**不许出现应用服务**。2026-10-13 的定案「容器只跑中间件」
      从前只写在 `AGENTS.md §7` 里，谁往 dev compose 加回 `backend` 都不会红——
      而它一进去，那个 16.5 GB 的镜像就重新变成 dev 的必经路径。
    prod（部署形态）判 R4：应用服务**不许发布宿主端口**。入口只有 nginx 的 80 一个，
      Python（服务名沿用 `backend`，角色是 ai-core）与 go-api 都只在 compose 网络里可达。

    分开判而不是判"有没有 ai-core 服务"：源码形态下那个服务**本来就该不存在**，
    把它当"服务不存在"的提示吞掉，等于让规则永远找不到对象——空规则比红规则危险。
    """
    errors: list[str] = []
    notes: list[str] = []
    services = (data or {}).get("services") or {}

    if dev:
        present = [name for name in APP_SERVICES if name in services]
        if present:
            errors.append(
                f"dev compose 里出现了应用服务 {present}。dev 形态容器只跑中间件"
                "（Go / Python / 前端源码跑，见 `dev.py serve` 与 `dev.py go-serve`），违反 R5"
            )
        else:
            notes.append("dev 形态：compose 里没有应用服务，符合「容器只跑中间件」的定案")
        return errors, notes

    for name in APP_SERVICES:
        if name == PUBLIC_ENTRY:
            continue
        svc = services.get(name)
        if svc is None:
            continue
        ports = svc.get("ports") or []
        if ports:
            errors.append(
                f"`{name}` 发布了宿主端口 {ports}。内部面与 Go 都必须只走 compose 网络，违反 R4"
            )
        if (svc.get("network_mode") or "").startswith("host"):
            errors.append(f"`{name}` 用了 host 网络，端口隔离等于没有，违反 R4")
    if not any(name in services for name in APP_SERVICES):
        notes.append("prod compose 里没找到任何应用服务，R4 这次没有东西可判")
    return errors, notes


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        paths = [Path(a) for a in args]
    else:
        # X2 与 Y4 共用这一条命令：nginx 决定"谁能被外部访问"，compose 决定"应用服务有没有开宿主端口"。
        # 两份 compose 都读：R5 的对象在 dev 那份，R4 的对象在 prod 那份，缺一份就有一条规则没归宿。
        # 显式传的路径缺失要报错，默认路径缺失只是没那个文件可查。
        paths = [p for p in (NGINX_CONF, COMPOSE_FILE, PROD_COMPOSE_FILE) if p.is_file()]
        if not paths:
            print("[nginx] 既没有 nginx/nginx.conf 也没有任一 compose，无从判定")
            return 1

    all_errors: list[str] = []
    all_notes: list[str] = []
    for path in paths:
        if not path.is_file():
            print(f"[nginx] 读不到 {path}：入口路由无法判定")
            return 1
        if path.name.startswith("docker-compose") or path.suffix in (".yml", ".yaml"):
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            # 形态由**文件名**定：dev 那份的合法形状是"没有应用服务"，prod 那份是
            # "应用服务不开宿主端口"。同一个函数按同一套规则判两份文件，
            # 结果只会是其中一条规则永远在报找不到对象。
            errors, notes = check_compose(data, dev=path.name == "docker-compose.yml")
        else:
            errors, notes = check_nginx(path.read_text(encoding="utf-8"))
        all_errors += [f"{path.name}: {e}" for e in errors]
        all_notes += [f"{path.name}: {n}" for n in notes]

    for n in all_notes:
        print(f"[nginx] 提示：{n}")
    if all_errors:
        for e in all_errors:
            print(f"[nginx] 违反：{e}")
        print("[nginx] 未通过。X2/Y4 的 expect 是「/api/ 只指 go-api、没有任何路由指向 ai-core」。")
        return 1
    print("[nginx] 通过：/api/ 全部指向 go-api，无路由指向 ai-core。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
