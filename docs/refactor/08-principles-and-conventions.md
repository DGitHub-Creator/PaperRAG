# 08 — 原则与开发规范（最高约束）

> **效力**：本文件是 `docs/refactor/` 的顶层约束。与其他任何文件冲突时**以本文件为准**；
> 与已锁定决策 Q1–Q8 冲突时，只有 §2 的阶段顺序律覆盖 Q1，其余 Q2–Q8 继续有效。
> 来源：用户《重构执行总纲》四条第一性原则（2026-10-09）+ 仓库既有规范与审计事实。
> 基线：`main @ 106f17dd`，2026-10-09。

---

## 1. 四条第一性原则

| # | 原则 | 操作含义（违反即退回重做） | 怎么机检 |
| --- | --- | --- | --- |
| **①** | **端到端链路优先，反对局部功能拼接** | 顺序固定为「可运行骨架 → 垂直链路打通 → 横向功能扩展」。禁止"先把某个模块做完再拼装"。每个阶段结束时必须存在**可运行、可测试、可演示**的系统状态 | 每阶段至少一条 `chain`/`e2e` 级验收命令（§4）为绿；阶段退出标准里没有端到端项 → 视为不合规 |
| **②** | **"完成"的唯一标准是端到端可验证行为** | 不接受"基本完成/大致可用/已支持"。每项任务必须同时给出**可验证完成标准**与**可验证执行路径**（命令 + 期望输出 + 证据等级） | `scripts/sync_progress.py --check`：`status=done` 而 `evidence < requires` → **直接失败** |
| **③** | **先对齐，再动手** | 每阶段开工前先交付：输入 / 输出 / 依赖 / 验收标准四元组，经确认后才实施。实施期间**禁止边写边改架构**；要改架构 → 停下，回到文档层重新对齐 | 任务卡缺任一字段即不可进入 `in_progress`；架构级变更必须先在 `02`/`04` 落地再写代码 |
| **④** | **最小修改，复用优先** | 优先复用现有资产（既有代码库）（62 个 Python 模块、前端、307 项测试）。禁止无关重构、大规模改写、与目标无关的代码清理 | 单提交只解决一件事；有效变更 > 400 行需拆分或在提交信息里说明；`git show --stat` 里出现与本阶段无关的文件 → 退回 |

四条原则冲突时按序号优先：**① > ② > ③ > ④**。
典型仲裁案例：V3.0 的「架构先行」与旧 Q1「先修完基线」冲突 → ①胜出，Q1 被 §2 取代。

---

## 2. 阶段顺序律（取代旧 Q1）

```
P0 架构与契约  →  P1 后端迁移 + 最小原型  →  P2 功能拓展  →  P3 多 Agent
（可运行骨架）    （一条窄链路端到端跑通）     （横向补深度）    （自主探索）
```

| 阶段 | 唯一目标 | 阶段结束时的可演示状态 | 该阶段禁止做的事 |
| --- | --- | --- | --- |
| **P0** | 把目标架构的**骨架与契约**搭起来 | `docker compose up` 起 Go + ai-core + 基础设施；浏览器经 **Go** 完成注册/登录/`/auth/me`；`contracts/` 有 OpenAPI + AI 执行契约且测试绿 | 迁移业务功能；重写旧 Python 逻辑；建双图；做 chunk 可信化 |
| **P1** | Go 接管前端实际调用的 13 条接口，**跑通最小原型** | 上传 PDF → 解析 → 索引 → 提问 → 看到带引用的回答，**全程只经 Go**；前端不再直连 Python | 引入新调度概念；把旧系统的历史缺陷当完成标准（引用粒度非证据级的限制要**写进文档**，不是偷偷扩大范围） |
| **P2** | 横向功能拓展与数据可信化 | `paper_chunks` 成为正文真相；引用可回溯到 PG 行与 PDF 位置；前端产品化页面可用 | 自主探索、Frontier 多轮规划 |
| **P3** | 多 Agent 自主科研任务 | ResearchRun + Frontier + Planner/Discovery/Reader/Writer 产出带引用报告，崩溃可恢复 | 双图 / Knowledge Explorer（属 P4 展望） |

**关键推论（必须接受，否则等于偷偷回到旧 Q1）**：

1. **不存在"Go 之前的一轮基线修复里程碑"**。旧系统剩余缺陷按「是否阻塞本阶段的端到端演示」决定去留：
   阻塞 → 进本阶段任务卡；不阻塞 → 进对应阶段（映射见 [04-migration.md](04-migration.md) §3）。
2. 已完成的 A0-1（前端故障 + typecheck 门禁）与 A0-3（鉴权与运行安全）——旧卡编号，重映射见 [04 §0.3](04-migration.md)**保留**，不重做、不回填。
3. P1 的最小原型允许跑在**尚不可信的 chunk 层**上，但其引用**不得宣称是证据链**；
   证据级引用是 P2 的验收项，文档与 README 的口径必须区分这两档。
4. chunk 可信化改在 **Go 侧新 schema**（`server/migrations/`）上做，不再由 Python 侧建表过渡。

---

## 3. 任务卡规范（原则③的落地形式）

每张任务卡（`docs/refactor/09-*.md` 与 `docs/progress.json` 一一对应）**必须**有七个字段：

| 字段 | 要求 |
| --- | --- |
| `输入` | 开工前必须存在的东西：依赖任务号、需要的密钥/容器/数据集、上游契约 |
| `输出` | 具体到文件与端点：新增/修改哪些文件、暴露哪些接口、生成哪些工件 |
| `依赖` | 只写任务号；不得存在循环依赖。`--check` 机检三条：任务号存在、`done` 的前置必须都 `done`、`in_progress` 不得抢跑还没开始的依赖（允许与进行中的前置并行——前置的 real 部分常常卡住本卡的 mock 部分） |
| `验收命令` | 可直接复制执行的一条（或多条）命令，而非"人工确认" |
| `期望输出` | 命令的成功判据：退出码、行数、字段、绿灯项 |
| `证据等级` | 该任务**要求达到的**最低等级（见 §4） |
| `规模/风险` | S/M/L/XL 与一句话风险 |

状态枚举（`progress.json`）：

```
status:   pending | in_progress | done | deferred | cancelled
evidence: none | mock | real | e2e          # 实际达到的等级
requires: mock | real | e2e                 # 宣称 done 所需的最低等级
```

**硬规则**：`status=done` ⟹ `evidence ≥ requires`。校验由 `scripts/sync_progress.py --check` 强制。

---

## 4. 验收标准写法与证据等级

证据等级从低到高：

| 等级 | 含义 | 典型命令 | 允许说"完成"吗 |
| --- | --- | --- | --- |
| `mock` | 单元级，外部依赖全部 mock | `uv run pytest -m unit -k xxx` | ❌ 只能说"已验证逻辑，未验证链路" |
| `real` | 真实 PG/Redis/Milvus 起容器，走真实链路但无 UI | `uv run pytest -m chain` | ✅ 可说后端链路完成 |
| `e2e` | 真实浏览器 + 真实后端，用户可见行为 | `npm run test:e2e` | ✅ 可说功能完成 |

写法要求：

1. 每条标准 = **命令 + 期望输出 + 等级**，三段缺一不可。
2. 命令必须声明可执行位置（仓库根 / `frontend/` / `server/`），跨环境要求见 §7。
3. 未跑通的标准只能是 `not_run` 或 `fail`，**不允许留空**，也不允许写"应该可以"。
4. 需要密钥或真实外部服务的标准标注 `needs_secret: true`，并说明无密钥时**哪一段无法验**。
5. 文档与 README 的能力声明用三档口径：**已实现 / 部分实现 / 规划中**。
   "代码或测试存在但没有任何调用方接入"属于**规划中**，不是已实现。

---

## 5. 复用与最小修改的具体边界

**优先复用（不动）**：`backend/rag/`（解析、清洗、分层分块、学术识别）、`backend/vectordb/`、
`backend/agent/`（LangGraph 图与提示词）、`backend/core/config/`、`frontend/` 现有组件、307 项既有测试。

**允许新增**：`server/`（Go）、`contracts/`、`scripts/`、`backend/internal_api/`、`tests/chain|e2e`、
`docs/refactor/`、`docs/progress.*`。

**禁止**：

- `git mv backend → ai-core` 之类目录大迁移（决策 Q2 有效；改名推迟到 P2 之后作为独立提交，且必须能单独回滚）。
- 为"顺手统一"而改动与本轮目标无关的文件（例：本轮目标是契约与后端，却顺手动前端的请求层）。
  前端请求层的整体替换是 `10-frontend-structure.md` 的**被指令任务**，不属于本条禁止范围；判据是每条机检都能回溯到该文的一句规定。
- 引入 Kafka/RabbitMQ/Neo4j/微服务注册中心（`02` §9）。
- 在旧 Python 侧新建第二套调度器（违反 L1）。
- 删除 `parent_chunks`/`multimodal.py`/`layout_analyzer.py` 等未接线代码——只降级口径，不删。

---

## 6. 开发规范（代码层）

| 主题 | 规定 |
| --- | --- |
| 语言 | 注释、日志文案、文档一律**中文**；标识符、错误码、日志字段名用英文 |
| 注释 | 默认不写；只写**为什么**（隐藏约束、不变量、特定 bug 的规避）。不复述代码在做什么 |
| 日志 | Go 用 `log/slog` 结构化字段；Python 用现有 `core/logging.py`。必须含 `trace_id`。**不记录论文全文**，只记录问题摘要、模型名、token 数 |
| 错误信封 | 对外保持 `{"detail": ...}`（`01` §6）；内部错误码表进 `contracts/`，每码固定 `retryable` 与 HTTP 映射 |
| 配置 | 只从环境变量读取（沿用 `backend/core/config/` 的分层）；密钥无默认值、缺失即拒绝启动；`.env` 不提交；示例只进 `.env.example` |
| 安全底线 | API Key 只在后端使用；PDF 存储路径可配置且文件不入 Git；不把外部文本直接拼进系统提示；鉴权一律以 DB 中的角色为准 |
| 测试 | marker 固定 `unit / integration / chain / e2e / slow`（`--strict-markers` 已开，注册属 P0-0）；端到端断言只针对**结构与可追溯性**，不断言模型文本内容 |
| 前端 | 分层单向 `components → composables → api → (browser)`；请求出口只有 `src/api/http.ts`，路径字面量只有 `src/api/client.ts`，登录态持久化只有 `src/api/token.ts`，状态层只允许模块级单例。具体十一条（R1–R11）与其理由见 `10-frontend-structure.md` §3，由 `scripts/check_frontend.py` 执行。门禁：`npm run typecheck` + `npm run build` + `check_frontend.py`（CI `frontend` job） |
| Go | `gofmt` + `go vet`；查询一律走 `sqlc`，不在业务代码里手写拼接 SQL |
| 提交 | Conventional Commits + 阶段前缀：`feat(p0):` / `fix(p1):` / `test(p0):` / `docs(p0):`。按关注点分批，一个提交一件事；统一 push 前先 `git fetch` |
| 同步 | 每个提交必须同时更新 `docs/progress.json`（§8） |

---

## 7. 跨环境可迁移性

目标环境是 **Windows + Docker Desktop**，同时 CI 跑 Linux。要求：

1. **命令只用跨平台入口**：统一收敛到 `scripts/*.py`（Python，已在依赖里）与 `docker compose`。
   禁止把关键流程写成仅 bash 可用的脚本；禁止 `sed -i`、`/proc`、`realpath` 等平台专属用法。
2. **路径**：Python 侧一律 `pathlib`，Go 侧 `filepath`；文档中的路径示例给相对路径。
3. **换行**：仓库根 `.gitattributes` 固定 `* text=auto eol=lf`（Go 与构建脚本对 CRLF 敏感）。
4. **版本只声明下限**：Go ≥ 1.25、Node ≥ 20、Python ≥ 3.12、Docker Desktop ≥ 4.x，
   不绑定具体补丁版本；CI 与本地用同一下限。下限以 `pyproject.toml` 的
   `requires-python = ">=3.12"` 与 `.python-version` 为准（本条此前写 3.11，是文档偏离了约束源）。
5. **容器优先**：`real`/`e2e` 级验证必须在 `docker compose` 起的环境里跑，避免"本机恰好装了某服务"。
6. **端口与主机名**不硬编码；一律从 compose 环境变量或配置读取。

---

## 8. 进度与日程强制同步（原则②的可见化）

```
docs/progress.json   ← 唯一真相（阶段、任务卡、退出标准、日程、风险、决策）
   ├─ 生成 → docs/PROGRESS.md    （人读：完成度、进度、待办、还差多少）
   └─ 生成 → docs/progress.html  （可视化：自包含单文件，双击即可离线打开）
```

规则：

1. **每次修改代码的同一提交里**必须更新 `docs/progress.json`；生成物由
   `uv run python scripts/sync_progress.py` 重算，**不手改生成物**。
2. CI 门禁：`uv run python scripts/sync_progress.py --check` 退出码 0。它检查
   ① 生成物与真相一致；② 任务号与依赖合法；③ `done ⟹ evidence ≥ requires`；
   ④ 每条退出标准都带命令；⑤ 状态与证据枚举合法。
3. 三份可读输出必须直接回答：**完成了多少**（总体与分阶段百分比）、
   **现在在哪**（当前阶段、进行中任务、本周日程）、**还差多少**（待办任务数、可开工的 frontier、未跑通的验收项）。
4. 日程以周为单位（W1…），起始日 2026-10-12；solo 投入 15–20h/周（决策 Q8），
   预估超出的阶段要显式标注，而不是偷偷改日期。

---

## 9. 明确不做（全阶段有效）

不引入 Kafka / RabbitMQ / Neo4j / 服务注册中心 · 不做端到端 GraphRAG 复杂算法 ·
不建两个全局调度器 · 不把 LangGraph State 当业务库 · 不把模型输出当可信事实 ·
不把 `≥95% / ≥90%` 设为 CI 门禁（决策 Q8：保留为质量目标）·
不做 A/B/C 三组对照实验与消融（DEFER 到 P3 之后）· 不改前端框架 ·
不在近期引入计费 / 团队协作 / 机构私有部署（产品愿景的 V4 层）。
