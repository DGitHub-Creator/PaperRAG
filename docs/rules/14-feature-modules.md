# 14 — 功能模块规划（产品轴逐模块：现状 / 目标行为 / 卡片 / 顺序 / 风险）

> **本文补的是什么**：`docs/progress.json` 只有**工程架构轴**（P0–P3）与**产品价值轴**（V1.0–V4.0）两套编号，
> 但两者之间缺一张"功能模块"表——回答不了「论文的 RAG 存储做到哪了」「自动抓取有没有代码」这类问题。
> 本文把产品愿景（[11](11-product-vision.md) §4 十项能力）拆成 17 个模块，逐模块给：
> **现状（带 file:line，现查）** → **目标可验证行为（判据命令）** → **归属（已有卡片 / 提案卡）** → **顺序约束** → **风险**。
>
> 三条口径纪律：
> 1. **现状一律现查代码**，不抄 `README.md` §1 的能力表（本轮就在那张表里查出三条失真，已更正）。
> 2. **提案卡不进分母**——登记与否是决策 **D5**，本文只把提案写到"一句话就能登记"的程度（§18 给汇总表与算术）。
> 3. 「未实现」有两种，本文严格区分：**函数没接**（加调用点即可）与**数据面不存在**（要建表/建字段才能接通）。
>    后者的工时是前者的十倍，混起来说会毁掉排期。

---

## 模块索引

| # | 模块 | 一句话 | 现状 | 归属 |
| --- | --- | --- | --- | --- |
| M1 | 论文摄取与解析 | 上传→解析→清洗→分块 | 部分实现 | P1-3 |
| M2 | 论文自动抓取与导入 | arXiv / DOI / 研究方向 | **零存在** | **P2-9**（已登记） |
| M3 | RAG 存储与真相层 | 正文归 PG，Milvus 只当索引 | **未实现** | P2-1 / P2-3 |
| M4 | 检索与匹配 | hybrid + RRF + rerank + 改写 | **已实现** | — |
| M5 | 学术元数据（公式 / 定理 / 引文 / 术语 / 图表） | 让"学术"两字进检索层 | 提取在跑、**入库即丢弃** | P2-2 / P2-3 |
| M6 | 问答与流式 | Agent 工具调用 + SSE / WS | 已实现（两项折扣） | P1-4 / P2-5 |
| M7 | 引用可信与原文定位 | 每条引用能回到 PDF 位置 | **未实现** | P2-7 / Z3 |
| M8 | 会话、笔记与工作区 | 研究过程的容器 | 会话活、`workspaces` 死表 | F-7（提案） |
| M9 | 主题分类与语义书架 | 自动成主题群 | **零存在** | **P2-10**（已登记） |
| M10 | 多论文比较矩阵 / Paper Diff | 跨篇结构化对比 | 零存在 | F-1（提案） |
| M11 | Gap Explorer 与假设看板 | 有证据的候选问题 | 零存在 | F-2（提案） |
| M12 | Research Lab | 从阅读到建模与验证 | 零存在 | F-3（提案） |
| M13 | Research Writing | 证据接地的写作产出 | 雏形在 P3 | F-5（提案） |
| M14 | Research Radar / Knowledge Diff | 长期跟踪文献变化 | 零存在 | F-4（提案） |
| M15 | 自主研究引擎 | Run / Frontier / Worker / 报告 | 零存在 | P3-1…P3-7 |
| M16 | 知识双图与 Evidence Registry | 结论可反向导航 | 死表 + 归属未定 | F-8（提案 / P4 未定） |
| M17 | 平台底座 | 认证 / 契约 / 任务态 / 门禁 | 进行中（架构轴 P0） | P0 / P1 |

---

## M1 论文摄取与解析

- **现状（部分实现）**：`backend/rag/document_loader.py` 负责 PDF/Word/Excel 解析 → `academic_cleaner` 清洗 → 分块。
  折扣两处：①默认结构分块只产**叶级块**，`_split_structural` 不产层级父块 → Auto-merging 合并数恒为 0；
  ②布局分析已接在 `document_loader.py:622`（`analyze_layout`），但外层是 `try/except Exception: pass`，
  失败静默，且产出的 `has_figure`/`has_table` 没有下游列可存（见 M5）。
  上传走 `POST /documents/upload/async`（`api/documents.py:410`），任务态默认进程内存（台账 C9）。
- **目标行为**：上传一篇论文 → 得到带层级关系的块树（叶块 + 父块 + root），任务状态**进程重启后仍可查**。
- **判据**：`uv run python -m pytest -q -m integration -k parent_chunks`（新增用例：一篇含二级标题的 PDF，
  断言 `chunk_level>0` 的父块数 > 0，且 `parent_chunk_id` 指向真实存在的块）+ Z4（重启恢复）。
- **归属**：编排移到 Go = **P1-3**；父块产出本身是 Python 侧修复（建议并入 P2-1，因为要动 chunk 树的数据面）。
- **顺序约束**：M3 之前不要单独修 Auto-merging——父块正文同样会被 `VARCHAR(2000)` 截断，修了也验证不了。
- **风险**：布局分析那个 `except: pass` 是**静默失败**，日志里没有痕迹；接线时先让失败可见，再谈准确率。

## M2 论文自动抓取与导入 ⚠️ 零存在

- **现状**：**不是"没接通"，是代码不存在**。`backend/` 全仓 grep `arxiv` / `doi` / `crossref` / `httpx` / `requests` 零命中
  （唯一 `doi` 是 `academic_cleaner.py:47` 的正文清洗正则）。入库只有人工上传一条路。
- **目标行为**：给 arXiv 分类/检索词或一串 DOI → 系统取回 PDF、识别元数据、按 `content_hash` 去重、排队解析入库，
  并记录**入库理由**（回答"这篇论文为什么在我的知识库里"）。
- **判据**：`uv run python -m pytest -q -m integration -k acquisition`；Z6 覆盖。
- **归属**：**P2-9**（12 h，deps P1-3 + P0-7）。⚠️ 抓取是网络型长任务，必须走 P1-3 的**持久化任务态**，
  不能用 `upload_jobs` 的进程内存态，否则一次重启就丢一批任务。
- **顺序约束**：arXiv 官方有速率与镜像约束（`_export_crawlers` 名单、5s 间隔、UA 规范），实现前先读，别做成被封的爬虫。
- **风险**：外部 API 可用性属**不可控依赖**，判据要能在离线时用录制的 fixture 跑，否则 CI 会脆。

## M3 RAG 存储与真相层 ⚠️ 数据面不存在

- **现状（未实现）**：叶级正文**只存在 Milvus**，字段 `text` 是 `VARCHAR(2000)`（`backend/vectordb/milvus_client.py:240`）
  → 超长块被截断且**无处回放**。PG 里没有对应正文表：`table-acl.md` 声明了 `papers` / `paper_versions` /
  `paper_files` / `paper_chunks`，但**这 4 张表在 `server/migrations/` 里根本不存在**（ACL 24 张 vs 实建 11 张，差 18 张，见 `13` §6.1）。
- **目标行为**：PG 持不截断的正文与结构树，Milvus 只存可重建的向量与稀疏索引；删集合后可用一篇论文重放重建。
- **判据**：`uv run python scripts/rebuild_chunks.py --verify-only`（P2-1 的 verify）；
  Z1「chunk 正文进 PG 且无截断」；每条检索结果能取到 `content_hash` 与完整正文长度。
- **归属**：**P2-1**（24 h，deps P1-8，建表走 `server/migrations/` + 同批登记 sqlc）→ **P2-3**（链路测试 8 h）。
- **顺序约束**：这是 M5 / M7 / M9 / M10 的**共同前置**——它们的判据都要求"正文与元数据可信且不截断"。
  `11 §7` 提的最小解法（把 P2-1/P2-2 前移）就是针对这条，尚未拍（**D4**）。
- **风险**：建表在 Go 侧 schema、写入仍在 Python，属过渡期双 owner；`table-acl.md` 对 `paper_chunks` 已写 `until-P2`，要守住。

## M4 检索与匹配 ✅ 已实现（唯一"模糊匹配"这块已闭环）

- **现状**：dense（BGE-M3 1024 维）+ **自实现 BM25 稀疏向量**（`backend/rag/embedding.py`）+ Milvus hybrid + RRF；
  链路在 `rag_pipeline.py:120 retrieve_initial` → `:439 retrieve_expanded`；Rerank 双轨、Context Expansion、
  HyDE / Step-back 查询改写都在。**这是今天唯一端到端有用的检索能力。**
- **已知边界**：①召回的正文来自 M3 的截断副本（长块看不全）；②公式分支恒空（见 M5）；
  ③`multimodal.py` 零调用方（图表检索不在这条链路上）。
- **判据**：`uv run python -m pytest -q -m integration`（现有 57 项里含检索层）；Z4 之后加"删集合重放"回归。
- **归属**：无新卡。P1-4 把门面移到 Go 时，**契约测试要逐字节比帧序列**（Y3），否则流式形状会漂。
- **风险**：Go 侧接管读接口时最容易顺手"重写一遍检索"——那是把已验证的实现换成未验证的实现。目标是**门面**，不是重写。

## M5 学术元数据：公式 / 定理 / 引文 / 术语 / 图表

- **现状（提取在跑，入库即丢弃）**：
  - 四个提取器都有调用方：`theorem_detector` / `citation_extractor` / `glossary_extractor` 被 `document_loader` 用，
    `citation_extractor` 还被 `rag_utils` 用。
  - **公式是特例，机理要说准**：查询侧已接进混合检索（`rag_utils.py:730` 调 `_formula_search`），
    死的是入库侧——`_build_formula_index`（`:644`）**零调用点** → LSH 索引永远空 → `formula_docs` 恒 `[]`。
    「函数没接」加一行调用就行；这里要的是**在解析后遍历 chunk 的 `formulas` 元数据填索引**，属数据面。
  - 丢弃点在 `backend/vectordb/milvus_writer.py`：写入字段清单里**没有** formulas / theorems / citations / glossary /
    `has_figure` / `has_table` 任何一列（见 `13` §6.2）。
  - `glossary_entries` 表零 ORM 读写；`glossary_extractor.py:13` 的 `GlossaryEntry` 是**同名 `NamedTuple`**，别误判成在用。
- **目标行为**：就该公式提问能命中含它的块（`formula_match=true` 且命中数 > 0）；定理/引文/术语作为可过滤字段进检索层。
- **判据**：`07` 的 T5（上传含 `$$...$$` 的论文 → 就该公式提问 → 断言 `formula_index_entries` 行数 > 0 且命中）；
  Z2「公式检索真实生效」。**注意**：T5 里的 `formula_index_entries` 目前**不存在**，要随 P2-2 一起建。
- **归属**：**P2-2**（10 h，deps P2-1）+ **P2-3**（8 h）。
- **顺序约束**：索引挂在截断文本上 = 错误结果被固化为"可信"，所以**必须先 M3**。
- **风险**：`formula_normalizer` 的标准化口径决定 LSH 分桶效果，接线前先跑一组同义式样本，别接完就宣称生效。

## M6 问答与流式

- **现状（已实现，两项折扣）**：Agent 问答走 LangGraph 工具调用（`backend/agent/`），SSE 端点
  `api/chat.py:53`、逐 chunk `yield` 在 `:66`；WS 在 `api/ws.py:52`。
  折扣①SSE 实际是**整段答案一次性下发**（非 token 级增量）；折扣②任务态与预算记账不在真相库里（M17）。
- **目标行为**：Go 门面接管 `/chat/stream` 与 `/ws/chat`，保持帧形状与错误信封逐字节一致；断线可按 `Last-Event-ID` 续传。
- **判据**：Y3（SSE 字节级帧序列跨语言比对）+ P2-5 的续传用例。
- **归属**：**P1-4**（14 h，deps P1-3）→ **P2-5**（14 h，append-only 会话 + 持久事件日志 + 续传）。
- **风险**：nginx 的 `X-Accel-Buffering` 与 Go 的 flush 策略会让"开发能流、生产一坨"（`01` §6.3 记过同型坑），判据必须走真 nginx。

## M7 引用可信与原文定位（Deep Reader 的地基）

- **现状（未实现）**：引用展示与 RAG Trace 在跑，但校验**只验 `[Source N]` 编号存在性**，
  不做语义接地；引用无法回到 PDF 位置——因为块级页码/字符偏移虽在 Milvus 有 `page_number`，
  而正文与结构在 PG 不存在（M3），元数据也被丢弃（M5）。
- **目标行为**：每条引用可点，展开"原文段落 + 所属论文 + PDF 页内位置"，并标出该句是否被证据支持。
- **判据**：**Z3**（引用可回溯到 `paper_chunks` 行与 PDF 位置，level e2e）+ Playwright 用例（P2-7）。
- **归属**：**P2-7**（16 h，deps P2-1 + P2-5）。产品口径：**P1 期间的引用一律标为非证据级**（D3 已定）。
- **风险**："引用存在"与"引用支持该陈述"是两件事；`not_doing` 已写明不得把模型检查通过当作一般情形已证明。

## M8 会话、笔记与工作区

- **现状**：会话侧是**活的**——`chat_sessions` / `chat_messages` 有真实读写
  （`services/conversation_storage.py:67,72,149,187,226` 与 `:80,93,157,197`）。
  **`workspaces` 是死表**：`backend/core/models.py:274` 定义，只在 `schemas.py` 出现，**无 ORM 读写点**；
  `workspace_members` 只读（`core/auth.py:428-431`）。没有笔记实体、没有报告版本、没有项目预算。
- **目标行为**：研究过程有持久容器——项目 / 任务清单 / 阅读进度 / 笔记 / 报告版本 / AI 预算（即 Research Workspace）。
- **判据**：`uv run python -m pytest -q -m integration -k workspace`（建表后：项目 CRUD + 成员权限 + 笔记 append-only）。
- **归属**：提案 **F-7 Research Workspace**（18 h，deps P3-1 + F-6）。`workspaces` 死表应在 F-7 里**启用或删除**，
  不要让它继续以"看起来有权限模型"的样子留在基线里。
- **风险**：权限语义与 M17 的认证耦合（`role` 不做枚举校验，台账 C21），扩成员模型时别引入两侧分歧。

## M9 主题分类与语义书架 ⚠️ 零存在

- **现状**：全仓无聚类 / 主题分组代码。前端也没有承载它的视图（无 router，见 `13` §7）。
- **目标行为**：对知识库自动产出主题群（例：「共识安全证明」「同步模型」「UC 理想功能」），
  支持按主题检索，且每个主题群能列出所属论文与依据。
- **判据**：`uv run python -m pytest -q -m integration -k topic_cluster`（≥20 篇 → ≥2 个群，且检索结果带 `topic` 标签）；Z6 覆盖。
- **归属**：**P2-10**（10 h，deps P2-1 + P2-9）。
- **顺序约束**：**必须在 M3 之后**——在 2000 字符截断副本上聚类，等于给不可信数据打标签（与 D3 的口径冲突）。
- **风险**：主题命名是 LLM 生成，容易"看起来像结论"；要存**依据**（哪些块贡献了这个主题），否则重演 M7 的可信问题。

## M10 多论文比较矩阵与 Paper Diff

- **现状**：零存在。既有检索（M4）只能返回若干块，没有跨篇对齐结构。
- **目标行为**：输入"比较这 8 篇论文对部分同步网络的建模方式"→ 产出矩阵（系统模型 / 时间假设 / 安全目标 /
  证明方法 / 局限性 × 每篇），**每格带原文证据**；Paper Diff 能对比同篇不同版本或两篇相关论文的方法变化。
- **判据**：`uv run python -m pytest -q -m integration -k compare_matrix`（N 篇 × M 维度，每格引用可解析回 `paper_chunks` 行）。
- **归属**：提案 **F-1**（16 h，deps P2-1、P2-3）。版本关系（预印本/会议/期刊）属 `11 §8` 第 2 项剩余部分 → F-9。
- **风险**：矩阵最容易产出"拼接摘要"而非"对齐证据"；判据要按**格**要求引用，不接受整篇级引用。

## M11 Gap Explorer 与假设看板

- **现状**：零存在。
- **目标行为**：基于论文与证据关系找缺口，每个候选问题给「已有研究 / 模型差异 / 待确认 / 验证路径」四段，
  并落进看板状态（有潜力 / 需补证据 / 已被研究 / 准备验证 / 不再研究）。
- **判据**：`uv run python -m pytest -q -m integration -k gap_candidate`（每个候选必须带 ≥1 条 `evidence_links`，
  且"未检索到充分证据"的项显式标 `insufficient`）。
- **归属**：提案 **F-2**（20 h，deps P2-1、P3-5、F-8 的一部分）。
- **产品纪律（已入 `not_doing`）**：只产**候选研究问题**，不宣称发现全新学术贡献。

## M12 Research Lab

- **现状**：零存在。
- **目标行为**：论文定理 → 建模假设 → 形式化规格草案 → 模型检查任务 → 结果 → 研究笔记，串成一条链。
- **判据**：`uv run python -m pytest -q -m integration -k lab_run`（一次 TLA+/CSP# 草案 → 工具调用 → 结果落 `research_events`）。
- **归属**：提案 **F-3**（24 h，deps P3-3）。外部工具链（模型检查器）可用性属不可控依赖。
- **口径纪律**：**模型检查通过特定配置/有限状态范围 ≠ 一般情形的数学证明**（`not_doing` 已写）。

## M13 Research Writing

- **现状**：雏形在 P3——带引用的报告生成与 `PARTIAL` 语义（P3-5）。没有 LaTeX/BibTeX 导出、没有"引用是否支持正文陈述"的检查。
- **目标行为**：产出阅读报告 / Related Work / 技术综述，每个关键陈述关联已核验文献，
  无来源内容必须显式标为「解释 / 观点 / 待验证」。
- **判据**：`uv run python -m pytest -q -m integration -k writing_grounding`（无来源陈述占比为 0，即每条都带标签）。
- **归属**：提案 **F-5**（12 h，deps P3-5、M7）。

## M14 Research Radar 与 Knowledge Diff

- **现状**：零存在。
- **目标行为**：把 Research Mission 存成长期项目，定期检查文献变化，并回答
  「新论文在哪个问题上补充 / 修改 / 挑战了你知识库里的结论」，而不是"出现了一篇新论文"。
- **判据**：`uv run python -m pytest -q -m integration -k radar_diff`（构造一条"挑战已有结论"的模拟更新 →
  必须落到具体 claim 与 evidence）。
- **归属**：提案 **F-4**（14 h，deps P3-1、M13/M7）。外部源变化频率不可控，判据须能用录制 fixture 跑。

## M15 自主研究引擎

- **现状（零存在）**：`go-worker` 只有探针（`server/cmd/worker/main.go:37-38`，`:52` 自陈调度器属 P3）；
  `research_projects` / `research_runs` / `research_plans` / `research_tasks` / `research_task_dependencies` /
  `research_events` / `outbox_events` **全部是 ACL 纸面表**（SQL 里不存在）。
- **目标行为**：围绕目标持续执行——Planner 分解 → Frontier 缺口发现 → Worker Pool 派发 → Verifier 核验 → 报告，
  预算耗尽产出 `PARTIAL` 并列出未解决问题；强杀后可从事件日志恢复。
- **判据**：W1–W5（已在 `progress.json`，level e2e/real：端到端产出带引用报告、崩溃恢复、幂等、暂停/继续/取消、预算 `PARTIAL`）。
- **归属**：**P3-1…P3-7**（78 h）。研究性课题（信息增益驱动规划，而非只按预算 + Frontier）= 提案 **F-10**（16 h）。
- **风险**：这是唯一"多全局调度器"风险的模块，`AGENTS.md` §7 已禁止建第二个调度器——Go 是唯一调度方，Python 不得再起循环。

## M16 知识双图与 Evidence Registry

- **现状**：`paper_nodes` / `citation_edges` 是**死表**（零读写）；`knowledge_items` / `exploration_gaps` /
  `evidence_links` / `research_claims` / `report_sections` 只在 ACL 里、SQL 里没有。
  `02 §8` 把双图标为 **P4 展望**，而 `progress.json` 的阶段只到 P3——**它会一直停在"展望"里**（`11 §8` 第 12 项）。
- **目标行为**：Knowledge Graph（Paper/Method/Assumption/Theorem/Claim/Evidence）与 Exploration Graph
  （Goal/Intent/Task/Finding/Gap/Hypothesis）可查、可反向导航。
- **判据**：`uv run python -m pytest -q -m integration -k graph_traceability`（从一条 claim 反查到支撑段落、所属论文、
  以及是哪次 Agent 任务提取的）。
- **归属**：提案 **F-8**（24 h），但**先要拍归属**：并进 P3 还是新开 P4（这条本身是 `11 §8` 第 12 项的要求）。
- **风险**：图的边质量依赖 M5 的元数据入库；先建图后补元数据会得到一张"看似完整实则空边"的图。

## M17 平台底座（认证 / 契约 / 任务态 / 记账 / 门禁）

- **现状（进行中，属架构轴 P0）**：认证 Python 为裁判、Go 已实现并被 golden vectors 钉住（X5 pass）；
  契约目录与静态门禁 done（X3 pass）；`/internal/v1/ai/*` 七条内部面**已建好但零 caller**；
  预算与 usage 记账的 `/stats/usage` 前端不调；任务态在进程内存（C9）。
  **2026-10-14 新增两条 Go 原生自助面**（`POST /api/v1/auth/password`、`GET|PUT /api/v1/me/preferences`）：
  它们**没有 Python 对照**，是新开的 Go 面——所以判据是"Go 自己的不变量"（旧口令错回 400 不 401、
  新口令与 register 同规则、`user_preferences` 的 created_at/updated_at 由写方给 UTC），
  不属于 X4 的跨语言兼容范围。数据面随之多一张实建表 `user_preferences`（迁移 `000003`）。
- **2026-10-14 前端侧补齐（同一条自助面被消费）**：设置页从「文档管理」单页**重做成用户设置四板块**
  （账号信息 / 外观·主题 / 偏好设置 / 修改密码），管理员在页尾**多一块「知识库管理」**（原文档上传与列表
  **逐字保留**，因为 `backend/api/documents.py` 每个端点都是 `Depends(require_admin)`，**不能**挪给普通用户）。
  偏好设置只落两个字段：`theme`（light/dark/system，system 用 `matchMedia` 解析一次，**不监听变化**）与
  `start_view`（**登录后**跳转目标；**刷新不跳**，避免 F5 把人从当前页拽走）；`start_view` 由 Go 只校验**形状**，
  「认不认识」交给前端 `router.hasRoute`——别让 Go 硬编码前端路由表。站点级 `alert`/`confirm` **全站退役**，
  换成 `useToast`/`useConfirm`（状态）+ `ToastHost`/`ConfirmHost`（DOM），`utils/dialog.ts` 仍是唯一接缝；
  另引入 `[data-theme="dark"]` 令牌块与**页宽统一 1280px**（删掉 `.page-inner.wide`）。
  ⚠️ **这条面上线的证据只到 mock/real 混合**：「知识库管理」块本轮**只验到错误路径**（Go 把 `/api/*` 反代到
  未启动的 Python → 红 toast「上游服务不可用」），**上传/删除的成功路径本轮没有重跑**——那是 P0-9 的 X7
  （浏览器级 e2e）该管的。
- **目标行为**：Go 是唯一公开入口与唯一调度方；任务态与记账落 PG；12 条未调用接口逐条有审计与 Deprecation 头。
- **判据**：X1/X2/X4/X6/X7/X8 + Y1/Y4/Y5 + Z4。
- **归属**：P0-1 / P0-5 / P0-6 / P0-7 / P0-8 + P1-0…P1-8 + P2-6。
- **风险**：**底座不产出用户可见能力**——这是 15% 完成度里最容易让人误判"产品快好了"的部分（`AGENTS.md` §3 已注明 P0 不产能力）。

---

## 18. 提案汇总（未进分母，等 **D5**）

| 提案 | 模块 | 工时 | deps | 判据（`-k` 选择器） |
| --- | --- | --- | --- | --- |
| F-1 比较矩阵与 Paper Diff | M10 | 16 | P2-1, P2-3 | `compare_matrix` |
| F-2 Gap Explorer + 假设看板 | M11 | 20 | P2-1, P3-5 | `gap_candidate` |
| F-3 Research Lab | M12 | 24 | P3-3 | `lab_run` |
| F-4 Research Radar / Knowledge Diff | M14 | 14 | P3-1 | `radar_diff` |
| F-5 Research Writing 完整化 | M13 | 12 | P3-5 | `writing_grounding` |
| F-6 产品入口层（路由一等概念） | `13` §7 | 8 | — | `nav_entries` |
| F-7 Research Workspace | M8 | 18 | P3-1, F-6 | `workspace` |
| F-8 双图 + Evidence Registry | M16 | 24 | P2-2, P3-3 | `graph_traceability` |
| F-9 版本关系 + Zotero/BibTeX | M2 | 10 | P2-9 | `bibmeta` |
| F-10 信息增益驱动的自主规划 | M15 | 16 | P3-2 | `info_gain` |
| F-11 工具与技能层（MCP / skills） | — | 12 | P1-8 | `tool_layer` |
| **合计** | | **178 h** | | |

**登记后的算术（一次算清，避免事后争辩）**：总工时 394 → **572 h**，卡片 40 → **51 张**，
完成度 58/394（14.7%）→ **58/572 ≈ 10.1%**。这是把"产品轴缺口"写进计划的**诚实代价**，
与 `11 §8` 的提醒一致；不登记则 14.7% 这个数**只对架构轴成立**，对外汇报会高估产品完成度。
建议的登记节奏：**先只登记 F-6 + F-7**（前端入口与工作区是 V1→V2 的必经路，且工时小、可验证），
其余 9 项随 V 版本临近再进分母。

## 19. 跨模块的三条顺序铁律

1. **数据面先于智能**：M3（真相层）→ M5（元数据）→ M7（引用可信）→ M9/M10/M11/M16。
   在截断副本上算主题、建图、产引用，等于把不可信结果包装成可信产出。
2. **门面先于重写**：P1 的 Go 接管是**加门面 + 契约逐字节比对**，不是用 Go 重写已验证的检索/解析逻辑。
3. **能力与判据同批**：任何模块转 `done` 必须带可跑判据（pytest 选择器或门禁脚本），
   且"收 0 项 = exit 5 = 不算绿"（与 X4 同口径）。
