# 02 — 目标架构（To-Be）

> **本文状态（2026-10-09 复核）**：性质=**决策**（To-Be：五条架构律 L1–L5、目录、契约、状态机、写入边界）。里程碑口径一律用 **P0–P3**；旧 `Milestone A/B/C`、`A0-x` 的对应关系见 [04 §0/§3](04-migration.md)。**大部分未实现**：Go 主后端与 Frontier 属 P1/P3，双图与 Evidence 属 P4 展望；已落地的只有契约目录（P0-4，`contracts/`）与 ai-core 内部执行面（P0-7，mock 级）。本文是目标态，不是现状——现状看 [01](01-current-architecture.md)。
> 输入：[plan-v2.0-researchpilot.md](../archive/refactor-plan-v2.0-researchpilot.md)（已归档）§1/§3/§4/§5 + 已确认决策 Q1–Q8（全 A）。
> 前提事实：[00-audit.md](00-audit.md)、[01-current-architecture.md](01-current-architecture.md)。
> **目标不是把代码变成 Go**，而是在功能正确、数据可信、可验证的基础上升级。凡与"数据可信"冲突的架构推进一律让路。

## 0. 五条不可违反的架构律

| # | 律 | 违反后果 |
| --- | --- | --- |
| L1 | **全局只有一个调度中心**：Research Run / Task 的生命周期、依赖、并发、预算、取消只由 Go 决定 | 双调度器争用同一 Run，出现不可复现的重复探索与成本失控 |
| L2 | **Python 只拥有局部**：一次 `AIExecution` 内部的 LangGraph 编排与检查点；产出的 `proposed_tasks` 是**建议**，必须经 Go 校验才入队 | 同 L1；且绕过预算与终止条件 |
| L3 | **PostgreSQL 是唯一业务真相**：文献、分块正文、证据、任务状态、事件日志以 PG 为准；Milvus 是可丢弃、可重建的索引 | 当前 `text VARCHAR(2000)` 截断即不可恢复（01 §7），无法支撑证据定位 |
| L4 | **模型输出一律非事实**：LLM/解析/网页/检索内容均视为不可信输入；只有经 Evidence 绑定且定位核验的陈述才标 `SUPPORTED` | 虚构引用与幻觉结论进入报告 |
| L5 | **渐进式，每阶段可独立启动与验证**：禁止一次性删除现有 Python 后端，禁止无业务价值的目录大迁移 | 中途不可演示、不可回滚 |

## 1. 目录布局（决策 Q2-A）

Go 落 `server/`，**Python 继续留在 `backend/`**，改名推迟到 P3 之后作为独立提交。

```text
ResearchPilot/
├── server/                     # Go 主后端（新增）
│   ├── cmd/
│   │   ├── api/                # HTTP/SSE/WS 服务入口
│   │   └── worker/             # Frontier 调度器 + Worker Pool 入口
│   ├── internal/
│   │   ├── auth/               # JWT 签发校验、PBKDF2、RBAC、workspace
│   │   ├── httpapi/            # Chi 路由、中间件、错误信封、SSE/WS 门面
│   │   ├── projects/           # ResearchProject
│   │   ├── runs/               # ResearchRun 状态机
│   │   ├── papers/             # Paper / PaperVersion / PaperFile
│   │   ├── chunks/             # PaperChunk 真相层（A0 由 Python 先落地）
│   │   ├── frontier/           # ResearchTask 队列：依赖、租约、幂等、重试
│   │   ├── scheduler/          # 唯一全局调度循环
│   │   ├── worker/             # goroutine pool、派发、fencing
│   │   ├── aiclient/           # Python AI Core 客户端（execute/submit/status/result）
│   │   ├── events/             # 持久事件日志 + SSE 游标续读
│   │   ├── knowledge/          # P4 展望（双图）
│   │   ├── evidence/           # P3/P4
│   │   ├── reports/            # P3
│   │   ├── storage/            # ObjectStorage 接口（本地卷 → S3）
│   │   └── observability/      # slog、metrics、trace 传播
│   ├── sql/                    # sqlc 查询
│   ├── migrations/             # golang-migrate SQL（唯一后续 schema 来源；**执行器尚未接线**，今天只有 `audit_schema.py` 与 sqlc 在读它——见 12 C18 / 决策 D8）
│   └── go.mod
├── backend/                    # Python AI Core（保留现路径，逐步退掉 api 层）
│   ├── internal_api/           # 新增：/internal/v1/ai/* 执行面
│   ├── agents/                 # planner/discovery/reader/analyst/explorer/verifier/writer
│   ├── rag/ vectordb/ agent/ core/models.py core/config/ …（沿用）
├── contracts/                  # OpenAPI + AI 执行契约 JSON Schema（Go/Python 共用）
├── frontend/                   # 保留 Vue 3，不改框架
├── docs/refactor/              # 本套 spec
└── docker-compose.yml          # 增加 go-api / go-worker 两个服务
```

**为什么 Python 保留 `backend/`**：62 个模块 + 41 个测试文件全部使用 `from backend.xxx` 绝对导入，`pyproject.toml` 的 packages.find、coverage source、`Dockerfile`、`main.py` 都指向它。同一次提交里既改目录又改架构会让 diff 不可评审、回归不可定位。

## 2. 进程与端口

| 进程 | 技术 | 对外 | 说明 |
| --- | --- | --- | --- |
| `go-api` | Chi + `net/http` | nginx → `/api/v1`、SSE、WS | 唯一面向浏览器 |
| `go-worker` | goroutine pool | 仅出站到 Python | 与 api 共享 PG，独立扩缩 |
| `ai-core` | FastAPI + uvicorn | **仅内网**，不发布到 nginx | 原 `backend` 容器改角色 |
| postgres / redis / milvus / minio / etcd | 不变 | — | Milvus 语义降级为"可重建索引"。**`minio` 这个槽位仍是 S3 兼容存储、服务名与 `MINIO_ADDRESS` 都不变，但镜像已换成 `versity/versitygw`**（MinIO 开源 Server 上游归档，原 pinned tag 全网取不到；台账 C24 / 决策 D9） |

`frontend/dist/` 由 nginx 直接服务；`app.py:141-150` 的静态挂载在 P1 完成时移除。

## 3. Go ↔ Python 契约（决策 Q7-A + 异步前置）

### 3.1 端点

| 端点 | 语义 |
| --- | --- |
| `POST /internal/v1/ai/execute` | **同步执行单个有界任务**（仅用于确定短时的任务；必须带 `deadline`） |
| `POST /internal/v1/ai/executions` | 提交，立即返回 `execution_id`（**MVP 即用，不作为后续升级**） |
| `GET /internal/v1/ai/executions/{id}` | 查询状态：`queued/running/succeeded/failed/cancelled` + `usage` |
| `GET /internal/v1/ai/executions/{id}/result` | 领取结果引用 `result_ref`（大输出走对象存储，不内联） |
| `POST /internal/v1/ai/executions/{id}/cancel` | 协作取消，向 LangGraph 传中断 |
| `GET /internal/v1/ai/healthz` `/readyz` | 探活（沿用现有 `health.py` 语义） |

> 异步前置的理由：LLM 类任务 30s–10min 是常态。纯同步会长时间占住 Go worker 连接，并把超时、取消、重试三套语义挤在一个 HTTP 请求里（00-audit §2.1 的 `LLM_TIMEOUT_SECONDS=30` 与 11 种 task_type 明显不匹配）。

### 3.2 请求体（`task_type` 分发，保留统一入口）

```jsonc
{
  "task_id": "uuid", "run_id": "uuid", "task_type": "READ_PAPER",
  "idempotency_key": "run:1:READ_PAPER:paper_v3",   // 见 §3.4
  "payload": { "paper_id": "...", "version_id": "...", "objective": "..." },
  "inputs":  { "object_ids": ["pdf:...", "parse:....json"] },  // 不传字节
  "config":  { "model": "...", "temperature": 0.2, "max_output_tokens": 4000 },
  "budget":  { "max_llm_calls": 6, "max_cost_usd": 0.05 },      // 沿用现有 budget.py 语义
  "deadline": "2026-10-09T12:00:00Z", "trace_id": "..."
}
```

响应统一：`status`、`result` 或 `result_ref`、`proposed_tasks[]`、`evidence_candidates[]`、`usage{calls,tokens,cost}`、`errors[]{code,retryable,detail}`。

**约定**：`evidence_candidates` 与 `proposed_tasks` 对 Go 而言是**输入建议**，不携带任何写权限。

### 3.3 支持的 task_type

`PLAN_RESEARCH`、`SEARCH_PAPERS`、`SCREEN_PAPERS`、`PARSE_PAPER`、`INDEX_PAPER`、`READ_PAPER`、`EXTRACT_KNOWLEDGE`、`COMPARE_PAPERS`、`EXPLORE_GAPS`、`VERIFY_EVIDENCE`、`GENERATE_REPORT`。

P0/P1 只需前 5 种（后 6 种属 P3/P4）。

### 3.4 幂等、取消、超时、fencing

| 关注点 | 设计 |
| --- | --- |
| 幂等键 | `idempotency_key = run_id + ":" + task_type + ":" + canonical_target`，PG `UNIQUE(run_id, idempotency_key)`；重复提交返回既有 `execution_id`（`ON CONFLICT DO NOTHING RETURNING`） |
| Python 侧幂等 | 以 `task_id` 建 `ai_executions` 行；已完成任务重复到达直接返回既有结果，**不重跑模型**（省钱关键） |
| 超时 | Go 侧 `context.WithTimeout(deadline)`；Python 侧 `asyncio.wait_for`；两侧都写 `usage` |
| 取消 | Go 置 `research_tasks.status=CANCELLED` + 调 `/cancel`；**结果落库前必须比对 `lease_token` 与 `run.state`**，取消后的过期结果直接丢弃（00-audit 无此机制） |
| 租约 | `lease_owner/lease_token/lease_expires_at`；续租由 worker 心跳；过期由 reaper 回 `READY` |
| fencing | 一切对 `research_tasks`/`paper_chunks`/`findings` 的写都带 `WHERE lease_token = $t`，token 单调递增，过期 worker 写入影响 0 行 |
| 重试 | `attempt_count/max_attempts` + `next_retry_at` 指数退避；`retryable=false` 的错误不重试 |
| 语义 | **至少一次**执行，明确不宣称跨 HTTP+PG+LLM 的 exactly-once（计划 §5.5） |

### 3.5 服务间鉴权与错误码

- P0/P1：静态服务令牌 `AICORE_INTERNAL_TOKEN`（Go 发 `Authorization: Bearer`），Python 校验 + compose 内网隔离，`ai-core` 不发布宿主端口。mTLS 记 DEFER。
- 错误码表（Python→Go，进 `contracts/`）：`INVALID_PAYLOAD`、`UNSUPPORTED_TASK_TYPE`、`BUDGET_EXCEEDED`、`MODEL_TIMEOUT`、`MODEL_RATE_LIMIT`、`PARSE_FAILED`、`INDEX_UNAVAILABLE`、`CANCELLED`、`INTERNAL`。每码固定 `retryable` 与 HTTP 映射。
- Go 对浏览器**保持现有信封**：`{"detail": ...}`（01 §6），只有 429 沿用现实现的 `{"error": ...}` 还是统一为 `detail`，作为兼容性决策留到 A0 结束后定案（见 04 §3.2）。

## 4. 状态机

### 4.1 ResearchRun（Go 独占写）

```
CREATED → PLANNING → RUNNING ⇄ (PAUSING → PAUSED → RUNNING)
                    RUNNING → COMPLETED | PARTIAL | FAILED | CANCELLED
```
- 暂停 = **安全点暂停**：停止派发新任务，允许在跑任务自然完成。
- 任何转移只经 `runs` service 校验；转移写 `research_events`。
- `PARTIAL` 必须能产出报告且显式列出未解决问题（计划 §5.7）。

### 4.2 ResearchTask（Go 独占写）

`PENDING →(依赖满足)→ READY →(领取)→ RUNNING → SUCCEEDED | FAILED`，扩展 `BLOCKED / RETRY_WAIT / CANCELLED / DEAD`。

领取 SQL 语义：`SELECT ... WHERE status='READY' AND next_retry_at<=now() ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT $n`，同事务写租约。

### 4.3 AIExecution（Python 独占写）

`ACCEPTED → RUNNING → SUCCEEDED | FAILED | CANCELLED`。只存在于 `ai_executions` 表，**Go 不写它，Python 不写 `research_tasks`**。

## 5. Frontier 与 Worker Pool

- Frontier = PostgreSQL `research_tasks` + 依赖表，非 Redis/队列中间件（计划 §5.3；决策不引入 Kafka）。
- 依赖解析由 scheduler 单循环完成：任务成功 → 找出以其为依赖的 `BLOCKED` → 全部满足则转 `READY` → 写事件。
- 同一个 Run 同一时刻**最多一个 Planner 任务**（计划 §5.6），仅在 Run 状态版本有效变化时触发。
- Worker 分类与初始并发（可调，非硬约束）：LLM 2–3、元数据检索 2–4、PDF 解析 1–2、向量索引 1–2。
- Worker 九步流程照计划 §5.4，额外强制：**第 7 步"事务内持久化业务结果"与第 8 步"标记完成"必须同一事务**，否则出现结果已写但任务仍显示 RUNNING 的裂口。

### 5.1 预算

Run 级 `max_papers / max_fulltext_reads / max_planning_rounds / max_expansion_depth / max_tasks / max_llm_tokens / max_cost / max_runtime / max_concurrent_workers`。

现状可复用：`core/budget.py` 的 per-query `MAX_LLM_CALLS=6`、`MAX_COST=0.05`（token 用 `len//4` 粗估）。**升级要求**：预算判定移到 Go（Run 级、跨任务），Python 的 budget 只作单次执行内的兜底；`usage` 必须持久化到 `model_usage_records`（现状 `budget.py` 仅 contextvars 内存，零持久化）。

## 6. 模块所有权与数据写入边界（交付物 5）

### 6.1 代码所有权

| 能力 | P1 之后归属 | 依据 |
| --- | --- | --- |
| JWT/RBAC/用户/workspace | **Go** | 复刻 PBKDF2 格式与 claims（01 §6、Q1） |
| 会话与消息 | **Go** | 需把覆盖式写改 append-only（00-audit §4） |
| 文档上传/删除/摄入的**编排** | **Go**（Frontier 任务） | 取代 `upload_jobs.py` 内存态 |
| PDF 解析、清洗、分层分块、学术识别 | **Python** | REUSE，正则实现成熟 |
| Embedding、BM25、Rerank、Hybrid、Context-expansion | **Python** | REUSE（计划 §4.1） |
| Milvus collection 建立/写入/删除 | **Python** | 唯一持有者；Go 只发指令与记录索引状态 |
| LangGraph 图、Agent 提示词、引用校验 | **Python** | 新 Agent 也建在此侧 |
| `research_*`、`papers*`、`paper_chunks`、`evidence_*`、`knowledge_*`、`exploration_*`、`reports*` | **Go** | L3 |
| `ai_executions`、LangGraph checkpoints、模型调用轨迹、解析中间产物 | **Python** | L2 |
| 事件日志 / SSE 游标 / Last-Event-ID | **Go** | 计划 §9.7，Redis 不得作为唯一事件源 |
| 全局调度、并发、重试、预算、取消 | **Go（唯一）** | L1 |

### 6.2 表级写入矩阵

| 表 | Go 写 | Python 写 | 说明 |
| --- | --- | --- | --- |
| `users` `workspaces` `workspace_members` | ● | ○(只读) | Python 只校验服务身份，不改业务主体 |
| `chat_sessions` `chat_messages` | ● | ✗ | 迁移后 Python 不再持久化对话 |
| `papers` `paper_versions` `paper_files` | ● | ✗ | Go 是文献实体权威 |
| `paper_chunks` | ● | ●（**仅 A0 过渡期**） | A0 由 Python 写以重建可信 chunk 层；Go 接管后改为 Go 写、Python 读 |
| `research_projects/runs/plans/tasks/task_dependencies` | ● | ✗ | L1 |
| `research_events` `outbox_events` | ● | ✗ | |
| `research_budget_usage` `model_usage_records` | ● | ✗（Go 从 `usage` 汇总） | Python 上报，Go 记账 |
| `knowledge_*` `exploration_*` `evidence_links` `research_claims` `report_*` | ● | ✗ | Python 只交候选（计划 §7.4） |
| `ai_executions` | ○(只读状态) | ● | Python 独占 |

○=只读，●=独占写，✗=禁止访问。矩阵的机器可读版本是 [`../../contracts/table-acl.md`](../../contracts/table-acl.md)，
由 `uv run python scripts/check_contracts.py` 在 CI 校验（规则：无双 W、`ai_executions` 必须 Python 独占、
`research_*` 的 Python 侧必须 ✗、Python 可写表 ≤2 张）；两者冲突时以 `table-acl.md` 为准并回改本表。
落实方式：Go 侧对 Python 只授予 `SELECT` + `ai_executions` 的 DML。

## 7. 前端与交付面

保留 Vue 3/Vite/TS，不换框架（计划 §9）。P1 只做**基址切换与故障修复**；A0 先让 6 项类型错误归零并把 `typecheck` 加进 CI（现状 CI 只 `npm run build`，01 §1 的机制缺口）。新增页面按 B/C 分批：Workspace、Monitor（SSE + `Last-Event-ID`）、Paper Reader、Report、Knowledge Explorer（有限节点展开）。

## 8. 双图与 Evidence（P4 展望轮廓，不展开）

`knowledge_nodes/edges` 复用现死表骨架（00-audit D5）；`exploration_*` 全新；强语义关系（`PROVES`/`CONTRADICTS_CLAIM`）**必须绑定 evidence**，禁止仅凭 embedding 相似建边。Evidence 状态 `SUPPORTED/INFERRED/CONFLICTED/UNVERIFIED`，`SUPPORTED ≠ 已独立验证证明正确`（计划 §8.1）。用关系表实现，**第一版不引入 Neo4j**。

## 9. 明确不做

一次性删除 Python 后端 · Kafka/RabbitMQ · 微服务注册中心 · Neo4j · 端到端 GraphRAG 复杂算法 · 为 P1/P2 推迟 P0 · 两个全局调度器 · 把 LangGraph State 当业务库 · 无标注数据下把 ≥95%/≥90% 当硬门禁（决策 Q8）。

## 10. 与产品愿景的关系

> 对照 [11-product-vision.md](11-product-vision.md)。本节是**建议与待决策项，不改现有架构律 L1–L5，也不改 §1 已落地的目录布局**；产品级缺口集中记在 `11 §8`。

**已覆盖**：`11 §4.4 Research Mission`（§1 的 `scheduler`/`frontier`/`worker`/`runs` + §5）· `11 §4.5 Research Knowledge Graph` 的**骨架位**（`knowledge/` 标 P4 展望）· `11 §6` 的"可信证据链"**原则**（L4 + `evidence/` 占位）· `11 §4.4` 的**报告出口**（`reports/` 标 P3）· `11 §4.1/§4.2` 的**存储与文件**前提（`papers/`、`chunks/`、`storage/`）· `11 §4.10 Research Workspace` 的前端面（§7 的 Workspace/Monitor/Reader/Report 页面）。

**未覆盖**：ARTEX 式的一等模块划分（`11 §9` + `§8` 第 10 项）在 §1 里**只占位不成模块**——`evidence/`、`reports/` 被压在 P3/P4，`llmpool/`+用量记账、`guard/`、`mcphttp/`+`skills/`、`notify/`+`selfupdate/`、独立 bench compose **完全没有**。建议的 Go 包名与归属（**待决策**）：

| 建议包 | 归属 | 对应愿景 | 与现状的关系 |
| --- | --- | --- | --- |
| `internal/evidence/` | L4 的落地形态，**升为一等包**（不是 P4 展望） | `§4.5`/`§6` 证据链、`§5①` 反向导航 | 现为 `evidence/` 占位；`papers/`、`chunks/` 只提供 hook 点 |
| `internal/report/` | 同时承载 V2 报告与 `§4.8` Research Writing | `§4.8`/`§5③` | 现为 `reports/`（P3），建议改名对齐 ARTEX |
| `internal/llmpool/` + `internal/llmrec/` | 模型池 + 逐次调用/用量记账 | `§4.10` 的"AI 预算"、`§4.4` 的预算耗尽 | 记账表 `model_usage_records` 已在 §6.2 矩阵里，但**没有对应包**；§5.1 的预算判定也缺一个落点 |
| `internal/guard/` | prompt injection / 工具白名单 / 上传面护栏 | `11 §11` 不把模型输出当事实 | `03 §6` 的缺口，目标架构里只有 L4 的原则、无模块 |
| `internal/mcphttp/` + `internal/skills/` | MCP 工具与技能扩展（学术 API、`§4.7` 验证工具） | `§4.7 Research Lab`、`§4.1` 的 Zotero/BibTeX | **完全没有**；`§3.3` 的 `task_type` 枚举无法表达外部工具 |
| `internal/notify/` + `internal/selfupdate/` | 自托管产品化 | `§4.9 Research Radar` 的主动通知、V4 私有部署 | **完全没有**（`11 §11` 把团队协作/私有部署留到 V4，但自更新不在非目标里） |
| `docker-compose.bench.yml` | 独立基准环境 | `11 §8` 第 11 项的可评估性（信息增益驱动规划需要能被量化对比） | P2-4 的 10–15 题回归集现在没有隔离的运行环境 |

**需拍板/冲突**：**有，两处**。①上表七项是否进 §1 目录与 §6.1 所有权表——选项 A：现在只登记为 `11 §8` 的候选卡，等 V2/V3 排期时再落目录（保持 L5 与"架构变更先回文档层对齐"）；选项 B：现在就把 `evidence/`、`report/`、`llmpool/` 三个包名写进 §1（代价是 §6.2 表级矩阵与 `contracts/table-acl.md` 要同批改，而 P0/P1 用不到）。②`notify/`+`selfupdate/` 与 `11 §11` 的口径张力：`§11` 说"团队协作与机构私有部署留到 V4"，但"主动发现"（`§4.9`）隐含推送能力——需要明确 `notify/` 是 V3 的 Radar 必需品还是 V4 的私有部署附属物。
