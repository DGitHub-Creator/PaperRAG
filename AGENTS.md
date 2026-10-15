# AGENTS.md —— 给接手这个仓库的 agent

> 本文只放三样东西：**项目愿景、项目规约、必须严格遵守的内容**。
> 它是常青的，所以**不写日志**——"第几轮做了什么、实跑读数是多少、当时踩了什么坑"一律在
> [`docs/WORKLOG.md`](docs/WORKLOG.md)；进度真相**只有** [`docs/progress.json`](docs/progress.json)；
> 代码层的问题与处置在 [`docs/rules/12-known-code-issues.md`](docs/rules/12-known-code-issues.md) 台账。
> 往本文里追加 dated 内容 = 违反 `docs/rules/08` §6。

## 1. 项目愿景与定位

**ResearchPilot**（原 PaperRAG）：面向研究者的 AI 科研工作台。

- **三条架构定位**：Go 是唯一公开入口与唯一全局调度；Python（`backend/`）只被动执行单次 `AIExecution`；
  **PostgreSQL 是唯一业务真相**，Milvus 降为可重建索引。
- **三方分工（用户 2026-10-14 定）**：前端负责展示；Python 负责核心业务端（agent 领域的库与方法多，
  用它方便）；Go 负责后端与编排等一切后端能力——**能用 Go 就用 Go，实现不了的才用 Python**，
  目标是一个高性能后端服务。
- **产品轴愿景**（五个入口、十项能力、V1.0–V4.0 路线）见 [`docs/rules/11-product-vision.md`](docs/rules/11-product-vision.md)。
  终局**不是**"输入主题一键生成一篇论文"，而是"输入研究方向，建立能持续积累知识、追踪证据、
  执行研究任务的科研工作空间"（`11 §11`）。
- **两轴别混用编号**：工程阶段 **P0–P3**（`plans/04` 定义）、产品价值 **V1.0–V4.0**（`rules/11` 定义），
  映射见 `11 §7`。

## 2. 文档权威层级（冲突时按此优先级）

> **目录结构、分类、命名与归档规则见 [`docs/README.md`](docs/README.md)（文档宪法）**；下表是**内容**的权威层级。

| 顺位 | 文件 | 性质 |
| --- | --- | --- |
| 1 | `docs/rules/08-principles-and-conventions.md` | **最高约束**（四条原则、阶段顺序律、任务卡规范、开发规范、进度同步律） |
| 2 | `docs/progress.json` | **进度唯一真相**；`PROGRESS.md` 与 `progress.html` 是它的生成物，改完必须重跑 `sync_progress.py` |
| 3 | `docs/plans/09-milestone-p0.md`、`docs/rules/10-frontend-structure.md` | 当前阶段的任务卡与退出标准 |
| 3.5 | `docs/rules/11-product-vision.md`、`docs/rules/12-known-code-issues.md` | 产品轴（V1–V4）与代码问题台账 |
| 3.6 | `docs/rules/13-frontend-backend-architecture.md`、`docs/rules/14-feature-modules.md`、`docs/rules/frontend-backend-division-of-labor.md` | **As-Is 实测**：13 = 前后端与数据面的当前形状（每条带 `file:line`），14 = 产品轴逐功能模块规划，division-of-labor = M1–M17 × 三方分工 + 表级写入边界 |
| 4 | `contracts/` | Go↔Python 契约；改契约改这里，`check_contracts.py` 机检 |
| 5 | `docs/WORKLOG.md` | **逐轮实录（日志）**：某轮的产出、证据等级、实跑读数、踩过的坑。dated 事实，**不作为规约** |
| 6 | `docs/reference/00-audit.md`、`docs/reference/01-current-architecture.md` | **dated 事实**：历史审计基线，**不是现状**（只读，不追改） |
| 7 | `docs/archive/` | 归档件，**不作为实施依据**，正文逐字保留 |

**两层分界（别混用）**：`docs/rules/` = **常青规则**（改它等于改契约，必须先回文档层对齐再动代码）；
`docs/plans/` = **会变的详细计划**（实施细节以它为准，但与 `rules/` 冲突时让位于 rules）。
**一句话**：内容听 `08`，结构听 `docs/README.md`，进度听 `progress.json`，历史听 `WORKLOG.md`。

## 3. 现在的架构事实（只留结论；来龙去脉见 `WORKLOG.md`）

- **两种运行形态**：dev = **中间件容器 + 三个源码进程**（Go / Python / 前端，见 §6），**dev compose 里没有任何应用服务**（由 `check_nginx_routes.py` 的 R5 守着，台账 C29 已处置）；
  prod = `docker-compose.prod.yml` 的**全栈容器**（部署形态）。"容器只跑中间件"这条定案**只管 dev**。
- **dev 的入口链**：`vite`（:5173）→ **go-api**（:8080）→ 尚未迁移的路径反代给 `PYTHON_UPSTREAM`
  （默认 `127.0.0.1:8000`）。**搬一条路由就少转发一条**（`14 §19` 铁律 2「门面先于重写」）。
- **Go 原生服务的面**：8 条业务（auth 的 register/login/me/password、me/preferences 的 GET+PUT、
  sessions 的 list/delete）+ 4 条探针（`/api/v1/health`、`/api/v1/ready` 及两条根路径别名）。
  `/ready` 的探测键是 `database` + `redis`，键名与 detail 文案与 Python 逐字对齐。
- **Python 仍是主业务后端**：浏览器面 13 条 + 内部面 7 条（`/internal/v1/ai/*`，**零生产调用方**）
  + 前端不调但仍可达 12 条 → "只被动执行单次 AIExecution"**尚未成立**。
  每条面由 `contracts/route-ownership.md` + `scripts/check_route_ownership.py` 逐一认领（归属 ∈ `go`/`shared`/`proxy`/`internal`）：接管了却没删、新加了没人认领，都会红。
- **数据面**：`server/migrations/` 3 份迁移**已有执行器**（`dev.py migrate-go`，决策 D8 定案：显式命令、不进启动路径；台账 C18 已处置），dev 库实测 13 张基础表 = 12 张建表 + `schema_migrations`；sqlc 10 条查询分布在 3 个文件
  （`users` / `user_preferences` / `chat_sessions`），也就是 **Go 今天只读写 3 张表**。
  ⚠️ `contracts/table-acl.md` 声明 25 张（现场取：`grep -c '^| `' contracts/table-acl.md`），其中 18 张的 `go: W` 是
  **纸面归属**（库里没有这些表，台账 C30，差集已逐张点名在 ACL 文末）；另有 5 张库里存在但未登记，归属属决策 D6。
- **文档真相不在 PG**：`/documents` 读文件系统 `UPLOAD_DIR` + `ingested_state.json` + Milvus（chunk 数），
  所以 Go 接管它的硬前置是先建文档真相表；`rag_trace` 是 pydantic **投影**而非透传（台账 C34）。
- **迁移编号规则**（详见 `plans/05 §2.6`）：`000001` 基线 / `000002` `ai_executions` / `000003`
  `user_preferences` 已落；`000004` `fix_drift` / `000005` `paper_chunks` 待落。**条件性预留不占号**。
  新表一律 `TIMESTAMPTZ`；可空列做唯一键成员时必须 `NOT NULL DEFAULT ''`（PG 里 NULL 互不相等，
  唯一约束会静默失效）；实现没写到的列不预先建；`GRANT` 在角色定义之前不写。
- **分支布局**：远端只剩 `main`，本地工作分支就是 `main`（跟踪 `origin/main`）。
  ⚠️ `backup/main-pre-rewrite-20261012` 携带 2026-10-11 历史重写**之前**的 92 个提交（含已清除的
  个人/设备信息）——**不要 push 它、不要删它、不要把本地 `main` 挪回它**。
  PR 入口形态：`https://github.com/DGitHub-Creator/ResearchPilot/pull/new/<分支名>`。
- **读数一律现场取，别抄文档里的数字**：`uv run python -m pytest -q`、`--collect-only -m <层>`、
  `uv run python scripts/sync_progress.py --check`、`grep -c operationId: contracts/openapi.yaml`。

## 4. ⚠️ 已被推翻的旧结论（**不要重复相信**）

> 一行一条；论证、取数方式与操作坑见 [`docs/WORKLOG.md`](docs/WORKLOG.md) 的**附 B / 附 B-1**。

| 旧结论 | 事实 |
| --- | --- |
| 「本机缺一次重启才能用 Docker」 | 真因只是 Docker Desktop 没在运行，拉起后约 5 秒就绪 |
| 「Docker Desktop 是系统级安装」 | **这条更正本身是错的**：它是 per-user 安装（`%LOCALAPPDATA%\Programs\DockerDesktop`） |
| 「compose 不写 `name:` 无所谓」 | 项目名会退回**目录名**（本机叫 `PaperRAG`），换目录 clone 就换一个项目名（C26，已钉 `researchpilot`） |
| 「只验骨架可跳过 LLM key」 | `app.py` 的 startup **无条件**调 `validate_config()`，缺 key 即拒绝启动 |
| 「schema 源整目录交给 sqlc 就行」 | `.down.sql` 按文件名排在 `.up.sql` **前面** → 先 DROP 再 CREATE。必须逐个列 `*.up.sql` |
| 「`--check-baseline` 通过 = 基线与真库一致」 | 它只校验**文件形态**；内容比对是 `--verify-columns`（快照缺 `columns` 时如实 exit 2） |
| 「sqlc 的 diff 能核对列默认值」 | **sqlc 不把 DEFAULT 编码进 Go 类型**，diff 抓不到；DEFAULT 的机检是 `--verify-columns` |
| 「本机没有 sqlc 二进制」 | `$HOME/go/bin/sqlc.exe` 就是钉住的 v1.30.0，`dev.py gen` 本来就优先用本机二进制 |
| 「真库有 9 张表」 | **10 张**（含 `alembic_version`）；它的归属是决策 D6 |
| 「`users.created_at`/`role` 库里没有 DEFAULT」 | 真库有 `DEFAULT now()` 与 `DEFAULT 'user'` |
| 「X5 的命令是 `cd server && go test -run …`」 | `server/` 根目录没有 Go 文件 → **rc 恒为 1，与测试是否存在无关**（C22）。已补包路径 |
| 「Go 依赖拉不动」 | 可解，但**本机 GOPROXY 一直没设**；`goproxy.cn` 后 1.6s 拉到 |
| 「密码长度用 `len(password)`」 | Go 的 `len(string)` 是**字节**，生产侧是**码点** → 用 `utf8.RuneCountInString` |
| 「Basic 方案的 401 是 `Invalid authentication credentials`」 | 实测 `OAuth2PasswordBearer` 回 **`Not authenticated`**；那句在 `HTTPBearer` 里，本项目没用 |
| 「Go 的 500 文案是 `Internal Server Error`」 | 生产侧是 `Internal server error`（**小写 s**）（C23，已对齐） |
| 「契约里 `role` 是 enum，Go 该按枚举校验」 | 实现是 `str \| None`，`role:"root"` 返回 **200** 并折叠成 `user`（C21）。照实现走 |
| 「`cp .env.example .env` 就能起」 | 旧模板的**行内注释**被 dotenv 当成值（`int('#1024')`），已改成整行注释 |
| 「compose 的 backend 开箱可用」 | **缺 `target: backend`** → 构建出 nginx 镜像 → 永远 unhealthy（已修） |
| 「旧名 PaperRAG 还留在 module path / 指标名」 | 已全部改为 `researchpilot`；**唯一保留旧字面量的是安全黑名单**（删了等于把泄露口令重新变成可用口令） |
| 「minio 镜像拉不到是网络问题」 | **上游归档**，`dl.min.io` 对当前版与全部归档版都 410 Gone（C24/D9）。已换 `versity/versitygw` |
| 「ACL 里写着 `go: W` 所以 Go 在写这张表」 | **纸面归属**：18 张表在 SQL 里根本不存在（C30）。判归属前先求差集 |
| 「契约里有 `/api/v1/health` 所以打它就通」 | **只有 Go 满足**；Python 的 health 路由不带 `/api/v1` 前缀（C31）。`check_contracts.py` 抓不到 |
| 「`/metrics` 在契约里说明监控已就位」 | **三不管端点**：契约有、Python 有、nginx 无 location、前端不调、Go 未实现 |
| 「prod compose 写了 `env_file:` 就能取到 `${VAR:?}`」 | **不能**：service 级 `env_file` 不参与顶层插值，prod 启动必须带 `--env-file`（C27） |
| 「Python 的 login/register/chat 是可用的（测试全绿）」 | 曾**对任何合法请求都回 500**（C32，已修）。无效 body 的用例覆盖不到限流路径；门面会掩盖上游坏死 |
| 「P0-8 要在 compose 里加三个应用服务」 | **前提被 2026-10-13 定案推翻**（C6 作废、遗留冲突记 C29）。别照旧卡片去加 compose 服务 |
| 「测试基线是 448 / 515 / 547 / 572 项」 | 都过期过。**读数现场取**，别抄文档 |
| 「文档里的数量与命令面是按机器现状写的」 | 2026-10-12 扫出 **12 处过期**（C19），并修掉一处自相矛盾（`TEMP`/`TMP` 该指工作区外） |
| 「别把重建出的库当原库用」 | `alembic upgrade head` 建的是**全新库**，拿它验 X6 的"存量库幂等"是**自证**；原对象已永久消失（C20） |

## 5. 本机环境要点（操作性约束）

- **前置**：Docker Desktop 必须在运行；引擎没起来时 `docker info` 只报 pipe-not-found（不是缺组件）。
- `.env` **三个必填**：`JWT_SECRET_KEY`、`LLM_API_KEY`、`LLM_MODEL`（后两个连只验骨架也要有非空占位值）。
  `.env` 与 `.env.production` **都不入库**；换 `JWT_SECRET_KEY` 等于让既有 token 全失效（生产必须先备份）。
- `scripts/audit_schema.py --live` 与 `probe_timestamps.py` **要显式 export `DATABASE_URL`**（脚本不读 config 默认值）。
- 中国大陆：`go env -w GOPROXY=https://goproxy.cn,direct`；`docker.io` 被 DNS 污染 → 用镜像源
  （`docker.m.daocloud.io` / `docker.1ms.run` / `quay.io` 直连），**要拉带版本号的 tag，别拉 latest 再改名**。
- **跑 chain / e2e 证据时 `dev.py serve` 要带 `--no-reload`**：集成用例往 `backend/data/documents/` 写文件会触发热重载、把真栈打断，chain 就红在一片"断言写错了"的表象里（本轮实测：带 reload 时 7 条红，`--no-reload` 时全量 644 passed）。内部执行面的 chain 用例还要 `AICORE_INTERNAL_TOKEN`，服务与用例必须用同一个值。
- **Playwright 的浏览器包在本机装不全**（镜像与官方 CDN 两次都只落 `chrome.dll`，`chrome.exe` 被丢，现象像杀软拦截新落地可执行文件），所以 e2e 实跑用 `E2E_BROWSER_CHANNEL=chrome` 走系统 Chrome；**不设这个变量就回到 Playwright 自带 chromium**，别把它写进默认值。
- **跑全量测试必须把 `TEMP`/`TMP` 指到工作区外的空目录**，否则 `tmp_path` 用例会以 `PermissionError`
  **假失败**；也**不要**用 `--basetemp` 指到工作区内（会产生谁都删不掉的毒目录）。
- Docker 数据盘与 WSL distro 本体都在 `D:\DockerData`；改它必须先 `docker desktop stop`（运行中改会被覆写）。
  **要挪盘趁项目小的时候挪**——Docker 是新建盘不是搬旧盘，挪完镜像全丢。
- ⚠️ **Milvus 不是"起起来就一直活着"**：实测约 25 分钟后因 etcd 磁盘停顿 FATAL 退出（C28）。
  **任何长时间跑 Milvus 的 real/e2e 证据都要中途复检容器还在不在。**
- 更细的坑（`psql` 表达式要带 `SELECT`、VHDX 不自动缩小、BuildKit 的 `# syntax` 行不走代理、
  `MSYS_NO_PATHCONV`、UTF-16 输出要 `iconv`、管道后取 `$?` 取到的是最后一个命令的 rc）见
  `WORKLOG.md` **附 B-1**；启动序列见 [`docs/plans/p0-environment.md`](docs/plans/p0-environment.md)。

## 6. 运行路径：容器只跑中间件，应用层源码跑

**2026-10-13 定案**：Docker 只用于中间件（数据库 / 队列 / 向量库 / 对象存储）；Go、Python、前端**一律源码运行**。

```bash
uv run python scripts/dev.py infra       # 只起中间件：postgres/redis/etcd/minio(versitygw)/milvus/attu
uv run python scripts/dev.py seed-admin  # 建/校管理员账号（口令只从 ADMIN_PASSWORD 环境变量取）
uv run python scripts/dev.py serve       # 宿主 uvicorn（ai-core；尚未搬走的路径由 Go 反代到此）
uv run python scripts/dev.py go-serve    # go-api（:8080，dev 单一入口；自动做 DATABASE_URL 归一化）
cd frontend && npm run dev               # vite（只监听 ::1，用 localhost 访问；/api 已代理到 :8080）
```

- 只起判据需要的最小集合：`dev.py up postgres redis` 比 `infra` 轻得多（见 §7 的进程纪律）。
- ⚠️ `attu` 的宿主端口是 **3001**（8080 让给 go-api，也是 X1 判据的落点）。
- `nginx` 的 `/api/` 已切到 `go-api`（X2 于第十七轮转 pass），但 **dev 形态下 nginx 不在请求路径上**：
  它属部署形态，实跑要起 prod compose（`go-api` 服务用 `server/Dockerfile` 构建）。
- ⚠️ 台账 **C29**（四处"应用服务容器化"遗留物）已于第十七轮**全部处置**：dev compose 的 `backend` 服务已删、
  `dev.py up` 现在等价于"起全部中间件"、`dev.py migrate` 改宿主跑 alembic、`server/Dockerfile` 转为被 prod 的
  `go-api` 服务使用，`check_nginx_routes.py` 的 R4 按形态分判并新增 **R5**（dev 不得出现应用服务）。
- **全新电脑的完整安装步骤**（依赖版本、五步命令、验收方法、起不来的三处排查）见 [README §3](README.md)。

## 7. 绝对不能做

- 不删 `parent_chunks` / `multimodal.py` / `layout_analyzer.py`（只降级能力口径，不删代码）。
- **不把应用服务塞进 dev 的 compose**（2026-10-13 定案，范围是 **dev**）：容器只跑中间件，
  Go / Python / 前端源码跑。想往 dev compose 里加 `go-api`/`go-worker`/`ai-core` 之前，
  先读台账 **C6**（原建议已作废）与 **C29**（遗留冲突项）。
  ⚠️ `docker-compose.prod.yml` 是**部署形态**、仍是全栈容器，本条不禁它。
- 不 `git mv backend → ai-core`；不引入 Kafka / RabbitMQ / Neo4j / 服务注册中心；不建两个全局调度器。
- **不把 mock 绿灯说成完成**：`status=done` 必须 `evidence ≥ requires`，由 `sync_progress.py --check` 强制。
  同理**不要在 P0 收口前开工 P1 的卡**（`08 §2` 阶段顺序律由同一条机检强制）。
- 不删 `docs/archive/` 里的归档件；不改 `docs/reference/00-audit.md`、`01-current-architecture.md` 里
  dated 的事实（它们是历史证据）。**不往本文追加 dated 内容**——日志进 `docs/WORKLOG.md`。
- 密钥只经环境变量，不提交 `.env` 与 `.env.production`；注释一律中文。
  管理员口令只从 `ADMIN_PASSWORD` 取，**不接受 CLI 参数**。
- **不要攒后台进程**（`08 §6`「后台进程」）：只起判据需要的最小集合，起之前先 `netstat`/`docker compose ps`
  盘点，验证一结束就停。⚠️ `TaskStop` 只杀外层 shell，**子进程可能活着占端口**（实测 vite 的子进程
  在 TaskStop 之后仍占着 5173，要 `taskkill /PID <pid> /T /F`），所以**每次收尾要复验端口**。
  遗留进程会占端口（本项目两次因 stale go-api 占 `:8080` 起服务失败），多起的容器会放大 etcd/Milvus
  的磁盘停顿（C28）。
- **不要为每次小改动重跑全量套件**（同一条纪律的 I/O 半边）：本仓库与 Docker 的 VHDX 在同一块物理盘上，
  改了哪个包就跑那个包；**全量 pytest 与 `npm run build` 在一个批次收尾时只跑一次**。
- **不要把新能力继续往大文件里叠**（`08 §6`「文件体积」）：新增一块默认落到**新文件/新包**，
  软上限 300 行、硬上限 500 行；拆的边界按 `08 §6` 指的分层口径走（Go `internal/<domain>`、
  Python `backend/<layer>/<module>`、前端 `10 §2` 五层——**一个板块一个组件**），不是"顺手分个 utils"。
  存量超标文件不追改，但**碰到就必须顺手拆**，且不许让它更长。
- **接管一条路由必须带上它原先的能力**：Python 那条被删掉之后，它的限流（C33）、缓存失效（C35）、
  探测键（X1 那一格）不会自动跟过来。**"Go 覆盖了这条路径"不等于"这条路径的能力没退化"**，
  而这类退化没有任何门禁会红——只能靠接管卡片把它列成验收项。
  **新接管一条面必须同时改 `contracts/route-ownership.md`**——这条现在有门禁会红了（第十七轮）。

## 8. 提交纪律

Conventional Commits（`fix(p0):` / `feat(dev):` / `chore(repo):` …）＋**每提交同更 `docs/progress.json`**
（并重跑生成物）＋ 门禁全绿。**按关注点分批**：代码 / 文档口径 / 进度收口各一个提交；
统一 push 前先 `git fetch`，确认 `git rev-list --left-right --count origin/main...HEAD` 是 `0 N`（快进）。

```bash
uv run python scripts/sync_progress.py --check
uv run python scripts/check_contracts.py
uv run python scripts/check_frontend.py
uv run python scripts/check_route_ownership.py  # 面归属 ↔ Go 注册 ↔ Python 路由 ↔ chain 用例
uv run python scripts/audit_schema.py --check-baseline
uv run python scripts/export_pbkdf2_golden.py --check
uv run python scripts/export_jwt_golden.py --check
uv run python -m pytest -q                  # 读数现场取，别抄文档
uv run python scripts/dev.py gen --check    # sqlc 生成物漂移门禁（改了 server/sql/queries 必跑）
cd server && gofmt -l . && go vet ./... && go test ./...
```

**`check_nginx_routes.py` 不在这份清单里**：它是 X2/Y4 的判据，在 nginx 切到 Go 之前必然红。
把一个阶段性的真实状态挂成提交门禁，结果只会是人人加 `|| true`，把判据废掉。
