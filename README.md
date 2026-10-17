# ResearchPilot

面向研究者的 AI 科研工作台，原名 PaperRAG，正在重构。
当前由 Go 提供公开入口和部分业务接口，Python 仍执行文档、检索及聊天业务，Vue 提供交互。
目标是 Go 统一编排、Python 执行局部 AI 任务、PostgreSQL 保存业务真相；目标尚未全部实现。

## 1. 从哪里开始

- 开发规则：[AGENTS.md](AGENTS.md)；文档分类：[docs/README.md](docs/README.md)。
- 当前实现及限制：[架构现状](docs/reference/13-frontend-backend-architecture.md)。
- 进度：[progress.json](docs/progress.json)，[可视化](docs/progress.html)由它生成。
- 本轮整改：[规范化 TODO](docs/plans/repository-standardization.md)、[问题台账](docs/plans/12-known-code-issues.md)。
- 目标与计划：[产品愿景](docs/rules/11-product-vision.md)、[迁移路线](docs/plans/04-migration.md)、[功能模块](docs/plans/14-feature-modules.md)。
- 跨服务约定：[contracts/](contracts/)；历史过程：[WORKLOG](docs/WORKLOG.md)。

不要把历史测试数量、旧命令记录或未来规划当作当前能力。

## 2. 能力边界

已有文档解析/分块、混合检索、模型问答、引用标签展示、会话历史、认证及偏好等实现。
这些能力需对应的数据库、Milvus、模型服务和配置，不能仅由单元测试推定整条链路可用。

已知限制：

- SSE/WebSocket 目前下发完整答案事件，不是模型逐 token 输出。
- 引用标签校验不是语义接地，也不是 PG 正文证据链。
- 文档状态仍依赖文件系统与索引，PG 正文真相层未完成；跨存储索引更新不是原子事务。
- 局部文档任务与 AIExecution 已支持启动恢复；不等同于 Go 全局调度。Redis 文档任务受保留期约束，内存模式不持久化。
- 多模态与布局代码保留，不能宣称已完成产品验收。
- 工作区、比较矩阵、Gap Explorer、Research Lab、Radar 等页面或规划不代表完整后端能力。

逐项缺口见问题台账；阶段完成状态只以 progress.json 为准。

## 3. 安装与开发运行

### 3.1 宿主工具

需要 Git、运行中的 Docker Desktop、uv、Node.js/npm 以及 Go。前端默认使用 Node.js 24，受支持版本约束见 frontend/package.json。
Python 解释器按 [.python-version](.python-version)，Go 按 [go.mod](server/go.mod)，依赖按锁文件安装。
sqlc 只在生成数据访问代码时需要，版本由 dev.py gen 校验。

网络不可达时配置适合当前环境的包源/代理，不提交设备专属设置，不把某次网络故障归因当成永久事实。

### 3.2 初始化

在仓库根目录执行；Windows 用 Copy-Item，其他环境用相应复制命令。

```powershell
Copy-Item .env.example .env
uv sync --frozen --extra test
uv run python scripts/dev.py doctor
```

编辑 .env：配置 JWT_SECRET_KEY、LLM_API_KEY、LLM_MODEL，必要时配置 LLM_BASE_URL。
JWT_SECRET_KEY 使用足够强的随机值；真实聊天/检索验收需要有效的模型配置，占位值不能证明可用。
内部执行接口另需 AICORE_INTERNAL_TOKEN。配置说明见 [.env.example](.env.example)，不要提交 .env。

### 3.3 中间件与迁移

```bash
uv run python scripts/dev.py infra
uv run python scripts/dev.py migrate-go
```

infra 启动开发中间件，首次可能需要下载镜像。只验认证与 PG/Redis 时，可改用 `dev.py up postgres redis`。
Go 迁移显式执行，失败先处理原因，不盲目 force dirty 或重建库；已有数据先备份。
开发命令在未显式配置 DATABASE_URL 时使用本机 compose 的开发库；生产环境必须显式配置连接。
Go 接管库的 Python 启动只读检查版本（至少 5 且 clean），不重复执行旧建表链。
未接管旧库仍沿用 Alembic；dirty/未完成迁移和失败均不以 create_all 静默兜底。

### 3.4 三个终端分别运行

```bash
# 仓库根目录：Python
uv run python scripts/dev.py serve --no-reload
```

```bash
# 仓库根目录：公开 Go 入口
uv run python scripts/dev.py go-serve
```

```bash
# frontend 目录
npm ci
npm run dev
```

浏览器访问 `http://localhost:5173`，开发请求经 Vite → Go → 必要时反代 Python。
不要遗漏 Go 进程后按旧 Python 单体说明启动。所有项目入口关闭 Uvicorn 代理头改写，可信代理由应用按 CIDR 校验；手动启动也需 --no-proxy-headers。验收时使用 --no-reload，避免上传测试文件触发服务重启。

PDF/DOCX/XLSX 使用锁定的实际解析依赖；旧 `.doc` 转换另需宿主或镜像安装 LibreOffice，未安装时不能宣称支持该路径。
启动会恢复持久化的局部索引意图、Redis 文档任务与 PG 执行；缺失或指纹不符的恢复原文会阻止启动，不自动清空 pending 或重建数据。

### 3.5 检查与收工

```bash
curl http://127.0.0.1:8080/api/v1/health
curl http://127.0.0.1:8080/api/v1/ready
curl http://127.0.0.1:8000/health
```

health 只证明进程存活，ready 按各服务实际依赖判断；两侧探针内容不强行视作相同。
完整 RAG 仍需真实 PDF 上传、索引、提问与引用检查。

用 Ctrl+C 结束本轮源码进程；只停止本轮启动的容器，例如 `docker compose stop postgres redis`。
不要使用 down -v 或删除数据目录作为普通收工操作。

### 3.6 部署形态

开发 compose 只运行中间件；[docker-compose.prod.yml](docker-compose.prod.yml) 是容器部署形态。
生产密钥与安全配置就绪后才部署；service 级 env_file 不参与顶层变量插值，命令必须显式传 --env-file。

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d postgres redis
# 先备份存量库，再以显式运维命令迁移；不放进应用启动路径。
docker compose --env-file .env.production -f docker-compose.prod.yml --profile tools run --rm --build migrate
# 显式创建/更新当前 Go/Python 受限运行角色，再启动应用。
docker compose --env-file .env.production -f docker-compose.prod.yml --profile tools run --rm --build database-roles
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

生产模板中的 replace-with-* 必须替换；管理员邀请码可以留空关闭管理员自助注册，内部执行令牌必须配置。
代理头默认关闭；只有填写实际受控代理 CIDR 后才启用 TRUST_PROXY_HEADERS。关闭时同一代理的访客共用限流桶，不能据此声称已按真实客户端限流。
生产 compose 使用独立 Go/Python 运行角色；数据库管理员仅交给显式迁移和角色配置工具，不注入应用。
GO_DB_PASSWORD、PYTHON_DB_PASSWORD 使用至少 32 字符的 URL 安全随机值（如 secrets.token_urlsafe(48)）。
角色配置幂等、事务执行，拒绝接管外部同名角色或保留额外成员/所有者权限；若 PUBLIC 额外授权扩大权限则拒绝配置，须先人工核查。
当前权限按实际调用方配置，保留旧 Python 认证/会话必需写入；[目标 ACL](contracts/table-acl.md) 的完全 Go 接管仍按阶段实施。开发环境继续使用本机开发账号，不能把它当作生产运行主体。

## 4. 验证

```bash
uv run ruff check backend tests scripts
uv run python scripts/check_repository.py
# 联网审计 uv.lock 全部 PyPI 版本（含其他平台/可选组）
uv run python scripts/check_repository.py --audit-dependencies
uv run python scripts/sync_progress.py --check
uv run python scripts/check_contracts.py
uv run python scripts/check_route_ownership.py
uv run python scripts/check_frontend.py
uv run python scripts/check_design_review.py
uv run python scripts/check_nginx_routes.py
uv run python scripts/audit_schema.py --check-baseline
uv run python scripts/audit_schema.py --verify-columns --out docs/reference/schema-audit-2026-10-17.json
uv run python -m pytest -q
```

Go 在 server 目录运行 gofmt、go vet ./...、go test ./...；前端在 frontend 目录运行 npm run typecheck、npm run build。
Go 安全审计使用 `go run golang.org/x/vuln/cmd/govulncheck@v1.1.4 ./...`，前端使用 `npm audit`；升级按实际公告与兼容回归处理，不忽略公告制造通过。
修改查询后运行 `uv run python scripts/dev.py gen --check`。

真实存储/HTTP 专项（HTTP 进程使用新建受限角色，测试铺数使用隔离管理员）：`uv run python scripts/verify_storage.py --http`，需运行的 PG/Redis 和 Go 工具链；它创建隔离测试库，启动临时 Go/Python 进程并在验收后清理，不调用外部 LLM。
另设 REFACTOR_TEST_MILVUS_URI 指向本机隔离 Milvus 时执行真实索引崩溃恢复专项，只创建自己的集合；未设置时该专项明确跳过。嵌入模型用测试向量隔离，不代表真实 BGE 检索质量。
chain 层需对应服务完整启动，浏览器验收使用 frontend 的 npm run test:e2e；具体环境看测试配置。
测试跳过、零收集、仅静态检查均不能宣称真实业务通过。

Windows 遇到临时目录 PermissionError 时，先核实权限，必要时将 TEMP/TMP 指向工作区外新建目录后复验。
不要放宽断言或关闭失败用例。测试读数只记录在 WORKLOG，不在 README 维护易过期数字。

## 5. 目录

| 路径 | 职责 |
| --- | --- |
| server/ | Go 入口、业务接口、SQL 查询与迁移 |
| backend/ | Python 模型、解析、检索、聊天与局部 AI 执行 |
| frontend/ | Vue 展示、交互与传输状态 |
| contracts/ | 接口、跨服务消息、错误及归属契约 |
| scripts/ | 开发入口、生成、审计与检查工具 |
| tests/ | unit、integration、chain 等验证 |
| docs/ | 稳定规则、计划、现状、证据与历史归档 |

依赖、上传文件、模型、日志、缓存和数据库卷属于运行资产，不手工改写第三方内容，也不纳入 Git。
