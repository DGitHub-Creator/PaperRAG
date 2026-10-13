# AGENTS.md —— 给接手这个仓库的 agent

> 目的只有一个：**让下一个 agent 不必重新踩坑**。这里只写「现在是什么样、什么已被推翻、什么绝对不能做」。
> 项目愿景见 [docs/refactor/11-product-vision.md](docs/refactor/11-product-vision.md)，架构与阶段见 [docs/refactor/](docs/refactor/)，
> 进度真相**只有** [docs/progress.json](docs/progress.json)。

## 1. 项目一句话

**ResearchPilot**（原 PaperRAG）：面向研究者的 AI 科研工作台。
Go 是唯一公开入口与唯一全局调度；Python（`backend/`）只被动执行单次 `AIExecution`；
**PostgreSQL 是唯一业务真相**，Milvus 降为可重建索引。

## 2. 文档权威层级（冲突时按此优先级）

| 顺位 | 文件 | 性质 |
| --- | --- | --- |
| 1 | `docs/refactor/08-principles-and-conventions.md` | **最高约束**（四条原则、阶段顺序律、任务卡规范、进度同步律） |
| 2 | `docs/progress.json` | **进度唯一真相**；`PROGRESS.md` 与 `progress.html` 是它的生成物，改完必须重跑 `sync_progress.py` |
| 3 | `docs/refactor/09-milestone-p0.md`、`10-frontend-structure.md` | 当前阶段的任务卡与 X1–X8 退出标准 |
| 3.5 | `docs/refactor/11-product-vision.md`、`12-known-code-issues.md` | **产品轴（V1–V4）** 与**代码问题台账**；两轴映射见 11 §7 |
| 4 | `contracts/` | Go↔Python 契约；改契约改这里，`check_contracts.py` 机检 |
| 5 | `docs/refactor/00-audit.md`、`01-current-architecture.md` | **dated 事实**：描述历史审计基线，**不是现状** |
| 6 | `docs/archive/` | 归档件，**不作为实施依据**，正文逐字保留 |

## 3. 现在的事实（2026-10-12）

- 进度 **16%**（58/372 h）；38 张卡：done **8** / in_progress **3** / pending **27**；24 条退出标准 pass **5**（X3 契约机检、X5 Go 验旧密码哈希、**X6 基线迁移非破坏+幂等**、X7 测试分层、X8 进度同步）；**fail 2**（X2 nginx 还指向 Python、X4 只剩 chain 半侧）、**not_run 17**（X1 要 compose 全栈，其余属 P1/P2/P3）。
- **2026-10-12 第三轮把 C20 的环境重建做完了**，因此 **P0-0 与 P0-2 双双转 done（real）**：`.env` 重建、Docker 数据盘迁到 `D:\DockerData`、5/6 镜像就位、PG+Redis healthy、宿主 `alembic upgrade head` 建出 **10 表 / 59 列**（`column_diff` 仍是 23 条，与原审计一致）、`--live` 重导带 `columns` → **`--verify-columns` 从 exit 2 变成真正的逐列比对 exit 0**、两份迁移在真 PG **15.19** 上验过幂等（空库 0→10→10；存量形态两遍各 30 条 skipping、表数恒 10；`000002` 10→11→11、`ai_executions` 恰 17 列）。`probe_timestamps.py` + `timestamp-audit.md` 也落了（X6 第三问），`server/migrations/README.md` 补上（卡片列了它但文件一直不存在）。
- ⚠️ ~~仍卡着的一件事：minio 镜像在所有可用源上都取不到~~ **2026-10-13 已解开（D9 定案：换 versitygw，dev 与 prod 两份编排都换）**。定性很关键：**这不是网络问题**——MinIO 把开源 Server 归档了，`dl.min.io` 对**当前版与所有归档版**都返回 410 Gone（正文写明项目 archived / no longer maintained），Docker Hub 的公开镜像也没了，所以任何镜像源都给不出那个 pinned tag。三条路的实测结论：①代理拉原 tag = 死路；③自建同版本镜像技术上可行（GitHub Release 资产还在：二进制 103,395,480 字节 + 官方 `.shasum`，且 `api.github.com` 的 asset 端点能绕开被污染的 `github.com`），**但本机到该 CDN 持续只有约 30 KB/s，103 MB 要 30–90 分钟**，换来的是停止维护、没有安全更新的组件，已放弃；②**选它**：`versity/versitygw:v1.8.0`（Apache-2.0、2026-09 构建、仍在维护、posix 后端直接落挂载目录）。实测：`dev.py infra` 六容器全起、`milvus-standalone` **healthy**、宿主 `:9091/healthz` **200 OK**、**Milvus 自己通过 S3 API 建出了 `a-bucket`**。⚠️ 对象级往返**也已单独验证**（stdlib 现签 SigV4 打 `localhost:9000`：建桶 200 / PUT 200 / GET 200 且字节一致 / HEAD 200 / LIST 200 两个键都在 / DELETE 204；**把 secret 改错后同一个对象 403**，所以凭据真在生效，不是一句默认值）。但还有一条别说过头的边界：验的是**存储网关的 S3 语义**，不是 Milvus 的索引读写——`a-bucket` 至今是空的，Milvus 空闲时不写对象，**「上传→切片→向量入索引」那条真链路要等 P1**。
- ⚠️ X6 虽 pass，但它在 `09` 里列的第二条判据 `migrate -path migrations` **今天跑不了**——golang-migrate 从未接线（台账 C18 / 决策 D8）；且它「在**存量库**上幂等」那一问的**原对象已永久失去**（C20）：今天用的是「alembic 建出来的 10 表库」这一存量形态，**不是**当年那个 `create_all`+alembic 混合库，别把两者当成一回事。
- **P0-0 done（2026-10-12 第三轮，real）**：`doctor` 全绿 → `up` 起容器 healthy → `ps` → `logs` exit 0 → **`down` exit 0** → 再 `up` 回来数据完好（表数 10、alembic head 不变）。此前"未标 done"只差 `down`/`logs` 没逐个实跑，现已补齐。历史证据链：2026-10-10 那次 `up` 起 7 容器、backend healthy、`/health` 容器内与宿主机均 200、`migrate` exit 0——**`migrate` 子命令的实跑证据仍是那一次**，本轮建库走的是宿主 `alembic upgrade head`（`dev.py migrate` 是容器内 alembic，要构建 16.5 GB 的 backend 镜像，只为建库不值得）。
- **P0-2 done（2026-10-12 第三轮，real）**：交付件六项齐全——`audit_schema.py`、`schema-baseline.json`（**现在带 `columns` 段**）、`probe_timestamps.py`、`timestamp-audit.md`、`migrations/000001_baseline.{up,down}.sql`、**`migrations/README.md`**（这份卡片列了一直却不存在，本轮补上：编号表、up/down 规则、「新迁移必须同批登记 sqlc.yaml」、两条门禁的口径差别，以及「这里目前没有执行器」）。此前挂着的两件都解了：`--verify-columns` 现在对真快照逐列比（exit 0），时间列判定也产出了——并且**探针法实测证实了 `05 §4` 的断言**：会话时区 `Asia/Shanghai` 下 aware `datetime.now(UTC)` 写进 naive 列会落成 **+8 小时偏移**（07:08:09→15:08:09）。⚠️ 分布法与交叉法**没有存量数据可判**（重建库是空的，而带历史数据那个库已永久消失），报告里如实记 `no_data`，不是"等以后有数据"。
- **P0-3 done（2026-10-12，mock）**：sqlc 的 schema 源已从临时参照改指真基线，`server/sql/schema.sql` 已删除；此前 Go 只看得见 `users` 一张表，现在 10 张表 / 59 字段全部进 model。`dev.py gen` 同批加三条生成前置检查（schema 源是含 `.down.sql` 的目录 → 拒绝；`migrations/*.up.sql` 未登记 → 拒绝；生成物有孤儿 `X.sql.go` → 拒绝），各有负向用例。
- 测试基线 **572 passed**（unit 515 / integration 57；2026-10-12 第三轮复跑，其中 `test_probe_timestamps.py` 25 项是新增）；`chain` 与 `e2e` **各 0 条用例**，`-m chain` 收 0 项时 pytest 返回 **exit=5 而不是 0，不能算绿**。取数命令 `uv run python -m pytest -q` 与 `--collect-only -m unit`，**别手抄本行的数字**。
- **2026-10-12：P0-6 认证垂直切片推到 mock 级上限，X5 转 pass、X4 只剩 chain 半侧红**。产出 `server/internal/auth/{password,jwt,service,handler}.go` ＋ config 七个认证键与 `ValidateAuth()` fail-fast ＋ `cmd/api` 挂三条路由 ＋ `GetProfileByUsername`（`/me` 不碰 `password_hash`）＋ `scripts/export_jwt_golden.py` → `contracts/jwt_golden.json`（9 条）。`go test ./internal/auth/...` 50 项 PASS、`npm run typecheck` 0 error、全量 547 passed。**Go 侧照抄了 Python 的若干现状而不是"顺手改好"**（各有用例钉住）：register 会 strip 而 login 不 strip、密码长度按**码点**算、`role` 不做枚举校验（`role:"root"` 折叠成 user，见台账 C21）、用户不存在与密码错同一个 401、重名 409 先于邀请码 403、detail 文案**含中英文混用**且全部由生产侧 handler 现跑取数。
- **X2/X4 仍 fail，红点各不相同**：X2 红在 `/api/` 还指向 Python（P0-8）；X4 的 Go 半侧已全绿，红在 `pytest -m chain -k go_auth` 收 0 项、rc=5（chain 层容器 fixture 属 P0-5）。X5 已 pass，但**它 `real` 那一档仍开着**：`--from-db` 的真库形状统计（含"是否残留 bcrypt 族"）因原真库消失而无法执行（C20），Go 不实现 bcrypt，P1 接管 `users` 前必须先跑一次 `--from-db`。
- **两侧结论相反的轴要写进文件而不是藏进代码**：`contracts/jwt_golden.json` 有 `divergences` 段（缺 `exp` 的令牌 Python 收 / Go 拒；alg 白名单 Go 写死 HS256），负向量另带 `rejected_by` 区分"令牌层拒"与"回库拒"。这份文件**不能逐字节重建**（token 带 exp），所以它的 `--check` 是语义校验：把已提交的每条 token 重新交给生产裁判，并比对 claims 与结构性字段。
- **（沿革，2026-10-12 上一轮）X2/X4/X5 从 `not_run` 改为 `fail`**——判定命令当时变得**都可跑**（新建 `scripts/check_nginx_routes.py`＋`scripts/export_pbkdf2_golden.py`→`contracts/pbkdf2_golden.json`），跑出来是红的：X2 红在 `/api/` 还指向 Python（P0-8），X4/X5 红在 `server/internal/auth` 这个 Go 包不存在（P0-6）。已核实 `go test ./internal/auth/...` 与 `go test -run <不存在的测试>` 都 **exit 1 而不是 0**（不会"没测试也算过"）。⚠️ **本轮更正两条**：①**X5 已转 pass**（Go 包落地），X4 的红点移到 chain 半侧；②那句"不会没测试也算过"只对了一半——X5 的命令原文 `cd server && go test -run TestVerifyLegacyHash` 打的是 `server/` 根目录（无 Go 文件），**rc 恒为 1 与测试是否存在无关**，也就是说那条判据**永远不可能变绿**（台账 C22，已补包路径）。`sync_progress.py` 的机检（**in_progress/done 阶段**的退出命令引用的 `scripts/*.py` 必须存在）仍有效，未来阶段允许预留。
- **golden vectors 的"不含密码明文"落成了可机检的形式**：向量是合成口令的摘要，口令由 `vector_id` 按文件内 `password_rule` 重建（`password = "ResearchPilot golden vector " + vector_id`，UTF-8）；每条期望值都由**生产裁判** `backend/core/auth.py:verify_password` 现算，不一致就拒绝导出。真库 `password_hash` **有意不导出**（提交进仓库就是离线爆破机），`--from-db` 只取形状统计并检查覆盖面（含"库里还有 bcrypt 族 → Go 接管会把这批人锁死"）。
- **Docker 现状（2026-10-13 更新）**：引擎可用；**数据盘与 WSL distro 本体都在 `D:\DockerData`**（`settings-store.json` 的 `CustomWslDistroDir`），C: 上已无任何 `.vhdx`。**6/6 中间件镜像就位并 healthy**（postgres/redis/etcd/**versitygw**/milvus/attu）。来源逐个核过（`docker image inspect --format '{{json .RepoDigests}}'` 会留下原始 registry，**别凭印象**）：postgres/redis/milvus/attu 四张走 `docker.m.daocloud.io`，etcd 直连 `quay.io/coreos/etcd:v3.5.18`，versitygw 走 `docker.1ms.run`——都重打成 compose 期望的 tag。⚠️ versitygw 第一次是从 `latest` 拉的，随后按 `:v1.8.0` 重拉并核对 **digest 一致**（`sha256:30292fc2…`），容器启动横幅自报 `Version v1.8.0, BuildTime 2026-09-04T23:11:49Z`——**拉取时要带版本号的 tag，别拉 latest 再改名**。⚠️ 先前记的「11 个镜像 / 约 4.3 GB」「5/6 镜像 + minio 取不到」都已作废。
- **搬盘这件事的两个坑**：①`wsl --manage` 只有 `--set-sparse`，**不能搬家**，所以只能走 Docker Desktop 自己的设置（改 `CustomWslDistroDir` 要 `docker desktop stop` 后生效，运行中改会被覆写）；②Docker 是**新建盘而不是搬盘**——旧盘 5.91 GB 成了孤儿（已确认无引用后删除），而当时已拉好的 4.2 GB 镜像全部丢失需重拉。**要挪盘就趁早挪。**
- **上一条的后果（台账 C20，已解除）**：导出 `docs/refactor/schema-baseline.json` 的那个**原真库随数据卷消失、不可复原**，`.env` 也曾丢失。重建序列本轮已跑通并留下证据（见 P0-0/P0-2 两条）。
- **别把重建出的库当原库用**：`alembic upgrade head` 建的是**全新库**，拿它验 X6 的「在**存量库**上幂等」是自证。那一问的原对象已永久失去，只保留 2026-10-11「临时库法」的实跑记录作历史证据；本轮用「alembic 建出的 10 表库」当作存量形态重验了一遍幂等（结果通过），但**它不等于当年那个 `create_all`+alembic 混合库**。
- **流程教训**：real 级证据必须落成**仓库内的文件**（快照 / 实跑记录），只存在于容器卷里的证据等于没有证据——一次清空就抹掉了。
- **2026-10-12 拍板了迁移编号分配**（详见 `docs/refactor/05` §2.6）：`000001` 基线 / `000002` `ai_executions`（已落）/ `000003` `fix_drift` / `000004` `paper_chunks`；**条件性预留不占号**（如 `auth_compat`），避免拿着没用的号。新表一律 `TIMESTAMPTZ`；可空列做唯一键成员时必须 `NOT NULL DEFAULT ''`（PG 里 NULL 互不相等，唯一约束会静默失效）；实现没写到的列不预先建；`GRANT` 在角色定义之前不写。
- **`000002_ai_executions.{up,down}.sql` 已在真 PG 上执行过（2026-10-12 第三轮，此前从未跑过）**：17 列逐条回指 `backend/internal_api/executions.py:26-42` 的 dataclass（这张表的列清单**没有任何文档逐字写过**），已登记进 `server/sqlc.yaml` 并生成 `AiExecution`。真库幂等实测：临时库里连跑两遍 `10→11→11`、两次 exit 0、`ai_executions` 恰 **17 列**；down 一遍有效、第二遍退出 3（「禁止 `DROP TABLE IF EXISTS`」规则的预期后果，见 `server/migrations/README.md`）。**P0-7 距 done 只差 compose 里「ai-core 不发布宿主端口」那一步（P0-8）与 chain 级 `-k ai_executions`（P0-5）**——不缺迁移文件证据了。
- Go 骨架 `gofmt`/`go vet`/`go test` 全绿，但**尚未进 compose、未与 Python 联调**（P0-1 的 real 缺口）。
- **分支布局（2026-10-12 收口）：远端只剩 `main`，本地工作分支就是 `main`（跟踪 `origin/main`）**，
  旧的 `main-sync`（本地与远端）已删除。⚠️ 两条容易踩的：
  ①**本地 `main` 已被重置到重写后的历史**，重写前的 92 个提交只在 `backup/main-pre-rewrite-20261012`（tip `e6cc211`）——
  **那条备份分支与"把本地 main 挪回去"这两件事都碰不得**，后者会把已清除的个人信息/设备信息写回工作区；
  ②`backup/…` 是本地分支，没有远端副本，**不要 push 它**，也别删（它是那些重写前 SHA 唯一还能解析的地方，`gc` 前）。
  PR 入口形态：`https://github.com/DGitHub-Creator/ResearchPilot/pull/new/<分支名>`。
- **2026-10-11 做过一次历史重写**（把个人信息与设备信息从仓库历史里清除）：102 个提交的作者/提交者统一为
  `ResearchPilot Dev <DGitHub-Creator@users.noreply.github.com>`；用户名、本机绝对路径、OS 与软件版本号、
  本机代理、设备级 SSH 别名已从**文件内容与提交信息**中一并清除。**此前的提交 SHA 全部改变**——
  文档里的 SHA 引用**大部分**已按 `git filter-repo` 的 commit-map 修正，但 2026-10-12 逐条核reachable性时
  查出三类残留，处置如下（判据统一是 `git merge-base --is-ancestor <sha> HEAD`）：
  - **已改**：`03`/`07` 里引用的 `4a5e806` → 重写后的等价提交 `a552a5c`。
  - **故意不改**（`AGENTS.md` §7 的规则优先）：`00-audit.md` 里的 `c55129e`（审计基线声明"main @ c55129e"）
    与 `4a5e806`、`docs/archive/refactor-06-milestone-a0.md` 里的 `2c3e58e`——dated 事实与归档件正文逐字保留。
    前两处指向的是**重写前的对象**，它们在本地**只**可从 `backup/main-pre-rewrite-20261012` 解析
    （2026-10-12 分支收口后，本地 `main` 已重置到重写后的 `origin/main`，不再携带重写前的提交；
    此前这里写的"可从 `main` / `backup/…` 解析"只剩后半为真。等价重写后分别是 `6e8c1a9` / `a552a5c`），
    但 `gc` 之后会消失。**别为了找回它们把本地 main 挪回 `e6cc211`**——那 92 个提交携带已清除的
    个人信息与设备信息，checkout 它们会把那些内容写回工作区。
  - `2c3e58e` 另有一层：**它不是重写造成的**，是**笔误**。同一提交（A0-1"修复 apiFetch/BASE 未导入…typecheck
    纳入 CI 门禁"）在重写前是 `2c3e583`、重写后是 `996cf777`（同文件另一处引用的正是后者），
    末位 `e`↔`3` 一位之差。所以按 `--grep=<标题>` 定位即可，别去找回一个从来没存在过的对象。
  - 因此外部笔记/Issue 里更老的 SHA 一律按 "`git log --all --grep=<提交标题>` 重新定位" 处理，
    不要直接 `git show`。

## 4. ⚠️ 已被推翻的旧结论（**不要重复相信**）

| 旧结论（曾在 README / p0-environment.md / progress.json 里） | 现场核查后的事实 |
| --- | --- |
| 「本机缺一次重启才能用 Docker」「WSL2 可选组件装完待重启」 | **错**。真因是 Docker Desktop 没在运行；启动后 **5 秒**引擎即就绪 |
| 「本轮 Docker daemon 不可达，real 级补证排队」（`progress.json` 的 `current`、`09` P0-2/P0-7 的当前状态） | **已过期**。2026-10-12 二次核查 daemon 可达。但补证的前置**变重了而不是变轻了**：数据面被清空（0 镜像 / 0 卷），所以是「重建 `.env` + 拉镜像 + `alembic upgrade head` 建库」，不是「启动 Docker」（见 §3 与台账 C20） |
| 「P0-2 剩下两件事只要 Docker 起来就能跑」「原真库一直在容器卷里等着」 | **错，而且不可逆**。原真库随数据卷消失、本机也无原生 PG，**无法复原**。X6 的「在存量库上幂等」这一问永久失去原对象：只保留 2026-10-11「临时库法」的实跑记录作历史证据，**不拿重建出的全新库自证充数** |
| 「Docker Desktop 是 per-user 安装 / CLI 29.8.2 / Desktop 4.94」 | **这条更正本身是错的，得翻回来**：2026-10-12 实测安装路径是 `%LOCALAPPDATA%\Programs\DockerDesktop`，而 `C:\Program Files\Docker\Docker` **不存在** → **就是 per-user 安装**，原先被推翻的那个结论其实是对的。具体版本号仍按隐私约定不写进仓库（`wsl -l -v` 的输出是 UTF-16，Git Bash 里要先 `iconv` 才看得见，别把"输出像乱码"当成"命令失败"） |
| 「compose 不写 `name:` 无所谓，项目名只是个标签」 | **会有实质后果**。Compose 在没有顶层 `name:` 时**拿项目目录名**当项目名，而本机 clone 目录仍叫 `PaperRAG`（这是刻意保留的旧字面量，远端已改名 ResearchPilot）→ 容器标签 `com.docker.compose.project=paperrag`、自动创建的网络与具名卷都会带 `paperrag_` 前缀，而且**换个目录 clone 就换一个项目名**，「跨机器可复现」直接失效。两份 compose 文件已钉成 `name: researchpilot`（台账 C26） |
| 「镜像名带不带 paperrag 一看就知道，不用查」 | 实测澄清：镜像与容器名其实**都是对的**（`postgres:15` 等上游名 + `container_name: researchpilot-*` + backend 镜像 `researchpilot-backend`），唯一的 `paperrag` 来源就是上一条那个项目名。报"名字没改干净"之前先分清是**镜像/容器名**还是**compose 项目名** |
| 「只验骨架可跳过 LLM key」 | **错**。`app.py` 的 startup 无条件调 `validate_config()`，缺 `LLM_API_KEY`/`LLM_MODEL` 即 `RuntimeError` 拒绝启动 |
| 「测试基线 448 / 333 / 307 项」 | **都过期了**。现状 **572 passed**（2026-10-12 第三轮，46.8s；unit 515 / integration 57）。沿革：448 → 449 → 515 → 547 → 572，每次涨的都是新增判据用例。**读数一律 `uv run python -m pytest -q` 现场取，别抄任何文档里的数字** |
| 「`09` X6 有两条判定命令，`pass` 等于两条都跑过」 | **只跑过一条**。`cd server && migrate -path migrations -database $DATABASE_URL version` **今天无法执行**：PATH 上没有 `migrate`，`server/go.mod` 里没有 golang-migrate 依赖，`dev.py migrate` 实际是容器内 `alembic upgrade head`（`dev.py:257-259`）。`server/migrations/` 现在只有 `audit_schema.py` 与 sqlc 两个**离线读者**，没有执行器。X6 的 real 级幂等证据来自「临时库法」人工实跑。命令列已按 `progress.json` 更正，接线属 P0-8/P1（台账 C18） |
| 「文档里的数量/命令面是按机器现状写的」 | **不是**。2026-10-12 扫了一遍，全部已就地更正：`09` 的 unit 310/integration 23 → **458/57**、`dev.py` 命令面六项 → **10 个子命令**（漏 `infra`/`serve`/`gen`）、`audit_schema` 判定单测 19/34 → **37**、`07` 的 391 → 458 与 449 → 515、`08` 的 Python ≥ 3.11 → **≥ 3.12**（约束源是 `pyproject` 的 `requires-python`）、`05 §2.5` 的"第二个后续迁移" → **第三个**（`000002` 已被 `ai_executions` 占了）、`05 §3` 的 `000004_paper_chunks.sql` → **`.{up,down}.sql` 且必须同批登记 sqlc**。还修掉两处**互相矛盾**的记录：`p0-environment.md` §4 曾让人把 `TEMP`/`TMP` 指到**工作区内**，与 §5 的"必须指到工作区外、否则产生删不掉的毒目录"正相反——以 §5 为准 |
| `09` P0-7 的输入行点名 `backend/services/agent_runner.py` | **该文件不存在**（目录里只有 `agent.py`/`cache.py`/`conversation_storage.py`/`tools.py`/`upload_jobs.py`）。P0-7 真正接线的复用点是 `core/dependencies.py` 的 `get_document_loader`/`get_milvus_writer`（见 `internal_api/registry.py:13`），已按实引用改写 |
| 「X2/X5 有判定命令，所以它们是 not_run（等着跑）」 | **错**。那两条命令引用的 `scripts/check_nginx_routes.py`、`scripts/export_pbkdf2_golden.py` **当时根本不存在**，等于退出标准没有判据。2026-10-12 两个脚本落地，三条退出（X2/X4/X5）转 `fail` 并写明红在哪；`sync_progress.py` 同批加了"命令里引用的脚本必须存在"的机检 |
| 「`cp .env.example .env` 就能起」 | **旧模板会炸**：`KEY= #值` 的行内注释被 python-dotenv 当成真实值（`int('#1024')`），2026-10-10 已把 11 行改成整行注释 |
| 「compose 的 backend 开箱可用」 | **缺 `target: backend`**：Dockerfile 多阶段且末阶是 nginx，不写 target 会构建出 nginx 镜像 → 永远 unhealthy（已修） |
| 「旧名 PaperRAG 还留在 go module path / Redis 前缀 / Prometheus 指标名 / 契约 $id」 | 2026-10-10 全部改为 `researchpilot`；**唯一保留旧字面量的是安全黑名单**（`paperrag-admin-2026`，删了等于把泄露口令重新变成可用口令） |
| 「`progress.json` 说本机未安装 Docker Desktop」 | 已改为「已解除」，并把推翻过程写进 `risks[0]` |
| 「真库有 9 张表」（`05 §2.2`） | **错**。真库是 **10 张表**（含 `alembic_version`）；`alembic_version` 是否该进 Go 基线仍待拍 |
| 「`users.created_at` / `users.role` 在库里没有 DEFAULT」（`05 §4`、`server/sql/schema.sql`） | **错**。真库有 `DEFAULT now()` 与 `DEFAULT 'user'`（否则这两列会出现在 `column_diff` 里）。那份失真所在的 `server/sql/schema.sql` 已于 2026-10-12 随 schema 源切换**删除**，正确结论记在 `05 §4.2.1` |
| 「把这两列的失真核对进 sqlc 的 diff 就行」 | **做不到**。切换后 `User` struct 与三条查询的生成类型逐字未变——**sqlc 不把列默认值编码进 Go 类型**，`gen --check` 只能抓类型/可空性/列与表的存在性。DEFAULT 的机检是 `audit_schema.py --verify-columns`（2026-10-12 落，快照需带 `columns`） |
| 「本机没有 sqlc 二进制，要 `go install …@v1.30.0`」（P0-3 旧记录） | **错**。`$HOME/go/bin/sqlc.exe` 就是钉住的 v1.30.0，`dev.py gen` 本来就优先用本机二进制、找不到才退回 `go run`。过期工具记录会让下一个 agent 白装一遍 |
| 「schema 源整目录交给 sqlc 就行」 | **会静默出错**。sqlc 按文件名顺序把目录里每个 `.sql` 当 schema 执行，`000001_baseline.down.sql` 排在 `.up.sql` **前面** → 先 DROP 再 CREATE，生成物等于按回退后的库产出。必须逐个列 `*.up.sql`（`dev.py gen` 已机检这条，以及"新 up 文件没登记""生成物有孤儿"两条） |
| 「`--check-baseline` 通过 = 基线与真库一致」 | **仍错**。它只校验**文件形态**（up 非破坏 + 幂等、down 配对），**不比对内容**。内容比对是另一条命令 `--verify-columns`（2026-10-12 落地，需要快照带 `columns`）。同一版的 down 规则不剥注释、up 剥（注释里写 `DROP TABLE IF EXISTS` 会被误判）——**已修**，两边现在一致 |
| 「`schema-baseline.json` 里有列清单可直接抄」 | **错**。旧版 `--live` 的 payload 只有 tables/alembic/tz/server_version/indexes/constraints/column_diff，**没有 columns**，所以基线的 varchar 长度与 NOT NULL 长期无机检。2026-10-12 已给 payload 补上 `columns` 并加了 `--verify-columns`，但**仓库里现存那份快照仍是旧版导出的、没有列清单**——要等 Docker 起来重跑 `--live` 才真的比得上 |
| 「X5 的判定命令是 `cd server && go test -run TestVerifyLegacyHash`」 | **那条命令永远不可能绿**。`server/` 根目录没有 Go 文件 → `no Go files` → `FAIL [setup failed]` → **rc 恒为 1，与测试是否存在无关**。已补包路径 `./internal/auth/...`（台账 C22）。教训：C17 曾把"这条命令 rc=1"当成好消息（证明不会假绿）——那没错，但**同一事实还意味着判据不可能被满足**，当时只看到前半。凡是"今天必然红"的判据都要多问一句"它将来有没有可能绿"；**可复用的检查办法**：把判据要测的实现全删掉再跑一次，rc 不变就说明这条命令根本没在测它声称要测的东西 |
| 「Go 的 500 文案是 `Internal Server Error`」 | **与生产侧不一致**。`backend/core/exceptions.py:unhandled_error_handler` 是 `Internal server error`（小写 s）；大写那句是 Starlette **没注册** handler 时的纯文本兜底，而 `app.py:94` 注册了。已对齐（台账 C23）——同一个 Go 服务里出现两种 500 文案正是 `01 §6.3` 记的坑 |
| 「契约里 `RegisterRequest.role` 是 enum `[user, admin]`，Go 该按枚举校验」 | **会造出两侧分歧**。实现是 `role: str \| None`，实测 `role:"root"` 返回 **200** 并被折叠成 `user`；多余字段也是 200（pydantic 不 forbid extra）。裁判是运行中的系统，Go 照实现走（台账 C21）。`check_contracts.py` **抓不到这类偏差**——它不校验请求 schema 与 pydantic 模型是否一致 |
| 「`Authorization: Basic …` 的 401 是 `Invalid authentication credentials`」 | **错**。实测 `OAuth2PasswordBearer`：缺头与非 bearer 方案都回 `Not authenticated`（那句 `Invalid authentication credentials` 在 `HTTPBearer` 里，本项目没用）。另：`Authorization: Bearer`（后面不跟令牌）**能过** bearer 这一关，失败发生在后面的令牌校验。所以 Go 侧要复刻的每一句 detail 都应**用生产 handler 现跑取数**（`internal/auth/handler.go` 顶部那张八行实测表就是这么来的），别照源码读一遍凭印象写 |
| 「Go 依赖拉不动，P0-1 之后每张 Go 卡都开不了工」（`risks[1]`） | **可解，但本机 GOPROXY 一直没设**。2026-10-12 实测 `go env GOPROXY` 仍是默认的 `proxy.golang.org`（curl 12s 超时），按 §5 改成 `goproxy.cn` 后 **1.6s** 就拉到了 `golang-jwt/jwt/v5 v5.3.1`。所以那条风险的缓解措施是有效的，只是**没被执行过**；文档写的是"该这么做"，不是"已经这么做了"，别把它当成既成事实 |
| 「密码长度校验用 `len(password)` 就行」 | **Go 里会错**。生产侧是 Python 的 `len(str)` = **码点**数，Go 的 `len(string)` = **字节**数；含中文的口令在 Go 侧会被判得更严，同一个口令 Python 放行、Go 拒绝。用 `utf8.RuneCountInString`（已有用例钉住） |
| 「minio 镜像拉不到是网络问题，换镜像源或配代理就能解」 | **不是网络故障，是上游归档**。MinIO 把开源 Server 归档了：`dl.min.io` 对当前版与**所有归档版**返回 410 Gone，Docker Hub 的公开镜像也没了，所以 `minio/minio:RELEASE.2024-05-28T17-19-04Z` 在任何源上都给不出（daocloud `denied`、两个备用源 `not found`、quay 无该命名空间）。解法是**换 S3 实现**而不是换源：dev 与 prod 两份 compose 已换成 `versity/versitygw:v1.8.0`（Apache-2.0，服务名仍叫 `minio`，所以 Milvus 的 `MINIO_ADDRESS` 一字未改）。按"起不来就是 `dev.py` 有问题"去查会完全查错方向（台账 C24 / 决策 D9） |
| 「prod compose 里写了 `env_file: .env.production`，`${VAR:?}` 就能取到密钥」 | **不能**。service 级 `env_file:` 只注入**容器**环境，不参与 compose **顶层变量插值**，所以 `${POSTGRES_PASSWORD:?}` 与 `${MINIO_ACCESS_KEY:?}` 仍看宿主环境。实测（临时目录放一份 `.env.production` 再 `config`）：不带 `--env-file` → 三条 required 全报缺失、rc=1；`docker compose --env-file .env.production -f docker-compose.prod.yml config` → rc=0。所以 prod 的启动命令**必须**带 `--env-file`（已写进该文件头注释）。⚠️ 顺带查实 `.env.production` **不在 `.gitignore` 里**（只有 `.env` 在）——是个真实的泄密入口，已补 |

## 5. 本机环境要点

- **前置**：Docker Desktop 必须在运行；引擎没起来时 `docker info` 只报 pipe-not-found（不是缺组件）。
- `.env` **三个必填**：`JWT_SECRET_KEY`、`LLM_API_KEY`、`LLM_MODEL`（后两个连只验骨架也要有非空占位值）。⚠️ 本机 `.env` 曾在 2026-10-12 一度丢失（它从未入库）；已按 `.env.example` 重建，但**原值不可恢复**——新 `JWT_SECRET_KEY` 是重新生成的随机值，所以**旧 token 全部失效**（本机开发库无妨，生产换值前必须先备份）。`LLM_API_KEY`/`LLM_MODEL` 目前是**明确标注的占位值**，要真跑 LLM 得自己替换。⚠️ 另有一条 compose 的 `DATABASE_URL` 细节：`scripts/audit_schema.py --live` 与 `probe_timestamps.py` 都**直接读环境变量**，跑它们前要显式 export。
- 中国大陆：`go env -w GOPROXY=https://goproxy.cn,direct`（**2026-10-12 已在本机执行**；此前 `go env GOPROXY` 一直是默认的 `proxy.golang.org`，curl 12s 超时，改成 goproxy.cn 后 1.6s 就能拉依赖）；`docker.io` 被 DNS 污染 → 用镜像源或本机代理（本机代理 `本机代理端口`）。**实测可用的拉取配方（2026-10-13）**：三个能用的源是 `docker.m.daocloud.io`（postgres/redis/milvusdb-milvus/zilliz-attu）、`docker.1ms.run`（versity/versitygw）、`quay.io` 直连（coreos/etcd），拉完 `docker tag` 成 compose 期望的名字（`library/postgres:15` → `postgres:15`），**不动仓库文件也不动全局配置**；**要拉带版本号的 tag，别拉 `latest` 再改名**（本机第一次就这么拉的，随后按 `:v1.8.0` 重拉核对 digest 才确认内容）。判"这张镜像到底从哪来的"用 `docker image inspect --format '{{json .RepoDigests}}'`，它会留下原始 registry。⚠️ `minio/minio` 那个 pinned tag **不在"源不够好"的范围内——任何源都没有**（上游归档，见 §4 与台账 C24），compose 已换 `versity/versitygw`。
- **要挪 Docker 数据盘就往早挪，且只能走 Docker 自己的设置**：`docker desktop stop` → 在 `%APPDATA%\Docker\settings-store.json` 写 `"CustomWslDistroDir": "D:\\DockerData"` → `docker desktop start`（运行中改会被覆写；`wsl --manage` 只有 `--set-sparse`，**搬不了**）。本机已如此，注册表里 `docker-desktop` 的 `BasePath` 就是 `D:\DockerData`，distro 本体（`main\ext4.vhdx`）与数据盘（`disk\docker_data.vhdx`）都在 D:。⚠️ **Docker 是新建盘而不是搬旧盘**：挪完后镜像会全丢、旧 vhdx 变孤儿要确认后手动删（本机 C: 因此从 7.8 GB 回到 14 GB）。
- **BuildKit 取 `# syntax=docker/dockerfile:1` 不走 Docker Desktop 代理**：Docker Hub 不可达时必挂；先用 daemon 把 `docker/dockerfile:1`、`node:20-alpine`、`python:3.12-slim`、`nginx:alpine` 拉到本地即可。
- `scripts/audit_schema.py --live` **需要显式导出 `DATABASE_URL`**（脚本不读 config 的默认值），否则它会以为本机没有 PG。它连列清单一起导出（`columns`），配套的离线比对是 `--verify-columns`。**2026-10-12 第三轮已用重建库重导过**，快照现在带 `columns`（10 表 / 59 列），`--verify-columns` 因此从"拒跑 exit 2"变成真正的逐列比对 exit 0——快照缺 `columns` 时它如实返回 2 而不是假装比过，这个行为要保留。
- 验证基线迁移是否真的幂等，用「临时库」法（不碰真库）：`pg_dump --schema-only langchain_app | psql -d <临时库>` 复制结构，再把 `000001_baseline.up.sql` 连跑两遍，两次都应 exit 0 且表数不变。⚠️ `psql` 里 `extract(epoch from …)` 这类表达式**必须带 `SELECT`**（`probe_timestamps.py` 第一版就栽在这，报 `syntax error at or near "extract"`）；而要看列名**别凭印象猜**——本轮把 `chat_messages` 的分组键猜成了 `session_id`，实际是 `session_ref_id`，一跑就 `UndefinedColumn`。
- Docker 数据盘是 VHDX，**删数据不会自动缩小**；真正回收要压缩/稀疏化。
- 受限沙箱下：docker 的命名管道、uv 的缓存、git 写 `.git/index.lock` 都可能被拒。**跑全量测试必须把 `TEMP`/`TMP` 指到工作区外的空目录**（本机实测），否则 41–42 个 `tmp_path` 用例会以 `PermissionError: [WinError 5]` **假失败**（表现为 `407 passed, 42 errors`——**不是仓库缺陷**）；也**不要**用 `--basetemp` 指到工作区内的既有目录。这些临时目录会带上创建时的完整性标签，策略在 `workspace-write` 与 `danger-full-access` 之间切换后就可能变成**谁都删不掉的毒目录**（本机出现过 `.tmp-pytest`/`.pytest-bt`/`pytest-of-<用户名>`/`tmp*/`），只能靠更高权限运行或用户自有终端清理。
- 更细的坑见 `docs/refactor/p0-environment.md` §4。

## 6. 两条运行路径

```bash
# 日常开发（推荐）：只有中间件用 Docker，后端/前端跑源码 —— 不构建 16.5 GB 的 backend 镜像
uv run python scripts/dev.py infra     # postgres/redis/etcd/minio/milvus/attu
uv run python scripts/dev.py serve     # 宿主 uvicorn --reload
cd frontend && npm run dev             # vite（只监听 ::1，用 localhost 访问）

# 容器级验收（P0-8 / P0-9 才需要）：全栈容器
uv run python scripts/dev.py up
```

**全新电脑的完整安装步骤**（依赖版本要求、五步命令、跑起来后的验收方法、起不来的三处排查）见 [README §3](README.md)。

## 7. 绝对不能做

- 不删 `parent_chunks` / `multimodal.py` / `layout_analyzer.py`（只降级能力口径，不删代码）。
- 不 `git mv backend → ai-core`；不引入 Kafka / RabbitMQ / Neo4j / 服务注册中心；不建两个全局调度器。
- **不把 mock 绿灯说成完成**：`status=done` 必须 `evidence ≥ requires`，由 `sync_progress.py --check` 强制。
- 不删 `docs/archive/` 里的归档件；不改 `00-audit.md`/`01-current-architecture.md` 里 dated 的事实（它们是历史证据）。
- 密钥只经环境变量，不提交 `.env`；注释一律中文。

## 8. 提交纪律

Conventional Commits（`fix(p0):` / `feat(dev):` / `chore(repo):` …）＋**每提交同更 `docs/progress.json`**（并重跑生成物）＋ 门禁全绿：

```bash
uv run python scripts/sync_progress.py --check
uv run python scripts/check_contracts.py
uv run python scripts/check_frontend.py
uv run python scripts/audit_schema.py --check-baseline
uv run python scripts/export_pbkdf2_golden.py --check
uv run python scripts/export_jwt_golden.py --check
uv run python -m pytest -q            # 现状 547 passed（unit 490 / integration 57）
uv run python scripts/dev.py gen --check   # sqlc 生成物漂移门禁（改了 server/sql/queries 必跑）
cd server && gofmt -l . && go vet ./... && go test ./...
```

**`check_nginx_routes.py` 不在这份清单里**：它是 X2/Y4 的判据，今天必然红（`/api/` 还指向
Python）。把一个阶段性的真实状态挂成提交门禁，结果只会是人人加 `|| true`，把判据废掉。
