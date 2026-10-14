# ResearchPilot

> 2026-10-09 起按《重构执行总纲》升级为 **ResearchPilot**（旧名与决策史见 `docs/archive/`）：
> Go 主后端（调度、鉴权、数据所有权）+ Python AI Core（解析、检索、推理），
> 目标是能自主完成「检索 → 深读 → 对比 → 探索 → 核验 → 报告」的科研平台。
> **重构进行中**：当前仓库里可跑的仍是 Python 单体 + Vue 前端，Go 侧只有骨架与数据访问层。

面向学术论文的 RAG 知识库，重点处理复杂版式、公式、定理、证明、引文与多轮问答溯源。

## 0. 先读这几份（文档权威入口）

| 要知道什么 | 去哪看 |
| --- | --- |
| **最高约束**：四条第一性原则、阶段顺序律、任务卡规范、开发规范 | [docs/refactor/08-principles-and-conventions.md](docs/refactor/08-principles-and-conventions.md) |
| **产品愿景**：五个入口、十项能力、V1–V4 路线、差异化与缺口清单 | [docs/refactor/11-product-vision.md](docs/refactor/11-product-vision.md) |
| **代码问题台账**：已发现的代码层问题（证据/影响/建议/归属），按愿景检查产出 | [docs/refactor/12-known-code-issues.md](docs/refactor/12-known-code-issues.md) |
| **前后端架构（As-Is 实测）**：运行形态、逐条端点、数据面差集、死代码清单，每条带 `file:line` | [docs/refactor/13-frontend-backend-architecture.md](docs/refactor/13-frontend-backend-architecture.md) |
| **功能模块规划**：M1…M17 逐模块的现状 / 目标行为 / 判据 / 卡片或提案 / 顺序约束 | [docs/refactor/14-feature-modules.md](docs/refactor/14-feature-modules.md) |
| **现在该做什么**：P0 任务卡（输入/输出/依赖/验收/证据等级）+ X1–X8 退出标准 | [docs/refactor/09-milestone-p0.md](docs/refactor/09-milestone-p0.md) |
| **进度多少 / 还差多少**：唯一真相源（`PROGRESS.md`、`progress.html` 是它的生成物） | [docs/progress.json](docs/progress.json) · [可视化看板](docs/progress.html) |
| 契约（浏览器面 / Go↔Python 内部面 / 错误码 / 表写入矩阵） | [contracts/](contracts/) |
| 目标架构（To-Be，大部分**未实现**） | [docs/refactor/02-target-architecture.md](docs/refactor/02-target-architecture.md) |
| 当前架构（**2026-10-09 dated 审计快照**，逐字保留、不作实施依据；要看今天的形状用上面的 `13`） | [docs/refactor/01-current-architecture.md](docs/refactor/01-current-architecture.md) |
| 从零起环境的命令序列 + 实跑记录 + 已知坑 | [docs/refactor/p0-environment.md](docs/refactor/p0-environment.md) |
| 文档索引与阅读顺序 | [docs/refactor/README.md](docs/refactor/README.md) |

被取代的旧计划全部移进 [docs/archive/](docs/archive/README.md)，**不作为实施依据**。
里程碑口径只用 **P0 架构与契约 → P1 后端迁移/最小原型 → P2 功能拓展 → P3 多 Agent**；
`Milestone A0/A/B/C` 属旧口径，对应关系见 [04-migration.md](docs/refactor/04-migration.md) §0。
**这是工程架构轴**；产品价值轴（V1.0 可信学术 RAG → V4.0 Research OS）与两者的映射见
[11-product-vision.md](docs/refactor/11-product-vision.md) §7——两条轴的编号不要混用。

## 1. 能力状态（三档口径，不含糊）

**已实现** = 在默认运行链路上生效且有用例；**部分实现** = 代码存在但有条件失效或未打通；
**未实现** = 有计划与卡片号，代码不存在或不产生用户可见能力。

| 能力 | 状态 | 说明 / 卡片 |
| --- | --- | --- |
| 混合检索（dense + 自实现 BM25 sparse + Milvus hybrid + RRF） | 已实现 | 稀疏向量是自实现 BM25（`backend/rag/embedding.py`），非 BGE-M3 原生 sparse |
| Rerank 双轨、Context Expansion、查询改写（HyDE / Step-back） | 已实现 | `backend/rag/rag_pipeline.py` |
| Agent 问答（LangGraph 工具调用、SSE / WebSocket） | 已实现 | SSE 目前**整段答案一次性下发**，非 token 级增量 |
| 引用展示、RAG Trace、会话历史 | 已实现 | 引用校验只验 `[Source N]` 编号存在性，不做语义接地 |
| 用户认证与权限 | 已实现 | JWT 分型、WS 回查用户表、限流按 `RATE_LIMIT` 真生效（`335aeb7e`）。前端**未接 refresh 流程**，60 分钟到期需重登 |
| 前端结构（单一请求出口、单一 token 所有者、模块单例状态） | 已实现 | FE-1；由 `scripts/check_frontend.py` 的 R1–R11 机器执行 |
| 契约目录与静态门禁 | 已实现 | P0-4 done；`scripts/check_contracts.py`（X3 本机 pass） |
| Go 服务骨架（health/ready、错误信封、trace、panic 兜底） | 部分实现 | P0-1：`gofmt`/`vet`/`test` 本机绿（16 项）；**未接真库、未进 compose** |
| Go 数据访问层（sqlc 生成物入库 + 连接池） | 部分实现 | P0-3 done（mock）：schema 源已从临时参照改指 P0-2 真库基线 `server/migrations/000001_baseline.up.sql`，10 张表全部生成 model；**仍未接进 compose**，池子只在有 `DATABASE_URL` 时启动 |
| ai-core 内部执行面（`/internal/v1/ai/*` 七条路径） | 部分实现 | P0-7：Python 侧 29 条 HTTP 级用例 + 幂等/取消/超时语义；`ai_executions` 表已有迁移文件 `server/migrations/000002_ai_executions.{up,down}.sql`（17 列，逐条回指 `executions.py`）并登记进 sqlc，但**未在真 PG 上执行过**；容器级链路仍未实现 |
| 学术结构识别（定理/证明/公式/引文/术语） | 部分实现 | 四个提取器**都接在分块期**（`theorem_detector` / `citation_extractor` / `glossary_extractor` 由 `document_loader` 调用，`citation_extractor` 还被 `rag_utils` 用），但 `backend/vectordb/milvus_writer.py` 写入的字段里没有这些列 → **入库即丢弃**，检索层拿不到 |
| 学术文档解析（PDF/Word/Excel、清洗、分块） | 部分实现 | 默认 PDF 结构分块只产叶级块，缺层级父块（`document_loader.py:_split_structural`） |
| Auto-merging（父级分块合并） | 部分实现 | 默认 PDF 路径不产父块 → 合并数恒为 0 |
| 文档上传与任务进度 | 部分实现 | 任务状态默认存**进程内存**，重启即丢（`USE_REDIS_JOB_MANAGER=true` 可切 Redis；根治属 P3 的 Go Frontier） |
| Schema 基线核查（`scripts/audit_schema.py`） | 部分实现 | P0-2：三模式已落——`--check-baseline`（文件形态：非破坏 + 幂等 + down 配对）、`--verify-columns`（与快照逐列比类型/varchar 长度/NOT NULL/DEFAULT）、只读 `--live`（37 项判定单测）。`migrations/000001_baseline` 已在真库结构的临时副本上连跑两遍幂等；`000002_ai_executions` 只过了离线形态检查，未在真库执行过。剩余：时间列语义探针（要往库写）与列级比对的实跑（要重导含 `columns` 的快照） |
| **Go 侧迁移执行器** | **未实现** | `server/migrations/` 只有**文件**，没有任何东西把它应用到库上：PATH 无 `migrate`、`server/go.mod` 无 golang-migrate 依赖、`dev.py migrate` 实为容器内 `alembic upgrade head`。今天读这两份 up 的只有两个离线工具（`audit_schema.py` 与 sqlc）。属 P0-8，先拍 D8（谁执行 / 何时执行 / 失败怎么办） |
| 入口路由机检（`scripts/check_nginx_routes.py`） | 已实现（判据） | X2/Y4 的判定：R1 `/api/` 必须指 `go-api`、R2 任何 location 不得指向 `ai-core`（含藏在 upstream 里）、R3 不得有 `/internal` 对外 location、R4 compose 里 `ai-core` 不发布宿主端口。21 项单测。**今天对真仓库配置如实 exit 1**（R1 命中，`/api/` 还指向 Python）——切 upstream 是 P0-8 的活 |
| PBKDF2 golden vectors（`scripts/export_pbkdf2_golden.py` → `contracts/pbkdf2_golden.json`） | 已实现（导出侧，mock 级） | X5 的输入件：10 条向量（6 正 4 负），覆盖标准 vs urlsafe base64、盐长 8/16/32、迭代数 40000/260000/310000 与 UTF-8 口令；期望值由生产 `verify_password` 现算，`--check` 防漂移。**文件不含明文口令，也不含真库 `password_hash`**（`--from-db` 只取形状统计）。Go 侧 `TestVerifyLegacyHash` 未写 → X5 仍 fail（P0-6） |
| 公式感知检索 | **未实现（死的是入库侧，不是查询侧）** | 查询链路其实已接进混合检索（`rag_utils.py:730` 调 `_formula_search`），但建索引函数 `_build_formula_index`（`rag_utils.py:644`）**零调用点**，LSH 索引永远是空的 → 恒返回 `[]`。「函数没接」与「接了但喂不到数据」修法不同，后者要补整条数据面 → P2-2 |
| ML 布局分析（图/表区域识别） | 部分实现 | **已接在入库链路上**（`document_loader.py:622` 调 `analyze_layout` 并给 chunk 打 `has_figure`/`has_table`）。两处折扣：外层是 `try/except Exception: pass`，失败静默；那两个标记没进 Milvus schema，检索层用不到 |
| 多模态图表检索 | **未实现** | `backend/rag/multimodal.py` 模块与单测都在，**零调用方** → P2 |
| 论文知识图谱 | **未实现（死表骨架）** | `paper_nodes` / `citation_edges` / `glossary_entries` 全仓只在 `backend/core/models.py` 出现，**零读零写** → `11 §8` 第 12 项（P4 展望，未定归属） |
| **论文自动抓取与导入**（arXiv / DOI / 研究方向） | **未实现（代码零存在）** | 不是"没接通"是"没有"：`backend/` 全仓 grep `arxiv` / `doi` / `crossref` / `httpx` / `requests` 无命中（唯一 `doi` 是 `academic_cleaner.py:47` 的正文正则），入库目前只有人工上传一条路 → **P2-9**（2026-10-13 立项） |
| 主题分类与语义书架 | **未实现** | 全仓无聚类/主题分组代码 → **P2-10**（2026-10-13 立项；必须排在 P2-1 chunk 真相层之后，否则是在 `VARCHAR(2000)` 截断副本上给不可信数据打标签） |
| `paper_chunks` 真相层（PG 持正文，Milvus 只存可重建索引） | **未实现** | 现在叶级正文**只在 Milvus** 且被 `VARCHAR(2000)` 截断（`backend/vectordb/milvus_client.py:240`），PG 里没有对应正文表 → P2-1 |
| 真实链路测试（chain 层）与浏览器 E2E | **未实现** | `pytest -m chain` 当前收集 0 项（exit=5）→ P0-5 / P0-9 / P1-6 |
| Go 接管 13 条浏览器接口 | **未实现** | → P1 |
| 多 Agent 自主探索（ResearchRun / Frontier / 报告生成） | **未实现** | → P3 |

断链的逐条证据见 [00-audit.md](docs/refactor/00-audit.md) §3；差距处置见 [03-gap-analysis.md](docs/refactor/03-gap-analysis.md)。

> **产品轴口径（V1.0–V4.0）**：上面这张表说的是**工程架构轴**的能力状态；用户视角的产品版本与缺口清单看
> [11-product-vision.md](docs/refactor/11-product-vision.md)（§10 路线、**§8 缺口清单**）。
> **当前 V1.0 未完成**——V1.0「可信学术 RAG」要求的可信化（chunk 真相层、公式/定理检索、原文定位）尚未做，
> 工作重心在架构轴 **P0**（骨架 + 契约 + 第一条垂直切片），P0 本身不产出产品能力。
> **2026-10-13 起分母已含产品轴两项**：`11 §8` 第 2 项的一部分登记成 **P2-9（论文自动抓取）/ P2-10（主题分类与语义书架）**，
> 所以完成度百分比比之前**更低**（58/394 h ≈ 14.7%）——这是把缺真实能力写进计划的诚实代价，不是进度倒退。
> 其余 10 项缺口（比较矩阵、Gap Explorer、Research Lab、Writing、Radar、Workspace、工具层、
> 信息增益驱动规划、双图、产品入口层）**仍在计划外**，等决策 **D5**。

## 2. 架构

### As-Is（当前可跑）

```mermaid
flowchart TB
    Browser["Browser / Vue 3 + TS"] --> API["FastAPI (backend/)"]
    Browser --> Stream["SSE / WebSocket"]
    Stream --> Agent["Agent Service"]
    API --> Auth["Auth / Sessions / Documents"]
    API --> Internal["/internal/v1/ai/* 内部执行面（P0-7，未接真库）"]
    Agent --> RAG["LangGraph RAG Pipeline"]
    RAG --> Milvus["Milvus: dense + sparse"]
    RAG --> PG["PostgreSQL: users, sessions, parent_chunks"]
    RAG --> Redis["Redis: cache, jobs"]
    API --> PG
    API --> Redis
    API --> Loader["Document Loader"]
    Loader --> PG
    Loader --> Milvus
```

### To-Be（目标，**未实现**，见 [02-target-architecture.md](docs/refactor/02-target-architecture.md)）

```mermaid
flowchart TB
    Browser["Browser"] --> Go["Go 主后端 server/：路由、鉴权、调度、数据所有权"]
    Go -->|"/internal/v1/ai/* Bearer 静态令牌"| AI["Python AI Core backend/：解析、检索、推理"]
    Go --> PG["PostgreSQL（唯一正文真相）"]
    Go --> Redis["Redis"]
    AI --> Milvus["Milvus（可重建索引）"]
    Go --> Worker["Go Worker：Frontier 派发 + 租约（P3）"]
```

Go 是唯一公开入口与唯一调度方；Python 只被动执行并如实上报，`proposed_tasks` /
`evidence_candidates` 对 Go 是**建议**，不携带写权限。

## 3. 从一台全新电脑跑起来

### 3.1 先装这几样（一次性，只需装宿主工具，装完不用管 Python 版本）

| 依赖 | 要求 | 用途 / 说明 |
| --- | --- | --- |
| **Git** | 较新版本 | 拉代码 |
| **Docker Desktop** | 较新版本，**必须处于运行状态** | 只用来跑中间件（postgres / redis / etcd / minio / milvus / attu）。Windows 用 WSL2 后端；`docker info` 能返回即就绪 |
| **uv** | 0.4+ | Python 依赖与解释器。**会自己装 Python 3.12**（仓库钉了 `.python-version = 3.12`），你不必单独装 Python |
| **Node.js** | **20 或更高**（含 npm） | 前端 dev server（Dockerfile 用的也是 node:20-alpine） |

只有做下面这些事时才需要额外安装：

| 可选依赖 | 版本 | 什么时候需要 |
| --- | --- | --- |
| Go | **1.25.1**（见 `server/go.mod`） | 编译/测试 Go 侧（`server/`）。只跑 Python 后端不需要 |
| sqlc | **v1.30.0**（版本钉死，`dev.py gen` 会校验） | 重新生成 Go 数据访问层（P0-3）。只跑项目不需要 |
| git-lfs | 任意 | 仓库 `.gitattributes` 给 `models/**` 留了 LFS 规则；**当前 HEAD 没有 LFS 文件**，不装也能正常跑 |

网络在中国大陆的话，提前做两件事（都是实测踩过的）：

```bash
go env -w GOPROXY=https://goproxy.cn,direct     # proxy.golang.org 在大陆不可达（仅 Go 侧需要）
# Docker Hub 若拉不动（DNS 污染），给 Docker Desktop 配镜像加速，或让引擎走本机代理
```

### 3.2 五步跑起来（推荐路径：源码运行，**不构建任何应用镜像**）

```bash
git clone <仓库地址> researchpilot && cd researchpilot
cp .env.example .env                    # 然后填三个必填项，见 3.4
uv sync --extra test                    # Python 依赖（uv.lock 可复现；顺带把 Python 3.12 装好）
uv run python scripts/dev.py doctor     # 自检：docker、.env、密钥占位值、端口占用、compose 静态校验
uv run python scripts/dev.py infra      # 只起中间件并等 healthy —— 不构建镜像
uv run python scripts/dev.py serve      # 本机源码跑后端（uvicorn --reload，:8000）

# 另开一个终端：
cd frontend && npm install && npm run dev    # http://localhost:5173
```

**这就够了。** 后端与前端都跑在你的机器上，Docker 只提供中间件；
不需要构建那个把全部依赖装进去的 16.5 GB backend 镜像（含 torch），改代码即时生效。
数据库/缓存/向量库地址无需配置——`DATABASE_URL` / `REDIS_URL` / `MILVUS_HOST` 的默认值已指向 `127.0.0.1`。

> 想严格保持 `uv.lock` 原样（镜像源配置不同时，不带 `--frozen` 的 `uv sync` 可能重写锁文件里的下载地址），
> 就用 `uv sync --frozen --extra test`。

### 3.3 怎么确认真的跑起来了

| 检查 | 期望 |
| --- | --- |
| `curl http://127.0.0.1:8000/health` | `{"status":"ok","version":"0.1.0"}` |
| `curl http://127.0.0.1:8000/ready` | 200，且 `database` / `redis` / `milvus` 三项都是 `connected` |
| 浏览器打开 `http://localhost:5173` | 前端页面可注册/登录，侧栏显示用户名 |
| `uv run python scripts/dev.py test -m unit` | 单元层全绿（全量基线：515 passed，其中 unit 458 / integration 57） |
| `docker compose ps` | postgres / redis / etcd / minio / standalone / attu 六个容器 running（除 attu 外均 healthy） |

两个最容易误判的点：

- **vite 5 只监听 `::1`**：请用 `http://localhost:5173`；用 `http://127.0.0.1:5173` 会连接失败。
- **健康探针不带 `/api/v1` 前缀**：`/health`、`/ready` 是裸挂载的；业务接口与 WebSocket 才在 `/api/v1` 下。

### 3.4 `.env` 的三个必填项（缺失或占位即拒绝启动，均已实测）

`JWT_SECRET_KEY`（`python -c "import secrets;print(secrets.token_urlsafe(32))"`）、`LLM_API_KEY`、`LLM_MODEL`——
**后两个连"只验骨架"也必须非空**（`app.py` 的 startup 无条件调 `validate_config()`），占位值即可。
`LLM_BASE_URL` 可选（走兼容 OpenAI 协议的自建网关时填）。

### 3.5 全栈容器：**已不再是验收路径**（2026-10-13 定案：容器只跑中间件）

定案是「容器只用于中间件，Go / Python / 前端一律源码跑」，所以**不需要**为验收构建那个把全部依赖
（含 torch）装进去的 16.5 GB `backend` 镜像，P0-8/P0-9 也不再验容器拓扑——X1 的判据已改写成
「`dev.py infra` 起中间件 + 宿主源码起进程」。

```bash
uv run python scripts/dev.py up        # ⚠️ 遗留命令：会 compose up -d 全栈（含 backend 镜像构建）
uv run python scripts/dev.py down      # 收工（不加 --volumes 不会删数据）
```

`up` 这条命令、dev compose 里的 `backend`/`nginx` 两个服务、`server/Dockerfile` 目前都还在仓库里，
它们是**与定案冲突的遗留物**，已登记为台账 **C29**，处置归 P0-8 —— 在它们被清理之前，**不要把 `dev.py up`
当成该跑的步骤**。真正的部署形态看 `docker-compose.prod.yml`（那份仍是全栈容器，且必须带 `--env-file`）。

### 3.6 起不来时先看这三处

1. `docker info` 只报 `pipe-not-found` → **Docker Desktop 没在运行**（不是缺组件、也不用重装，启动后约 5 秒引擎就绪）。
2. `doctor` 报端口被占 → 5432 / 6379 / 19530 / 8000 被本机其它实例占用，`doctor` 会指出是谁在用。
3. 上传的文件在容器里看不到 → Docker Desktop 的 File Sharing 需要包含项目所在盘
   （`volumes/`、`models/`、`data/`、`logs/` 都是 bind mount）。

更细的坑（`daemon.json` 的 BOM、代理键名大小写、`UseContainerdSnapshotter` 切换导致"镜像消失"、
受限运行下跑测试要指定 TEMP 等）见 [p0-environment.md](docs/refactor/p0-environment.md) §4。

完整序列（含首拉耗时、迁移、冒烟、收工）见 [p0-environment.md](docs/refactor/p0-environment.md) §2。

<details>
<summary>不用 dev.py 的手工路径</summary>

```bash
docker compose up -d postgres redis etcd minio standalone attu
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
cd frontend && npm install && npm run dev
```

| 服务 | 端口 | 用途 |
| --- | --- | --- |
| PostgreSQL | 5432 | 用户、会话、父级分块 |
| Redis | 6379 | 缓存、任务状态 |
| Milvus | 19530 | 向量检索 |
| S3 存储（compose 服务名仍叫 `minio`，镜像已是 `versity/versitygw`） | 9000 | Milvus 对象存储。**没有 9001 控制台**：MinIO 开源 Server 已被上游归档、镜像全网取不到，换成的 versitygw 不带 Web 控制台（`docs/refactor/12` 台账 C24） |
| Attu | 8080 | Milvus Web 管理 |
| 后端 | 8000 | `/`（前端）、`/docs`、`/health`、`/ready` |

环境变量：`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（兼容旧名 `ARK_API_KEY` / `BASE_URL` / `MODEL`），
`JWT_SECRET_KEY`（必填），`AICORE_INTERNAL_TOKEN`（Go→ai-core 内部令牌，留空则内部面拒绝一切请求）。

</details>

## 4. 仓库结构

```text
ResearchPilot/            # 仓库名、包名、镜像名、指标名已统一（改名于 2026-10-10 收口）
  backend/                Python AI Core：api/ core/ rag/ services/ agent/ vectordb/ internal_api/
  server/                 Go 主后端（P0-1 起）：cmd/api、cmd/worker、internal/{config,db,httpapi,observability}
  frontend/               Vue 3 + Vite + TS：src/{api,composables,components,utils,i18n}
  contracts/              契约唯一真相源：openapi.yaml、ai-execution.schema.json、error-codes.md、table-acl.md
  scripts/                dev.py（统一入口）、check_contracts.py、check_frontend.py、check_nginx_routes.py、
                          audit_schema.py、export_pbkdf2_golden.py、sync_progress.py
  tests/                  unit/ integration/（chain/ e2e/ 尚未建立）
  docs/refactor/          现行 spec（08 最高约束、09 任务卡、10 前端结构、00–05/07 事实与实施）
  docs/archive/           已归档的旧计划（不作为实施依据）
  alembic/                Python 侧迁移（Go 侧用 server/migrations/，两者边界见 contracts/table-acl.md）
```

## 5. 接口面

**浏览器面**（18 个操作 = 13 条前端在调 + 5 条探针）以 [contracts/openapi.yaml](contracts/openapi.yaml) 为准，
由 `scripts/check_contracts.py` 双向机检（契约声明了但前端没调、或前端调了但契约没有，都会红）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/auth/{register,login,refresh}` | 注册 / 登录 / 刷新 |
| GET | `/api/v1/auth/me` | 当前用户 |
| GET/DELETE | `/api/v1/sessions[/{id}]` | 会话列表 / 消息 / 删除 |
| POST | `/api/v1/chat`、`/api/v1/chat/stream` | 同步 / SSE 流式 |
| WS | `/api/v1/ws/chat?token=...` | WebSocket 流式 |
| GET/POST/DELETE | `/api/v1/documents/*` | 列表 / 异步上传 / 任务查询 / 增量导入 / 异步删除 |
| POST | `/api/v1/cache/clear` | 清缓存（admin） |
| GET | `/api/v1/stats/usage` | 使用统计 |

**内部执行面**（Go ↔ ai-core，不对浏览器暴露、不进 `openapi.yaml`）以
[contracts/ai-execution.schema.json](contracts/ai-execution.schema.json) 为准：
`POST /internal/v1/ai/execute`、`POST /internal/v1/ai/executions`、`GET …/{id}`、`GET …/{id}/result`、
`POST …/{id}/cancel`、`GET /internal/v1/ai/{healthz,readyz}`。鉴权是 `Authorization: Bearer $AICORE_INTERNAL_TOKEN`，
**未配置即拒绝服务**；错误体是 `{"detail": "...", "errors": [{code, retryable, ...}]}`，
九个错误码见 [contracts/error-codes.md](contracts/error-codes.md)。P0 只注册 `PARSE_PAPER`、`INDEX_PAPER` 两种 `task_type`。

## 6. 测试与门禁

分层由 marker 表达，目录即分层（`tests/conftest.py` 自动补标）：

| 层 | marker | 依赖 | 现状 |
| --- | --- | --- | --- |
| L0 单元 | `unit` | 无 | 458 项，每次提交 |
| L1 集成 | `integration` | TestClient（真库属 P1-6） | 57 项，每次提交 |
| L3 链路 | `chain` | compose 全栈 + LLM key | **0 项**（`-m chain` 返回 exit=5，不是绿） |
| L4 浏览器 | `e2e` | 全栈 + Playwright | **0 项**（P0-9） |

```bash
uv run pytest -q                                  # 全量 515 项
uv run pytest -m unit -q                          # 分层
uv run ruff check backend/ tests/ scripts/
uv run python scripts/check_contracts.py          # 契约双向吻合 + 错误码逐字一致
uv run python scripts/check_frontend.py           # 前端结构 R1–R11
uv run python scripts/sync_progress.py --check    # 进度产物与真相源一致
uv run python scripts/audit_schema.py --check-baseline   # 迁移非破坏 + 幂等 + down 配对
uv run python scripts/export_pbkdf2_golden.py --check    # golden vectors 与生成器不漂移
uv run python scripts/check_nginx_routes.py       # X2/Y4 判据；今天如实红（/api/ 仍指 Python）
cd frontend && npm run typecheck && npm run build
cd server && gofmt -l . && go vet ./... && go test ./...
uv run python scripts/dev.py gen --check          # sqlc 生成物无漂移（要先 git add，它比的是索引）
```

CI（`.github/workflows/ci.yml`）五个 job：backend / go / frontend / progress / docker。

**证据等级**：`none < mock < real < e2e`，写在 `docs/progress.json` 每张卡上，
`sync_progress.py` 会拦住「标了 done 但证据等级不够」。**2026-10-12 状态**：本机 Docker 已装且可用
（前提是 Docker Desktop 在运行；daemon 没起时 `docker info` 只报 pipe-not-found），中间件 6 个容器与
`dev.py infra` / `serve` 两条路径均已实跑；P0-0 已取得 real 级证据（`up` / `/health` 200 / `migrate` exit 0）。
P0 的 8 条退出标准现在是 **pass 4（X3/X6/X7/X8）· fail 3（X2/X4/X5）· not_run 1（X1）**：
fail 那三条的判定脚本已在 2026-10-12 落地并真的跑过——X2 红在 `/api/` 还指向 Python（P0-8），
X4/X5 红在 `server/internal/auth` 这个 Go 包还不存在（P0-6）。
**`fail` 与 `not_run` 是两回事**：前者已判定且不合格，后者还没判。X6 虽是 pass，
但它列出的 `migrate -path migrations` 那一半**跑不了**（golang-migrate 未接线，见 `docs/refactor/12` C18）。
**mock 绿灯不等于完成**——这是原则②。

## 7. 改名收口（2026-10-10 完成）

旧名在本仓已清除，**唯一保留旧字面量的地方是安全黑名单**——那不是命名残留：

| 项 | 现值 | 为什么留 |
| --- | --- | --- |
| `ADMIN_INVITE_CODE` 弱默认值黑名单 | 同时拒 `paperrag-admin-2026` 与 `researchpilot-admin-2026` | 已泄露口令的**拒绝清单**：只删旧值等于把暴露过的口令重新变成可用口令 |

同批改掉的：Go module path（`go.mod` + 7 行 import）、`REDIS_KEY_PREFIX`（含 `upload_jobs` 的作业键
前缀）、Prometheus 指标名（含 `Info` 组件名）、compose 镜像名、契约 `$id` 命名空间、远端 URL 改为
`git@github.com:DGitHub-Creator/ResearchPilot.git`。

既有部署若已在采集旧指标名或依赖旧 Redis 键，需同步更新抓取配置；旧键 TTL（1 天）到期即自行消失。
`docs/archive/` 下的归档件按仓库纪律逐字保留（历史记录，不是现状描述）。

## 8. 已知问题与升级注意

功能层面（证据见 [00-audit.md](docs/refactor/00-audit.md)）：

- 公式感知检索、多模态图表检索、ML 布局分析、论文知识图谱：**代码存在但未接入任何运行链路**。
- 默认 PDF 解析路径不产层级父块 → Auto-merging 恒不生效、`parent_chunks` 近乎空表。
- 分块期提取的公式/引文/术语/章节元数据在写入 Milvus 时被丢弃。
- 叶级分块正文**只在 Milvus**，字段 `VARCHAR(2000)` 会截断超长内容。
- 上传任务状态默认存进程内存，重启即丢。

安全基线：

- `ALLOWED_ORIGINS` 默认 `*`（生产校验拒绝启动）；上传上限默认 100MB，均需显式配置。
- 前端没有 refresh token 流程，`/auth/refresh` 无调用方。
- 全局限流只覆盖 HTTP；WebSocket 走自带的每用户 10 条/60 秒计数，不受 `RATE_LIMIT` 影响。
- 部署在自有反代之后必须设 `TRUST_PROXY_HEADERS=true`，否则限流按代理 IP 计数，所有访客共用一个桶。

启动行为变更（`335aeb7e` 起）：

- `JWT_SECRET_KEY` 无默认值，缺失即**拒绝启动**；`ADMIN_INVITE_CODE` 未配置则注册接口不能创建 admin。
- `init_db()` 不再在 Alembic 失败时回退 `create_all`；存量用 `create_all` 建表、无 `alembic_version` 的库
  需先人工补基准版本（步骤属 P0-2）。
- `RATE_LIMIT` 真的生效（`APP_ENV=production` 默认 60/minute，开发环境默认关闭）。
- 429 与校验失败的错误信封统一为 `{"detail": "..."}`（决策 K1/K4）；校验失败从 422 降级为 400 + 字符串。

## 9. 开发约定（摘要，全文见 [08](docs/refactor/08-principles-and-conventions.md)）

1. **端到端链路优先**：骨架 → 垂直链路 → 横向拓展，每阶段必须产出可运行可测试可演示的系统状态。
2. **完成 = 端到端可验证行为**：不接受"基本完成/大致可用/已支持"；验收标准必须可机检。
3. **先对齐再动手**：每阶段先定输入/输出/依赖/验收，禁止边写边改架构。
4. **最小修改**：优先复用现有资产，禁止无关重构与大规模改写。
5. 注释一律中文；密钥只经环境变量，不提交 `.env`；LLM 日志只记问题/模型/token 数，不记全文。
6. **每次改动同步计划与日程**：改 `docs/progress.json`（真相）→ 生成 `PROGRESS.md` / `progress.html` → `sync_progress.py --check` 是 CI 门禁。

## 10. Git

多账号场景下 remote URL 要匹配 `~/.ssh/config` 的 Host 别名：

```bash
git remote set-url origin git@github.com:DGitHub-Creator/ResearchPilot.git
ssh -T git@github.com
```

> 别名必须与 `~/.ssh/config` 里真实存在的 `Host` 一致（本机只有 `github.com` / `github-ryan` /
> `aliyun-mrm`）。写一个不存在的别名会在 `git fetch` 时直接变成
> `ssh: Could not resolve hostname ...`，而不是鉴权失败，容易误判成网络问题。

## License

MIT
