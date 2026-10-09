# 07 — 最小真实 E2E 测试方案

> 决策 Q8：真实浏览器 E2E、真实 DB/Milvus 集成、跨语言契约、10–15 个固定科研问题回归为**必做**；A/B/C 三组实验、20+ 题 benchmark、消融实验 DEFER 到 Milestone C 之后。
> 定位：**测"当前系统"（Python 后端原样）**，且在 Milestone A 后**不改一行测试代码**就能对着 Go 后端复跑（04 §1 里程碑 A 退出条件 ④）。这是本方案最重要的设计约束。

## 1. 为什么现在必须有它

现状 280 项测试全绿，但对三处真实故障完全盲（03 §1）：`useAuth` 的 `apiFetch` 未导入、上传 URL 缺前缀、`_build_formula_index` 零调用点。根因是测试把 LangGraph / sentence_transformers / Milvus 全 mock 掉（提交 `4a5e806` 自陈），且 `pyproject.toml:92` 的 `fail_under=40` 允许低覆盖。**mock 测试证明的是"函数按我以为的方式被调用"，不是"用户能用到这个功能"。**

A0 的验收标准（06 §0 E1–E10）全部依赖本方案落地，因此它是整个重构的可判定性基础。

## 2. 分层与被测对象

| 层 | marker | 依赖 | 断言对象 | 运行位置 |
| ---| --- | --- | --- | --- |
| L0 单元 | `unit` | 无（可 mock） | 纯函数、状态机、解析器 | 每次提交 |
| L1 集成-数据 | `integration` | 真实 PG + Redis（compose） | 仓储层读写、缓存一致、任务状态、鉴权 | 每次提交 |
| L2 集成-检索 | `integration` | 真实 PG + Redis + Milvus | embedding/BM25/hybrid/rerank/auto-merge/公式索引 | PR + nightly |
| L3 链路 | `chain` | 上述 + LLM key | 上传→入库→检索→回答→引用可回溯 | nightly（花真钱） |
| L4 浏览器 E2E | `e2e` | 全套 + Playwright | 用户可感知的四条主路径 | PR（mock LLM 桩）+ nightly（真 LLM） |
| L5 契约 | `contract` | Go + Python 同时起 | 跨语言请求/响应/错误码/流帧字节形状 | Milestone A 起，每次提交 |

**关键取舍**：L4 在 PR 上跑**假 LLM 桩**（Python 侧 `AICORE_STUB_LLM=1` 时返回固定结构化答案，走完整 Agent 图与 SSE 通道），nightly 跑真模型。理由：E2E 要验的是"链路通不通、形状对不对、引用能不能回溯"，这三件事与模型文本内容无关；真模型只增加成本与不确定性。

## 3. 断言纪律（避免测试变成"第二个 mock 骗局"）

1. **永不断言 LLM 返回的自然语言内容**。只断言：事件序列合法、`[Source N]` 编号 ∈ `source_map`、每个 citation 能解析出 `filename`/`page`、`source_map.chunk_id` 在 `paper_chunks` 里**存在对应行**。
2. **一切"入库成功"的判定来自数据库而非 API 返回码**：上传后断言 `count(paper_chunks where level=3) > 0`、`content_hash` 非空、`index_state='ready'`。
3. **引用定位必须能回原文**：随机抽 N 个 chunk，用 `page_number` + `start_char/end_char` 从 `paper_files.object_id` 指向的 PDF 重取文本，与 `paper_chunks.text` 做归一化比对（阈值 0.9），失败即红。这是未来 ≥95% 定位准确率目标的**技术地基**（决策 Q8：目标保留但不作硬门禁，此断言作为结构门禁）。
4. **禁止在测试里 patch 被测链路的任何环节**。需要隔离时降级到 L1/L2，不许在 L3/L4 打洞。
5. 每个 A0 缺陷都要有一条**先红后绿**的测试（本方案在 A0-1/A0-3 修复之前先落地 §4 用例，预期 4 红 4 绿——红灯即基线证据，写进 `docs/refactor/baseline-results.md`）。

## 4. 四条主路径用例

| # | 用例 | 步骤 | 通过判据 | 当前预期 |
| --- | --- | --- | --- | --- |
| T1 | 注册 → 登录 → 身份 | 新用户注册 → 登录 → 受保护页 | localStorage 有 `accessToken`，`/auth/me` 返回本人 | **红**（G1 `apiFetch`） |
| T2 | 上传 PDF → 入库 | admin 登录 → 选样例 PDF → 观察 XHR 上传进度 → 轮询 job 到 `completed` | 网络层命中 `/api/v1/documents/upload/async`；PG 出现 paper/paper_version/全部层级 chunk；`index_state='ready'` | **红**（G2 URL 前缀） |
| T3 | 提问 → 流式回答 → 引用 | 输入含公式的科研问题 → 收 SSE/WS 帧 → 渲染 | 事件序列合法；`citations` 非空；每个 `chunk_id` 可回查；RagTrace 面板显示检索步骤 | 绿（但公式分支恒空，见 T5） |
| T4 | 会话持久化 | 刷新页面 → 历史列表 → 打开旧会话 | 消息条数与 `rag_trace` 与刷新前一致 | **红/部分**（G15 覆盖式写；且 `ChatResponse` 丢 `source_map`） |
| T5 | 公式检索链路 | 上传含 `$$...$$` 的论文 → 就该公式提问 | `formula_index_entries` 行数 > 0；检索结果含 `formula_match=true` 的 chunk | **红**（D1 死代码） |
| T6 | 权限边界 | 普通用户调用 admin 接口 / 无 token / 用 refresh token 当 access | 分别 403 / 401 / 401 | **红**（G3） |
| T7 | 限流 | 压测越过 `RATE_LIMIT` | 429 且带 `X-RateLimit-*`；信封与前端错误处理兼容 | **红**（G5 无全局限流） |
| T8 | 断线与恢复 | 上传中关闭浏览器 → 重新登录查询 job；SSE 中途断连 | job 状态可查回且最终一致；SSE 重连不产生重复消息 | **红**（G17 内存态；Redis 模式会永远 running） |

> T8 的"内存 job 重启即丢"按决策 Q1-A **不在 A0 修复**（由 Go Frontier 取代），因此 T8 对 job 持久性只做**记录性断言**（写入 baseline-results 作为已知限制），不设为门禁。其余 7 条全部是 A0 门禁。

## 5. 样例语料

`tests/fixtures/corpus/`（进仓库，总量控制在 5MB 内，全部为可自由分发的论文）：

| 文件 | 用途 | 要求 |
| --- | --- | --- |
| `synthetic_formula_paper.pdf` | T5 公式 | 自造 LaTeX 生成，含 5 个可提取公式（`$`、`equation` 环境各覆盖），页码稳定 |
| `synthetic_structure_paper.pdf` | T2/T3 分块与定位 | 明确 H1/H2/H3 + 定理/证明块 + 5 处引文 + 2 处缩略语，便于断言章节路径与 `page_number` |
| 1 篇真实开放获取短论文 | 现实版式 | 双栏、有图，验证解析器降级路径 |
| `malformed.pdf`（截断文件） | 健壮性 | 必须失败且返回结构化错误，不 500 |

自造合成论文是刻意的：断言可以写死（块数、层级、公式数），而不必容忍真实论文的不确定性。

## 6. 10–15 个固定科研问题集

`tests/fixtures/research_questions.json`，每题字段：`id`、`question`、`type`（定义/对比/公式/定理条件/局限/引文）、`expected_signals`（应命中的 filename/章节/关键词，**不是标准答案**）、`record_only: true`。

- 覆盖：单论文事实题 5、跨论文比较 3、公式/定理条件 3、检索否定题 2（语料里没有的内容，期望系统明确说"未找到"）、引用定位题 2。
- **只记录不判定**：nightly 跑完把每题的召回 chunk、是否命中 `expected_signals`、token 与耗时写入 `docs/refactor/baseline-results.md` 的追加表，形成可观察的回归趋势。这是 Milestone B/C 阶段 A/B 实验的**数据管道预置**，但本身不设阈值门禁（决策 Q8）。
- 检索否定题是防幻觉的早期信号：现在系统在没有证据时是否会硬凑 `[Source N]`，`verify.py` 只查编号不查语义（00-audit §2.1），这类题能立刻暴露。

## 7. 契约测试（L5，Milestone A 起）

`contracts/` 目录为唯一契约源，Go 与 Python 各自生成/校验：

| 内容 | 形式 |
| --- | --- |
| 浏览器 API | OpenAPI 3.1；测试对比 Go 与 Python 对同一请求的**状态码 + 响应体 JSON 结构 + 关键头**（含 429 的 `{"error":...}` 差异，01 §6） |
| 流式帧 | 逐帧比对：`data:` 前缀、事件 `type` 顺序、`[DONE]` / `{"type":"done"}` 差异（01 §4）—— 用录制-回放（同一 prompt、同 stub LLM）产出字节序列 diff |
| AI 执行契约 | JSON Schema（02 §3.2 请求/响应 + 错误码表）；Python 侧 Pydantic 严格校验，Go 侧 `contracts/` 生成 struct；`UNSUPPORTED_TASK_TYPE`/`BUDGET_EXCEEDED` 等每码一条测试 |
| 密码哈希 | golden vectors：Python 生成的若干 `pbkdf2_sha256$...` 串 + 明文，Go 必须逐条验证通过（04 §5 风险 1） |
| JWT | golden tokens：Python 签发 → Go 校验（含 `type` 语义、过期、错误 secret） |

契约测试跑在真实两个服务上（compose profile `contract`），不允许用 testdouble 代替任一端。

## 8. 工程落地

| 项 | 选择 |
| --- | --- |
| E2E 工具 | Playwright（chromium 单浏览器；`@playwright/test` 放 `frontend/devDependencies`，测试目录 `tests/e2e/` 在仓库根，避免与后端测试混） |
| 服务编排 | `docker compose --profile test up -d`（新增 `test` profile，端口随机化避免与开发实例冲突）；`tests/conftest.py` 提供 `stack_url` fixture 供 pytest 侧 L1–L3 与 Playwright 的 `webServer` 共用 |
| 数据隔离 | L1–L3 每模块独立 database（`template1` clone）或 `TRUNCATE` + 事务回滚；L2 每模块独立 Milvus collection（前缀 + pytest xdist id），**teardown 必须删干净**（现网 `drop_collection` 零调用，说明该能力从未被验证过） |
| 密钥 | 仅 nightly 需要：GitHub Actions secrets；PR 上 L4 走 stub LLM，零成本 |
| CI 分工 | 每次提交：`unit` + `integration`(PG/Redis) + `contract`（A 之后）+ `e2e`(stub)；PR 合并前：加 `integration`(Milvus)；nightly：`chain` + `e2e`(real) + 科研问题集记录 |
| 时间预算 | L1 单模块 ≤30s，全量 `unit+integration` ≤6min（超则拆分并行）；nightly ≤25min |
| 可复用性约束 | 所有对 URL/端点的引用集中在 `contracts/` 与 `tests/e2e/fixtures.ts`；测试里**不出现** Python 专有概念（如 `rag_trace` 的 pydantic 形状差异），只断言对外形状 |

## 9. 与 06 的关系

A0-6 交付本方案的 L1–L5 骨架与 T1–T8 用例；06 §0 的 E1–E10 是本方案通过与否的判定表。**先落地红灯（§3.5），再做 A0-1/A0-3/A0-4/A0-5 的修复使其转绿**，红灯截图与失败清单归档进 `docs/refactor/baseline-results.md` 作为 Phase 0 §2.3 要求的"既有测试结果与已知失败"记录。
