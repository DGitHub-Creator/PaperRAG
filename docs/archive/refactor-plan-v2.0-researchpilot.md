# PaperRAG → ResearchPilot 重构计划 V2.0

> ⚠️ **已归档（2026-10-09），不作为实施依据**（原位于 `docs/refactor/plan-v2.0-researchpilot.md`，逐字存档未改正文）。
> 本文的决策 **Q1「Go 之前先做一轮完整基线修复」已被《重构执行总纲》推翻**：原则①「端到端链路优先」要求
> 架构与契约先行，阶段模型改为 **P0 架构与契约 → P1 后端迁移/最小原型 → P2 功能拓展 → P3 多 Agent**。
> 现行口径：[08-principles-and-conventions.md](../refactor/08-principles-and-conventions.md)（最高约束）、
> [04-migration.md](../refactor/04-migration.md)（路线与旧卡片重映射）、[09-milestone-p0.md](../refactor/09-milestone-p0.md)
> （任务卡与退出标准）、[progress.json](../progress.json)（进度真相源）。
> 本文保留的价值是「当时为什么这么定」，以及 00-audit / 02-target 的输入出处；凡与上述文件冲突，一律以上述文件为准。

2026 年 10 月 9 日 · Go 主后端 + Python AI Core · 面向 Coding Agent 的完整实施方案

这次正式确定技术路线：

Go 负责系统控制与业务后端，Python 负责 AI 推理、LangGraph 和论文处理。

目标是在保留 PaperRAG 现有 RAG 能力的基础上，将其升级为能够自主开展论文检索、深度阅读、多文献对比、知识探索、证据核验和研究报告生成的 ResearchPilot 平台。

### 核心架构决策

Go Backend

API、JWT/RBAC、科研项目、Planner 调度控制、Frontier、Worker Pool、数据库、任务恢复、SSE

Python AI Core

LangGraph、LLM、Planner 推理、文献搜索、PDF 解析、RAG、专用 Agent、证据分析

关键约束：全局任务调度只有 Go 一个控制中心。 Python LangGraph 只负责单个智能任务内部的推理流程，不能自行绕过 Go 创建或调度全局任务。

## 一、确定技术栈

| 层次        | 推荐技术                        | 说明                    |
| --------- | --------------------------- | --------------------- |
| Web 前端    | 保留原技术栈                      | 不因重构而重新开发前端           |
| Go API    | Go + Chi                    | 轻量、兼容标准 `net/http`    |
| 数据访问      | pgx + sqlc                  | SQL 显式管理，便于事务和并发控制    |
| 全局任务队列    | PostgreSQL Frontier         | 支持持久化、任务依赖、租约         |
| AI 服务     | FastAPI + Pydantic          | Python 对外提供内部 AI 执行接口 |
| Agent 工作流 | LangGraph Python            | 专用 Agent 内部编排、检查点     |
| LLM 工具层   | 复用现有 LangChain              | 保留现有模型与工具抽象           |
| 数据层       | PostgreSQL + Redis + Milvus | 业务数据、缓存通知、向量检索        |
| 文件存储      | 本地共享存储，预留 S3 接口             | 保存 PDF 与研究报告          |
| 部署        | Docker Compose              | 先实现单机多容器              |

Chi 基于 Go 标准 HTTP 接口，适合模块化 API 服务；PostgreSQL 的 `FOR UPDATE SKIP LOCKED` 可以支持队列式任务领取。

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

go-chi/docs: chi docs · GitHub

+1



LangGraph 的 Checkpointer 则用于 Python Agent 内部的持久化执行和中断恢复，而不是替代 Go 的全局科研任务队列。

[image](https://www.google.com/s2/favicons?domain=https://github.com\&sz=32)

GitHub

+1



## 二、完整实施任务书（直接交给 Coding Agent）

下面这份是可独立使用的工程实施文档。它包含架构边界、推荐目录、服务契约、数据库模型、Agent 调度机制、研发里程碑和测试要求。

# ResearchPilot V2.0 — Go + Python 混合架构重构任务书

## 0. 项目背景与最终目标

项目名称：ResearchPilot

原项目：PaperRAG

GitHub：[https://github.com/DGitHub-Creator/PaperRAG](https://github.com/DGitHub-Creator/PaperRAG)

目标：将现有 PaperRAG 升级为具备自主科研探索能力的多 Agent 平台。

采用：

- Go：主后端、业务逻辑、身份认证、持久化任务调度、Worker Pool、科研项目管理、数据服务、事件与 SSE。
- Python：AI Core、LangGraph、论文处理、模型调用、混合检索、Agent 推理和证据分析。
- PostgreSQL：业务数据、任务队列、知识图谱、运行记录。
- Milvus：向量检索和论文语义索引。
- Redis：缓存、通知、限流辅助。
- Docker Compose：部署与环境管理。

核心科研流程：

研究问题 → 自主规划 → 文献发现 → 文献筛选 → 深度阅读 → 跨论文比较 → 研究缺口识别 → 动态探索 → 证据核验 → 报告生成。

最终用户只需要提交研究问题、确定探索范围和资源预算，即可获得可追溯的科研分析结果。

注意：

“一键科研”指自动化文献研究与探索流程，不意味着自动完成真实科研创新、数学证明或实验验证。系统必须明确区分论文陈述、可核验事实、推断与待验证假设。

---

## 1. 最高优先级架构规则

### 1.1 单一全局调度中心

Go 是全局 Research Run 的唯一生命周期与任务调度控制中心。

Go 负责：

- 研究项目和运行实例
- 任务依赖、优先级及 Frontier 队列
- Worker 分配和并发控制
- 任务租约、重试与幂等
- 全局研究预算与停止条件
- 数据库权威状态
- 用户暂停、继续和取消
- 任务事件与进度流

Python 不得绕过 Go 直接创建全局任务或更新 Go 业务表。

Python Agent 可以返回新任务建议，但必须经过 Go 验证，才能加入 Frontier。

### 1.2 Python 是独立 AI 执行服务

Python 保留：

- LangGraph
- LangChain
- LLM Provider
- Embedding
- BM25
- Reranker
- Query Rewrite
- HyDE
- PDF Parser
- Agent 专用提示词
- 学术检索工具
- 证据支持性判断

Python 提供内部 HTTP API，不直接面向浏览器提供新的核心业务接口。

### 1.3 状态所有权

必须建立明确的数据写入边界。

Go 拥有：

- Research Project
- Research Run
- Research Task
- Paper Metadata
- Research Finding
- Knowledge Graph
- Exploration Graph
- Evidence Registry
- Report Metadata
- Event Log

Python 拥有：

- AI Worker 临时上下文
- LangGraph Checkpoint
- 模型调用轨迹
- Embedding 与向量索引执行逻辑
- 暂存的解析结果与候选分析结果

Python 可以访问独立的 Checkpoint 存储，但不得未经 Go Service 校验直接修改核心业务状态。

Milvus 是可重新构建的检索索引，不是论文和证据的唯一真实来源。

### 1.4 渐进式重构

严格遵守：

1. 保留当前 PaperRAG 的可用能力。
2. 先建立 Go Backend。
3. 再逐步将原有 Python 业务接口迁移至 Go。
4. 保留 Python RAG 与 AI 模块。
5. 建立稳定的跨语言服务契约。
6. 最后引入多 Agent 自主研究。
7. 每个阶段必须可以独立启动与验证。

不能一次性删除原有 Python Backend。

---

## 2. Phase 0：完整代码审计

这一阶段必须先完成。

### 2.1 审计范围

全面检查现有 PaperRAG：

- README、项目结构、依赖文件
- 后端入口和 API
- 前端技术栈
- 用户认证和权限
- PDF 上传、解析、分块
- BGE Embedding
- BM25 和 Milvus
- Rerank
- Query Rewrite、HyDE
- LangGraph 节点、边和状态
- PostgreSQL 实体与表结构
- Redis 的实际用途
- SSE 实现
- Docker / Docker Compose
- 测试与 CI
- 运行配置、日志和安全问题

输出每条核心调用链的源码文件与函数定位。

### 2.2 必须生成的审计文档

- `docs/refactor/00-audit.md`
- `docs/refactor/01-current-architecture.md`
- `docs/refactor/02-target-architecture.md`
- `docs/refactor/03-gap-analysis.md`
- `docs/refactor/04-migration.md`

给所有现有模块标注：

- REUSE：直接复用
- EXTEND：在原有实现上扩展
- MOVE：迁移所属服务
- REFACTOR：内部重构
- NEW：新增
- DEFER：暂缓

### 2.3 建立基线

运行原项目测试。

验证至少以下流程：

1. PDF 上传和解析
2. 文档向量化
3. 向量与关键词检索
4. Rerank
5. LangGraph 回答生成
6. SSE 输出
7. 用户权限
8. 数据库读写

记录既有测试结果与已知失败，不允许假设旧项目完全正常。

完成 Phase 0 后才能进入实际架构重构。

---

## 3. Phase 1：建立 Go 主后端

### 3.1 推荐 Go 技术选型

推荐：

- Router：Chi
- HTTP：net/http
- 数据库驱动：pgx
- SQL 代码生成：sqlc
- 数据库迁移：golang-migrate 或现有兼容方案
- 日志：log/slog
- 配置：环境变量 + 结构化配置
- API 契约：OpenAPI
- 单元测试：Go testing
- 依赖注入：显式构造，暂不引入复杂框架

不强制引入 GORM、Kafka、微服务注册中心等组件。

如现有项目已有统一技术规范，先对比后选择。

### 3.2 Go 模块划分

建议采用模块化单体：

- `auth`：认证、授权、用户隔离
- `users`：用户管理
- `projects`：科研项目
- `papers`：论文元数据、文件信息
- `research`：研究运行实例
- `frontier`：任务队列与依赖
- `scheduler`：研究调度器
- `workers`：Worker Pool
- `knowledge`：知识实体与关系
- `exploration`：探索历史
- `evidence`：证据管理
- `reports`：研究报告
- `events`：事件流与 SSE
- `aiclient`：Python AI Core 客户端
- `storage`：文件存储
- `observability`：日志、指标、链路追踪

### 3.3 API

初期至少实现：

- `POST /api/v1/research/projects`
- `GET /api/v1/research/projects`
- `GET /api/v1/research/projects/{id}`
- `POST /api/v1/research/projects/{id}/runs`
- `GET /api/v1/research/runs/{id}`
- `POST /api/v1/research/runs/{id}/pause`
- `POST /api/v1/research/runs/{id}/resume`
- `POST /api/v1/research/runs/{id}/cancel`
- `GET /api/v1/research/runs/{id}/tasks`
- `GET /api/v1/research/runs/{id}/events`
- `GET /api/v1/research/runs/{id}/report`

保留现有旧 RAG API，必要时先通过 Go 代理到原 Python 服务。

不要在迁移期间同时让两个后端独立管理同一份业务状态。

### 3.4 认证和权限

Go 统一处理 JWT 与 RBAC。

主要资源权限以用户或工作空间为边界。

所有 Paper、Project、Run、Report 的访问必须校验所有权或共享授权。

Python AI Core 仅通过内部网络访问，使用服务间令牌或更严格的服务身份验证。

### 3.5 阶段验收

- Go API 服务可以独立运行。
- 可以创建、查询科研项目。
- 可以通过 Go 调用旧 Python RAG。
- 原有论文问答功能保持可用。
- 用户认证及权限边界正确。
- Docker Compose 可以启动混合架构。

---

## 4. Phase 2：将 Python 整理为 AI Core

### 4.1 核心要求

不重写已经成熟的 PDF Parser、Embedding、Rerank 和 Retrieval。

将 Python 代码逐步整理为独立 AI 能力服务。

内部逻辑模块：

- `llm`：LLM Provider、模型配置、重试
- `retrieval`：Hybrid Search / Rerank
- `parsing`：PDF 结构化解析
- `academic_search`：学术文献发现
- `agents`：专项 Agent
- `graphs`：LangGraph 工作流
- `tools`：Agent 工具接口
- `schemas`：Pydantic 输入输出模型
- `checkpoint`：LangGraph 执行检查点
- `observability`：模型调用与 Token 追踪

### 4.2 Go–Python 内部契约

建议首先采用 HTTP + JSON。

设计统一执行接口：

`POST /internal/v1/ai/execute`

请求字段：

- `task_id`
- `run_id`
- `task_type`
- `idempotency_key`
- `payload`
- `config`
- `deadline`
- `trace_id`

响应字段：

- `task_id`
- `status`
- `result`
- `proposed_tasks`
- `evidence_candidates`
- `usage`
- `errors`

支持的任务类型：

- PLAN_RESEARCH
- SEARCH_PAPERS
- SCREEN_PAPERS
- PARSE_PAPER
- INDEX_PAPER
- READ_PAPER
- EXTRACT_KNOWLEDGE
- COMPARE_PAPERS
- EXPLORE_GAPS
- VERIFY_EVIDENCE
- GENERATE_REPORT

返回给 Go 的 `proposed_tasks` 仅是建议，不代表 Python 已经创建正式任务。

Go 必须再次验证类型、目标范围、去重 Key、依赖和预算。

### 4.3 执行方式

MVP 首先使用同步 HTTP 执行单个有界任务。

每个 Worker 任务都有超时、取消机制和明确的最大输出大小。

不得让一个 HTTP 请求执行无限长的研究流程。

后续如单项 PDF 解析或 Agent 任务过长，可以升级为：

提交任务 → 返回 execution ID → 状态查询或回调 → 结果领取。

需要确保异步任务同样支持幂等与故障恢复。

### 4.4 统一 LLM Gateway

保留已有模型接入能力，并抽象：

- 模型供应商
- 模型名称
- 采样参数
- 结构化输出
- 工具调用
- 最大 Token
- 超时
- 重试
- Token 使用量
- 费用估算

允许 Planner、Reader、Verifier 使用不同模型。

系统不应依赖某一个固定的大模型。

### 4.5 阶段验收

- Python AI Core 可独立启动。
- Go 能调用旧 RAG 的核心检索和生成能力。
- PDF 解析、Embedding、Rerank 功能可复用。
- 输入输出 Schema 校验正确。
- 调用超时和服务不可用时返回规范错误。
- 跨服务 Trace ID 可以关联。

---

## 5. Phase 3：实现 Go Research Engine

这是整个新架构最重要的后端模块。

### 5.1 三层模型

Project：长期研究项目。

Run：某次具体科研探索执行。

Task：一次可调度、可重试的原子工作单元。

同一 Project 可多次运行，并产生不同版本的报告。

### 5.2 Run 状态机

定义：

- CREATED
- PLANNING
- RUNNING
- PAUSING
- PAUSED
- CANCELLING
- COMPLETED
- PARTIAL
- FAILED
- CANCELLED

任何状态转移必须通过 Go Research Service 校验。

暂停采用安全点暂停：停止派发新任务，允许正在执行的任务完成或在支持时协作中断。

取消需要向 Python 传递取消信号，并阻止过期结果覆盖取消状态。

### 5.3 Frontier Task Queue

使用 PostgreSQL 任务表作为第一版持久化队列。

核心字段：

- task_id
- run_id
- type
- payload
- status
- priority
- dependencies
- idempotency_key
- attempt_count
- max_attempts
- lease_owner
- lease_token
- lease_expires_at
- next_retry_at
- created_at
- updated_at

主要任务状态：

PENDING → READY → RUNNING → SUCCEEDED / FAILED

扩展状态：

BLOCKED、RETRY_WAIT、CANCELLED。

Go Scheduler 必须负责依赖解析，将满足依赖的任务转入 READY。

### 5.4 Worker Pool

采用 goroutine + context + 有界并发。

建议初期：

- LLM Worker：2–3
- 文献元数据检索 Worker：2–4
- PDF 解析 Worker：1–2
- 向量索引 Worker：1–2

以上仅是初始配置，需根据设备、外部 API 限流和模型服务能力调整。

Worker 流程：

1. 从数据库安全领取 READY 任务。
2. 写入租约、租约令牌及 RUNNING 状态。
3. 构建 Python AI Core 请求。
4. 发送带超时的 HTTP 请求。
5. 记录执行过程与资源使用。
6. 校验 Python 返回结构。
7. 在事务中持久化业务结果。
8. 标记任务完成。
9. 写入事件并触发依赖解析或重新规划。

数据库任务领取可以采用事务 + `FOR UPDATE SKIP LOCKED`。

### 5.5 幂等与故障恢复

必须考虑：

- Go 进程突然退出
- Python 进程突然退出
- 数据库短暂不可用
- Python 已执行成功但 Go 未收到响应
- 任务租约超时
- 同一任务被重复分配
- 外部模型 API 超时
- 用户执行取消后旧结果返回

任务通过 idempotency_key 防止重复创建。

通过 lease_token 或递增版本进行 fencing，阻止过期 Worker 覆盖新状态。

采用至少一次执行语义，不宣称跨 HTTP、数据库和 LLM API 可以实现严格 Exactly Once。

对于可能重复发生的模型调用，通过可恢复检查点、结果缓存和执行 ID 尽量降低重复成本。

### 5.6 Scheduler 调度逻辑

Go Scheduler 周期性检查：

- 新研究项目
- 已完成任务
- 尚未解决的依赖
- 新增证据
- Planner 重新规划请求
- 失败重试
- 预算与终止条件

只有状态版本发生有效变化时，才触发新的 Planner 任务。

同一个 Run 同一时刻最多存在一个有效 Planner 任务。

### 5.7 预算管理

每个 Run 配置：

- max_papers
- max_fulltext_reads
- max_planning_rounds
- max_expansion_depth
- max_tasks
- max_llm_tokens
- max_cost
- max_runtime
- max_concurrent_workers

预算耗尽时允许生成部分完成报告，但必须明确指出哪些问题未解决。

### 5.8 阶段验收

- Go Scheduler 可以自主分配任务。
- Python Worker 能完成实际执行。
- 多 Worker 不会错误提交同一任务。
- 进程重启后可恢复尚未完成的工作。
- 暂停、继续和取消正常。
- 重复执行不会产生重复的业务实体。
- 达到预算后能够正确停止。

---

## 6. Phase 4：实现论文科研 Agent

初期不要全部 Agent 同时开发。

推荐执行顺序：

### 6.1 Research Planner

输入：

- 当前研究问题
- 研究范围
- 已读文献摘要
- 已有知识
- 未解决的问题
- Frontier 状态
- 剩余预算

输出：

- 目标分解
- 子研究问题
- 推荐任务
- 任务依赖
- 优先级
- 停止或继续的理由

Go 负责验证和提交计划。

### 6.2 Paper Discovery Agent

功能：

- 研究问题转检索式
- OpenAlex / Semantic Scholar / arXiv / Crossref 检索
- DOI/arXiv ID 去重
- 相关度评估
- 引用和被引关系扩展
- 推荐阅读顺序

不得把只有摘要的论文伪装成已完成全文阅读。

### 6.3 Paper Reader Agent

结构化提取：

- Research Problem
- Contributions
- Methodology
- Assumptions
- Results
- Limitations
- Claims
- Supporting Evidence

对 UC 与分布式系统论文增加专业模板：

- Network Model
- Adversary Model
- Corruption Model
- Trust Assumptions
- Timing Assumptions
- Safety / Liveness Properties
- Ideal Functionality
- Simulator
- Theorem / Lemma / Proof
- Failure Threshold

阅读结果使用 Pydantic 模型输出。

每条关键陈述保留证据来源和原文定位。

### 6.4 Cross-Paper Analyst

对多篇论文进行：

- 方法分类
- 核心假设比较
- 实验或证明条件对比
- 相同问题的不同技术路线对比
- 研究局限分析
- 结论冲突检测

形成统一比较矩阵。

### 6.5 Explorer Agent

根据已有证据寻找未解决问题。

例如：

“某篇 HotStuff 论文证明终止性，但没有明确讨论时钟功能的可组合性。”

Explorer 可以提出：

- 检索时钟模型相关论文
- 寻找部分同步 UC 功能定义
- 对比不同协议的终止性假设

但不能直接将这些候选问题判定为真实学术创新点。

### 6.6 Verifier Agent

独立于 Reader 与 Writer。

职责：

- 校验参考文献真实性
- 校验证据定位
- 检查原文是否支持陈述
- 区分直接引用和跨文献推断
- 发现证据不足的结论

### 6.7 Writer Agent

使用已经结构化的阅读卡片、比较矩阵和证据编写：

- 文献阅读报告
- 研究脉络分析
- 方法对比报告
- 待验证假设清单
- 后续阅读计划
- BibTeX 参考文献

### 6.8 推荐 Agent 开发顺序

第一批：Planner、Discovery、Reader、Writer。

第二批：Analyst、Verifier。

第三批：Explorer。

在 Explorer 上线之前，系统应先具备稳定的固定多阶段研究工作流，作为实验基线。

---

## 7. Phase 5：双图知识与探索系统

借鉴 ARTEX 思路，但为科研领域重新定义实体。

### 7.1 Literature Knowledge Graph

保存可跨项目复用的论文知识。

主要实体：

- Paper
- Author
- Method
- Concept
- Assumption
- Theorem
- Claim
- Evidence
- ResearchProblem

主要关系：

- CITES
- PROPOSES
- USES
- REQUIRES_ASSUMPTION
- PROVES
- SUPPORTS
- CONTRADICTS_CLAIM
- RELATED_TO
- EXTENDS

所有强语义关系必须保存证据，不能仅因 Embedding 相似就建立 PROVES 或 CONTRADICTS_CLAIM。

### 7.2 Research Exploration Graph

保存一次研究任务的探索过程。

主要实体：

- Goal
- Intent
- Task
- Observation
- Finding
- Gap
- Hypothesis

主要关系：

- DECOMPOSES
- DEPENDS_ON
- PRODUCES
- DERIVED_FROM
- NEEDS_VERIFICATION
- MOTIVATES

Knowledge Graph 跨项目复用，但须遵守文献权限与数据隔离。

Exploration Graph 默认按 Research Run 隔离。

### 7.3 图与向量检索融合

Milvus 负责候选语义召回。

PostgreSQL 知识关系负责实体关联和限定范围。

建议优先使用：

1. 向量与关键词检索获得候选片段。
2. 根据 Paper、Section、Claim 进行关系扩展。
3. 使用 Reranker 重新排序。
4. 返回证据及其上下文关系。

不要从一开始就尝试复杂的端到端 GraphRAG 算法。

### 7.4 图谱写入

Python 返回候选实体和关系。

Go Knowledge Service 负责：

- 结构校验
- 实体规范化
- 去重
- 版本控制
- 证据绑定
- 持久化

建议使用关系表实现图结构，第一版不新增 Neo4j。

### 7.5 阶段验收

对于任意科研发现，能够追踪：

研究问题 → 探索任务 → 相关论文 → 结论 → 证据 → PDF 原文。

能够展示该发现是由哪个任务、哪次执行和哪些文献产生的。

---

## 8. Phase 6：Evidence Service 与科研报告

### 8.1 证据模型

至少保存：

- evidence_id
- paper_id
- paper_version_id
- section_id
- chunk_id
- page
- text_span
- content_hash
- source_type
- verification_status

状态：

- SUPPORTED：直接原文支持且定位已核验
- INFERRED：根据来源进行推断
- CONFLICTED：来源或解释之间存在冲突
- UNVERIFIED：尚无充分证据

SUPPORTED 不能解释为数学证明已经被系统独立证明正确。

### 8.2 报告格式

研究报告包含：

1. 研究问题
2. 文献检索策略
3. 文献筛选过程
4. 核心论文阅读卡片
5. 主要研究方法
6. 关键假设对比
7. 已有结论与证据
8. 多论文差异
9. 潜在研究问题
10. 待验证假设
11. 后续研究建议
12. 参考文献
13. 执行成本与局限性

每条关键结论可以点击跳转至 PDF 对应页面或章节。

### 8.3 导出

首先支持 Markdown。

随后扩展 PDF、DOCX、BibTeX 和结构化 JSON。

报告中不允许伪造 DOI、论文题目、页码、参考文献或原文引用。

---

## 9. Phase 7：前端 Research Workspace

不强制更换当前前端框架。

增加以下功能页面。

### 9.1 Dashboard

显示：

- 项目列表
- 最近研究任务
- 文献数量
- 已完成任务
- 待验证发现
- 任务成本

### 9.2 Research Workspace

创建研究任务时输入：

- 研究问题
- 自定义研究目标
- 文献范围
- 论文数量
- 探索深度
- 时间范围
- 模型选择
- 成本预算

### 9.3 Research Monitor

通过 Go SSE 展示：

- Planner 当前计划
- Worker 当前任务
- 任务完成状态
- 正在阅读的论文
- 最新研究发现
- Token 与成本
- 错误与重试

允许用户暂停、继续、取消。

### 9.4 Paper Reader

展示 PDF 和结构化阅读卡片。

支持原文定位与证据高亮。

### 9.5 Knowledge Explorer

两种视图：

- 文献知识图谱
- 科研探索路径图

初期采用有限节点展开，避免一次渲染完整大型图谱。

### 9.6 Research Report

支持：

- 报告阅读
- 引用跳转
- 对比矩阵
- 人工审核
- 导出
- 报告版本历史

### 9.7 SSE 可靠性

Go 保存事件序号和事件日志。

Redis 可以用于消息通知，但不能作为唯一持久事件来源。

客户端断线后通过 Last-Event-ID 或等价游标从持久事件日志继续读取。

---

## 10. 数据库模型与存储设计

### 10.1 主要 PostgreSQL 表

科研项目：

- research_projects
- research_runs
- research_plans
- research_tasks
- research_task_dependencies
- research_events
- research_budget_usage

文献管理：

- papers
- paper_versions
- paper_files
- paper_sections
- paper_chunks
- paper_references
- paper_parse_jobs

知识管理：

- knowledge_nodes
- knowledge_edges
- exploration_nodes
- exploration_edges
- exploration_anchors

证据与报告：

- evidence_links
- research_claims
- research_findings
- report_versions
- report_claim_links

运行与集成：

- ai_executions
- outbox_events
- model_usage_records

根据现有数据库模式进行调整，不允许盲目创建重复表。

### 10.2 索引设计

至少考虑：

- project_id / run_id
- task_status + priority + created_at
- lease_expires_at
- paper DOI / arXiv ID
- unique idempotency_key per Run
- evidence source reference
- knowledge edge source/target
- tenant_id / owner_id

数据库必须使用正式迁移脚本管理。

### 10.3 对象存储

PDF 原始文件、解析中间产物和大报告不直接存放在业务表的大字段中。

本地 Docker MVP 可先使用共享文件存储。

抽象 ObjectStorage 接口，以便未来迁移到 S3 或兼容对象存储。

Go 和 Python 使用对象 ID 或受控存储 URI 访问文件。

### 10.4 向量索引一致性

以 Go 业务数据库保存的文献及片段元数据为权威来源。

通过索引任务与 Outbox 驱动 Python 生成和写入 Milvus 向量。

允许最终一致性，但必须记录索引状态、版本及失败原因。

索引失败不能导致论文元数据丢失。

---

## 11. 可观测性、可靠性与安全

### 11.1 Observability

所有跨服务任务携带：

- trace_id
- request_id
- project_id
- run_id
- task_id
- ai_execution_id

Go 记录任务调度及业务状态。

Python 记录模型调用、工具耗时、Token 与 Agent Trace。

日志不能包含 API Key、用户隐私或不必要的 PDF 全文。

### 11.2 Prompt Injection 防护

PDF、论文网页、摘要以及外部工具返回内容全部视为不可信输入。

不能把检索到的文献内容当作系统指令。

Agent 工具采用白名单和结构化参数校验。

模型不具备执行任意操作系统命令或修改业务数据库的默认权限。

### 11.3 外部数据安全

处理：

- PDF 文件大小和 MIME 校验
- 恶意 PDF 和解析异常
- 外部 URL SSRF 风险
- 学术 API 限流
- 版权和全文访问限制
- 文档归属和授权访问

### 11.4 故障恢复

必须测试：

- Go 崩溃
- Python 崩溃
- Redis 不可用
- Milvus 暂时不可用
- PostgreSQL 短暂断开
- 模型 API 限流
- 用户取消进行中的任务
- 同一任务重复执行

所有可能重试的持久化操作必须具备明确的幂等策略。

---

## 12. 测试与科研评测

### 12.1 测试分层

单元测试：

- Go Service
- Scheduler
- 任务状态机
- 预算与优先级
- Python Parser
- Python Agent Schema

集成测试：

- Go → Python
- Go → PostgreSQL
- Python → Milvus
- PDF → 解析 → 检索
- Run → Planner → Worker → Report

端到端测试：

- 用户创建研究项目
- 系统自动完成多篇论文阅读
- 生成引用报告
- 暂停/恢复
- SSE 重连
- 报告原文回跳

### 12.2 AI 效果对比

建立三组实验：

A：原 PaperRAG。

B：固定多阶段工作流。

C：ResearchPilot 自主规划探索。

评估：

- Recall\@K / nDCG
- 文献覆盖率
- 引用定位准确率
- Evidence Support Rate
- Unsupported Claim Rate
- Research Question Coverage
- 重复探索率
- Task Completion Rate
- 人工审查时间
- Token 成本
- P50/P95 执行时延

### 12.3 消融实验

分别关闭：

- Frontier 动态规划
- Exploration Graph
- Knowledge Graph
- Evidence Verifier
- Query Rewrite / HyDE

通过实验判断哪些组件带来真实收益，而不是默认组件越多效果越好。

### 12.4 目标阈值

初期工程验收建议：

- 核心 API 契约测试通过率：100%
- 引用原文定位准确率：目标 ≥95%
- 关键结论证据支持率：目标 ≥90%
- 任务恢复功能测试：全部通过
- 关键科研工作流可以稳定完成
- 不允许虚构参考文献

以上为目标阈值，不是已有实验结果。

---

## 13. 分阶段开发排期

建议个人开发周期约 8 周，实际以源码审计和可投入时间为准。

### Week 1：仓库审计与 Go 后端初始化

- 完成 P0 审计
- 明确旧 RAG 模块
- 建立 Go 项目骨架
- 配置 PostgreSQL
- 建立 Go → Python 通信
- 保证原 RAG 正常运行

交付：可启动的 Go + Python 基础环境。

### Week 2：业务 API 与 Python AI Core

- Research Project API
- 用户认证与权限迁移
- Python 内部 AI 执行接口
- RAG Service 适配
- 统一错误与 Trace ID
- 基础集成测试

交付：用户通过 Go API 访问现有 RAG 能力。

### Week 3：文献发现与结构化阅读

- 多学术搜索 Provider
- 论文元数据模型
- PDF 结构化阅读
- 阅读卡片
- 原文 Evidence Anchor

交付：自动搜索并阅读多篇论文。

### Week 4：Go Research Engine

- Research Run 状态机
- Frontier Queue
- Worker Pool
- Planner 调度
- 任务依赖、超时、租约
- 幂等、重试和恢复

交付：可自动完成固定多阶段科研任务。

### Week 5：Agent 协作与动态探索

- Planner Agent
- Reader Agent
- Analyst Agent
- Explorer Agent
- Frontier 动态扩展
- 预算与结束条件

交付：能够根据证据缺口自主生成下一轮研究任务。

### Week 6：双图与证据系统

- Knowledge Graph
- Exploration Graph
- Knowledge / Evidence Service
- 证据支持性核验
- 跨论文比较

交付：可追溯科研知识与探索路径。

### Week 7：前端与报告

- Research Workspace
- 实时任务进度
- Paper Reader
- Knowledge Explorer
- Report Writer
- Markdown 导出

交付：完整可演示的 ResearchPilot。

### Week 8：测试、评测与工程优化

- 全部回归测试
- 故障恢复测试
- 多 Agent 评测
- 消融实验
- 性能与成本优化
- 架构及部署文档

交付：可部署、可评测、可展示的完整项目。

---

## 14. MVP 优先级

如开发资源有限，优先完成：

P0：

- Go API
- Python AI Core
- 学术检索
- PDF 阅读
- 基础 Planner
- 任务队列
- 结构化阅读卡片
- 多论文比较
- 带引用的报告

P1：

- 完整双图
- 动态 Explorer
- 自动任务优先级
- 高级证据核验
- 任务可视化

P2：

- 高级 GraphRAG
- 多模型自动路由
- 深度引文网络分析
- 协同科研工作区
- 大规模分布式调度
- PDF / DOCX 多格式高级报告
- 用户自定义 Agent / Skill

不要为了实现 P1、P2 而延迟可用的 P0。

---

## 15. 每阶段 Agent 工作规则

每一个阶段按照以下流程：

1. 阅读相关源码。
2. 列出本阶段真实涉及的文件和接口。
3. 说明拟修改的原因与影响范围。
4. 编写必要的测试或基线。
5. 实现最小可运行改动。
6. 运行单元测试与集成测试。
7. 检查旧 RAG 功能。
8. 更新 API 和架构文档。
9. 提交独立 Commit。
10. 汇总完成内容、测试、风险和下一步。

原则：

- 不以重构名义删除成熟功能。
- 不引入不必要的框架。
- 不大量复制旧代码。
- 不建立两个互相冲突的任务调度器。
- 不把 LangGraph State 当作长期业务数据库。
- 不把模型输出直接当作可信科研事实。
- 不在没有测试的情况下宣布重构完成。

---

## 16. 最终项目验收场景

研究输入：

“研究部分同步网络下 Tendermint 与 HotStuff 的终止性证明，重点分析其时间假设、领导者切换机制及 UC 安全建模问题。”

系统应完成：

1. Go 创建 Research Project 与 Run。
2. Go 派发规划任务。
3. Python Planner 生成研究子目标。
4. Go 将合法任务加入 Frontier。
5. Discovery Agent 检索相关文献。
6. Reader Agent 选择并深度阅读关键论文。
7. Analyst Agent 生成网络模型、时间假设、证明方法的对比矩阵。
8. Explorer Agent 识别证据缺口。
9. Go 判断预算与依赖并派发下一轮任务。
10. Verifier Agent 检查关键结论的原文证据。
11. Writer Agent 生成科研报告。
12. Go 持久化结果并通过 SSE 推送进度。
13. 前端展示报告、引用和探索历史。

最终输出：

- 相关论文清单
- 结构化阅读卡片
- 方法与假设比较矩阵
- 研究知识图谱
- 科研探索过程
- 证据引用
- 待验证研究问题
- 后续阅读计划
- Markdown 研究报告

整个执行过程支持暂停、继续、取消、失败恢复与成本审计。

---

## 17. 立即开始执行的任务

现在开始 Phase 0。

首先审计 PaperRAG 的全部源码。

重点判断：

1. 现有 FastAPI 哪些接口应该迁移到 Go？
2. 哪些 RAG 模块应该继续保留在 Python？
3. LangGraph 现有 Graph 能否复用为专用 Worker？
4. PostgreSQL 的数据如何迁移并保持兼容？
5. Milvus 索引是否需要调整？
6. 当前 PDF Parser 和 Reranker 能否直接复用？
7. Go API 如何在不破坏旧系统的情况下逐步接管？
8. 哪些功能已经存在，哪些模块需要新增？

输出实际代码级别的重构路线、目录方案、数据库迁移计划和第一阶段具体任务。

先完成审计，不要直接全面重写项目。

本计划是目标架构，必须根据真实仓库代码调整。

## 三、建议采用的目标项目目录

这不是你当前仓库的实际目录，而是 Agent 审计后可以参考的目标组织方式。

```
PaperRAG/
├── backend/                   # Go 主后端
│   ├── cmd/
│   │   ├── api/               # HTTP 服务入口
│   │   └── worker/            # 调度与 Worker 入口
│   ├── internal/
│   │   ├── auth/
│   │   ├── projects/
│   │   ├── papers/
│   │   ├── research/
│   │   ├── frontier/
│   │   ├── scheduler/
│   │   ├── worker/
│   │   ├── knowledge/
│   │   ├── exploration/
│   │   ├── evidence/
│   │   ├── reports/
│   │   ├── events/
│   │   └── aiclient/
│   ├── migrations/
│   ├── sql/
│   └── go.mod
│
├── ai-core/                   # Python AI 服务
│   ├── app/
│   │   ├── api/
│   │   ├── agents/
│   │   │   ├── planner.py
│   │   │   ├── discovery.py
│   │   │   ├── reader.py
│   │   │   ├── analyst.py
│   │   │   ├── explorer.py
│   │   │   ├── verifier.py
│   │   │   └── writer.py
│   │   ├── graphs/
│   │   ├── retrieval/
│   │   ├── parsing/
│   │   ├── tools/
│   │   ├── schemas/
│   │   ├── llm/
│   │   └── services/
│   └── tests/
│
├── frontend/                  # 保留现有前端
├── contracts/                 # Go/Python API Schema
├── docs/
│   ├── architecture/
│   ├── refactor/
│   └── benchmarks/
├── benchmarks/
├── docker/
└── docker-compose.yml
```

我还建议保留原来的 PaperRAG 品牌，把 ResearchPilot 作为新增的科研探索模块名称。如果以后项目成熟，再考虑是否整体更名，避免一开始就进行大量无业务价值的目录和品牌修改。

## 四、最重要的三个验收里程碑

里程碑 A：Go 成功接管后端

不要求新增 AI 功能，但所有主要业务请求经过 Go，Python 专注 RAG 和模型能力。旧系统功能可用、测试通过。

里程碑 B：Go Planner–Worker 跑通

输入研究问题，Go 能派发任务，Python 能完成文献检索和阅读，任务可以恢复，最终生成带引用的研究报告。

里程碑 C：自主科研探索闭环

系统能够根据已有证据识别未解决问题、动态追加任务、更新双图，并提供可解释的探索路径和可信的科研报告。

我的建议是：先完成里程碑 A 和 B，再投入双图和自主 Explorer。 这会给你一个始终可以运行和展示的项目，也能清晰地区分 Go 后端工程能力与 AI Agent 算法能力。

最终，这个项目的技术定位就相当明确了：Go 持久化任务执行引擎 + Python LangGraph AI Core + 多 Agent 科研探索 + Evidence-grounded RAG。既有实际科研价值，也能展示你的 AI 后端和系统设计能力。