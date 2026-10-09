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
| 1 | `dev.py doctor` | — | — | ⬜ not_run | 期望：无密钥时 exit=1 并列出阻塞项 |
| 2 | `dev.py up` + `ps` | — | — | ⬜ not_run | 记录首拉耗时 |
| 3 | `curl :8000/health` | — | — | ⬜ not_run | 期望 200 |
| 4 | `dev.py migrate` | — | — | ⬜ not_run | 存量库无 `alembic_version` 时见 §4 第 4 条 |
| 5 | `test -m unit` / `-m integration` | — | — | ⬜ not_run | 期望 310 / 23 通过（本地已跑通，容器环境需复现） |
| 6 | 全量 `uv run pytest -q` | — | — | ⬜ not_run | 期望 333 通过（2026-10-09 本地基线） |

**2026-10-09 状态**：本机（Windows）**未安装 Docker Desktop**，`dev.py doctor` 实测返回
exit=1 并给出"未找到 docker CLI"。因此 §2 的 4-8 步与 X1/X6/X7 的容器部分尚未实跑，
P0-0 的证据等级停在 mock（脚本与分层的单元级验证 9 项通过），不标 done。

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

## 5. 与本卡之外的关系

- `dev.py seed` 不在本卡：种开发数据需要先跑通上传→入库链路（属 P1），
  现在写只会是一个假装能用的空壳命令。已在 `09` P0-0 输出项标注顺延。
- Go 侧的 schema 迁移用 `server/migrations/` + golang-migrate（P0-2 起），与这里的 alembic
  并存到有单一写者为止；两者操作的表由 `contracts/table-acl.md`（P0-4）划界。
