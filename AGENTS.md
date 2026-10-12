# AGENTS.md —— 给接手这个仓库的 agent

> 目的只有一个：**让下一个 agent 不必重新踩坑**。这里只写「现在是什么样、什么已被推翻、什么绝对不能做」。
> 项目愿景见 [docs/refactor/11-product-vision.md](docs/refactor/11-product-vision.md)，架构与阶段见 [docs/refactor/](docs/refactor/)，
> 进度真相**只有** [docs/progress.json](docs/progress.json)。

## 1. 项目一句话

**ResearchPilot**（原 PaperRAG）：面向研究者的 AI 科研工作台。
Go 是唯一公开入口与唯一全局调度；Python（`backend/`）只被动执行单次 `AIExecution`；
**PostgreSQL 是唯一业务真相**，Milvus 降为可重建索引。

## 2. 文档权威层级（冲突时按此优先级）

| 顺位 | 文件 | 性质 |
| --- | --- | --- |
| 1 | `docs/refactor/08-principles-and-conventions.md` | **最高约束**（四条原则、阶段顺序律、任务卡规范、进度同步律） |
| 2 | `docs/progress.json` | **进度唯一真相**；`PROGRESS.md` 与 `progress.html` 是它的生成物，改完必须重跑 `sync_progress.py` |
| 3 | `docs/refactor/09-milestone-p0.md`、`10-frontend-structure.md` | 当前阶段的任务卡与 X1–X8 退出标准 |
| 3.5 | `docs/refactor/11-product-vision.md`、`12-known-code-issues.md` | **产品轴（V1–V4）** 与**代码问题台账**；两轴映射见 11 §7 |
| 4 | `contracts/` | Go↔Python 契约；改契约改这里，`check_contracts.py` 机检 |
| 5 | `docs/refactor/00-audit.md`、`01-current-architecture.md` | **dated 事实**：描述历史审计基线，**不是现状** |
| 6 | `docs/archive/` | 归档件，**不作为实施依据**，正文逐字保留 |

## 3. 现在的事实（2026-10-12）

- 进度 **12%**（45/372 h）；38 张卡：done 6 / in_progress 4 / pending 28；24 条退出标准 pass **4**（X3 契约机检、**X6 基线迁移非破坏+幂等**、X7 测试分层、X8 进度同步）；P0 38%，P1/P2/P3 = 0%。
- **P0-0 已取得 real 级证据**：`doctor` 全绿 → `up` 起 7 容器、backend healthy → `/health` 容器内与宿主机均 200 → `migrate` exit 0（未标 done 仅因 `down`/`logs` 未逐个实跑）。
- **P0-2 真库基线已交付（evidence 升到 real，X6 转 pass）**：`docs/refactor/schema-baseline.json` 由 `--live` 导出（PG 15.18，**10 张表**，alembic head `add_paper_knowledge_graph`，ORM 与真库漂移 23 处），`server/migrations/000001_baseline.{up,down}.sql`（10 表 / 59 列）已落地；离线 `--check-baseline` exit 0，并已把真库结构复制到临时库**连跑两遍均 exit 0**（幂等）。原挂的收尾（`sqlc.yaml` 指到 `migrations/`，与 `dev.py gen --check` 同一原子改动）**已于 2026-10-12 完成**。**本卡仍未 done 的两件都要 Docker**：现存快照是补 `columns` 之前导的，新命令 `--verify-columns` 如实返回 2；`probe_timestamps.py` 与时间列语义审计未产（X6 验收的第三问「每表时间列判定」）。
- **P0-3 done（2026-10-12，mock）**：sqlc 的 schema 源已从临时参照改指真基线，`server/sql/schema.sql` 已删除；此前 Go 只看得见 `users` 一张表，现在 10 张表 / 59 字段全部进 model。`dev.py gen` 同批加三条生成前置检查（schema 源是含 `.down.sql` 的目录 → 拒绝；`migrations/*.up.sql` 未登记 → 拒绝；生成物有孤儿 `X.sql.go` → 拒绝），各有负向用例。
- 测试基线 **475 passed**（unit + integration）；`chain` 与 `e2e` **各 0 条用例**，`-m chain` 收 0 项时 pytest 返回 **exit=5 而不是 0，不能算绿**。
- Docker 可用；数据盘位置可在 Docker Desktop 设置里改（不占系统盘）；当前 11 个镜像 / 约 4.3 GB，**没有 backend 镜像**（按需构建）。
- **2026-10-12 拍板了迁移编号分配**（详见 `docs/refactor/05` §2.6）：`000001` 基线 / `000002` `ai_executions`（已落）/ `000003` `fix_drift` / `000004` `paper_chunks`；**条件性预留不占号**（如 `auth_compat`），避免拿着没用的号。新表一律 `TIMESTAMPTZ`；可空列做唯一键成员时必须 `NOT NULL DEFAULT ''`（PG 里 NULL 互不相等，唯一约束会静默失效）；实现没写到的列不预先建；`GRANT` 在角色定义之前不写。
- **`000002_ai_executions.{up,down}.sql` 已落地但从未在真 PG 执行过**：17 列逐条回指 `backend/internal_api/executions.py:26-42` 的 dataclass（这张表的列清单**没有任何文档逐字写过**），已登记进 `server/sqlc.yaml` 并生成 `AiExecution`，`--check-baseline` exit 0。所以 P0-7 仍停 mock，不缺迁移文件而缺真库幂等验证 + compose 端口（P0-8）。
- Go 骨架 `gofmt`/`go vet`/`go test` 全绿，但**尚未进 compose、未与 Python 联调**（P0-1 的 real 缺口）。
- **2026-10-11 做过一次历史重写**（把个人信息与设备信息从仓库历史里清除）：102 个提交的作者/提交者统一为
  `ResearchPilot Dev <DGitHub-Creator@users.noreply.github.com>`；用户名、本机绝对路径、OS 与软件版本号、
  本机代理、设备级 SSH 别名已从**文件内容与提交信息**中一并清除。**此前的提交 SHA 全部改变**——
  文档里的 SHA 引用已按 `git filter-repo` 的 commit-map 修正；若外部笔记/Issue 里还留着更早的 SHA，
  它们指向的提交已不存在，请用 `git log --grep=<标题>` 重新定位。

## 4. ⚠️ 已被推翻的旧结论（**不要重复相信**）

| 旧结论（曾在 README / p0-environment.md / progress.json 里） | 现场核查后的事实 |
| --- | --- |
| 「本机缺一次重启才能用 Docker」「WSL2 可选组件装完待重启」 | **错**。真因是 Docker Desktop 没在运行；启动后 **5 秒**引擎即就绪 |
| 「Docker Desktop 是 per-user 安装 / CLI 29.8.2 / Desktop 4.94」 | **错**。系统级安装（不是 per-user）；具体版本号已从文档移除（避免暴露设备信息） |
| 「只验骨架可跳过 LLM key」 | **错**。`app.py` 的 startup 无条件调 `validate_config()`，缺 `LLM_API_KEY`/`LLM_MODEL` 即 `RuntimeError` 拒绝启动 |
| 「测试基线 448 / 333 / 307 项」 | 现状 **472 passed**（2026-10-12）；那些数字是 2026-10-09 的历史记录 |
| 「`cp .env.example .env` 就能起」 | **旧模板会炸**：`KEY= #值` 的行内注释被 python-dotenv 当成真实值（`int('#1024')`），2026-10-10 已把 11 行改成整行注释 |
| 「compose 的 backend 开箱可用」 | **缺 `target: backend`**：Dockerfile 多阶段且末阶是 nginx，不写 target 会构建出 nginx 镜像 → 永远 unhealthy（已修） |
| 「旧名 PaperRAG 还留在 go module path / Redis 前缀 / Prometheus 指标名 / 契约 $id」 | 2026-10-10 全部改为 `researchpilot`；**唯一保留旧字面量的是安全黑名单**（`paperrag-admin-2026`，删了等于把泄露口令重新变成可用口令） |
| 「`progress.json` 说本机未安装 Docker Desktop」 | 已改为「已解除」，并把推翻过程写进 `risks[0]` |
| 「真库有 9 张表」（`05 §2.2`） | **错**。真库是 **10 张表**（含 `alembic_version`）；`alembic_version` 是否该进 Go 基线仍待拍 |
| 「`users.created_at` / `users.role` 在库里没有 DEFAULT」（`05 §4`、`server/sql/schema.sql`） | **错**。真库有 `DEFAULT now()` 与 `DEFAULT 'user'`（否则这两列会出现在 `column_diff` 里）。那份失真所在的 `server/sql/schema.sql` 已于 2026-10-12 随 schema 源切换**删除**，正确结论记在 `05 §4.2.1` |
| 「把这两列的失真核对进 sqlc 的 diff 就行」 | **做不到**。切换后 `User` struct 与三条查询的生成类型逐字未变——**sqlc 不把列默认值编码进 Go 类型**，`gen --check` 只能抓类型/可空性/列与表的存在性。DEFAULT 的机检是 `audit_schema.py --verify-columns`（2026-10-12 落，快照需带 `columns`） |
| 「本机没有 sqlc 二进制，要 `go install …@v1.30.0`」（P0-3 旧记录） | **错**。`$HOME/go/bin/sqlc.exe` 就是钉住的 v1.30.0，`dev.py gen` 本来就优先用本机二进制、找不到才退回 `go run`。过期工具记录会让下一个 agent 白装一遍 |
| 「schema 源整目录交给 sqlc 就行」 | **会静默出错**。sqlc 按文件名顺序把目录里每个 `.sql` 当 schema 执行，`000001_baseline.down.sql` 排在 `.up.sql` **前面** → 先 DROP 再 CREATE，生成物等于按回退后的库产出。必须逐个列 `*.up.sql`（`dev.py gen` 已机检这条，以及"新 up 文件没登记""生成物有孤儿"两条） |
| 「`--check-baseline` 通过 = 基线与真库一致」 | **仍错**。它只校验**文件形态**（up 非破坏 + 幂等、down 配对），**不比对内容**。内容比对是另一条命令 `--verify-columns`（2026-10-12 落地，需要快照带 `columns`）。同一版的 down 规则不剥注释、up 剥（注释里写 `DROP TABLE IF EXISTS` 会被误判）——**已修**，两边现在一致 |
| 「`schema-baseline.json` 里有列清单可直接抄」 | **错**。旧版 `--live` 的 payload 只有 tables/alembic/tz/server_version/indexes/constraints/column_diff，**没有 columns**，所以基线的 varchar 长度与 NOT NULL 长期无机检。2026-10-12 已给 payload 补上 `columns` 并加了 `--verify-columns`，但**仓库里现存那份快照仍是旧版导出的、没有列清单**——要等 Docker 起来重跑 `--live` 才真的比得上 |

## 5. 本机环境要点

- **前置**：Docker Desktop 必须在运行；引擎没起来时 `docker info` 只报 pipe-not-found（不是缺组件）。
- `.env` **三个必填**：`JWT_SECRET_KEY`、`LLM_API_KEY`、`LLM_MODEL`（后两个连只验骨架也要有非空占位值）。
- 中国大陆：`go env -w GOPROXY=https://goproxy.cn,direct`；`docker.io` 被 DNS 污染 → 用镜像源或本机代理（本机代理 `本机代理端口`）。
- **BuildKit 取 `# syntax=docker/dockerfile:1` 不走 Docker Desktop 代理**：Docker Hub 不可达时必挂；先用 daemon 把 `docker/dockerfile:1`、`node:20-alpine`、`python:3.12-slim`、`nginx:alpine` 拉到本地即可。
- `scripts/audit_schema.py --live` **需要显式导出 `DATABASE_URL`**（脚本不读 config 的默认值），否则它会以为本机没有 PG。2026-10-12 起它会连列清单一起导出（`columns`），配套的离线比对是 `--verify-columns`；**现存那份快照还是旧版导出的、没有 `columns`**，此时 `--verify-columns` 如实返回 2 而不是假装比过（见 §4 末两行）。
- 验证基线迁移是否真的幂等，可用「临时库」法（不碰真库）：`pg_dump --schema-only langchain_app | psql -d <临时库>` 复制结构，再把 `000001_baseline.up.sql` 连跑两遍，两次都应 exit 0 且表数不变。
- Docker 数据盘是 VHDX，**删数据不会自动缩小**；真正回收要压缩/稀疏化。
- 受限沙箱下：docker 的命名管道、uv 的缓存、git 写 `.git/index.lock` 都可能被拒。**跑全量测试必须把 `TEMP`/`TMP` 指到工作区外的空目录**（本机实测），否则 41–42 个 `tmp_path` 用例会以 `PermissionError: [WinError 5]` **假失败**（表现为 `407 passed, 42 errors`——**不是仓库缺陷**）；也**不要**用 `--basetemp` 指到工作区内的既有目录。这些临时目录会带上创建时的完整性标签，策略在 `workspace-write` 与 `danger-full-access` 之间切换后就可能变成**谁都删不掉的毒目录**（本机出现过 `.tmp-pytest`/`.pytest-bt`/`pytest-of-<用户名>`/`tmp*/`），只能靠更高权限运行或用户自有终端清理。
- 更细的坑见 `docs/refactor/p0-environment.md` §4。

## 6. 两条运行路径

```bash
# 日常开发（推荐）：只有中间件用 Docker，后端/前端跑源码 —— 不构建 16.5 GB 的 backend 镜像
uv run python scripts/dev.py infra     # postgres/redis/etcd/minio/milvus/attu
uv run python scripts/dev.py serve     # 宿主 uvicorn --reload
cd frontend && npm run dev             # vite（只监听 ::1，用 localhost 访问）

# 容器级验收（P0-8 / P0-9 才需要）：全栈容器
uv run python scripts/dev.py up
```

**全新电脑的完整安装步骤**（依赖版本要求、五步命令、跑起来后的验收方法、起不来的三处排查）见 [README §3](README.md)。

## 7. 绝对不能做

- 不删 `parent_chunks` / `multimodal.py` / `layout_analyzer.py`（只降级能力口径，不删代码）。
- 不 `git mv backend → ai-core`；不引入 Kafka / RabbitMQ / Neo4j / 服务注册中心；不建两个全局调度器。
- **不把 mock 绿灯说成完成**：`status=done` 必须 `evidence ≥ requires`，由 `sync_progress.py --check` 强制。
- 不删 `docs/archive/` 里的归档件；不改 `00-audit.md`/`01-current-architecture.md` 里 dated 的事实（它们是历史证据）。
- 密钥只经环境变量，不提交 `.env`；注释一律中文。

## 8. 提交纪律

Conventional Commits（`fix(p0):` / `feat(dev):` / `chore(repo):` …）＋**每提交同更 `docs/progress.json`**（并重跑生成物）＋ 三个门禁全绿：

```bash
uv run python scripts/sync_progress.py --check
uv run python scripts/check_contracts.py
uv run python scripts/check_frontend.py
uv run python -m pytest -q            # 现状 449 passed
```
