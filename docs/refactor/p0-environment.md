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
git clone <repo> && cd PaperRAG

# 1) 自检：docker 在不在、.env 有没有、密钥是不是还是占位值、端口有没有被占
uv run python scripts/dev.py doctor

# 2) 配密钥（.env 不入库；这一步是交互式的人为动作，dev.py 不代填 secrets）
cp .env.example .env
uv run python -c "import secrets;print(secrets.token_urlsafe(32))"   # 输出写进 .env 的 JWT_SECRET_KEY=
# 要验问答链路再补 LLM_API_KEY / LLM_BASE_URL；只验骨架可跳过

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

## 3. 实跑记录（填这张表才算 real 级验收）

| # | 步骤 | 主机 / 环境 | 日期 | 结果 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 1 | `dev.py doctor` | Windows / docker CLI 29.8.2 | 2026-10-09 | ✅ pass | 实测 exit=1，且**只**报两条：daemon 没在跑、缺 `.env`。这正是期望——阻塞项列得出来才叫自检 |
| 1b | `docker compose config --quiet` | 同上（daemon 停着） | 2026-10-09 | ✅ pass | 这条**不需要 daemon**：插值、字段拼写、端口形状纯客户端就能判。已接进 `doctor`，让"compose 写坏了"和"环境没起来"分成两个原因 |
| 2 | `dev.py up` + `ps` | — | — | ⬜ not_run | 记录首拉耗时 |
| 3 | `curl :8000/health` | — | — | ⬜ not_run | 期望 200 |
| 3b | `gofmt` + `go vet` + `go test` | Windows / go1.25.1 | 2026-10-09 | ✅ pass | 16 项 Go 用例全绿，无需容器 |
| 4 | `dev.py migrate` | — | — | ⬜ not_run | 存量库无 `alembic_version` 时见 §4 第 4 条 |
| 5 | `test -m unit` / `-m integration` | Windows | 2026-10-09 | ✅ pass | 391 / 57 通过；容器环境需复现一次 |
| 6 | 全量 `uv run pytest -q` | Windows | 2026-10-09 | ✅ pass | 448 通过（2026-10-09 本机基线）；`-m chain` 当前收集 0 项、exit=5，不是绿 |

**2026-10-09 状态更正**（先前这里写的是"本机未安装 Docker Desktop"，已被现场核查推翻）：
Docker CLI 29.8.2 + Compose v5.5.1 + Docker Desktop 4.94（**per-user 安装**，在
`（per-user 安装目录）`）都在。daemon 起不来的唯一原因是 **WSL2 的 Windows
可选组件装完还没重启**，而 per-user 安装用不了 Hyper-V 后端，所以没有绕开重启的第二条路。
因此 §2 的 4/6/8 步与 X1/X6/X7 的容器部分仍未实跑，P0-0 的证据等级停在 mock；
能实跑的三条（1、1b、3b）都已跑过并记在上面。重启后按本序列从第 4 步继续。

## 4. 已知坑（按踩到的顺序）

1. **换行**：容器里的 `entrypoint.sh` / Dockerfile 带 CRLF 会直接起不来。仓库 blob 全是 LF，
   `.gitattributes` 已钉 `* text=auto eol=lf`，不要再在 Windows 上手动改回 `core.autocrlf`。
2. **`.env` 缺失或占位密钥**：`d8f1563` 起 `JWT_SECRET_KEY` 为空或是占位值即拒绝启动（fail-fast，
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
8. **daemon 起不来的时候，`docker info` 不给原因**：本机实况是 Docker Desktop 已装但
   `docker info` 只回一句 "Docker Desktop is unable to start"。真正的原因在
   `（Docker 配置目录）\log\host\com.docker.backend.exe.log`——这次读到的是
   `Wsl/WSL_E_WSL_OPTIONAL_COMPONENT_REQUIRED` + "A reboot is required to complete the WSL
   installation"。**per-user 安装只能用 WSL2 后端**（日志里 Hyper-V 选项写着
   "Per-user installations can't run the Hyper-V backend"），所以没有绕开重启的替代配置。
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

## 5. 与本卡之外的关系
- `dev.py seed` 不在本卡：种开发数据需要先跑通上传→入库链路（属 P1），
  现在写只会是一个假装能用的空壳命令。已在 `09` P0-0 输出项标注顺延。
- Go 侧的 schema 迁移用 `server/migrations/` + golang-migrate（P0-2 起），与这里的 alembic
  并存到有单一写者为止；两者操作的表由 `contracts/table-acl.md`（P0-4）划界。
