# AGENTS.md — 仓库协作与开发规范

## 1. 使用范围与实现原则

适用于 ResearchPilot 仓库自有代码、脚本、数据库迁移、配置和现行文档。
用户本轮指令优先；不要把历史记录中的建议当成当前要求。

- 优先最简单、直接、最少改动的实现，先检查已有函数和类型。
- 只有多个真实实现、调用方或重复逻辑才引入抽象；不要提前增加 Manager、Service、Factory、Adapter 等层。
- 按故障根因重构，保留已有能力与对外契约；不能靠吞异常、空返回或修改测试掩盖缺陷。
- 文件拆分以职责为依据；行数用于提醒审查，不作为制造转发文件的理由。

## 2. 权威入口与冲突处理

| 问题 | 依据 |
| --- | --- |
| 原则、阶段顺序、证据与任务卡 | [最高约束 08](docs/rules/08-principles-and-conventions.md) |
| 工程进度 | [progress.json](docs/progress.json)，生成页面不手改 |
| 对外接口、跨语言消息、数据归属 | [contracts/](contracts)，以实现和契约检查核实差异 |
| 阶段计划与产品模块 | [plans/](docs/plans)，计划不是完成证据 |
| 当前实现与已知限制 | [架构现状 13](docs/reference/13-frontend-backend-architecture.md)、[问题台账 12](docs/plans/12-known-code-issues.md) |
| 文档分类与维护 | [docs/README.md](docs/README.md) |
| 历史过程与当时读数 | [WORKLOG](docs/WORKLOG.md)、reference 中注明日期的快照、archive |

规则约束目标，代码与本轮运行证据说明现状；二者不一致时登记差距，不能把目标写成事实。
档案与旧测试读数不能证明当前状态。不要在本文件维护百分比、测试数量、镜像数量或机器配置。

## 3. 架构边界

ResearchPilot 是 AI 科研工作台，产品愿景见 [11](docs/rules/11-product-vision.md)。
目标是 Go 唯一公开入口及全局编排、Python 执行局部 AI 任务、PostgreSQL 保存业务真相、Milvus 保存可重建索引。
这属于目标边界，迁移尚未全部完成；现有反代与 Python 业务接口见架构现状和 route-ownership 契约。

前端负责展示，后端能力优先 Go，模型、解析与检索执行复用 Python；不建第二个全局调度器。
工程轴 P0–P3 与产品轴 V1–V4 分开，质量修复不自动完成产品任务卡。
不为赶进度打乱依赖；正确性、架构一致性、可测试性优先于功能数量和速度。

## 4. 开工与变更方式

1. 检查 Git 工作区、相关实现、契约、当前任务状态和适用目录规则，保留已有未提交改动。
2. 说明具体故障、修复范围和验收方法；架构或对外行为改变先更新对应设计与契约。
3. 按根因修改生产代码，补能复现故障的测试；mock 只隔离外部依赖，不替换被测核心。
4. 修复后更新现状、台账及质量清单；过程证据写 WORKLOG，阶段状态写 progress.json。

## 5. 数据、密钥与资源

- 密钥经环境变量注入，禁止提交 .env、生产配置、上传文件、模型、日志、缓存和数据库卷。
- 变更现有库前备份；验证优先隔离库，清理只能针对本轮创建的对象。
- 不原地改已发布迁移，不用新建空库冒充历史存量兼容性证据。
- Docker、端口和后台进程先盘点再启动，只启动验证需要的服务；结束停止本轮启动的进程与容器，保留数据卷。
- Windows 临时目录权限错误先核实运行环境；必要时将 TEMP/TMP 指向工作区外新建目录，不改测试断言绕过。

## 6. 开发与验收入口

安装步骤以 [README](README.md) 为准，命令参数以 `scripts/dev.py --help` 为准。
开发 compose 只运行中间件；Go、Python、前端源码运行。prod compose 是部署形态，不混用两套拓扑。

```bash
uv run python scripts/dev.py up postgres redis
uv run python scripts/dev.py migrate-go
uv run python scripts/dev.py serve --no-reload
uv run python scripts/dev.py go-serve
# 在 frontend 目录：npm run dev
```

chat/索引验收另需 Milvus 及其依赖和实际模型配置；内部执行面还需 AICORE_INTERNAL_TOKEN。
只起 PG/Redis 不能据此宣称完整 RAG 可用。验证命令见 §9；真实存储专项使用 `scripts/verify_storage.py`。

## 7. 保留能力与禁区

- 不删除 parent_chunks、multimodal.py、layout_analyzer.py；未达到能力要求就明确降级口径。
- 不将 backend 整体改名 ai-core，不引入 Kafka、RabbitMQ、Neo4j、服务注册中心或重复调度器。
- 不删除历史归档，不追改 00/01 的 dated 事实；需要纠正现状时改现行入口。
- 不用 mock 结果填 real/e2e 证据，不把零用例收集、跳过或离线检查说成通过真实链路。
- 不删除泄露口令的安全黑名单；不推送含清除前个人信息的备份分支。
- 除非处理明确问题，不重写 Git 历史；确需重写时先备份、核对影响并同步 SHA 引用。

## 8. 提交与进度纪律

Conventional Commits，一个提交一个关注点；未得到发布指令不擅自推送。
每次提交同步 progress.json 并运行 `scripts/sync_progress.py`；只更新有证据支持的状态。
不得用质量修复工时抬高产品进度。提交前检查 diff、敏感信息和相关门禁。

## 9. 全仓开发规范（阿里规约的跨语言适配）

来源：[阿里巴巴官方开发手册与工具](https://github.com/alibaba/p3c)。采用其命名清晰、异常可观测、
资源有界、安全校验、数据库约束、测试与工程治理要求；Java/MySQL 专属规则不直接套到本项目。
Go 遵循 gofmt/vet 与标准库惯例，Python 遵循 PEP 8 与 Ruff，Vue/TypeScript 使用真实依赖类型。
下面规则适用于仓库自有代码、脚本、配置、迁移和现行文档；第三方依赖、模型、缓存、数据库卷是运行资产，
由依赖锁定与运行配置管理，不手改其内容。历史报告保留当时事实，现行入口必须明确引用当前文件。

### 实现与命名

- 优先现有函数、现有类型和最少改动；没有多个真实实现或调用方，不新增 Manager、Factory、Adapter、Registry 等层。
- 名称使用准确英文；Python 用 snake_case，Go 按导出规则命名，Vue 组件用 PascalCase，TS 函数用 camelCase。
- 变量名解释领域含义；公共常量放在所属域，不建立无边界的 constants/utils 大杂烩。
- 只在职责混杂、重复或复杂度有实证时拆分；禁止为缩短文件制造转发层、循环导入或空实现。
- 第三方库优先使用其正式类型与受支持接口，禁止伪造声明来掩盖类型错误；生成代码由生成器修改。

### 异常、日志与资源

- 不吞异常，不把数据库失败伪装成空列表、未找到或任务成功；边界层返回契约内错误，内部保留异常链。
- 只有明确可选的能力允许降级，必须记录原因；核心写入或清理失败必须使任务失败。
- Python 异常转换使用 `raise ... from exc`；没有可用异常变量且刻意隐藏内部链时明确 `from None`。
- HTTP 对外不泄露凭据、连接串、堆栈和内部路径；诊断细节只进受控日志，日志不记录 token、密码或全文。
- 每个请求的日志含 trace_id，跨服务透传；日志文件必须轮转。JSON 与文本日志由统一入口配置。
- 文件、数据库会话、临时目录和连接必须在异常路径也释放；禁止固定临时文件名和无上限重试。
- HTTP 包装器必须保留 flush、hijack、取消等底层能力；验证首帧到达和连接升级，不能只测最终响应。
- 等长数据配对使用 `zip(..., strict=True)`；允许截短必须显式 `strict=False` 并解释业务原因。

### 安全与数据库

- 用户、模型、检索原文均视为不可信输入；所有最终 HTML 在进入 v-html 前统一净化，不自行编写正则净化器。
- 文件名不得含路径段、反斜杠、NUL 或 Windows 数据流分隔符；数据库查询参数化，Milvus 字符串使用合法转义。
- 密钥只来自运行环境，示例不得包含真实密钥；禁止关闭 TLS 校验和执行不可信字符串。
- PostgreSQL 为唯一业务真相；表有主键，业务唯一性由约束保证，索引依据实际查询设计，不为形式批量添加。
- 新时间列用 TIMESTAMPTZ 与 UTC；既有时间语义变更必须先取证，不能直接把 naive 时间解释为本地时间。
- 已发布迁移不原地改写，结构修复使用新迁移；up/down 配对，验证空库与存量库、重复执行及失败恢复。
- 数据变更前保存可恢复备份；验收优先用隔离数据库，不能用重建的新库冒充原库证据。

### 工程、文档与 Git

- Python 依赖唯一声明在 pyproject.toml，uv.lock 保证可复现；requirements.txt 只提供 pip 安装入口。
- 前端 package.json 与锁文件同步，CI 使用 npm ci；格式服从 .editorconfig/.gitattributes，文本 UTF-8、LF。
- 本机 .env、模型、上传文件、日志、容器卷和构建缓存不得提交；现行文档相对链接必须可解析。
- 历史事实、测试读数、计划、已实现能力分开记录；没有本轮复验的历史测试不得冒充当前结果。
- 新提交使用 Conventional Commits，一个提交一个关注点；历史提交只有存在实际治理问题才改写，先保留可恢复备份并更新引用。
- 质量整改不代表产品功能完成，不借规范化提前实现未批准的阶段任务；整改证据写 WORKLOG 和 progress.json。

### 必跑检查

```bash
uv run ruff check backend/ tests/ scripts/
uv run python scripts/check_repository.py
uv run python scripts/sync_progress.py --check
uv run python scripts/check_contracts.py
uv run python scripts/check_frontend.py
uv run python scripts/check_route_ownership.py
uv run python scripts/check_design_review.py
uv run python scripts/check_nginx_routes.py
uv run python scripts/audit_schema.py --check-baseline
uv run python scripts/audit_schema.py --verify-columns
```

按修改范围运行 pytest、Go vet/test、前端 typecheck/build 与 Playwright；全量检查在一个批次收尾只跑一次。
脚本通过仅证明其检查项通过，不能据此宣称全仓安全、真实数据库或产品端到端均已验证。
