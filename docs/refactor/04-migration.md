# 04 — 迁移路线（P0–P3，架构先行）

> 路线：**P0 架构与契约 → P1 后端迁移与最小原型 → P2 功能拓展与数据可信化 → P3 多 Agent 自主探索**（双图属 P4 展望）。
> 最高约束见 [08-principles-and-conventions.md](08-principles-and-conventions.md)；进度与日程见 [../progress.json](../progress.json)（生成物 [PROGRESS.md](../PROGRESS.md) / [progress.html](../progress.html)）。
> 排期前提（决策 Q8）：solo，每周 15–20 小时。

## 0. 路线为什么改版（2026-10-09）

旧路线是 `A0 基线修复与数据可信化 → A Go 主后端接管 → B Frontier → C 双图`，其中 A0 被定为
**Go 之前的前置里程碑**（旧决策 Q1）。用户《重构执行总纲》的第一性原则①「端到端链路优先」与此冲突：
把旧系统修到完美**不产生任何可演示的端到端状态**，而"Go 骨架 + 一条窄链路先跑通"才产生。

因此 **Q1 被取代**，路线改为架构先行。改动范围仅限**顺序与归属**，不含新的技术决策：
五条架构律（L1–L5）、目录布局（Q2-A：Go 落 `server/`，Python 留在 `backend/`）、
Go↔Python 契约（Q7-A）、Schema 治理（Q4）、E2E 分层与测试纪律（Q8）**全部沿用** `02`/`05`/`07`。

### 0.1 已完成的部分保留

| 已完成 | 提交 | 处置 |
| --- | --- | --- |
| A0-1 前端故障修复 + `typecheck` 进 CI | `2c3e583` | 保留。P0/P1 的前端基址切换与 CI 门禁直接复用 |
| A0-3 鉴权与运行安全（token 分型、WS 回查、密钥 fail-fast、限流真生效、删静默 `create_all`） | `d8f1563` | 保留。这是 P0-6 Go 复刻认证的**行为基线**：Go 必须逐条对齐 `backend/core/auth.py` 的现状语义 |

**不回填、不重做、不因为改版而撤销。** 测试从 280 增至 307 项，全绿。

### 0.2 与总纲的三处口径差异（需你确认后 P0 才开工）

| # | 总纲要求 | 本路线的做法 | 理由 |
| --- | --- | --- | --- |
| D1 | 目标目录含 `ai-core/`（Python 独立目录） | **物理目录保持 `backend/`**，`ai-core` 只作为 compose 服务名与角色名 | 62 模块 + 41 测试文件用 `from backend.xxx` 绝对导入；同批改目录又改架构会让 diff 不可评审。原则④ + 已锁定 Q2-A。改名留到 P2 之后作为**可单独回滚**的独立提交 |
| D2 | P0 完成后"旧接口必须迁移或标记 deprecated" | 13 条被前端实际调用的接口在 **P1** 迁完；其余 12 条无人调用的接口在 P1 末统一返回 `Deprecation` 头 | `01` §3 的调用方事实：只有 13 条真在被调。原则①要求 P0 只交付骨架 + 一条垂直切片，接口搬迁是 P1 的目标 |
| D3 | chunk 可信化 | 从"A 的前置阻塞"改为 **P2**，且改在 **Go 侧新 schema** 上做 | 原则①：它是横向深度，不是骨架。代价必须写明：P1 的引用只到"可展示副本"粒度，**不得称为证据链**（`08` §2 推论 3） |

---

## 1. 阶段总表

| 阶段 | 目标 | 进入条件 | 退出标准（全部可机检，命令见 `09` 与 `progress.json`） | 估时 |
| --- | --- | --- | --- | --- |
| --- | --- | --- | --- | --- |
| **P0** 架构与契约 | 骨架可运行 + 契约锁定 + 第一条垂直切片（认证） | 无 | ① `docker compose up` 起 `go-api`/`go-worker`/`ai-core` + 基础设施，`/api/v1/health` 与 `/ready` 200；② `contracts/openapi.yaml` + `contracts/ai-execution.schema.json` 存在且契约测试绿；③ Go 侧 register/login/me 通过，PBKDF2 golden vectors 能验旧密码；④ 前端只打 Go（grep 无 Python 直连）；⑤ pytest marker 注册完成，`-m unit/integration/chain` 可用 | 2–2.5 周 |
| **P1** 后端迁移 + 最小原型 | 13 条接口由 Go 服务，**上传→解析→索引→问答→引用**窄链路端到端只经 Go | P0 退出全绿 | ① Go 覆盖 13 条 + `health/ready/metrics`；② `npm run test:e2e` 在 Go 后端全绿（登录→上传→轮询 completed→提问→见 `[Source N]`）；③ 跨语言契约测试通过；④ `ai-core` 不对浏览器暴露（nginx 无路由）；⑤ 其余 12 条接口有逐条调用方审计记录并带 `Deprecation` 头 | 3–4 周 |
| **P2** 功能拓展与数据可信化 | `paper_chunks` 成 PG 真相、公式检索真实生效、会话 append-only、预算持久化、前端产品化 | P1 退出全绿 | ① `rebuild_chunks --verify-only` 退出 0 且覆盖全部叶子块；② `pytest -m chain -k formula` 绿且 `formula_index_entries` 行数 > 0；③ 引用可回溯到 `paper_chunks` 行 + PDF 页码；④ 崩溃后任务状态可从 PG 恢复（不含 Frontier）；⑤ README 能力表三档口径与实际一致 | 4–5 周（**预计超 6 周日程**，见 §7） |
| **P3** 多 Agent 自主探索 | ResearchRun + Frontier + Planner/Discovery/Reader/Writer + 报告 | P2 退出 + 学术检索 Provider 可用 | ① 固定多阶段工作流端到端产出带引用报告；② Go/Python 强杀后崩溃恢复测试通过；③ 幂等：重复派发不产生重复实体；④ 暂停/继续/取消正常；⑤ 预算耗尽产出 `PARTIAL` 报告并列出未解决问题 | 5–6 周 |
| （P4 展望） | Knowledge/Exploration 双图 + Analyst/Verifier/Explorer | P3 退出 | 见 `02` §8，本轮不排期 | — |

**顺序结论**：先骨架、再窄链路、再数据可信、再自主探索；双图永远排在自主探索之后（沿用旧计划末尾建议）。

---

## 2. 每阶段的可演示状态（原则①的具体形态）

| 阶段 | 演示脚本（30 秒内可看完） |
| --- | --- |
| P0 | `docker compose up` → 打开前端 → 注册 → 登录 → 侧栏显示用户名 → `curl Go /api/v1/auth/me` 返回同一用户。**证明**：Go 已是唯一入口，Python 退为内部服务，契约双向锁定 |
| P1 | 上面全部 + 上传一篇 PDF → 进度到 `completed` → 提问 → 流式回答带 `[Source 1]` 与 citations 列表。**证明**：窄链路端到端只经 Go，旧功能未退化 |
| P2 | 上面全部 + 点击某条引用 → 显示 PG 里的完整 chunk 正文（无 2000 字截断）与 PDF 页码/章节路径 → 打开 Monitor 页看到事件日志续传 |
| P3 | 输入一个研究问题 → Run 进入 `RUNNING` → Frontier 多轮派发 → 中途 `kill -9` worker → 重启后从租约过期处继续 → 产出带引用的报告与未解决问题清单 |

每个阶段结束时，上一阶段的演示脚本必须**仍然全绿**（回归不退化）。

---

## 3. 旧 A0 任务卡的去向（逐条处置）

| 旧卡 | 内容 | 新归属 | 处置理由 |
| --- | --- | --- | --- |
| A0-0 | 可复现环境：`.env.example` 死键清理、启动序列实跑、pytest marker 注册 | **P0-0** | 后续所有验收命令都依赖 `-m` 过滤，属骨架的一部分 |
| A0-1 | 前端故障 + typecheck 门禁 | ✅ **已完成** `2c3e583` | — |
| A0-2 | Schema 与时间戳只读核查（`audit_schema.py`、`probe_timestamps.py`） | **P0-2 的前置子项** | Go 建基线迁移前必须知道现库真实结构（`05` §1/§4） |
| A0-3 | 鉴权与运行安全 | ✅ **已完成** `d8f1563` | 转为 P0-6 的 Go 侧行为基线 |
| A0-4 | Chunk 可信化（Python 侧建表 + 链路改造） | **P2-1**，**改在 Go 侧 schema** | 原则①：横向深度；且 L3/Q4 要求新表出自 `server/migrations/` |
| A0-5 | 公式索引接通 | **P2-2** | 依赖 P2-1 的 chunk 真相层，否则索引挂在截断文本上 |
| A0-6 | 真实链路测试与科研回归集 | **拆两半**：真实链路 E2E 骨架进 **P1-6**（原则①要求 P1 就有端到端证据）；chunk/公式相关的链路用例进 **P2-3**；10–15 题固定回归集进 **P2-4** | "先有测试再宣布完成"不能等到 P2 |
| A0-7 | 文档与状态修正 | **持续项**，随每阶段收口（README 三档口径已在 `6221147` 完成第一轮） | 原则②的文档诚实要求 |

[`../archive/refactor-06-milestone-a0.md`](../archive/refactor-06-milestone-a0.md) 已归档为**历史记录**（含 E1–E10 状态与文件级细节），不再作为排期依据；
重映射表同时写在该文件 §4，避免只有这里能看到。

---

## 4. 切换策略（L5 渐进，按接口而非整体替换）

### 4.1 单一写者原则

任何时刻，同一份业务状态只允许一个进程写。切换按**接口逐个**完成：

```
阶段 1  Go 反向代理      浏览器 → Go → Python     Go 只做透传 + 鉴权 + trace_id，先验证路由/错误信封/流式形状
阶段 2  Go 接管读接口    /auth/me /sessions /sessions/{id} /documents
阶段 3  Go 接管写接口    /auth/register /login /sessions DELETE /documents/delete/*
阶段 4  Go 接管流式与上传编排 /chat/stream + /ws/chat + /documents/upload/async（Go 门面，内部调 ai-core）
阶段 5  Python 退内网    移除静态挂载(app.py:141)、移除业务 API、只留 /internal/v1/ai/*
```

映射到阶段：**P0** 覆盖阶段 1（代理骨架 + 认证切片）；**P1** 覆盖阶段 2–5 与最小原型。
每步一个独立提交、一次端到端复跑、一次回滚演练。

### 4.2 必须逐字节保持的兼容语义（`01` §6）

`{"detail": ...}` 错误信封（429 是 `detail` 还是现实现的 `{"error": ...}`，在 P0-4 契约锁定前定案，改动会影响 `useChat.ts`/`AuthPanel` 的错误处理）·
无分页的全量列表形状 · **PBKDF2 哈希格式**（Go 必须能验旧密码，golden vectors 先行）·
JWT claims（`sub`=用户名、`role`、`exp`、refresh 带 `type`）· localStorage 键名 `accessToken`/`currentUser` ·
WS query `token` · SSE 事件 `content/rag_step/citations/trace/error` + `[DONE]` · `rag_trace` 的两种形状（REST 过滤 / 流式原样）。

### 4.3 数据兼容

PostgreSQL 结构收编与 chunk 重建见 [05-database-migration.md](05-database-migration.md)；
Milvus 保持"可重建索引"定位，Go 侧记录 `index_state`，索引失败**不影响**文献元数据。

---

## 5. 回滚设计

| 阶段 | 回滚点 | 手段 |
| --- | --- | --- |
| P0 | 每张任务卡一个提交；`contracts/` 与 Go 骨架在切换前端基址前不动 Python | `git revert` 单卡；前端基址回退 = 改一处 `BASE` 常量并重新 build |
| P1 | 阶段 4/5 之前保留 `backend` 面向浏览器的完整能力 | 切 nginx `location /api/` upstream 从 `go-api` 回 Python（**一条配置，不是代码回退**）；Go 写的表 Python 侧只读，不冲突 |
| P2 | chunk 重建脚本写新表不动旧表；新版本 ready 后才切 `current_version_id` | 脚本带 `--dry-run` 与按 filename 删除本次写入；旧版本 chunk 保留可回退 |
| P3 | Frontier 关闭时退回"固定顺序执行"开关（同一 worker 二进制，`scheduler.mode=sequential`） | 事件日志与任务表保留，重放即可 |
| P4 | Explorer/双图关闭后 P3 报告链路不受影响（图只读增强） | `knowledge.enabled=false` |

**禁止的回滚方式**：删表、清 Milvus 集合后重建、`git reset --hard` 丢掉迁移脚本。

---

## 6. 风险登记

| 风险 | 触发 | 缓解 |
| --- | --- | --- |
| Go 验不了旧密码 | PBKDF2 base64 编码差异（标准 vs urlsafe）、盐长度 | P0-6 前先产出"旧哈希 golden vectors"，Go 单测逐条通过后才允许接管 `users` |
| SSE 形状漂移 | Go 侧缓冲/flush 策略、nginx `X-Accel-Buffering`（现由 `chat.py:75-79` 显式关掉） | P1 的契约测试对比 Python 与 Go 的**字节级帧序列** |
| 同一 Run 双写 | 阶段 2–4 期间 Python 仍在写 `chat_messages` | 切换窗口内该接口只允许单边写；feature flag + 写路径断言 |
| P1 引用被当成证据链 | chunk 真相层还没建，引用来自 Milvus 截断副本 | 前端与 README 显式标注"P1 引用为非证据级"；证据级属 P2 验收（§0.2 D3） |
| 6 周日程与 solo 投入不匹配 | 总纲的 6 周按全职强度估算；solo 15–20h/周下 P0+P1 ≈ 5–6.5 周，P2 落在 W7 之后 | §7 的压缩选项 + `progress.json` 里显式标 overtime，不虚报日期 |
| 旧库无 `alembic_version` | 历史 `init_db` 曾静默 `create_all`（已修，`d8f1563`） | P0-2 的 `05` §2 先核查后收编；create_all 建出的库需人工补基准版本才能启动 |
| naive 时间戳语义不明 | 历史数据混用 `utcnow()` 与 `now(UTC)` | `05` §4 的先验证后转换；P0-2 只读核查产出结论 |
| 弃用接口打破外部使用者 | 直接删 12 条无人调用接口 | `03` §5 的逐条调用方审计记录，先返回 `Deprecation` 头再下线 |
| Windows + Docker Desktop 上跑不通 | bind mount 权限、行尾 CRLF、端口占用、路径长度 | 跨环境律（`08` §7）：命令只走 `scripts/*.py` + compose；`.gitattributes` 固定 eol=lf；P0-8 必须在 Windows 实跑一遍 |

---

## 7. 日程与压缩选项

**周历**（起始 2026-10-12，solo 15–20h/周）：

| 周 | 日期 | 目标 | 阶段 |
| --- | --- | --- | --- |
| W1 | 10/12–10/18 | 骨架：Go 服务 + compose + 契约目录 + marker 注册 | P0-0…P0-4 |
| W2 | 10/19–10/25 | 契约锁定 + 认证垂直切片 + ai-core 内部面 | P0-5…P0-9 |
| W3 | 10/26–11/01 | 最小原型：Go 接管读/写接口，窄链路端到端跑通 | P1-0…P1-4 |
| W4 | 11/02–11/08 | 流式与上传编排、前端基址切换、E2E 全绿 | P1-5…P1-7 |
| W5 | 11/09–11/15 | 前端产品化（Monitor/Reader 骨架）、弃用接口收口 | P1-8 + P2 前端项 |
| W6 | 11/16–11/22 | 回归与发布：P1 退出标准全绿、文档口径复核 | P1 收口 |
| W7+ | 11/23 起 | **P2 数据可信化与功能拓展**（chunk 真相层、公式索引、回归集） | P2 |

**不可压缩项**：P0 的骨架 + 契约 + 认证切片、P1 的端到端 E2E。它们决定后续所有验收的可判定性。
**可后移项**：P1 的 12 条弃用接口收口（可延到 P2 初）、前端产品化页面（Monitor/Reader 的完整版）。
**明确不排期**：A/B/C 对照实验、20+ 题 benchmark、消融（决策 Q8，DEFER 到 P3 之后）。

## 8. 工作纪律

见 [08-principles-and-conventions.md](08-principles-and-conventions.md) §1、§3、§4、§6。
其中与本路线直接相关的三条：**不在没有端到端验证的情况下宣布阶段完成** ·
**每次修改同一提交内同步 `docs/progress.json`** · **架构变更先回文档层对齐再写代码**。

## 9. 与产品愿景的关系

> 对照 [11-product-vision.md](11-product-vision.md)。**P0–P3 是工程架构轴，V1.0–V4.0 是产品价值轴，两条轴的编号不得混用**（`11 §7`）。逐格映射的权威表在 `11 §7`，本节只记本路线的缺口与冲突，不复述那张表。

**已覆盖**：`11 §4.1 AI 论文图书馆` 与 `§4.2 Deep Reader` 的**数据前提** → 本文 P2-1（chunk 真相层）+ P2-2（公式检索）· `11 §4.4 Research Mission` 的**执行引擎** → P3 的 ResearchRun/Frontier/Worker · `11 §4.8 Research Writing` 的雏形 → P3 的带引用报告与 `PARTIAL` · `11 §4.5` 双图 → P4 展望（`02 §8`）。P1 的窄链路对应 V2.0 的"一键科研 MVP"入口。

**未覆盖**：`11 §4.3 比较矩阵 / Paper Diff`、`§4.6 Gap Explorer / Hypothesis Board`、`§4.7 Research Lab`、`§4.9 Research Radar / Knowledge Diff`、`§4.10 Research Workspace`，以及五个产品入口作为一等概念、工具与技能层（MCP/skills）——全部指向 `11 §8`。另：`11 §8` 第 11 项所要求的"信息增益驱动规划"P3 也没有（P3 只有预算 + Frontier，无证据充分性/信息增益驱动的任务规划）。

**需拍板/冲突**：**有，一处顺序冲突（`11 §7` 已标 ⚠️）**。V1.0 的口径是"**必须先完成现有基础的修复与可信化**"（`11 §10` 前提），而本文 §0.2 D3 把 chunk 可信化从"A0 前置"改为 **P2**（Go 迁移之后，见 §1 的 P2 行与 §7 的 W7+）。两个选项：
- **选项 A（`11 §7` 的建议）**：把 **P2-1/P2-2 前移**，与 P0-2 真库基线同批做（两者都不需要 Go），V1.0 的可信化因此提前；代价是 P0 的"骨架 + 契约 + 第一条垂直切片"边界被打破，P0 工期与 X1–X8 口径要重新定义。
- **选项 B（不动本文档顺序）**：**显式声明 V1.0 = 现有 Python 链路的可信化**，即 V1.0 交付在 Python 单体上完成（PDF 解析、公式/定理检索、原文定位、结构化阅读卡片），架构轴的 P2-1/P2-2 表述为"把已可信的数据面搬到 Go 侧新 schema"；代价是 V1.0 前后要做两次数据面工作，且 §0.2 D3 的"P1 引用不得称为证据链"约束在 V1.0 期间必须一直挂着。
