# 07 — 最小真实 E2E 测试方案

> **本文状态（2026-10-09 复核）**：性质=实施（测试纪律与用例清单）；**未实现**——落地卡片是
> **P0-5**（L5 跨语言契约）、**P0-9**（L4 浏览器 E2E 骨架 + `tests/e2e/`）、**P1-6**（L1–L3 真实链路）、
> **P2-3/P2-4**（chunk/公式链路用例与 10–15 题固定回归集）。当前仓库里 `chain` 与 `e2e` 两层
> **各 0 条用例**（`uv run pytest -m chain` 返回 exit=5「没收到用例」，不是绿），
> 进度以 [../progress.json](../progress.json) 为准。
>
> 决策 Q8：真实浏览器 E2E、真实 DB/Milvus 集成、跨语言契约、10–15 个固定科研问题回归为**必做**；
> A/B/C 三组实验、20+ 题 benchmark、消融实验 DEFER 到 **P4 展望**（双图与 Evidence）之后。
> 定位：**测"当前系统"（Python 后端原样）**，且在 **P1**（Go 接管 13 条接口）后**不改一行测试代码**
> 就能对着 Go 后端复跑——这是本方案最重要的设计约束，判定见 [04](04-migration.md) §1 的 P1 退出标准。

## 1. 为什么现在必须有它

方案立项时的现状是 280 项测试全绿，但对三处真实故障完全盲（[03](03-gap-analysis.md) §1）：
`useAuth` 的 `apiFetch` 未导入、上传 URL 缺前缀、`_build_formula_index` 零调用点。
根因是测试把 LangGraph / sentence_transformers / Milvus 全 mock 掉（提交 `a552a5c` 自陈；2026-10-12 历史重写后本分支上的等价 SHA，此前这里写的 `4a5e806` 只在重写前的 `main`/备份分支上存在），
且 `pyproject.toml` 的 `fail_under=40` 允许低覆盖。
**mock 测试证明的是"函数按我以为的方式被调用"，不是"用户能用到这个功能"**——这句话是原则②的由来。

前两处已由 **FE-1**（前端结构重构，`apiFetch` 随请求层一起消失并由 `check_frontend.py` 的 R1 挡住复发）
与 **A0-1/A0-3**（`996cf777` / `335aeb7e`）修掉；第三处（公式索引死代码）属 **P2-2**，仍未实现。
本方案剩下的价值是：让"链路通不通"这件事**可判定**，而不是靠人肉点一遍。

## 2. 分层与被测对象

层名与 `pyproject.toml` 注册的 marker 一致（P0-0 交付），目录即分层由 `tests/conftest.py` 自动补标。

| 层 | marker | 依赖 | 断言对象 | 运行位置 | 落地卡片 |
| --- | --- | --- | --- | --- | --- |
| L0 单元 | `unit` | 无（可 mock） | 纯函数、状态机、解析器 | 每次提交 | 已有 458 项（2026-10-12） |
| L1 集成-数据 | `integration` | 真实 PG + Redis（compose） | 仓储层读写、缓存一致、任务状态、鉴权 | 每次提交 | 已有 57 项（**mock 级**：无真库）；真实化属 P1-6 |
| L2 集成-检索 | `integration` | 真实 PG + Redis + Milvus | embedding/BM25/hybrid/rerank/auto-merge/公式索引 | PR + nightly | **未实现**（P1-6 / P2-2） |
| L3 链路 | `chain` | 上述 + LLM key | 上传→入库→检索→回答→引用可回溯 | nightly（花真钱） | **未实现**（P1-6；`chain` 目录当前不存在） |
| L4 浏览器 E2E | `e2e` | 全套 + Playwright | 用户可感知的四条主路径 | PR（stub LLM）+ nightly（真 LLM） | **未实现**（P0-9 交付骨架） |
| L5 契约 | `chain`（跨语言） | Go + Python 同时起 | 跨语言请求/响应/错误码/流帧字节形状 | 每次提交 | **未实现**（P0-5） |

> L5 不单独注册 `contract` marker：`pyproject.toml` 只有 `unit/integration/chain/e2e/slow` 五个，
> 多一个 marker 就多一处"分层与目录不一致"的漂移面。跨语言契约测试放 `tests/chain/`，
> 用 `-k contract` 或文件名筛。

**关键取舍**：L4 在 PR 上跑**假 LLM 桩**（Python 侧 `AICORE_STUB_LLM=1` 时返回固定结构化答案，
走完整执行链与 SSE 通道），nightly 跑真模型。理由：E2E 要验的是"链路通不通、形状对不对、
引用能不能回溯"，这三件事与模型文本内容无关；真模型只增加成本与不确定性。
**`AICORE_STUB_LLM` 尚未实现**（属 P0-9 的前置，见 [09](09-milestone-p0.md) P0-9 输出行）。

## 3. 断言纪律（避免测试变成"第二个 mock 骗局"）

1. **永不断言 LLM 返回的自然语言内容**。只断言：事件序列合法、`[Source N]` 编号 ∈ `source_map`、
   每个 citation 能解析出 `filename`/`page`、`source_map.chunk_id` 在 `paper_chunks` 里**存在对应行**。
2. **一切"入库成功"的判定来自数据库而非 API 返回码**：上传后断言 `count(paper_chunks where level=3) > 0`、
   `content_hash` 非空、`index_state='ready'`。（`paper_chunks` 属 **P2-1**，在此之前本条**无法执行**。）
3. **引用定位必须能回原文**：随机抽 N 个 chunk，用 `page_number` + `start_char/end_char` 从
   `paper_files.object_id` 指向的 PDF 重取文本，与 `paper_chunks.text` 做归一化比对（阈值 0.9），失败即红。
   这是 ≥95% 定位准确率目标的**技术地基**（决策 Q8：目标保留但不作硬门禁，此断言作为结构门禁）。
4. **禁止在测试里 patch 被测链路的任何环节**。需要隔离时降级到 L1/L2，不许在 L3/L4 打洞。
   （反面教材就在仓库里：`tests/conftest.py` 在 import 期 patch 掉 HuggingFace——那是 L0/L1 的合法做法，
   但同一个手法出现在 L3 就等于没测。）
5. 每个已修缺陷都要有一条**先红后绿**的测试；红灯清单与失败输出写进
   `docs/refactor/baseline-results.md`（**未实现**：该文件尚未建立，属 P1-6）。

## 4. 四条主路径用例（T1–T8）

| # | 用例 | 步骤 | 通过判据 | 2026-10-09 状态 |
| --- | --- | --- | --- | --- |
| T1 | 注册 → 登录 → 身份 | 新用户注册 → 登录 → 受保护页 | localStorage 有 `accessToken`，`/auth/me` 返回本人 | **未实现**（P0-9）；底层缺陷 G1 已由 FE-1 修掉，但浏览器级从未跑过 |
| T2 | 上传 PDF → 入库 | admin 登录 → 选样例 PDF → 观察 XHR 上传进度 → 轮询 job 到 `completed` | 网络层命中 `/api/v1/documents/upload/async`；PG 出现 paper/paper_version/全部层级 chunk；`index_state='ready'` | **未实现**（P1-6）；G2 已修，PG 侧断言要真库 |
| T3 | 提问 → 流式回答 → 引用 | 输入含公式的科研问题 → 收 SSE/WS 帧 → 渲染 | 事件序列合法；`citations` 非空；每个 `chunk_id` 可回查；RagTrace 面板显示检索步骤 | **未实现**（P1-6）；面板形状已由 FE-1 按契约纠形 |
| T4 | 会话持久化 | 刷新页面 → 历史列表 → 打开旧会话 | 消息条数与 `rag_trace` 与刷新前一致 | **未实现**；G15（覆盖式写）与 `ChatResponse` 丢 `source_map` **仍未修**，属 P1 |
| T5 | 公式检索链路 | 上传含 `$$...$$` 的论文 → 就该公式提问 | `formula_index_entries` 行数 > 0；检索结果含 `formula_match=true` 的 chunk | **未实现**；D1 死代码属 **P2-2**，此前本用例必然红 |
| T6 | 权限边界 | 普通用户调用 admin 接口 / 无 token / 用 refresh token 当 access | 分别 403 / 401 / 401 | **未实现**（P0-9）；Go 侧同一断言属 P0-6 |
| T7 | 限流 | 压测越过 `RATE_LIMIT` | 429 且带 `X-RateLimit-*`；信封是 `{"detail": ...}`（K1 已统一） | **部分**：mock 级已有 `tests/integration/test_rate_limit_enforcement.py`；真实 Redis 共享存储下的行为**未实现**（P1-6） |
| T8 | 断线与恢复 | 上传中关闭浏览器 → 重新登录查询 job；SSE 中途断连 | job 状态可查回且最终一致；SSE 重连不产生重复消息 | **未实现**；job 内存态按 Q1-A 不在 P0/P1 修（由 P3 的 Go Frontier 取代），本条只做**记录性断言**，不设门禁 |

> 判定口径变更（相对旧版）：旧文以 `06 §0` 的 E1–E10 为判定表，`06` 已归档；
> 现行判定表是 [09](09-milestone-p0.md) §0 的 **X1–X8**，逐条带命令与期望，由 `progress.json` 记录 pass/not_run。

## 5. 样例语料（**未实现**，属 P1-6）

`tests/fixtures/corpus/`（进仓库，总量控制在 5MB 内，全部为可自由分发的论文）：

| 文件 | 用途 | 要求 |
| --- | --- | --- |
| `synthetic_formula_paper.pdf` | T5 公式 | 自造 LaTeX 生成，含 5 个可提取公式（`$`、`equation` 环境各覆盖），页码稳定 |
| `synthetic_structure_paper.pdf` | T2/T3 分块与定位 | 明确 H1/H2/H3 + 定理/证明块 + 5 处引文 + 2 处缩略语，便于断言章节路径与 `page_number` |
| 1 篇真实开放获取短论文 | 现实版式 | 双栏、有图，验证解析器降级路径 |
| `malformed.pdf`（截断文件） | 健壮性 | 必须失败且返回结构化错误，不 500 |

自造合成论文是刻意的：断言可以写死（块数、层级、公式数），而不必容忍真实论文的不确定性。
`tests/fixtures/` 目前只有既有单测用的小样本，上述四个文件**都还没有**。

## 6. 10–15 个固定科研问题集（**未实现**，属 P2-4）

`tests/fixtures/research_questions.json`，每题字段：`id`、`question`、`type`（定义/对比/公式/定理条件/局限/引文）、
`expected_signals`（应命中的 filename/章节/关键词，**不是标准答案**）、`record_only: true`。

- 覆盖：单论文事实题 5、跨论文比较 3、公式/定理条件 3、检索否定题 2（语料里没有的内容，期望系统明确说"未找到"）、引用定位题 2。
- **只记录不判定**：nightly 跑完把每题的召回 chunk、是否命中 `expected_signals`、token 与耗时写入
  `baseline-results.md` 的追加表，形成可观察的回归趋势。这是 **P3/P4** 阶段 A/B 实验的**数据管道预置**，
  本身不设阈值门禁（决策 Q8）。
- 检索否定题是防幻觉的早期信号：`verify.py` 只查编号不查语义（[00-audit](00-audit.md) §2.1），这类题能立刻暴露。

## 7. 契约测试（L5，**P0-5 交付，当前未实现**）

[`contracts/`](../../contracts/) 目录为唯一契约源，Go 与 Python 各自生成/校验。
静态部分已经有门禁（`scripts/check_contracts.py`，X3 本机 pass）；**下面这五行都要两个真服务同时起**：

| 内容 | 形式 | 现状 |
| --- | --- | --- |
| 浏览器 API | OpenAPI 3.1；对比 Go 与 Python 对同一请求的**状态码 + 响应体 JSON 结构 + 关键头**（错误信封已统一为 `{"detail": ...}`，K1/K4） | 未实现（P0-5） |
| 流式帧 | 逐帧比对：`data:` 前缀、事件 `type` 顺序、`[DONE]` / `{"type":"done"}` 差异（[01](01-current-architecture.md) §4）——录制-回放（同一 prompt、同 stub LLM）产出字节序列 diff | 未实现（P0-5） |
| AI 执行契约 | [`ai-execution.schema.json`](../../contracts/ai-execution.schema.json)；Python 侧 Pydantic 严格校验已落（P0-7，29 条 HTTP 级用例），Go 侧 struct 与逐码测试未实现 | **半实现**：Python 侧 mock 级已有；Go 侧属 P0-5 |
| 密码哈希 | golden vectors：Python 生成若干 `pbkdf2_sha256$...` 串，Go 必须逐条验证通过（**导出物不含密码与盐明文**） | **导出侧已实现（2026-10-12，mock 级）**：`scripts/export_pbkdf2_golden.py` → `contracts/pbkdf2_golden.json` 10 条（6 正 4 负），期望值由生产 `verify_password` 现算；"不含密码与盐明文"落成"不含明文口令、也不含真库摘要"（口令由 `vector_id` 按 `password_rule` 重建，真库只在 `--from-db` 下给形状统计）。**Go 侧逐条验证未实现（P0-6 / X5）** |
| JWT | golden tokens：Python 签发 → Go 校验（含 `type` 语义、过期、错误 secret） | 未实现（P0-6 / X4） |

契约测试跑在真实两个服务上（compose profile `contract`），不允许用 testdouble 代替任一端。
**该 profile 尚未加进 `docker-compose.yml`**（属 P0-5 的输出行）。

## 8. 工程落地

| 项 | 选择 | 现状 |
| --- | --- | --- |
| E2E 工具 | Playwright（chromium 单浏览器；`@playwright/test` 放 `frontend/devDependencies`，测试目录 `tests/e2e/` 在仓库根） | 未实现（P0-9） |
| 服务编排 | `docker compose --profile test up -d`（新增 `test` profile，端口随机化避免与开发实例冲突）；`tests/conftest.py` 提供 `stack_url` fixture 供 pytest 侧 L1–L3 与 Playwright 的 `webServer` 共用 | 未实现（P0-5/P0-9） |
| 数据隔离 | L1–L3 每模块独立 database（`template1` clone）或 `TRUNCATE` + 事务回滚；L2 每模块独立 Milvus collection（前缀 + pytest xdist id），**teardown 必须删干净** | 未实现；现网 `drop_collection` 零调用点，说明该能力从未被验证过 |
| 密钥 | 仅 nightly 需要：GitHub Actions secrets；PR 上 L4 走 stub LLM，零成本 | 未实现 |
| CI 分工 | 每次提交：`unit` + `integration` + 契约静态门禁；PR 合并前：加真实 PG/Redis 的 `integration`；nightly：`chain` + `e2e`(real) + 科研问题集记录 | **部分**：`.github/workflows/ci.yml` 现有 backend/go/frontend/progress/docker 五个 job，全部是 mock 级；nightly 工作流未实现 |
| 时间预算 | L1 单模块 ≤30s，全量 `unit+integration` ≤6min（超则拆分并行）；nightly ≤25min | 本机全量 **515 项约 40s**（2026-10-12 复测；此前记的 449 项是 2026-10-11 的读数） |
| 可复用性约束 | 所有对 URL/端点的引用集中在 `contracts/` 与 `tests/e2e/fixtures.ts`；测试里**不出现** Python 专有概念，只断言对外形状 | 前端侧已由 FE-1 的 R6（DTO 只在 `api/types.ts`）保证一半 |

## 9. 与里程碑卡片的关系

- **P0-5** 交付 L5 契约测试（含 compose `contract` profile）；**P0-9** 交付 L4 骨架与 T1/T6 的浏览器级断言。
- **P1-6** 交付 L1–L3 的真实化（真 PG/Redis/Milvus + 样例语料 + `baseline-results.md`）。
- **P2-3/P2-4** 交付 chunk/公式链路用例与固定问题集。
- 判定表是 [09](09-milestone-p0.md) §0 的 X1–X8（旧 `06 §0` 的 E1–E10 已随 `06` 归档）。
- **纪律**：本文任何一条在没有真实栈的情况下都不得记为 pass；`progress.json` 里对应退出标准写 `not_run`，
  由 `sync_progress.py --check` 拦住"done 但证据等级不够"。

## 10. 与产品愿景的关系

> 对照 [11-product-vision.md](11-product-vision.md)。产品级缺口集中记在 `11 §8`，本节只列 E2E 面的**模式维度缺口**。

**已覆盖**：`11 §4.4 Research Mission` 的**崩溃恢复**（T8 的"最终一致"、§3 的"入库判定来自数据库"）· `11 §4.8 Evidence-grounded Writing` 的**最小地基**（T3 的"每个 `chunk_id` 可回查"+ §3 第 3 条"引用定位必须能回原文"）· `11 §4.2 Deep Reader` 的**定位**前提（T5 公式链路 + §3 第 3 条按 `page_number`+`start_char` 回 PDF）· `11 §4.3` 的**跨论文比较**只被 §6 的"跨论文比较 3 题"**记录性**碰到。

**未覆盖**：T1–T8 全是**单模式问答链路**用的——`11 §4.2` 的**定位跳转**（T3 只验 `chunk_id` 可回查，不验前端真的跳到位）· `11 §4.3` **比较矩阵**（每格带原文证据，无任何断言）· `11 §4.4` **Mission 可恢复**（T8 只测上传 job 与 SSE，不是 Run 的租约/fencing 恢复，后者要等 P3）· `11 §4.6` Gap Explorer / Hypothesis Board · `11 §4.7` Research Lab · `11 §4.9` Radar。按 mode 扩 E2E 这件事本身也**没有卡片**：现在的卡片是 P0-9（T1/T6）、P1-6（T2/T3/T4/T7/T8）、P2-3（T5）。全部指向 `11 §8`。

**需拍板/冲突**：**有，两处**。①**"证据接地"与 §3 第 1 条/§6 的张力**：§3 明令"**永不断言 LLM 返回的自然语言内容**"、§6 的固定问题集"**只记录不判定**"、`03 §8` 又把 ≥90% 证据支持率列为**不作硬门禁**的质量目标。于是"证据接地"目前只能测**结构**（有无 pair），测不了**语义**（引用是否真的支持那句话）。选项 A：在 P2-3 新增一条**不做语义判定**的接地断言——每个 `claim` 必须能映射到一条带原文偏移的证据（可机检、不含模型判断）；选项 B：保持现状，接地交给 V3.0 的 `VERIFY_EVIDENCE` 自己带测试，本节只留记录性用例。②**mode 维度的 E2E 放哪一层**：`11 §3` 要求五个入口各自可验，选项 A：Playwright 参数化按 mode 跑（成本高，但 L4 已有 stub LLM 的先例，PR 上零模型成本）；选项 B：只对"可判定的业务不变量"（定位跳转、矩阵格子非空、Run 可恢复）下断言，各 mode 只跑一条冒烟。
