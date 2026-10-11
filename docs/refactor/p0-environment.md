# P0 可复现环境：从零到 `/health` 200

P0-0 的产物之一。目标：**换一台机器、换一个操作系统，照这份序列复制粘贴就能把栈起来**。
所有命令都走 `scripts/dev.py`（只用标准库，故在 `uv sync` 之前也能跑），不在文档里写只适用于
某个 shell 的一次性命令。

实跑要求见 `09-milestone-p0.md` P0-0 的"等级 = real"：本文档的 §3 是实跑记录表，
**没填完的表就是没验过的证据**，不允许据此把任务标成 done。

## 1. 前置条件（跨环境六条，见 `08` §7）

| 依赖 | 版本要求 | 检查方式 |
| --- | --- | --- |
| Python | ≥ 3.12（`.python-version` 钉住） | `uv run python -V` |
| Go | ≥ 1.25（`server/go.mod` 钉 `go 1.25.1`） | `go version` |
| uv | 任意近期版本 | `uv --version` |
| Docker + compose v2 | 支持 `docker compose`（不是只能 `docker-compose`） | `docker compose version` |
| 宿主机内存 | ≥ 12 GB（Milvus standalone + BGE-M3 一起要） | — |
| Git 换行策略 | 由 `.gitattributes` 钉死 `eol=lf`，不依赖 `core.autocrlf` | `git check-attr text eol -- Dockerfile` |
| Node（只前端需要） | 见 `frontend/package.json` | `node -v` |

Windows 需要 Docker Desktop（WSL2 后端）。Linux 装 docker-ce + compose 插件即可，序列相同。

## 2. 启动序列

```bash
# 0) 拿代码
git clone <repo> && cd <repo-dir>   # 仓库改名后目录名跟着变，别写死

# 1) 自检：docker 在不在、.env 有没有、密钥是不是还是占位值、端口有没有被占
uv run python scripts/dev.py doctor

# 2) 配密钥（.env 不入库；这一步是交互式的人为动作，dev.py 不代填 secrets）
cp .env.example .env
uv run python -c "import secrets;print(secrets.token_urlsafe(32))"   # 输出写进 .env 的 JWT_SECRET_KEY=
# LLM_API_KEY / LLM_MODEL 是硬要求：backend/app.py 的 startup 无条件调 validate_config()，
# 缺失即 RuntimeError 拒绝启动（本机实测），所以**只验骨架也必须给非空值**（占位即可）。
# 要真答问题再补 LLM_BASE_URL；compose 已把这三个变量透传进 backend 容器。

# 3) 装依赖（可复现：uv.lock）
uv sync --extra test

# 3b) Go 骨架自检（不需要容器；中国大陆网络先设 GOPROXY，见 §4 第 7 条）
cd server && gofmt -l . && go vet ./... && go test ./... && cd ..

# 4) 起基础设施 + backend，等到容器 healthy
uv run python scripts/dev.py up                    # 首拉镜像 + Milvus 启动约 3-8 分钟
uv run python scripts/dev.py ps

# 5) 数据库基线（backend 启动时已自动 upgrade head；这步给"只改库不重启"和排错用）
uv run python scripts/dev.py migrate

# 6) 冒烟：三条 readiness
curl http://localhost:8000/health                  # backend
docker compose exec postgres pg_isready -U postgres
docker compose exec redis redis-cli ping

# 7) 测试分层（P0-0 X7 的判定命令）
uv run python scripts/dev.py test -m unit
uv run python scripts/dev.py test -m integration

# 8) 收工（--volumes 会连数据一起删，仅在你确认库里没有要留的东西时用）
uv run python scripts/dev.py down
```

P0-1 之后会多出 `go-api` / `go-worker` / `ai-core` 三个服务，以及 nginx upstream 切换（P0-8）。
那之后的入口仍是 `dev.py up`，命令面不变，只改 `docker-compose.yml`。

### 2.1 源码运行（日常开发的推荐路径）

只有中间件用 Docker，后端与前端跑在宿主上——**不构建 backend 镜像**（含 torch 的 16.5 GB）：

```bash
uv run python scripts/dev.py infra    # 只起 postgres/redis/etcd/minio/milvus/attu 并等 healthy
uv run python scripts/dev.py serve    # 本机 uvicorn --reload
cd frontend && npm run dev            # vite dev server
```

`DATABASE_URL` / `REDIS_URL` / `MILVUS_HOST` 的默认值已指向 `127.0.0.1`，无需额外环境变量。
2026-10-11 本机实测：`infra` 起 6 容器全 healthy（且未构建任何镜像）→ `serve` 后 `/health` 与
`/ready` 均 200（database / redis / milvus 三项 connected）→ `http://localhost:5173/api/v1/auth/me`
经 vite 代理的返回与直连后端逐字一致。**vite 5 只监听 `::1`**：用 `localhost` 访问，
用 `127.0.0.1` 会连接失败。探针路由**不带 `/api/v1` 前缀**（`/health`、`/ready`），
业务接口与 WS 才在 `/api/v1` 下。

上面 §2 的全栈容器序列仍是 **P0-8/P0-9 的验收路径**——那两卡验的是容器拓扑本身。

## 3. 实跑记录（填这张表才算 real 级验收）

| # | 步骤 | 主机 / 环境 | 日期 | 结果 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 1 | `dev.py doctor` | Windows（本机） / docker CLI 29.8.2 | 2026-10-09 | ✅ pass | 实测 exit=1，且**只**报两条：daemon 没在跑、缺 `.env`。这正是期望——阻塞项列得出来才叫自检 |
| 1b | `docker compose config --quiet` | 同上（daemon 停着） | 2026-10-09 | ✅ pass | 这条**不需要 daemon**：插值、字段拼写、端口形状纯客户端就能判。已接进 `doctor`，让"compose 写坏了"和"环境没起来"分成两个原因 |
| 2 | `dev.py up` + `ps` | Windows（本机） / Docker Desktop（本机实测）（系统级安装，Client（本机实测）） | 2026-10-10 | ✅ pass | 7 个容器起来：postgres / redis / etcd / minio / standalone / attu 全 healthy，backend 由 unhealthy 转 healthy。首拉镜像本机不复现（镜像已在），构建约 2–3 分钟 |
| 3 | `curl :8000/health` | 同上 | 2026-10-10 | ✅ pass | 容器内与宿主机均 HTTP 200，返回 `{"status":"ok","version":"0.1.0"}` |
| 3b | `gofmt` + `go vet` + `go test` | Windows（本机） / go1.25.1 | 2026-10-09 | ✅ pass | 16 项 Go 用例全绿，无需容器 |
| 4 | `dev.py migrate` | 同上 | 2026-10-10 | ✅ pass | exit 0；backend 启动时已自动 `alembic upgrade head`，手动复跑无变更 |
| 5 | `test -m unit` / `-m integration` | Windows（本机） | 2026-10-09 | ✅ pass | 391 / 57 通过；容器环境需复现一次 |
| 6 | 全量 `uv run pytest -q` | Windows（本机） | 2026-10-09 | ✅ pass | 448 通过（2026-10-09 本机基线）；`-m chain` 当前收集 0 项、exit=5，不是绿 |

**2026-10-10 状态更正（推翻 2026-10-09 那版"缺一次重启"的结论）**：真因不是 WSL 组件待重启，
而是 **Docker Desktop 根本没在运行**——`Start-Process 'Docker Desktop.exe'` 之后 **5 秒**引擎就绪，
`docker info` 返回 `（本机实测，linux 引擎）`。同一段另有两处与现场不符：安装形态是
**系统级**（`（Docker Desktop 安装目录）`，`com.docker.service` 为 Manual/Stopped），
不是 per-user 的 `（per-user 安装目录）`（该路径实测不存在）；版本也不是
"CLI 29.8.2 / Desktop 4.94"，实测版本与本行旧记录不同（具体版本号已移除）。
`wsl -l -v` 显示 `docker-desktop` 为 WSL 2、`wsl --status` 正常。

2026-10-09 那版之所以看着自洽，是因为**没把 daemon 拉起来就下了结论**；教训与 `03` §7 的
"文档谎报清单"同类：**环境结论必须来自本机实跑，不能来自日志片段的推断**。本次起栈还额外
暴露了三处真实缺陷（`.env.example` 行内注释、compose 缺 `target`、镜像名沿用目录名），
均已修复并记入 §4 第 10/12 条。

## 4. 已知坑（按踩到的顺序）

1. **换行**：容器里的 `entrypoint.sh` / Dockerfile 带 CRLF 会直接起不来。仓库 blob 全是 LF，
   `.gitattributes` 已钉 `* text=auto eol=lf`，不要再在 Windows 上手动改回 `core.autocrlf`。
2. **`.env` 缺失或占位密钥**：`335aeb7e` 起 `JWT_SECRET_KEY` 为空或是占位值即拒绝启动（fail-fast，
   这是有意的）。`dev.py doctor` 会先替你拦住这一步。
3. **端口冲突**：5432 / 6379 / 19530 / 8000 被宿主上其他实例占用是 compose 起不来的第一原因，
   `doctor` 会逐个提示是谁在用。
4. **存量库没有 `alembic_version`**：历史上用 `create_all` 建出来的库没有版本行，删掉静默兜底后
   backend 会拒绝启动。人工补基准版本的操作步骤属 **P0-2**（`audit_schema.py --check-baseline`），
   不在本卡解决。
5. **首拉很慢**：Milvus + etcd + minio + BGE-M3 模型下载。`dev.py up --timeout 600` 放宽等待，
   或 `--no-wait` 起完自己看 `logs -f`。
6. **bind mount 权限**：`volumes/`、`models/`、`data/`、`logs/` 在项目根下（`DOCKER_VOLUME_DIRECTORY`
   可覆盖）。Docker Desktop 需要把项目所在盘加进 File Sharing，否则容器里目录是空的。
7. **Go 模块代理**：`proxy.golang.org` 在中国大陆不可达（本机实测 dial tcp 超时）。设
   `go env -w GOPROXY=https://goproxy.cn,direct`，或单条命令带 `GOPROXY=https://goproxy.cn,direct go mod tidy`。
   注意 `go mod tidy` 比 `go build` 要得多——它连依赖自己的测试依赖（testify 等）一起解析，
   所以首次 tidy 失败不代表代码有问题。容器构建用 `--build-arg GOPROXY=...`，仓库不写死镜像。
8. **daemon 起不来时 `docker info` 不给原因，要看日志**：它只回
   `open //./pipe/dockerDesktopLinuxEngine: ... cannot find the file specified`（引擎没跑）或
   `Access is denied`（受限/权限）。真因在 `（Docker Desktop 日志目录）`：`monitor.log` 记
   `backend crashed ... reporting error to user`，`com.docker.backend.exe.log` 的 `GET /error`
   带完整 JSON。本机实测踩过一次：**`daemon.json` 带 UTF-8 BOM**（PowerShell 5.1 的
   `Set-Content -Encoding utf8` 会写 BOM）→ `parsing JSON: invalid character '茂'` → 引擎弹
   错误对话框并退出，`docker desktop restart` 会卡在那里等对话框被点掉。
   改这个文件务必无 BOM 写（`[System.IO.File]::WriteAllText($p,$json,(New-Object System.Text.UTF8Encoding($false)))`），
   而且**不要拿 PowerShell 的 `ConvertFrom-Json` 当校验**——它容忍 BOM，会给假绿；
   用 Python 的 `json.loads(open(p,'rb').read().decode('utf-8'))` 校验。
   另有一条能立刻用：`docker compose config` **不需要 daemon**，compose 自身的错先在停机状态下判掉。
   凡涉及 up/health 的行都填不了时，别据此推断"链路是好的"——那正是 `08` §1 ②禁止的事。
9. **`uv sync` 会重写整个 `uv.lock` 的下载源**：本机的 PyPI 镜像只活在当时的环境变量里
   （仓库没有 `uv.toml`，`env` 里也没有 `UV_INDEX_URL`），一旦不带镜像就跑
   `uv sync`/`uv lock`，3265 条 URL 会从 `pypi.tuna.tsinghua.edu.cn` 翻成 `pypi.org`，
   在中国网络下等于把可复现安装打断。更坏的是重解析会顺手丢掉 `nvidia-*`/`cuda-pathfinder`
   上的 `sys_platform != 'win32'` marker——这台 Windows 开发机随后就会去抓 CUDA wheel。
   规避：只改 `pyproject.toml` 的依赖声明、手工把对应两行插进 `uv.lock`
   （`[package.optional-dependencies]` 与 `[package.metadata].requires-dist` 各一条，按字典序落位），
   再用 `uv sync --extra test --locked` 验证（`--locked` 只校验不重解析）；
   确实要重解析时带 `uv lock --default-index https://pypi.tuna.tsinghua.edu.cn/simple`。
   **diff 只看增删行数不够**——这种整文件重写统计数看着正常，内容却全变了。
10. **`.env.example` 的历史写法会炸**：`KEY= #值`（赋值后跟行内注释）在 python-dotenv 下
   `#值` 会被当成真实值，`DENSE_EMBEDDING_DIM= #1024` → `int('#1024')` 抛 `ValueError`，
   应用起不来、13 个测试文件连收集都过不去（2026-10-10 已把那 11 行改成整行注释）。
   自检：`python -c "from dotenv import dotenv_values as v;print(v('.env.example'))"`。
11. **构建期 BuildKit 取 `# syntax=docker/dockerfile:1` 不走 Docker Desktop 代理**：Docker Hub
   被 DNS 污染时必然 `failed to fetch oauth token ... timeout`（daemon 侧的拉取反而是通的）。
   绕过：先用 daemon 把这 4 个镜像拉到本地经典存储，BuildKit 就会用本地前端——
   `docker pull docker/dockerfile:1 node:20-alpine python:3.12-slim nginx:alpine`。
12. **compose 的 backend 服务必须写 `target: backend`**：`Dockerfile` 是多阶段且**最后一阶是
   `nginx`**；不写 target 时构建出的是 nginx 镜像 → 容器监听 80，而端口映射与 healthcheck 都是
   8000，**永远 unhealthy**（实测容器日志里是 nginx 的 entrypoint）。
13. **数据盘被换过/恢复过之后 `container_name` 会撞车**：旧栈残留容器占着同名
   （`milvus-etcd`/`milvus-minio`/`milvus-standalone`/`milvus-attu`），compose 报
   `Conflict. The container name "/milvus-etcd" is already in use`。**重命名即可，不必删除**：
   `docker rename milvus-etcd milvus-etcd-prev`（4 个各做一遍），卷与数据不受影响。
14. **换镜像存储会让镜像"消失"**：`settings-store.json` 的 `UseContainerdSnapshotter` 决定你看的是
   containerd 那套还是经典 `overlay2` 那套。本机实测：置 `true` 时 `docker images` 只剩 4 个而
   `Local Volumes 3` 仍在（卷看得见、镜像看不见）；改回 `false` 后 10 个镜像 + 8 个容器全部回来。
   同文件的 `CustomWslDistroDir` 决定数据盘落在哪个盘（指回 `（数据盘目录，可在设置里改）`
   后旧数据盘被重新挂载、数据无损失）。注意 Docker Desktop 会重写该文件：代理键名是
   `ProxyHTTPMode`（大写 HTTP），写错大小写等于没写。
15. **受限运行下 `tmp_path` 类测试必失败**：`PermissionError: [WinError 5] ...\Temp\pytest-of-<用户名>`，
   与仓库无关——把 `TEMP`/`TMP` 指到工作区内可写目录再跑即可（本机实测集成层由
   `46 passed / 1 failed / 10 errors` 变为 `56 passed / 1 failed`）。

## 5. 与本卡之外的关系
- `dev.py seed` 不在本卡：种开发数据需要先跑通上传→入库链路（属 P1），
  现在写只会是一个假装能用的空壳命令。已在 `09` P0-0 输出项标注顺延。
- Go 侧的 schema 迁移用 `server/migrations/` + golang-migrate（P0-2 起），与这里的 alembic
  并存到有单一写者为止；两者操作的表由 `contracts/table-acl.md`（P0-4）划界。
