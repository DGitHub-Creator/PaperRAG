# 03 — 差距分析（Gap Analysis）

> **本文状态（2026-10-09 复核）**：性质=**决策依据**（差距清单、断链处置、未调用接口审计纪律、测试缺口）。里程碑口径一律用 **P0–P3**；旧 `Milestone A/B/C`、`A0-x` 的对应关系见 [04 §0/§3](04-migration.md)。清单本身不单独跟踪状态；每条差距的处置去向与完成情况见 [04 §0/§3](04-migration.md) 与 [../progress.json](../progress.json)。
> 现状见 01，目标见 02。每项标 **阻断里程碑**（A0/A/B/C）与**工作量档位**（S≈≤2h，M≈半天，L≈1–2天，XL≈≥3天；按 solo 15–20h/周）。

## 1. 功能正确性缺口（全部阻断 A）

| # | 缺口 | 证据 | 里程碑 | 档位 |
| --- | --- | --- | --- | --- |
| G1 | 登录/注册运行时 `ReferenceError`，且 **typecheck 红但 CI 只跑 build** | `useAuth.ts:2,34,45`；CI `npm run build` 无 `typecheck` | **A0** | S |
| G2 | 异步上传 URL 缺 `/api/v1` 前缀，被静态挂载吞掉 | `useDocuments.ts:143` vs `api.ts:3` | **A0** | S |
| G3 | `get_current_user` 不校验 `type` → **refresh token 可当 access token** | `core/auth.py:274-287` | **A0** | M |
| G4 | `ADMIN_INVITE_CODE` 有硬编码默认值，知道即可自助注册 admin | `config/auth.py:14`、`core/auth.py:352` | **A0** | S |
| G5 | `RATE_LIMIT` 仅用于日志，`default_limits=[]` → **无全局限流**；日志谎报"已启用" | `app.py:67-70`、`rate_limit.py:39` | **A0** | M |
| G6 | 危险默认值成体系：JWT secret 占位、`JWT_EXPIRE_MINUTES=1440`、`ALLOWED_ORIGINS=*` + credentials | `config/auth.py:5-12`、`app.py:92-98` | **A0** | M |
| G7 | `config/dev.py`/`prod.py` 从未被导入 → 环境预设全部失效 | 00-audit D8 | **A0** | M |
| G8 | 死配置 7 项（`ENABLE_HYDE`/`RETRIEVAL_COARSE_K`/`RERANK_TOP_N`/`RRF_K`/`FAST_MODEL`/`AMAP_*`） | grep 零引用 | A | S |
| G9 | `init_db()` alembic 失败后**静默 create_all** | `core/database.py:99-120` | **A0** | M |

## 2. 数据可信缺口（A 的前置阻塞，对应决策 Q5）

| # | 缺口 | 证据 | 里程碑 | 档位 |
| --- | --- | --- | --- | --- |
| G10 | **叶子块正文只存在于 Milvus，`text VARCHAR(2000)` 超长截断且不可恢复** | `milvus_client.py:240`、`documents.py:173-174` | **A0** | L |
| G11 | PDF 默认路径 `_split_structural` 只产 `chunk_level=3`，不产 1/2 → `parent_chunks` 实际近空、Auto-merging 恒 0 | `document_loader.py:496-587` | **A0** | L |
| G12 | 学术元数据在写入映射中被丢弃（`formulas/citations/glossary_terms/chapter_path/parent_content/has_figure/has_table`） | `milvus_writer.py:130-159` | **A0** | M |
| G13 | **没有 papers/documents 关系实体**：清单靠 Milvus 聚合 + 无锁文件 `ingested.json` | `documents.py:384,73-99` | A | L |
| G14 | 无文献版本概念：同名重传硬覆盖，旧版本不可寻址，无别名切换；`drop_collection` 零调用 | `milvus_client.py:303` | A | XL |
| G15 | `chat_messages` 覆盖式写（先 `.delete()` 再整批重插）→ 无法承载 evidence/finding 关联 | `conversation_storage.py:80` | A | M |
| G16 | 时间戳 naive/aware 混用且列是 `timestamp without time zone`；ORM/迁移漂移 3 处 | 00-audit §4 | **A0** | L |
| G17 | BM25 词频落文件、上传任务落内存/Redis TTL，均与 DB 无事务关系 | `embedding.py:80`、`upload_jobs.py:102,332` | A | L |
| G18 | `ParentChunk` docstring 的层级语义与实现相反（文档 0=叶，实现 3=叶） | `models.py:207-210` vs `rag_utils.py:727` | **A0** | S |

## 3. 功能断链处置（对应决策 Q6）

| 断链 | 处置 | 里程碑 | 理由 |
| --- | --- | --- | --- |
| D1 公式检索死代码（`_build_formula_index` 无调用） | **修通**，并补"上传→入库→查询"真链路测试 | **A0** | Reader Agent 读 UC/分布式论文依赖公式与定理元数据；同时是 README 谎报的源头 |
| D2 分层分块/Auto-merging 失效 | **修通**（并入 G11） | **A0** | 同上 |
| D3 元数据入库丢弃 | **修通**（并入 G12） | **A0** | 同上 |
| D4 多模态未接线 | **DEFER**，保留模块，不宣传 | C | 独立 feature，接线属新增而非迁移 |
| D6 布局分析装饰性 | **DEFER**，保留模块 | C | 同 D4 |
| D5 知识图谱死表（`paper_nodes`/`citation_edges`/`glossary_entries`） | **收编**为 `knowledge_*` 骨架，A0 只补索引漂移 | C | 表已建，复用比新建省 |
| D7 workspace/RBAC 空壳（`_check_workspace_access` 零调用、两表零写入） | **A0 不激活**，Go `auth` 接管时一并实现真实守卫 | A | 提前在 Python 补端点等于写丢弃代码 |
| D8 死配置 | 清理 | A | 见 G8 |

**同步动作**：README 的"项目简介/技术栈"需区分 **已实现 / 部分实现 / 规划中**（见 §7 文档谎报清单）。

## 4. 架构缺口（目标有、现状无）

| 目标能力 | 现状 | 里程碑 | 档位 |
| --- | --- | --- | --- |
| ResearchProject / Run / Task 三层与状态机 | **完全没有**（只有 chat_session） | A→B | XL |
| 持久化 Frontier（依赖、租约、幂等、重试） | 没有；`upload_jobs` 是内存/Redis 的进度条 | B | XL |
| 全局 Scheduler（唯一控制中心，Planner 单例） | 没有；现"多跳 Agent"实为单次工具 + 内层≤3 次检索（`tools.py:167`） | B | L |
| Worker Pool + fencing | 没有（`BackgroundTasks` 线程池，进程内） | B | L |
| Go↔Python 契约（execute/submit/status/result + 错误码 + 服务令牌） | 没有；Python 直接面向浏览器 | A | L |
| Evidence Registry / 语义接地校验 | 只有编号存在性校验（`verify.py:36`）；`evidence/retrieved_locators` 采了不用 | B→C | XL |
| 事件日志 + SSE `Last-Event-ID` 续读 | 没有（SSE 一次性下发整段答案，非 token 流） | A(SSE 门面)→B(事件表) | L |
| 预算持久化（`model_usage_records`） | 只有 contextvars 内存计数，零持久化 | B | M |
| 学术检索 Provider（OpenAlex/S2/arXiv/Crossref） | 没有；现只有本地语料检索 | A→B | XL |
| 报告生成与导出 | 没有 | B | L |
| 对象存储抽象（object_id） | 没有；本地文件直连路径 | A | M |

## 5. 未被前端调用的 12 条接口（对应决策 Q3-A）

`/auth/refresh`、`/chat`(同步)、`/documents/upload`(同步)、`/documents/{filename}`(同步删)、`/documents/upload/jobs`(列表)、`/documents/ingest`、`/cache/clear`、`/stats/usage`(GET/DELETE)、`/health`、`/ready`、`/metrics`。

**处置纪律（不得跳过）**：逐条完成**调用方审计**后才可弃用——检查仓库内脚本（`scripts/evaluate_rag.py`、`backend/agent/eval/run_eval.py`）、`docs/` 示例、CI、nginx 配置、Docker 健康检查（`docker-compose.yml:94` 的 backend healthcheck 可能依赖 `/health`）、外部使用者。`/health`、`/ready`、`/metrics` 属运维接口，**保留并由 Go 复刻**，不列入弃用。

## 6. 安全与合规缺口（计划 §11）

| 风险 | 现状 | 里程碑 |
| --- | --- | --- |
| Prompt injection | 论文全文直接进 LangChain prompt，无"内容非指令"分隔、无工具白名单校验 | B（Python Agent 层） |
| SSRF / 任意路径 | `/documents/ingest` 的 `directory` 接受任意服务端路径（`documents.py:605`）；外部 URL 抓取尚无实现 | A（Go 侧改为受控 object_id/白名单目录） |
| 上传面 | 仅 `MAX_UPLOAD_SIZE_MB=100`，无 MIME/真实类型校验、恶意 PDF 无隔离解析 | A |
| 鉴权语义 | G3/G4/G6 + WS 只解 token 不回查 DB、不查 role（`ws.py:43-48`） | **A0** |
| 限流 | G5；反代后共享一个桶（nginx 未配 trusted proxy） | **A0** |
| 内部服务暴露 | Python 现监听 0.0.0.0:8000 且面向浏览器；AI Core 化后必须只内网 | A |
| 密钥 | 无 `.env`；`JWT_SECRET_KEY` 有弱默认 | **A0** |
| 版权/全文 | 外部学术 API 全文获取的合规限制未定义 | B |

## 7. 文档谎报清单（需修正）

`README.md:9-16` 与 `docs/archive/plan-5-academic.md`（已归档）把 D1/D4/D5/D6 全标 ✅；`agent/core.py:3` 注释声称按 `complexity` 路由（实现只读 `classification`）；`ws.py:4-5` 声明不存在的 `/ws/upload/{job_id}`；`ParentChunk` docstring 层级语义反向；`app.py:67` 日志谎报全局限流；`README.md:216-218` "当前已知问题"漏掉全部真实断链。→ A0 内一并修正，README 改为三档状态表。

## 8. 测试与评测缺口（对应决策 Q8）

| 缺口 | 现状 | 里程碑 |
| --- | --- | --- |
| 真实浏览器 E2E | **完全没有**（0 个 Playwright/Cypress） | A0 起建，A 扩展 |
| 依赖真实 PG 的集成测试 | 没有；会话/文档测试全 mock（`4a5e806` 提交即"mock langgraph/sentence_transformers"） | A0 |
| 依赖真实 Milvus 的集成测试 | 没有 | A0 |
| **上传→入库→查询** 链路测试 | 没有；这正是 D1/D2/D3 能长期潜伏的原因 | **A0** |
| 跨语言契约测试（Go↔Python） | 不存在（Go 尚未引入） | A |
| 10–15 个固定科研问题基础回归 | 只有 `scripts/evaluate_rag.py`、`backend/agent/eval/run_eval.py`，无固定题集与基线记录 | A0 立骨架，A 补齐 |
| A/B/C 三组实验、20+ 问题 benchmark、消融 | 无 | **DEFER 到 C 之后** |
| ≥95% 定位准确率 / ≥90% 证据支持率 | 无标注数据 | 保留为**质量目标**，不作硬门禁 |

**纪律**：280 项 mock 测试继续保留并必须保持绿，但**不得作为"链路通过"的证据**；任何标记"某里程碑完成"的结论必须引用 A0 建立的真实 E2E 结果。
