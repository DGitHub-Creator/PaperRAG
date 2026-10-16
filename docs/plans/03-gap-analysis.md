# 03 — 差距分析（Gap Analysis）

> 文档性质：实施计划/运行参考。文中早期实跑与现状数字是 dated 记录，不自动代表当前工作区。
> 当前实现见 [13](../reference/13-frontend-backend-architecture.md)，状态见 [progress.json](../progress.json)，启动见 [README](../../README.md)。

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
| G16 | 时间戳 naive/aware 混用且列是 `timestamp without time zone`；ORM/迁移漂移 3 处（**审计时的口径**：索引/UNIQUE/时区三类）。2026-10-11 `--live` 实测 `column_diff` 是 **23 条**，口径不同且**不含类型漂移**：22 条 `no_server_default`（`chat_messages.content`、`users.username` 这类 NOT NULL 文本列——ORM 给的是 Python 侧 `default=`，库侧本就没有 server DEFAULT，基线照库抄所以也不给）＋ 1 条 `only_in_db`（`alembic_version.version_num`）。G16 点名的三件事里只有"时区"一条会进这 23 条之外的判据，索引/UNIQUE 两条记在 `05 §2.5`。读数与出处见 `AGENTS.md` §3 | 00-audit §4 | **A0** | L |
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

> **与产品愿景的关系（2026-10-11 补）**：D1/D2/D3 不是普通缺陷，它们直接决定 [11](../rules/11-product-vision.md) 的两个入口能不能成立——
> D1（公式索引死代码）与 D3（公式/定理元数据入库即丢弃）是 **`11 §4.2 Deep Reader` 的公式解释、定理条件与 Formal Methods 模式**的硬阻塞，
> 也是 `11 §10` 里 **V1.0「公式/定理检索」** 的直接依赖；D2（层级分块失效）连着 `§4.2` 的结构导航与 `§4.3` 的"每格带原文证据"。
> 因此这三条在 `11 §8` 的语境下属于 **V1.0「先修好现有基础」** 的必修项，而不是可后移的优化。
> 处置去向仍是本文 §3 表里的 **P2-1/P2-2**（本文 §3 的"里程碑 A0"是旧口径），**顺序冲突的选项 A/B 见 [04](04-migration.md) §9**。

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
| 依赖真实 PG 的集成测试 | 没有；会话/文档测试全 mock（提交 `a552a5c` 即"mock langgraph/sentence_transformers"，历史重写后的等价 SHA） | A0 |
| 依赖真实 Milvus 的集成测试 | 没有 | A0 |
| **上传→入库→查询** 链路测试 | 没有；这正是 D1/D2/D3 能长期潜伏的原因 | **A0** |
| 跨语言契约测试（Go↔Python） | 不存在（Go 尚未引入） | A |
| 10–15 个固定科研问题基础回归 | 只有 `scripts/evaluate_rag.py`、`backend/agent/eval/run_eval.py`，无固定题集与基线记录 | A0 立骨架，A 补齐 |
| A/B/C 三组实验、20+ 问题 benchmark、消融 | 无 | **DEFER 到 C 之后** |
| ≥95% 定位准确率 / ≥90% 证据支持率 | 无标注数据 | 保留为**质量目标**，不作硬门禁 |

**纪律**：280 项 mock 测试继续保留并必须保持绿，但**不得作为"链路通过"的证据**；任何标记"某里程碑完成"的结论必须引用 A0 建立的真实 E2E 结果。

## 9. 与产品愿景的关系

> 对照 [11-product-vision.md](../rules/11-product-vision.md)。**分工声明（避免两份清单打架）**：**产品级能力的差距一律在 `11 §8` 跟踪**，本文只登记**架构缺口与数据可信缺口**（§2/§4）及由此派生的功能断链（§1/§3/§6/§8）。同一个问题在两处出现时，**"要不要做、排哪一版"看 `11 §8`，"为什么现在做不了"看本文**。

**已覆盖**：`11 §4.2 Deep Reader` 的**技术阻塞**（D1 公式索引、D2 分层分块、D3 元数据丢弃）· `11 §4.1 AI 论文图书馆` 的**实体前提**（G13 无 papers 关系实体、G14 无版本概念）· `11 §4.4/§4.6/§4.9` 的**共同地基**（§4 的 Frontier/Scheduler/Worker、§2 G15 会话覆盖式写、G16 时间戳语义）· `11 §6` 的"可信证据链"（§4 的 Evidence Registry 缺口、G10 正文只在 Milvus）· `11 §4.7 Research Lab` 的**外部能力入口**（§4 的学术检索 Provider）· `11 §11` 的口径纪律（§6 的 prompt injection / 工具白名单）。

**未覆盖**：本文**刻意不覆盖**产品能力域本身——`11 §4.3` 比较矩阵与 Paper Diff · `§4.5` 双图/Exploration Graph · `§4.6` Gap Explorer 与 Hypothesis Board · `§4.7` Research Lab 的形式化验证与实验复现 · `§4.8` Research Writing · `§4.9` Radar/Knowledge Diff · `§4.10` Workspace（项目/笔记/报告版本/预算/协作）· `11 §3` 五个入口作为一等概念 · `11 §5` 三个惊艳功能 · `11 §9` 的 MCP/skills 与 ARTEX 式一等模块。以上全部指向 `11 §8`，本文**不重复列举、也不重复判定**。

**需拍板/冲突**：**无口径冲突**（分工是互补的），但有一处**登记冲突**要拍：`11 §8` 的第 2–10 项一旦登记为任务卡，本文 §4 的"架构缺口"与它们的**分母会重叠**（例：`§4.5` 双图既在本文 §4 行里，又在 `11 §8` 第 12 项里），会让 `progress.json` 的完成度被同一件事扣两次。选项 A：本文 §4 只保留"为产品能力铺路"的架构项，产品能力项全部移交 `11 §8`；选项 B：保持两份并存，在 `11 §8` 页首声明"本文条目不进 `progress.json` 分母，登记时去重"。另：`11 §8` 第 11 项（信息增益驱动规划）在本文**完全无对应行**（§4 只有预算与 Frontier 缺失），登记前需要先在本文件补一条架构缺口。
