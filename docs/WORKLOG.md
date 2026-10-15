# WORKLOG —— 逐轮实录（append-only，倒序）

> **性质：日志，不是权威。** 这里记「哪一轮做了什么、拿到什么等级的证据、留下什么坑」。
> 内容冲突时：规约听 [`rules/08`](rules/08-principles-and-conventions.md)，进度听
> [`progress.json`](progress.json)，现状听 [`rules/13`](rules/13-frontend-backend-architecture.md)，
> 待办听 [`rules/12`](rules/12-known-code-issues.md) 台账。
>
> **为什么单独一份**（2026-10-15 用户明确要求）：`AGENTS.md` 只放愿景 / 规约 / 硬约束，
> `progress.json` 的 `current` 只放当前读数与下一步，任务卡的 `note` 只放卡片定义。
> 这三处从前都长成了日志——一个字段几万字、一张卡片 note 塞满实跑读数——结果是"规约"要翻很久才找得到，
> 而"日志"散在四个地方互相重复。日志一律进本文件。
>
> **轮转规则**：一个阶段（P0 / P1 / …）收口后，把该阶段的轮次移进 [`archive/`](archive/README.md)，
> 本文件只留当前阶段（与 `08 §6`「文件体积」同一条纪律：日志也会长，长了就轮转，不要无限追加）。
>
> **每条格式**：日期 + 一句话结论 → 做了什么 → 证据等级与读数 → 留下的坑 / 指针。
> 写的时候遵守 `08 §6`：只写**为什么**与**当时量到了什么**，不复述代码在做什么。

---

## 2026-10-15 · 第十八轮 —— 决策层重拍：D4 撤回前移建议，原则序位与九条禁止技术债入规

**一句话**：用户推翻了我上一轮建议的"P2-1/P2-2 前移"，定下**正确性 > 架构一致性 > 可测试性 > 功能完整度 > 开发速度**，
并把 D4/D5/D6、F-7、M16、C33–C37 一次性拍完；本轮**只改文档层与决策记录，零实现改动**。

- **拍了什么**：D4 = 保留 P1 → P2，不前移、不拆 `P2-1/P2-2` 成 `P1-9/P1-10`、不解锁依赖；
  D5 = 11 项提案全部登记 Backlog，**确认版本范围后才进正式分母**；D6 = 5 张未归属表**先审计使用情况**再一次性定归属与生命周期；
  F-7 = 保留真实依赖，**允许登记、不允许提前执行**；M16 = 不塞进 P3，列为后续独立阶段候选；
  C33–C37 = 全部落实到 P1，**不允许带着已知缺陷进入下一阶段**。
- **写了哪几处**：`rules/08` 加原则序位（§1 末）、§2 增补"不许解锁跨阶段依赖 + 不提前实现 ≠ 不提前设计"、
  新增 **§10 禁止的技术债**（九条禁止/应做对照 + 开发期数据可重置的前提）；
  `rules/11 §7` 把"最小解法建议"划掉并写明**撤回理由**（现在不是生产环境，不需为上线做阶段穿插）；
  `rules/14` 同步 M3/M8(F-7)/M16/§18 四处口径；`rules/12` 新增 **A-2**（C33–C37 的归属卡 + 可机检验收条件 + 不许怎么做）；
  `plans/04` 新增 **§4.4 设计门禁**（P1 接管卡开工前必须审查的五件事：数据标识/服务职责/错误语义/流式事件契约/数据所有权）；
  `AGENTS.md` §1/§4/§7 各加一条；`progress.json` 摘除 D4/D5/D6、P1 的 `not_doing` 补一条、`current` 改成新的开工安排。
- **证据等级**：mock（纯文档与决策记录）。门禁：`sync_progress --check` / `check_contracts` / `check_frontend` /
  `check_route_ownership` / `check_nginx_routes` 全绿。
- **我撤回的东西**：第十七轮我给的建议表（波次 0–7、"先做 M3 再回头做 P1 门面"）与"D4 前移"倾向**全部作废**。
  作废的理由值得留着：那条建议会让 P2 的存储方案以"先做一半"的形态进 P1，正是本轮新立 §10 禁止的那一类临时实现；
  而它换来的只是产品轴提前一到两个波次可见，在开发阶段这不是优先项。
- **留下两件待拍**：①设计门禁要不要成为正式退出标准 `Y7`（会把全阶段分母从 25 条变 26 条）——本轮按"门禁"执行、**不擅自改分母**；
  ②**D3 与 D4 是同一条冲突的另一半**（"chunk 可信化移到 P2 且接受 P1 引用为非证据级"）——用户这次没点名 D3，
  但它已被 D4 定案隐含回答，仍挂在待决里会误导后来人，需要确认是否一并闭掉。

## 2026-10-15 · 第十七轮 —— P0 收口：X2 转 pass、四条卡 done、分工口径落进机检

**一句话**：把 P0 剩下的四张卡（P0-6/P0-7/P0-8/P0-9）与唯一一条 fail（X2）一起收掉，
顺带把「前端 / Go / Python 谁做什么」从四段散文变成一个可执行脚本 + 一张归属表。

- **用户拍的四个决定**（动手前对齐，不是事后追认）：X2 的拓扑选 **①Go 进 prod compose**
  （结论：不是 Go 的特性也不是 nginx 的限制，而是 `check_nginx_routes.py` 的 `resolve()` 把 `go-api`
  当**主机名**认——真正约束只是"nginx 要能解析出一个叫 go-api 的主机"）；D8 = **dev.py 显式 migrate 命令**
  （不进启动路径）；P0-7 证据档 = 多加一次真 LLM 成功执行；P0-9 = 装 Playwright 跑结构级 e2e。
- **X2 与 C29（P0-8）**：`nginx/nginx.conf` 的 `/api/`、`/api/v1/ws/`、`= /health`、`= /ready` 全切
  `upstream go-api`，保留 `backend` upstream 作为 04 §5 要求的**一行回退**；prod compose 加 `go-api` 服务
  （用 `server/Dockerfile` 构建、不发布宿主端口）；dev compose 的 `backend` 服务**删除**；
  `dev.py migrate` 从"容器内 alembic"改为宿主跑；`check_nginx_routes.py` 的 R4 改为**按形态分判**并新增
  **R5**（dev compose 不得出现应用服务）——那条定案从前只是 `AGENTS.md §7` 的一句话，现在有门禁。
  判据实测 rc=0，单测 42 项（每条规则一正一篡改）。**X2 的 level 永久 e2e**：本机没起过 prod 全栈
  （要构建 16.5 GB 的 backend 镜像，而它与仓库在同一块盘上），所以这条 pass 的证据是**静态配置级**。
- **D8 落地**：新 `server/cmd/migrate`（golang-migrate 库）+ `dev.py migrate-go`。真库连跑两遍 `up` 均 rc=0、
  `version: 3 clean`，库里 13 张基础表 = 12 张建表 + `schema_migrations`，`ai_executions` **第一次真实存在**。
  两个连接串坑是照生产侧现状写的：`.env` 里的 `DATABASE_URL` 是 SQLAlchemy 的 `postgresql+psycopg2://`，
  直接交给驱动报的是看不出根因的 "unknown scheme"，所以命令内归一；没写 `sslmode` 就补 `disable`，
  否则 lib/pq 默认 `require` 会以 x509 失败。X6 的「版本与设计一致」这一问从此有命令可跑（C18 处置）。
- **P0-7 的 real 档**：`tests/chain/test_ai_executions.py` 12 项，成功路径是**真解析器读真 PDF**
  （集成层用的 `b"%PDF-1.4 fake"` 在桩 loader 下够用，落到真 loader 就 PARSE_FAILED，"成功路径"就永远升不到 real）。
  ⚠️ **推翻我自己给用户的一个前提**：用户批准"再加一次真 LLM 成功执行"，但 P0 注册的两个类型
  （`PARSE_PAPER`/`INDEX_PAPER`）**都不调 LLM**（实测 `usage.calls=0`），所以那一档在 P0-7 的范围内**够不着**，
  不是我省略了。LLM 调用随 P1 的 LLM 任务类型落地。
- **查出的两条新事实**（都进了台账）：**C37** `ai_executions` 表已落库但 `ExecutionStore` 是进程内 dict、
  **零写入方**——表与实现脱节，和 C30 同形；**C36** `register` 面 Go 已接管但两侧从未对拍（chain 的种子直接写 PG），
  Python 那条还活着，删除前没有一致性基线。
- **分工变成机检**：新 `contracts/route-ownership.md`（37 行：方法 × 路径 × 归属 ∈ `go`/`shared`/`proxy`/`internal`
  × `Python 仍在`）+ `scripts/check_route_ownership.py`，回查三个真相源（Go 源码路由注册、`backend.app` 实际路由表、
  `tests/chain` 用例名）。它第一次跑就抓到两类东西：①归属为 `go` 却仍被 Python 服务的**五条面**——
  第十四轮定的"接管即删"实际没删，因为 chain 的逐字对拍需要两侧在场，这是**有意保留**但没人写过；
  ②我自己在表里写的"对拍保留"有两条其实**没有用例**（`register`），于是脚本要求例外要么指到
  `tests/chain/<文件>.py::<用例名>`，要么登记成欠账。按路径字面量 grep 判不准（删除面在测试里写成
  `LIST_PATH + 具体 id`），会误判成没测过——所以登记到**用例名**，这是确定性的。
  另一处真实缺口顺带修掉：**`dev.py serve` 默认绑 `0.0.0.0`**，而 P0-7 要求源码形态下 ai-core 只绑回环
  （Go 反代本来就走 `127.0.0.1`，绑 `0.0.0.0` 只是把 `/internal/v1/ai/*` 暴露到局域网）。已改默认值并由单测钉住。
- **P0-9**：`frontend/e2e/p0-auth.spec.ts` 9 项结构级 + `playwright.config.ts` + `npm run test:e2e` + `docs/plans/p0-demo.md`。
  三条踩坑值得单独记：①**spec 不能放 `tests/e2e/`**——Node 从仓库根往上找不到 `node_modules`，
  `import '@playwright/test'` 直接解析失败，工具链在哪棵树 spec 就得在哪；②**Playwright 每条用例一个新 context**，
  localStorage 的 token 不跨用例，按"注册一次后面复用"写会让后面的用例全停在 `/login`，
  而失败表象像"选择器错了"（第一版就是这么红的）；③**本机 chromium 包两次都只解出 `chrome.dll`**
  （镜像与官方 CDN 都一样，现象像杀软拦新落地的可执行文件），所以实跑用 `E2E_BROWSER_CHANNEL=chrome`，
  不设该变量仍回默认 chromium——这是**本机环境事实**，不写进默认值。
  另外 `/settings` 上有**两个**"退出登录"（rail 图标只有 title、账号板块是文字按钮），按名字点会撞 strict mode。
- **chain 红过的 7 条不是仓库缺陷**：`dev.py serve` 带 `--reload` 时，集成用例往 `backend/data/documents/` 写文件
  会触发热重载打断真栈，新的 chain 文件恰好排在集成层之后。带 reload 全量 7 条红，`--no-reload` 全量 **644 passed**。
  **证据跑必须 `--no-reload`**，这条写进 `AGENTS.md §5` 与 `p0-environment §2.1`。
- **读数（现场取）**：全量 644 passed = unit 527 / integration 57 / chain 27 / pytest-e2e 0；Playwright 9 项；
  `-m chain` 27 collected；`dev.py` 13 个子命令；prod compose 8 个服务、dev compose 6 个（全是中间件）；
  完成度 30%（118/394 h），X1–X8 全 pass。
- **门禁**：`sync_progress --check` / `check_contracts` / `check_frontend` / `check_route_ownership` /
  `audit_schema --check-baseline` / 两份 golden `--check` / `dev.py gen --check` / `gofmt` + `go vet` + `go test ./...` 全绿。
- **留下的坑与指针**：`/metrics` 仍是三不管（归属表里登记为 `proxy`，Go 未实现）；dev 里 Go 反代 Python 的 WS
  在页面关闭时报 `ECONNRESET` 噪声（vite 侧打印，不影响用例），P1-4 接管流式时一并看；
  D6（那 5 张库里存在但未登记归属的表）与 C34/C35 仍待拍/待处置，都属 P1。

## 2026-10-15 · 文档层重构


**一句话**：把散在四处的日志收进本文件，`AGENTS.md` 瘦回"愿景 + 规约 + 硬约束"，并按当前进度同步全项目 docs。

- **做了什么**：新建本文件；`AGENTS.md` §3 的十几条"第 N 轮"巨型 bullet 与 §4 的长论证搬来这里，
  正文只留结论一行 + 指针；`progress.json` 的 `current` 从几万字瘦成"当前读数 + 下一步 + 指针"；
  `plans/09` 每张卡的 `note` 只留卡片定义（输入 / 输出 / 判据 / 依赖 / 一句话状态）；
  `rules/12` 台账的超长证据格压成"结论 + 取数命令 + 本文件指针"。
- **同批同步的陈旧读数**（全部现场取数，不抄旧值）：全量 **599 passed** = unit 527 / integration 57 /
  chain 15 / e2e 0；契约 **21 个操作**；前端 **60 个源文件**；迁移 **3 份 up / 12 张建表**；
  sqlc **10 条查询**（`users` 6 / `user_preferences` 2 / `chat_sessions` 2）；`dev.py` **12 个子命令**；
  Go 原生路由 **8 条业务 + 4 条探针**；卡片 **40 张**（done 10 / in_progress 3 / pending 27）、
  **72/394 h = 18.3%**；退出标准 **25 条：pass 7 / fail 1（X2）/ not_run 17**。
- **证据等级**：mock（纯文档，零实现改动）。门禁：`sync_progress.py --check` / `check_contracts.py` /
  `check_frontend.py` 全绿。
- **留下的坑**：`rules/13` 是"As-Is 实测 + 每条带 `file:line`"，本轮只更新了被这几轮改动**直接推翻**的部分
  （Go 路由清单、`/ready` 探测键、契约操作数、sessions 归属），**没有重做全量复核**——它其余断言的时效性
  要等下一次专门核对。

---

## 2026-10-14 · 第十五轮 —— X1 转 pass：Go 的 `/ready` 补上 Redis 探测

**一句话**：X1 的 expect 点名"PG/Redis 依赖探活通过"，而 Go 从前只注册了 `database` 一个 Check，
Redis 那一格**无物可判**——补上之后 X1 转 pass（real），P0-1 随之 done（real）。

- **做了什么**：`server/internal/httpapi/redischeck.go` 手写一次 RESP PING（**没引 go-redis**：一个探针
  不值得多一条依赖与供应链面，而且它不带连接池、不带重试、不带后台 goroutine，不会因为 `/ready`
  被反复打而拖住进程）；`internal/config` 加 `REDIS_URL`（与 Python 同键同默认值）；`cmd/api` 现在注册
  `database` + `redis` 两个探测键。三处口径是照抄生产侧的：键名、成功 detail `connected`、
  失败 detail `disconnected: …`。**AUTH 先于 PING**——带口令的 Redis 上裸 PING 会被 `-NOAUTH` 打回，
  那就成了"Go 报 error / Python 报 ok"的假分歧。失败文案只带回首条单词，因为 detail 会进日志与公开响应。
- **证据等级 real**：`curl :8080/api/v1/ready` → 200，`checks` 里 `database` 与 `redis` 都是 ok /
  `connected`；`/api/v1/health` → 200。Go 侧 15 项单测用真 TCP 假服务端跑，其中最要紧的一条是
  **"对面 accept 但不回话时探针必须按时撒手"**（那才是健康检查最容易失效的方式）。
  chain 侧新增 `test_go_readiness_probes_exactly_what_x1_names`。`-m chain` **15 项全绿**、
  全量 **599 passed**。
- **⚠️ 口径要说准，别当成跑过全栈**：X1 的判据命令写的是 `dev.py infra`（六容器），我按 expect 实际点名的
  依赖收窄成了 `up postgres redis`——expect 只说 PG/Redis，Milvus 与对象存储不参与这两条探针的判定。
  同日早前那次六容器全 healthy 的实跑仍成立（那次 Python 的 `/ready` 三键全 ok），但**本条 pass 的直接
  依据是两容器形态**。
- **由此定下的一条写判据的规矩**：Python 的 `/ready` 在 Milvus 不起时是 503，所以 chain 的探针用例
  **不断言状态码**、只断言两侧共有键的说法一致——把环境事实写进判据就会得到一个偶发红。
- **P0-1 转 done（real）**：它的 real 缺口是"未进 compose、未与 Python 联调"，前者被 2026-10-13 的定案
  取消，后者已由 chain 层 15 项用例取证。⚠️ 边界：`go-worker` 只验到"进程能起 + 暴露探针"
  （`cmd/worker/main.go:52` 自陈 `worker_idle`），调度器属 P3。
- **留下的坑**：Go 侧仍**没有限流层**（台账 C33），X1 这个缺口与它是同一形状——接管一条面就顺手丢掉
  原面上的一项能力，而且没有任何门禁会因此变红。

---

## 2026-10-14 · 第十四轮 —— Go 接管第一条业务读接口（`/sessions` 列表与删除）

**一句话**：`GET /api/v1/sessions` 与 `DELETE /api/v1/sessions/{session_id}` 从此是 Go 原生，
判据是 chain 级的**逐字对拍**：同一份真库、同一个令牌，Go 与 Python 的 JSON 完全相同。

- **做了什么**：新包 `server/internal/session`（`session.go` + `handler.go`）＋ `sql/queries/chat_sessions.sql`
  两条查询 ＋ `cmd/api` 的 `mountSessionRoutes`。身份解析复用 `internal/auth` 新导出的
  `RequireIdentity`（两段 401 的文案不同是生产侧现状，收成一个函数而不是每个 handler 抄一遍）。
  共享的两句对外文案（`Internal server error` / `Not authenticated`）上移到 `httpapi`，
  避免同一个服务里长出两种 500 文案（那是 C23 记过的坑）。
- **两处最容易漂的形状专门钉住**：①naive `TIMESTAMP` 的 `isoformat()`——带微秒给 6 位、微秒为 0 整段省略、
  **绝不带时区后缀**，所以不能用 `time.RFC3339Nano`（它把非零纳秒输出成 1–9 位可变长度）；
  ②**空结果必须是 `[]` 不是 `null`**（Go 的 nil 切片会编成 `null`，前端 `.map()` 直接炸）。
- **证据等级 real**：`pytest -m chain -k go_read` 收 **6 项全绿**（P1-1 的判据选择器）。另有：越权删除与
  "不存在"回**同一句** 404（不给归属探测留缝）、消息行确实由基线里那条 `ON DELETE CASCADE` 带走、
  重复删除算 404 不算成功。Go 侧 15 项单测。
- **一处有意分歧**（已写进代码注释与台账）：Python 把存储层异常吞成空列表
  （`conversation_storage.py:170`），Go 如实回 500——"读不出来"伪装成"你没有会话"会让用户去重建会话。
- **⚠️ 三条后续各卡一道前置，别顺手做**：
  ① `GET /sessions/{id}`（消息）卡在 `rag_trace` 是 **pydantic 投影而非透传**（见下一轮之前的现跑实测，
     台账 **C34**）；
  ② `/documents` 卡在文档真相不在 PG，而且列表还依赖 Milvus 取 chunk 数（停掉 Milvus 后实测直接 500）；
  ③ **Go 的删除不失效 Python 的 Redis 会话缓存**，所以"删完仍能从 Python 读到旧消息"的脏读窗口
     今天是真实的（台账 **C35**）。chain 用例里**刻意没断言**这一半，免得把已知缺口写成偶发红。
- **用户拍板**：「后端成型」走最大档（推到 Python 只剩内部面）、被接管的 Python 路由**直接删**、
  验收取 chain 级真容器 + 真 PG。同批拍了**「先收 P0，再开 P1」**——把 `/sessions` 落 Go 之后想标
  P1-1 `in_progress`，被 `sync_progress.py --check` 拦下（阶段顺序律），所以证据记在 P0-8。

---

## 2026-10-14 · 第十三轮 —— chain 容器 fixture 落地（P0-5 done、X4 转 pass），顺带抓出 C32

**一句话**：chain 层第一次真跑，补上了 X4 缺的那一向（Go 签发 → Python 校验），
并且**当场抓出一个生产缺陷**：五条 Python 面对任何合法请求都回 500。

- **做了什么**：`tests/chain/` 四件（`_runtime.py` / `conftest.py` / `test_go_auth_cross_validation.py` /
  `test_contract_chain.py`）＋ `tests/unit/test_chain_runtime.py`。用例覆盖：Go 签发 → Python 校验、
  Python 签发 → Go 校验、伪造 secret 两侧都 401、改库里的 `role` 之后两侧都读到新值（钉住
  `ParseAccessToken` 连 role 都不返回那个决定）、login / me / 错误文案的跨语言逐字对拍。
- **"不伪装通过"落成三档可证伪的实现**：①`preflight_action(markexpr)`——显式 `-m chain` 时起不来就**红**，
  被全量收集路过才 skip（否则"全绿"可以是"一个都没跑"，X4 从前正是这么红的）；②种子**直接写 PG**，
  不用被测面铺数据（否则接口坏了会以"铺数据失败"的形态报错）；③静态门禁带 `checked >= 5` 兜"检查自己失效"。
- **C32（已修，real）**：slowapi 要求被 `@limiter.limit` 装饰的端点同时有 `request: Request` 与
  `response: Response` 两个**按名字**注入的形参，而 `backend/api/auth.py`（register/login/refresh）与
  `chat.py`（chat/chat-stream）里 `request` 是 pydantic 请求体、`response` **从来没声明过** →
  **五条面对任何合法请求都回 500**。它是分两层露出来的：改完 `request` 的名，接着报
  `parameter 'response' must be an instance of starlette.responses.Response`。
  修完用管理员账号现跑复核：Python 侧 200 且 `X-RateLimit-Limit` 头在（限流真的生效且可观察）。
- **三条方法论比缺陷本身值钱**：①**用无效 body 的用例覆盖不到限流路径**——
  `tests/integration/test_error_envelope.py:25` 打 login 用的是 `json={}` 与 `{"username":1}`，
  都在 pydantic 校验阶段就 422 返回、压根不执行 wrapper，所以"572 项全绿"与"真实登录 500"可以同时成立；
  ②**门面会掩盖上游坏死**——dev 的登录自第十轮起走 Go 原生面，Python 那条从此没人打，
  "前端能用"不构成"后端没坏"的证据；③凡是**按名字注入**的框架约定都要静态检查，别靠发请求
  → 落成 `tests/unit/test_rate_limit_signatures.py`。
- **同批新记 C33**：Go 侧一条限流都没有（实测 python 200 + 头在 / go 200 + 头不在），而本轮定的处置方式是
  "接管一条就删 Python 那条"——**每接管一条路由就静默丢掉它的限流**，登录/注册这两个最该限流的面其实已经丢了。
- **读数**：`-m chain` 9 项（本轮）→ 全量 **593 passed**；X4 转 pass，X1 从 `not_run` 改成有明确红点的 `fail`。
- **环境事实**：这一轮 `dev.py infra` 六容器全 healthy（**Milvus 这次也起来了**，Python 的 `/ready`
  三键全 ok）；但它随后又自己挂了（C28 复现一次）。

---

## 2026-10-14 · 第十二轮 —— 设置页重做 + 站内提示/确认 + 暗色主题 + 页宽统一

**一句话**：前端消费上一轮的 Go 自助面，设置页从"文档管理"单页变成用户设置四板块。

- **做了什么**：①设置页四板块——账号信息（含退出登录）/ 外观·主题（light/dark/system）/
  偏好设置（`start_view` 下拉，选项从 `NAV_GROUPS` 生成，不新起一份路由清单）/ 修改密码
  （只做非空 + 两次一致，**强度规则留给后端**，两处各写一份必然漂移）；
  **管理员在页尾多一块「知识库管理」**，原上传与文档列表 HTML 逐字保留——因为
  `backend/api/documents.py` 每个端点都是 `Depends(require_admin)`，不能把这页挪成全用户可见。
  ②站点级 `alert`/`confirm` **全站退役**，换成 `useToast`/`useConfirm`（状态层）+ `ToastHost`/`ConfirmHost`
  （DOM），`utils/dialog.ts` 仍是唯一接缝（它 import 两个 composable，是 `10 §2` 里只开给接缝文件的
  两处叶子层例外之一）。③暗色主题靠 `variables.css` 的 `[data-theme="dark"]` 令牌块（含 `.hljs` 调色），
  `document.documentElement.dataset.theme` 只在 `utils/theme.ts` 里写（R3 禁 composable 碰 DOM）。
  ④页宽统一 **1280px**：删掉 `.page-inner.wide`，10 个视图的 `wide` 类一并去掉。
- **两个口径**：`system` 主题用 `matchMedia` **解析一次、不监听变化**（"用户手动选的这一次"与
  "操作系统后来变了"该给出不同结果）；`start_view` **只在登录后跳、刷新不跳**（否则 F5 会把人从当前页拽走）。
- **证据等级 mock/real 混合，要如实说**：改密码、偏好读写、主题切换、提示/确认框**真跑过**（真库 + 真浏览器）；
  但「知识库管理」块**只验到错误路径**（Go 把 `/api/*` 反代到未启动的 Python → 红 toast「上游服务不可用」），
  上传/删除的成功路径本轮没重跑，那属 P0-9 的 X7。
- **读数**：`check_frontend.py`（当时 55 源文件）/ `check_contracts.py`（21 操作）/ `sync_progress.py --check` /
  全量 **572 passed**，`npm run typecheck` 0 error。

---

## 2026-10-14 · 第十一轮 —— 两条 Go 原生自助面（改密码 + 用户偏好）

**一句话**：Go 从"只认 register/login/me"扩到账号自助面，并为此建了 `user_preferences` 表。

- **做了什么**：`POST /api/v1/auth/password` 与 `GET|PUT /api/v1/me/preferences`
  （实现落 `internal/auth/{service,handler,preferences}.go`）＋迁移 `000003_user_preferences`
  （TIMESTAMPTZ 且不给库侧 DEFAULT、`theme` 有 CHECK 闭集、FK 到 users ON DELETE CASCADE），
  同批登记 `sqlc.yaml` 并重生成 `db.UserPreference`；契约 +3 操作 +2 schema（18 → 21），
  `table-acl.md` +1 行（go=W / python=X），`frontend/src/api/{client,types}.ts` +3 函数 +3 类型。
- **为什么这是"新面"而不是"复刻"**：As-Is 的 Python 侧**没有**这两个端点，所以没有裁判可对齐，
  判据只能是 Go 自己的不变量——四条都写进了注释与单测：①**旧口令错回 400 而不是 401**
  （前端把 401 当会话过期收尾、会把人踢回登录页，而打错旧口令不该有那个后果）；②新口令走与 register
  同一套规则（**码点**长度 + 至少两类 ASCII 字符）且**不 strip**（口令是不透明串，静默去空格等于替用户改密码）；
  ③`theme` 是三态闭集、**三处同值**（迁移 CHECK / Go 常量 / 契约 enum），`start_view` **只校验形状**
  （`^[a-z][a-z0-9_-]{0,31}$`）——刻意不把前端路由表抄进 Go，抄了必随产品增长而漂；
  ④**库里没有偏好行时回默认值而不是 404**（"还没设置"与"设置读不出来"是两回事）。
- **证据等级 real**：`user_preferences` 在 dev 库上连跑两遍 `up.sql`（第二遍 `skipping`、rc=0、
  表数 10→11→11）；`login → PUT(dark/library) → GET → 落库` 往返一致、时间列落 `+00`（UTC）、
  upsert 二次不覆盖 `created_at`；非法 theme / 非法 slug / 缺字段 / 无 token 四条错误路径实测
  400/400/400/401 且文案逐字符合预期；改密码在一次性用户 `pwtester` 上验完（新口令可登、旧口令 401、
  旧口令打错 400、弱新口令 400、无 token 401）后**清理测试行**。
- **留下的坑**：`ai_executions`（`000002`）**至今没在任何长期库上建过**，dev 库距 12 张表齐还差它（属 P0-7）。

---

## 2026-10-14 · 第十轮 —— dev 单一入口打通 + 管理员账号就位

**一句话**：Go 成了 dev 形态下的唯一公开入口（靠反代），并且有了可用的管理员账号。

- **做了什么**：①`server/internal/httpapi/upstream.go`（`httputil` 反代）+ `cmd/api` 读 `PYTHON_UPSTREAM`
  （默认 `http://127.0.0.1:8000`），把**尚未迁移的路径**（`/api/*`、`/internal/*`、`/ws/*`、`/metrics`）
  透明转发给源码跑的 Python；`vite.config.js` 的 `/api` 代理从 `:8000` 改指 `:8080`。
  这是 `14 §19` 铁律 2「门面先于重写」的落地——**搬一条路由就少转发一条**，Go 不必等 Python 全搬完。
  新增 4 条 Go 单测钉住"转发不改路径/不动 query、原生路由不被反代遮蔽、上游不可达回 502 信封、
  无上游时 404 仍是 JSON 信封"。②`attu` 宿主端口 `8080`→`3001`（8080 归 go-api，也是 X1 判据落点）——
  此前 Go 从没在 dev 起过，冲突一直没暴露。③`server/cmd/seed` + `dev.py seed-admin`：口令**只从
  `ADMIN_PASSWORD` 环境变量取**（不接受 CLI 参数），`ADMIN_RESET_PASSWORD=1` 才重置；
  `sql/queries/users.sql` 补 `UpdateUserPasswordByUsername` / `UpdateUserRoleByUsername`。
- **证据等级 real（本轮唯一）**：六中间件起来后宿主源码起 go-api，`/api/v1/health` 与 `/ready` 各 **200**
  （ready 的 PG 探活真连上库），`register`（带邀请码）建出 `role=user`、`login` 用 `admin` 拿回真实 JWT、
  `/auth/me` 回 `{username, role}`，一条未迁移路径经反代打到上游 200。
- **⚠️ 边界**：那次上游是**仓库外一次性 stub**（不是 `dev.py serve` 起的真 ai-core），所以 X1 当时仍不判 pass；
  `nginx` 未切 Go（属 P0-8）。
- 前端同批移除登录页那句把内部架构术语当产品文案的 `auth.hero_foot`。

---

## 2026-10-14 · 第九轮 —— 前端重建（引入 vue-router，13 条路由页全部就位）

**一句话**：用户拍板引入 vue-router 4，前端从"`useNav` 三值枚举 + 三个视图"变成 13 条懒加载路由 + 外壳。

- **做了什么**：`router/index.ts`（13 条懒加载路由 + 未登录守卫）、`AppShell.vue` + `AppRail.vue`（五组导航）
  + `TopBar.vue`、`views/` 13 页、`Icon.vue`（55 个内联 SVG）、`PageHeader.vue` / `SampleNotice.vue`、
  `mock/{library,analysis,program}.ts`、`useAppSession.ts`；删 `components/{Sidebar,ChatView,HistorySidebar,SettingsView}.vue`
  与 `assets/sidebar.css`。`NavKey` 由三值枚举扩为**路由名联合类型**（仍必须写在一行，机检只取该声明首行）。
- **数据来源分档说清楚**：真实接口只有 4 处（对话、书架的文献页签、历史会话、文档管理），
  其余 9 页与书架的主题群/抓取两个页签是 mock，一律带「示例数据」徽标 + 归属卡号。
- **顺带查实两条**：①**Font Awesome 从未被引入**（`index.html` 无 link、`package.json` 无依赖），
  旧模板的图标一直渲染成空白 → 改内联 SVG，无网络依赖；②`ChatView` 的「已连接」徽标原本写死，
  WS 断了照样显示已连接 → 已接 `useWebSocket().isConnected`。
- **证据等级 mock**：门禁全绿 + `pytest` 572 passed，并用**仓库外一次性 HTTP stub** 在浏览器里逐条打开
  13 条路由。⚠️ 三条浏览器验证的边界：无头浏览器视口是 **0×0，截图不可用**
  （`NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`），只能用 `evaluate_script` 查 DOM / `innerText` / computed style，
  所以只核得了"结构与设计令牌是否落地"、核不了像素级审美；`alert()` 会**阻塞** 0×0 页面的主线程
  （表现为 evaluate_script 超时），验前要先换成非阻塞收集器；`.auth-hero` 之类在窄视口下被 media query
  设成 `display:none`，`innerText` 查不到，要查 `querySelector` 是否存在。
- `nginx/nginx.conf:71` 已有 `try_files $uri $uri/ /index.html`，history 模式的 SPA 回退本就位。

---

## 2026-10-14 · 第八轮 —— docs/ 目录重构（纯文档，零实现改动）

**一句话**：`docs/refactor/*` 按"常青规则 / 会变的计划 / 只读事实"三分，解进 `rules/` `plans/` `reference/`。

- **做了什么**：`docs/refactor/README.md` 升级为 `docs/README.md`（**docs 目录宪法**：四层结构、优先级、
  命名、归档、新增文档规则）。**新增铁律：新文档不再取新号**，既有两位数前缀降级为"永久 ID、不是顺序、
  不复用"。全仓引用（含 13 个前端注释、`scripts/*.py`、`contracts/openapi.yaml`、`AGENTS.md §2`、
  根 README 目录树）同批改指新路径，跨层相对链接重算；归档件正文逐字保留（抬头残留的 `../refactor/…`
  不追改，映射表见 `archive/README.md` 末尾）。

---

## 2026-10-13 · 第七轮 —— 补两份 As-Is 文档（13 / 14），并登记 C30 / C31

**一句话**：起因是用户按功能模块问进度，而计划里只有架构轴，答不了"论文自动抓取做到哪了"。

- **做了什么**：新建 `rules/13-frontend-backend-architecture.md`（前后端与数据面的**当前形状**，
  逐条 `file:line` + 每节附取数命令）与 `rules/14-feature-modules.md`（产品轴拆成 M1…M17，
  每模块给现状 / 目标可验证行为 / 判据命令 / 卡片或提案 / 顺序约束 / 风险）。`AGENTS.md §2` 登记为顺位 3.6。
- **现查得到、过去没有任何文档逐字写过的事实**：①**dev 形态下 Go 不在请求路径上**（当时 `vite.config.js:8-14`
  把 `/api` 直接代理到 `127.0.0.1:8000`，两份 compose 都没有 `go-api`/`go-worker`）——所以"Go 是唯一公开入口"
  当时**没有运行时承载物**，X2 只能静态判 nginx 配置，这不是脚本缺陷；②Go 面当时只挂 7 条路由，
  `cmd/worker/main.go:52` 自陈调度器属 P3，sqlc 只对 `users` 生成 SQL；③Python 面按调用方分三类实测：
  浏览器在用 13 条 + 内部面 7 条（**零生产调用方**）+ 前端不调但仍可达 12 条 → "Python 只被动执行单次
  AIExecution"尚未成立（差 25 条面）；④**ACL 与迁移是两个不相交一半的集合**（C30）；
  ⑤**契约的服务侧不一致是机检盲区**（C31）；⑥前端当时**没有 vue-router**，这正是 `11 §8` 第 1 项
  "产品入口层作为一等概念"缺口的技术根因；⑦死表 4 张：`workspaces` / `paper_nodes` / `citation_edges` /
  `glossary_entries`（最后一张还被 `glossary_extractor.py:13` 的同名 `NamedTuple` 掩盖，容易误判成在用）。
- **本轮不改任何实现**，也不把 `14 §18` 的 11 项提案登记进分母（那是决策 D5 的账）。

---

## 2026-10-13 · 第六轮 —— 按功能模块核了一遍真实现状，并据此立项 P2-9 / P2-10

**一句话**：README 的三档能力表里有三条与代码不符，逐条现查（不是抄表），并据缺口立了两张新卡。

- **查实的三条失真**：①**"ML 布局分析无调用方"是错的**——`layout_analyzer` 已接在
  `document_loader.py:622` 的入库链路上（只是 `except Exception: pass` 把失败静默吞掉，产出的
  `has_figure`/`has_table` 没进 Milvus schema，所以检索层用不到）；②该行指的 `milvus_writer.py` 路径不存在，
  真实文件是 `backend/vectordb/milvus_writer.py`；③"公式感知检索＝未实现"这句**结论对、机理说反了**：
  查询侧其实已接进混合检索（`rag_utils.py:730 _formula_search`），死的是入库侧——
  `_build_formula_index`（`:644`）**零调用点**，LSH 索引永远是空的，所以恒返回 `[]`。
  **这条区分值得留着**："函数没接"和"接了但喂不到数据"的修法完全不同，前者加一行调用、后者要补整条数据面。
- **另核过**：`multimodal.py` 确属零调用方；图谱三张表全仓只在 `backend/core/models.py` 出现、零读零写；
  Milvus 集合的 `text` 字段是 `VARCHAR(2000)`（`milvus_client.py:240`），所以正文截断属实；
  `backend/` 里**没有任何** arXiv/DOI/CrossRef/httpx/requests 代码（唯一 `doi` 是 `academic_cleaner.py:47`
  的正文正则），即"论文自动抓取"不是没接通，是**根本不存在**。
- **据此立项**（用户拍板：接受分母变大）：**P2-9 论文自动抓取与元数据识别**（12 h）、
  **P2-10 主题分类与语义书架**（10 h，**必须排在 chunk 真相层之后**——在截断副本上算主题等于给不可信数据打标签）；
  退出标准同批加 **Z6**。**分母随之变大：372 → 394 h，卡片 38 → 40 张，完成度 15.6% → 14.7%**。

---

## 2026-10-13 · 第五轮 —— 用户定案「容器只跑中间件，应用层不容器化」

**一句话**：起因是台账 C6 把"compose 里还没有 Go 服务"当成待修项，而实际工作流是中间件用容器、前后端源码跑。

- **定案后逐项改口径**：①**X1 判据**从"`compose ps` 里 `go-api`/`go-worker`/`ai-core` healthy"改成
  "`dev.py infra` 起中间件 + 宿主源码起 go-api/ai-core，`/api/v1/health` 与 `/ready` 各 200"，
  并写明这条**不再证明编排层**；②**X2 的 R4**（compose 里 ai-core 不发布宿主端口）在 dev 形态下无物可判，
  等价口径换成"ai-core 只绑 `127.0.0.1`"——⚠️ 这条**有实质风险**：一个在 dev 形态下永远找不到 `ai-core`
  的规则会静默变成"过了"，而**空规则比红规则危险**；③P0-8 卡标题与输出清单重写；④M0.0/M0.4 收口写法同步；
  ⑤`p0-environment.md` §2 降级为"历史实跑现场 + 部署同构参考"；⑥**C6 作废并移进 §C**，
  16.5 GB 那句移出 P0 阻塞清单。**新记 C29**：与定案冲突的四个遗留物（dev compose 的 backend/nginx、
  `dev.py up`、`server/Dockerfile`、R4 判据）——当轮只改文档口径，实现一个没动。
- **一条边界**：`docker-compose.prod.yml` 是部署形态、仍是全栈容器，本次定案没有否定它。

---

## 2026-10-13 · 第四轮（含同日下午补记）—— D9 定案：minio 换成 versitygw

**一句话**：先定性——**这不是网络问题**，MinIO 把开源 Server 归档了，任何镜像源都给不出那个 pinned tag。

- **定性证据**：`dl.min.io` 对**当前版与全部归档版**都返回 410 Gone（正文写明 "The open-source MinIO Server,
  MinIO Client (mc) and MinIO KES projects are archived and no longer maintained"），Docker Hub 的公开镜像也没了。
  实测 daocloud 回 `denied`、两个备用源回 `not found`、quay 无该命名空间。
- **试过的第三条路（已放弃）**：GitHub Release 资产还在，可自建同版本镜像（二进制 103,395,480 字节 +
  官方 `.shasum`，且 `api.github.com` 的 asset 端点能绕开被污染的 github.com），**但本机到该 CDN 的持续
  吞吐只有约 30 KB/s，103 MB 要 30–90 分钟**，换来的是一个已停止维护、没有安全更新的组件。
- **最终选 D9 的第②条**：`versity/versitygw:v1.8.0`（Apache-2.0、2026-09-04 构建、仍在维护、同样讲 S3 协议，
  posix 后端把对象直接落到挂载目录）。**compose 的改动保持最小**：服务名仍叫 `minio`（Milvus 那侧的
  `MINIO_ADDRESS: minio:9000` 一个字都不用改）；凭据改用 `ROOT_ACCESS_KEY`/`ROOT_SECRET_KEY`
  （versitygw 不读 `MINIO_*`，留着只会让人以为改密码有效）；控制台端口 9001 去掉；
  **健康检查从 `/minio/health/live` 降级成 `nc -z` TCP 探活**（镜像里没有 curl，它也没有那个端点）。
- **补记①（凭据改走环境变量）**：`--access/--secret` 有环境变量兜底（`versitygw gateway --help` 实测列出
  `$ROOT_ACCESS_KEY_ID`/`$ROOT_ACCESS_KEY` 与 `$ROOT_SECRET_ACCESS_KEY`/`$ROOT_SECRET_KEY`），
  所以 dev 与 prod 都改成环境变量——**prod 不再把真密钥写进命令行，因为 command 会原样出现在 `docker inspect` 里**。
- **补记②（对象级 S3 往返单独验过）**：venv 里没有 boto3/minio，于是用 stdlib `hmac`+`hashlib` 手签 SigV4
  打 `localhost:9000`——建桶 200 / PUT 200 / GET 200 且**读回字节与写入一致** / HEAD 200 / LIST 200 /
  DELETE 204×3；再把 secret 改错 → 同一个对象 **403**，所以 env 传进去的凭据是真在生效。
  ⚠️ 第一次 LIST 回 403 是**我的签名脚本把 `?list-type=2` 当成了 path 的一部分**，不是网关缺陷——
  按 C22 那条方法论，先怀疑判据再怀疑被测物。
- **补记③④（prod 也一起换 + 新台账 C27）**：`.env.production` **不会**被自动加载进 compose 的**顶层插值**
  （service 级 `env_file:` 只注入容器环境），所以 `${POSTGRES_PASSWORD:?}` 等仍看宿主环境，
  prod 启动**必须**带 `--env-file`。实测法不碰仓库：把 prod 文件复制到临时目录 + 放一份哑值 `.env.production`，
  不带 `--env-file` → 三条 required 全报缺失、rc=1；带上 → rc=0。
- **补记⑤（堵一个泄密入口）**：`.env.production` **不在 `.gitignore` 里**（只有 `.env` 在，那行还带一串尾随空格），
  `git add -A` 会把生产密钥整份提交进去；已补忽略项。
- **补记⑥（镜像来源要用 `RepoDigests` 核，别凭印象）**：versitygw 第一次是从 `docker.1ms.run` 的 **`latest`**
  拉下来再重打成 `:v1.8.0` 的，随后按 `:v1.8.0` 重拉并确认 **digest 一致**（`sha256:30292fc2…`），
  容器启动横幅自报 `Version v1.8.0, BuildTime 2026-09-04T23:11:49Z`——**要拉带版本号的 tag，别拉 latest 再改名**。
  逐个核完：postgres/redis/milvus/attu 走 `docker.m.daocloud.io`、etcd 直连 `quay.io/coreos/etcd:v3.5.18`、
  versitygw 走 `docker.1ms.run`。**清理重名 tag 时补两条账**：①它们只是同一个 image ID 上的第二个 tag、
  层完全共享，所以 `docker rmi <源tag>` 只清列表、**几乎不回收磁盘**（`docker system df` 报的可回收量是 44 MB，
  其中只有 32 MB 是真孤儿 `curlimages/curl`）——想靠删重名 tag 腾出几个 GB 是错觉（本轮我先把它估成 3.5 GB，是错的）；
  ②untag 会**连 `RepoDigests` 里那条源 registry 一起删掉**，之后就看不出这张图从哪来了，所以来源映射只能靠文档。
- **⚠️ 边界（别说过头）**：验的是**存储网关的 S3 语义**，不是 Milvus 的索引读写——`a-bucket` 至今是空的
  （Milvus 空闲时不写对象），**"上传→切片→向量入索引"那条真链路要等 P1**。
- **补记⑧（新台账 C28，归因要说准）**：`milvus-standalone` 起来约 25 分钟后**自己 FATAL 退出**。因果链是
  **etcd 的磁盘**不是 S3：`docker logs milvus-etcd` 报 `wal/wal.go:805 slow fdatasync took=6.247571869s
  expected-duration=1s`，Milvus 各组件在 etcd 注册带 TTL 的 lease，etcd 一停 → 心跳超时 → querycoord
  `handleNodeDown` → exit 1。**全程没有任何 S3 报错**。同批量化对比（同一个 `alpine:3.20` 容器里
  `dd bs=512 count=1 conv=fsync` 各 5 次）：bind mount **10.7–87.2 ms** vs named volume **4.0–16.4 ms**，
  1 MB 顺序写 bind 侧只有 5.3–7.9 MB/s。稳态离 etcd 那条 1 s 告警线还差两个量级，所以是**潜在脆弱性而不是必然故障**；
  但那一次 6.25 s 恰好发生在"重建容器 + 拉镜像"的同一时刻，而 bind 目录与 VHDX **同在 D: 一块物理盘上**。
  ⚠️ 顺带查实：**prod compose 用的是 named volume，dev 反而是 bind mount，两者本来就不对称**。
  **三条缓解（etcd 换 named volume / `DOCKER_VOLUME_DIRECTORY` 指到 ext4 / 调大 lease 超时）一条都没动**
  （属存储拓扑决策，且 P0-0 的 real 证据是在 bind mount 形态下拿的）。
  **因此"6 容器 healthy"要带条件说：起来时 healthy ≠ 十分钟后还活着。**

---

## 2026-10-12 · 第三轮 —— 按用户「解除所有阻塞」执行 C20 的环境重建

**一句话**：`.env` 重建、数据盘迁出系统盘、镜像 5/6 就位、真库建出来、快照重导、两份迁移真库验幂等 →
P0-0 与 P0-2 双双转 done（real）。

- **①`.env` 重建**：`JWT_SECRET_KEY` 是新随机值（**既有 token 全部失效**，本机开发库无妨），
  `LLM_API_KEY`/`LLM_MODEL` 放的是**明确标注的占位值**（本轮全程不调 LLM，只过启动校验）。
- **②数据盘迁出系统盘**：本机没有 registry mirror 且 docker.io 直连超时，但 quay.io 与镜像源可达，
  于是用 `docker.m.daocloud.io` 拉取后重打成 compose 期望的 tag（不动仓库文件、不动全局配置）。
  用户接着要求挪到 D:——`wsl --manage` 只有 `--set-sparse`、**不能搬家**，所以只能走 Docker 自己的设置：
  `docker desktop stop` → 写 `settings-store.json` 的 `CustomWslDistroDir=D:\DockerData` → start。
  实测**WSL distro 本体跟着搬了**（注册表里 `docker-desktop` 的 BasePath 就是 `D:\DockerData`），
  C: 上已无任何 `.vhdx`。⚠️ 但那是**新建盘而不是搬盘**：已拉的 4.2 GB 镜像丢失需重拉；
  C: 那块 5.91 GB 老盘经用户确认后删除，**C: 可用由 7.8 GB 回到 14 GB**。
  ⚠️ 另一条：**改完 `CustomWslDistroDir` 之后 Docker Desktop 自己退出过一次**，所以搬盘之后第一次
  `logs`/`down` 其实失败了（报 `dockerDesktopLinuxEngine` 管道不存在），必须 `docker desktop start` 重来
  ——**命令返回非零时先分清是脚本缺陷还是引擎没在跑**。
- **③镜像 5/6 就位**，minio 取不到 → 当轮登记为决策 **D9**（次日第四轮定案换 versitygw）。
- **④PG+Redis healthy**；宿主跑 `alembic upgrade head`（3 revision，head=`add_paper_knowledge_graph`）建出
  **10 表 / 59 列**，与原基线一致、`column_diff` 仍是 **23 条**；不走 `dev.py migrate`
  （那要构建 16.5 GB backend 镜像）。
- **⑤`--live` 重导成功、快照带上 `columns`**，**`--verify-columns` 从 exit 2 变成真正的逐列比对 exit 0**
  （类型/长度/NOT NULL/DEFAULT 四项）。
- **⑥两份迁移在真 PG 15.19 上验幂等**：空库 0→10→10；存量形态（`pg_dump --schema-only` 复制进临时库）
  两遍各 30 条 skipping、表数恒 10；`000002` 10→11→11、`ai_executions` 恰 **17 列**；全部 exit 0。
  down 跑一遍有效、第二遍退出 3——这是 `migrations/README.md` 里"禁止 `DROP TABLE IF EXISTS`"那条规则的
  **预期后果**，不是缺陷。
- **⑦`probe_timestamps.py` + `timestamp-audit.md` 落地**（11 个 naive 时间列逐个判定；分布法/交叉法如实报
  `no_data`；配 25 项单测）。**探针法实测证实了 `05 §4` 那条断言**：会话时区 `Asia/Shanghai` 下
  aware `datetime.now(UTC)` 写进 naive 列会落成 **+8 小时偏移**（07:08:09→15:08:09），
  而 `now() AT TIME ZONE 'UTC'` 与字面量两条路径恒为 UTC——以前是推断，现在是量出来的。
- **⑧补齐卡片列了一直却不存在的那份 `server/migrations/README.md`** → P0-2 转 done（real），进度 12% → 14%。
- **⑨两处顺带查明**：`image: postgres:15` 是**浮动 tag**（这次 15.19、原审计 15.18，台账 **C25**）；
  compose 没有顶层 `name:` 时项目名会**退回目录名**（本机目录仍叫 PaperRAG → 容器标签 `paperrag`、
  网络与具名卷带 `paperrag_` 前缀，且换目录 clone 就换一个项目名），已在两份 compose 里钉成
  `researchpilot`（台账 **C26**）；`down`（不带 `-v`）后重建到新项目，**PG 数据完好**（10 表 + head 未变）。
- **⑩P0-0 转 done（real）**：本卡唯一欠的证据是"`down`/`logs` 没逐个实跑"，本轮补齐：`doctor` 全绿 →
  `up postgres redis` healthy → `ps` → `logs postgres` exit 0（其中 "PostgreSQL Database directory appears
  to contain a database; Skipping initialization" 正好证明数据在 bind mount 里）→ **`down` exit 0** →
  再 `up` 回来表数仍 10、alembic head 未变。`migrate` 子命令的实跑证据仍是 2026-10-10 那次 7 容器全栈记录。
- **⑪红点照旧**：X1 `not_run`、X2 `fail`、X4 `fail`。
- **顺带纠正一条文档旧结论**：**Docker Desktop 其实是 per-user 安装**（`%LOCALAPPDATA%\Programs\DockerDesktop`，
  而 `C:\Program Files\Docker\Docker` 不存在）——`AGENTS.md §4` 里那条"系统级安装（不是 per-user）"的更正
  本身是错的，被它推翻的原结论反而对。

---

## 2026-10-12 · 第二轮 —— 分支收口 + 一次文档-机器核对（C19）

**一句话**：把误推到 `main-sync` 的提交快进回 `main`，并逐条实跑核对文档里的读数与命令面。

- **分支收口（用户指示）**：本轮最初把 5 个提交推到了 `main-sync`，用户指出应该落在 `main`。核实后确认这是
  **干净的快进**（`origin/main` 正好是 main-sync 的祖先，落后 0 / 领先 5），所以用
  `git push origin main-sync:main` 快进远端，**不需要 force、不覆盖上游**。然后本地 `main` 重置到
  `origin/main` 并切为工作分支、本地与远端的 `main-sync` 均已删除。
- **⚠️ 这里有一个必须记住的坑**：**本地** `main`（`e6cc211`）与 `backup/main-pre-rewrite-20261012` 携带的是
  2026-10-11 历史重写**之前**的 92 个提交，重写正是为了从历史里清除个人信息与设备信息——
  **推它会把这些重新公开，checkout 它会把它们写回工作区**。所以"推到 main"只能理解为推**远端** main。
  收口后重写前的提交只保存在那条 backup 分支（本地、无远端副本，`gc` 前是唯一还能解析那些老 SHA 的地方）。
- **文档-机器核对（台账 C19）**：逐条 `git grep` + 实跑取数，就地更正 12 处过期读数与命令面
  （unit/integration 310/23 → 458/57、全量 449 → 515、`audit_schema` 判定单测 19/34 → 37、
  `dev.py` 六项 → 10 个子命令、`08` 的 Python ≥ 3.11 → **≥ 3.12**（约束源是 `pyproject` 的
  `requires-python`）、`05 §2.5` 的"第二个后续迁移"→ 第三个、`05 §3` 的 `000004_paper_chunks.sql` →
  `.{up,down}.sql` 且必须同批登记 sqlc、`09` P0-7 输入点名的 `backend/services/agent_runner.py`
  **不存在** → 改指 `core/dependencies.py` 的两个 getter、`09 §0`"当前状态一律 not_run"→ pass 4 / fail 3 / not_run 1）。
  并修掉一处**自相矛盾**的记录：`p0-environment.md §4` 曾让人把 `TEMP`/`TMP` 指到工作区**内**，
  与 §5 及 `AGENTS.md §5` 的"必须指到工作区外，否则产生删不掉的毒目录"正相反——以工作区外为准。
- **同时暴露一条真实代码缺口（C18 / 决策 D8）**：`server/migrations/` 有文件、**没有执行器**——
  PATH 无 `migrate`、`server/go.mod` 无 golang-migrate 依赖、`dev.py migrate` 实为容器内
  `alembic upgrade head`，所以 `09` X6 判定命令里那一半跑不了。
- **SHA 引用可达性**：用 `git merge-base --is-ancestor` 逐条判，`03`/`07` 里的 `4a5e806` 改为重写后的
  `a552a5c`；`00-audit` 与 `docs/archive` 里的死引用按 `AGENTS.md §7` 故意保留；并查实 archive 的
  `2c3e58e` 与重写无关、是 `2c3e583` 的**笔误**（同一提交重写后是 `996cf777`）。
- **门禁全绿读数**：五道离线门禁 exit 0、`pytest -q` **515 passed / 46.21s**、Go 侧四包全绿、
  X2 `check_nginx_routes.py` 如实 exit 1、`--verify-columns` 如实 exit 2（当时快照无 `columns`）。

---

## 2026-10-12 · 第一轮 —— P0-6 认证垂直切片（X5 转 pass、X4 只剩 chain 半侧红）

**一句话**：Go 侧认证切片落地并被 golden vectors 钉住，X5 转 pass。

- **产出**：`server/internal/auth/{password,jwt,service,handler}.go` ＋ `internal/config` 扩七个认证键与
  `ValidateAuth()` fail-fast（空密钥在**所有**环境拒绝启动，占位密钥与两个泄露过的邀请码只在生产拒绝）
  ＋ `cmd/api` 挂三条路由 ＋ `GetProfileByUsername`（`/me` 不碰 `password_hash`）
  ＋ `scripts/export_jwt_golden.py` → `contracts/jwt_golden.json`（9 条）＋ 32 项单测。
- **几条照抄现状而不是"顺手改好"的地方**（各有用例钉住）：①register 会 strip 而 login **不 strip**；
  ②密码长度按**码点**算（Go 的 `len(string)` 是字节，含中文的口令会被判得更严）；③`role` 不做枚举校验，
  `role:"root"` 被折叠成 `user`（实测生产侧返回 200，台账 **C21**）；④多余字段忽略；⑤用户不存在与密码错误
  返回**同一个** 401；⑥校验顺序是"重名 409 先于邀请码 403"；⑦400/401/403/409/500 的 detail 文案
  **含中英文混用这个现状**，全部由生产侧 handler 现跑取数（`handler.go` 顶部那张八行实测表），不是按印象写的。
- **两处结构性收口**：`/me` 走新增的 `GetProfileByUsername`（原先 `GetUserByID` 自称"/me 专用"，
  但 JWT 的 `sub` 是用户名不是 id，那个声明落不了地）；角色一律回库取，`ParseAccessToken` **连 role 都不返回**。
- **修掉判据自身的一个缺陷（C22）**：X5 的命令原先是 `cd server && go test -run TestVerifyLegacyHash`，
  而 `server/` 根目录没有 Go 文件 → `no Go files` → **rc 恒为 1，与测试是否存在无关**。
  C17 当时把这条当成"不会假绿"的好消息，但它同时意味着**这条判据永远不可能变绿**。已补包路径。
  **可复用的检查办法**：把判据要测的实现全删掉再跑一次，rc 不变就说明这条命令根本没在测它声称要测的东西。
- **两侧结论相反的轴写进文件而不是藏进代码**：`contracts/jwt_golden.json` 有 `divergences` 段
  （缺 `exp` 的令牌 Python 收 / Go 拒；alg 白名单 Go 写死 HS256），负向量另带 `rejected_by`
  区分"令牌层拒"与"回库拒"。这份文件**不能逐字节重建**（token 带 exp），所以它的 `--check` 是语义校验。
- **顺带修掉 P0-1 留下的一处不一致（C23）**：Go 的 `Recover` 中间件把 500 写成 `Internal Server Error`，
  而生产侧 `unhandled_error_handler` 是 `Internal server error`（小写 s）——同一个 Go 服务里出现两种 500 文案
  正是 `01 §6.3` 记的那个坑。
- **golden vectors 的"不含密码明文"落成了可机检的形式**：向量是合成口令的摘要，口令由 `vector_id`
  按文件内 `password_rule` 重建；每条期望值都由**生产裁判** `backend/core/auth.py:verify_password` 现算。
  真库 `password_hash` **有意不导出**（提交进仓库就是离线爆破机）。
- **读数**：`go test ./internal/auth/...` 50 项 PASS、全量 **547 passed**、`npm run typecheck` 0 error。
- **X5 的 `real` 那一档仍开着**：`--from-db` 的真库形状统计（含"是否残留 bcrypt 族"）因原真库消失而无法执行
  （C20），Go 不实现 bcrypt，**P1 接管 `users` 前必须先跑一次 `--from-db`**。

---

## 2026-10-12 · 第二轮之前 —— C20：Docker 数据面被清空，原真库永久消失

**一句话**：这不是"等 Docker 起来"，而是**不可逆的数据丢失**——导出 `schema-baseline.json` 的那个原真库没了。

- **实测**：daemon **可达**（`docker info` 正常返回），但 `docker system df` 四项全 0、`docker volume ls` 空、
  `docker ps -a` 无容器；`.env` 也不在（`.gitignore` 忽略、从未入库）；5432/6379/2379/9000/19530 均无监听，
  本机也没有原生 PG。VHDX 仍占 1.64 GB 是"删数据不自动缩小"的**残留空间而非数据**。
  alembic 链本身完好（3 个 revision），故库可重建。清空原因未查明，所以不能假定它不会再来一次。
- **作废的三条记录**：`progress.json` 的"本轮 daemon 不可达所以 real 级补证排队"、`AGENTS.md §3` 的
  "11 个镜像 / 约 4.3 GB"、以及"P0-2 剩下两件事只要 Docker 起来就能跑"。
- **真正的后果是不可逆的那一半**：X6 的"在**存量库**上幂等"这一问**永久失去原对象**——只保留 2026-10-11
  "临时库法"的实跑记录作历史证据，**不拿 `alembic upgrade head` 重建出的全新库自证充数**
  （新库没有 `create_all` 与 alembic 的混合历史，而那种存量形态正是 X6 关心的对象）。
  同理 `--from-db` 的覆盖面检查（库里是否残留 bcrypt 族）也跑不了。
- **流程教训（比逐条改更有用）**：**real 级证据只存在于容器卷里等于没有证据，一次清空就抹掉**——
  往后一律落成仓库内的文件。
- 原库里的开发数据（论文 / 会话 / Milvus 向量）已丢失，用户 2026-10-12 确认为开发数据、直接重建。

---

## 2026-10-09 … 2026-10-11 · 立项与基线（沿革）

- **2026-10-09**：`SPEC-1` 把 spec 按四条原则重排为 P0–P3 并建起 `progress.json` + `sync_progress.py`
  的进度机制；`P0-4` 契约目录五件齐、X3 本机 pass（K1/K4 定案落地：429 与降级后的 400 都走 detail 信封）。
  基线记为 `main @ 106f17dd`。
- **2026-10-10**：现场核查**推翻**了"本机缺一次重启才能用 Docker"——真因只是 Docker Desktop 没在运行，
  拉起后约 5 秒引擎就绪。同批修掉三处真实缺陷：`.env.example` 行内注释被 dotenv 当成值
  （`KEY= #值` → `int('#1024')`，应用起不来 + 13 个测试文件收集失败）、compose 缺 `target: backend`
  （Dockerfile 多阶段且末阶是 nginx，不写 target 会构建出 nginx 镜像 → 永远 unhealthy）、
  镜像名仍按旧目录名推导（已钉为 `researchpilot-backend`）。实跑：`up` 起 7 容器、backend healthy、
  `/health` 容器内与宿主机均 200、`migrate` exit 0。
- **2026-10-11**：`P0-2` 的真库审计跑通（`--live` 导出 `schema-baseline.json`：PG 15.18、10 张表、
  alembic head=`add_paper_knowledge_graph`、ORM 与真库漂移 23 处），`000001_baseline.{up,down}.sql`
  按真实结构抄录 → X6 转 pass。同日做了**历史重写**（把个人信息与设备信息从仓库历史里清除，
  102 个提交的作者/提交者统一为 `ResearchPilot Dev`，**此前的提交 SHA 全部改变**）。
  新增 `dev.py infra` 与 `dev.py serve`，把"源码运行 + 中间件容器"列为一等路径；README §3 重写为
  "从一台全新电脑跑起来"。当时暴露的三个坑：vite 5 只监听 `::1`（访问用 localhost 而非 127.0.0.1）、
  探针路由不带 `/api/v1` 前缀、`dev.py up` 的健康等待写死了含 backend 的容器清单
  （会让 `up postgres` 一直等一个从未创建的容器直到超时，已修）。
- **测试基线沿革**：448 → 449 → 515 → 547 → 572 → 593 → **599**，每次涨的都是新增判据用例。
  **读数一律现场取**（`uv run python -m pytest -q`），别抄任何文档里的数字。

---

## 附：本机验证边界（长期有效的操作性事实）

这些不是"某一轮发生了什么"，而是**每次要 real 级证据时都得先知道的事**，所以留在日志末尾备查；
规约性质的部分在 `AGENTS.md §5`。

1. **能验到哪一层**：Docker Desktop 运行中；`postgres / redis / etcd / minio(versitygw) / milvus / attu`
   六容器都能起并 healthy。PG 里是 `alembic upgrade head` 建出的库（数据在 `<repo>/volumes/postgres`
   这个 bind mount 里，`down` 不带 `-v` 时数据完好）。⚠️ **但 Milvus 不是"起起来就一直活着"**：
   实测约 25 分钟后 FATAL 退出（C28），所以**任何长时间跑 Milvus 的 real/e2e 证据都要中途复检容器还在不在**。
2. **拉镜像的三个可用源**：`docker.m.daocloud.io`（postgres/redis/milvusdb-milvus/zilliz-attu）、
   `docker.1ms.run`（versity/versitygw）、`quay.io` 直连（coreos/etcd）；拉完 `docker tag` 成 compose
   期望的名字，不动仓库文件也不动全局配置。判某张镜像从哪来的用
   `docker image inspect --format '{{json .RepoDigests}}'`（但它只在源 tag 还挂着的时候有效）。
3. **Docker 数据盘与 WSL distro 本体都在 `D:\DockerData`**（`settings-store.json` 的 `CustomWslDistroDir`；
   改它必须先 `docker desktop stop`）。**要挪盘趁项目小的时候挪**——Docker 是新建盘不是搬旧盘。
4. **Go 依赖能拉，前提是先设 GOPROXY**：默认 `proxy.golang.org` 实测 12s 超时，
   `go env -w GOPROXY=https://goproxy.cn,direct` 后 1.6s 拉到。**文档写"该这么做"不等于"已这么做"。**
5. **操作细节**：`audit_schema.py --live` 与 `probe_timestamps.py` **要显式 export `DATABASE_URL`**；
   `docker compose config` 不需要 daemon；全量 pytest 前把 `TEMP`/`TMP` 指到**工作区外**的空目录
   （否则 41–42 个 `tmp_path` 用例会以 `PermissionError: [WinError 5]` **假失败**，表现为
   `407 passed, 42 errors`——不是仓库缺陷）；`wsl -l -v` / `reg query` 输出常是 UTF-16，
   Git Bash 里要先 `iconv -f UTF-16LE -t UTF-8`；往容器传 `/usr/...` 这类路径要 `MSYS_NO_PATHCONV=1`；
   **取退出码的语句不能接在管道后面**（`... | head; echo $?` 测到的是 `head` 的 rc，栽过两次）。
6. **前端页面在本机怎么验**：Python/Go 没起时可在**仓库外**起一个一次性 HTTP stub 监听 `127.0.0.1:8000`，
   它只要答几个端点就能走完真实登录表单 → 落 token → 挂外壳 → 逐条打开路由；验完删掉，不进仓库。
   ⚠️ 三条边界见第九轮那条（视口 0×0 截图不可用 / `alert()` 阻塞主线程 / media query 隐藏的节点查
   `querySelector` 而不是 `innerText`）。这层证据只能算 **mock 档**，浏览器级 e2e 判据属 P0-9 的 X7。
7. **进程卫生（2026-10-15 用户明确要求，已进 `08 §6`）**：只起判据需要的最小集合；起之前先
   `netstat -ano` / `docker compose ps` 盘点；用完即停；**`TaskStop` 只杀外层 shell，子进程可能活着占端口**
   （实测 vite 的子进程在 TaskStop 之后仍占着 5173，要 `taskkill /PID <pid> /T /F`），所以**每次收尾要复验端口**。
   同一条纪律的另一半是 **I/O**：本仓库与 Docker 的 VHDX 在同一块物理盘上，**不要为每次小改动重跑全量套件**
   ——实测一小时内三遍全量 + 两遍 `npm run build` 就把机器拖到无法使用，而当时端口全空、没有遗留进程、
   `vmmem` 只有几十 MB（**卡顿来自磁盘不是内存**）。

---

## 附 B：历次文档-机器核对查出的失真（**不要重复相信**左列）

这张表是 `AGENTS.md §4` 的详细版：§4 只留一行结论，论证与取数方式在这里。
判据统一是**现场跑一遍**，不是读源码凭印象——本表每一条都曾以"文档写得很确定"的形态存在过。

| 旧结论（曾在 README / plans / progress.json 里） | 现场核查后的事实 |
| --- | --- |
| 「本机缺一次重启才能用 Docker」「WSL2 组件装完待重启」 | 真因只是 Docker Desktop 没在运行；拉起后约 **5 秒**引擎就绪。`docker info` 报 pipe-not-found 就是"没起"，不是"缺组件" |
| 「Docker Desktop 是系统级安装」 | **这条更正本身是错的**：安装路径是 `%LOCALAPPDATA%\Programs\DockerDesktop`，而 `C:\Program Files\Docker\Docker` 不存在 → **就是 per-user 安装**，被它推翻的原结论反而对 |
| 「compose 不写 `name:` 无所谓」 | Compose 会拿**项目目录名**当项目名，本机 clone 目录仍叫 `PaperRAG` → 容器标签 `com.docker.compose.project=paperrag`、自动创建的网络与具名卷都带 `paperrag_` 前缀，且**换个目录 clone 就换一个项目名**，"跨机器可复现"直接失效（台账 C26，已钉成 `name: researchpilot`） |
| 「镜像名带不带 paperrag 一看就知道」 | 镜像与容器名其实**都是对的**（上游名 + `container_name: researchpilot-*`），唯一的 `paperrag` 来源是上一条那个项目名。报"名字没改干净"之前先分清是**镜像/容器名**还是 **compose 项目名** |
| 「只验骨架可跳过 LLM key」 | `app.py` 的 startup **无条件**调 `validate_config()`，缺 `LLM_API_KEY`/`LLM_MODEL` 即 `RuntimeError` 拒绝启动 |
| 「schema 源整目录交给 sqlc 就行」 | **会静默出错**：sqlc 按文件名顺序把目录里每个 `.sql` 当 schema 执行，`000001_baseline.down.sql` 排在 `.up.sql` **前面** → 先 DROP 再 CREATE，生成物等于按回退后的库产出。必须逐个列 `*.up.sql`（`dev.py gen` 已机检这条，另有"新 up 未登记""生成物有孤儿"两条） |
| 「`--check-baseline` 通过 = 基线与真库一致」 | 它只校验**文件形态**（up 非破坏 + 幂等、down 配对），**不比对内容**。内容比对是另一条命令 `--verify-columns`。同一版的 down 规则不剥注释、up 剥（注释里写 `DROP TABLE IF EXISTS` 会被误判）——已修，两边现在一致 |
| 「`schema-baseline.json` 里有列清单可直接抄」 | 旧版 `--live` 的 payload **没有 `columns`**（只有 tables/alembic/tz/server_version/indexes/constraints/column_diff），所以基线的 varchar 长度与 NOT NULL 长期无机检。已补 `columns` 与 `--verify-columns`；**快照缺 `columns` 时它如实返回 2 而不是假装比过，这个行为要保留** |
| 「真库有 9 张表」（`05 §2.2`） | **10 张**（含 `alembic_version`）；`alembic_version` 是否该进 Go 基线仍待拍（决策 D6） |
| 「`users.created_at` / `users.role` 在库里没有 DEFAULT」 | 真库有 `DEFAULT now()` 与 `DEFAULT 'user'`（否则这两列会出现在 `column_diff` 里）。那份失真所在的 `server/sql/schema.sql` 已删除，正确结论记在 `05 §4.2.1` |
| 「把这两列的失真核对进 sqlc 的 diff 就行」 | **做不到**：切换 schema 源后 `User` struct 与三条查询的生成类型逐字未变——**sqlc 不把列默认值编码进 Go 类型**，`gen --check` 只能抓类型/可空性/列与表的存在性。DEFAULT 的机检是 `audit_schema.py --verify-columns` |
| 「本机没有 sqlc 二进制，要 `go install …@v1.30.0`」 | `$HOME/go/bin/sqlc.exe` 就是钉住的 v1.30.0，`dev.py gen` 本来就优先用本机二进制、找不到才退回 `go run`。**过期工具记录会让下一个人白装一遍** |
| 「X5 的判定命令是 `cd server && go test -run TestVerifyLegacyHash`」 | **那条命令永远不可能绿**：`server/` 根目录没有 Go 文件 → `no Go files` → `FAIL [setup failed]` → **rc 恒为 1，与测试是否存在无关**（台账 C22，已补包路径）。C17 曾把"rc=1"当成好消息（证明不会假绿）——那没错，但**同一事实还意味着判据不可能被满足** |
| 「Go 依赖拉不动，P0-1 之后每张 Go 卡都开不了工」 | 可解，但**本机 GOPROXY 一直没设**：`go env GOPROXY` 仍是默认的 `proxy.golang.org`（curl 12s 超时），改成 `goproxy.cn` 后 **1.6s** 拉到。所以那条风险的缓解措施是有效的，只是**没被执行过** |
| 「密码长度校验用 `len(password)` 就行」 | **Go 里会错**：生产侧是 Python 的 `len(str)` = **码点**数，Go 的 `len(string)` = **字节**数；含中文的口令在 Go 侧会被判得更严。用 `utf8.RuneCountInString`（已有用例钉住） |
| 「`Authorization: Basic …` 的 401 是 `Invalid authentication credentials`」 | 实测 `OAuth2PasswordBearer`：缺头与非 bearer 方案都回 **`Not authenticated`**（那句在 `HTTPBearer` 里，本项目没用）。另：`Authorization: Bearer`（后面不跟令牌）**能过** bearer 这一关，失败发生在后面的令牌校验。所以 Go 侧要复刻的每一句 detail 都应**用生产 handler 现跑取数** |
| 「Go 的 500 文案是 `Internal Server Error`」 | 与生产侧不一致：`backend/core/exceptions.py:unhandled_error_handler` 是 `Internal server error`（**小写 s**）；大写那句是 Starlette **没注册** handler 时的纯文本兜底，而 `app.py:94` 注册了（台账 C23，已对齐） |
| 「契约里 `RegisterRequest.role` 是 enum，Go 该按枚举校验」 | **会造出两侧分歧**：实现是 `role: str \| None`，实测 `role:"root"` 返回 **200** 并折叠成 `user`，多余字段也是 200（pydantic 不 forbid extra）。裁判是运行中的系统，Go 照实现走（台账 C21）。`check_contracts.py` **抓不到这类偏差** |
| 「`cp .env.example .env` 就能起」 | **旧模板会炸**：`KEY= #值` 的行内注释被 python-dotenv 当成真实值（`int('#1024')`），已把 11 行改成整行注释 |
| 「compose 的 backend 开箱可用」 | **缺 `target: backend`**：Dockerfile 多阶段且末阶是 nginx，不写 target 会构建出 nginx 镜像 → 永远 unhealthy（已修） |
| 「旧名 PaperRAG 还留在 go module path / Redis 前缀 / 指标名 / 契约 $id」 | 2026-10-10 全部改为 `researchpilot`；**唯一保留旧字面量的是安全黑名单**（`paperrag-admin-2026`，删了等于把泄露口令重新变成可用口令） |
| 「minio 镜像拉不到是网络问题」 | **不是网络故障，是上游归档**（见第四轮那条）。按"起不来就是 `dev.py` 有问题"去查会完全查错方向（台账 C24 / 决策 D9） |
| 「`contracts/table-acl.md` 里某表写着 `go: W`，所以 Go 现在就在写它」 | **纸面归属，不是现状**：ACL 声明 24 张、基线 SQL 只建 12 张，其中 18 张的 `go: W` 在库里**没有对应表**；反向有 5 张实建表未进 ACL（台账 C30）。判归属前先求差集 |
| 「契约里有 `GET /api/v1/health`，所以打它就通」 | **今天只有 Go 满足**：Python 的 `health_router` 在 `app.py:149` 注册时**不带 `/api/v1` 前缀**，路由本体是根路径 `/health`、`/ready`；Go 两边都挂。`check_contracts.py` **抓不到**——它只比"前端实调集合 ↔ 契约"，不校验服务侧（台账 C31） |
| 「`/metrics` 在契约里，说明监控已就位」 | **三不管端点**：契约声明它、Python 有实现（`app.py:150`），但 nginx 没有对应 location、前端不调、Go 未实现 |
| 「prod compose 里写了 `env_file:` 就能取到 `${VAR:?}` 密钥」 | **不能**：service 级 `env_file` 只注入容器环境、不参与顶层插值，所以 prod 必须 `docker compose --env-file .env.production -f docker-compose.prod.yml up -d`（台账 C27）。⚠️ 顺带查实 `.env.production` **不在 `.gitignore` 里**（只有 `.env` 在）——已补 |
| 「Python 的 login/register/chat 是可用的（毕竟测试全绿）」 | **错，而且错得很难发现**（见第十三轮 C32）。**通用教训**：门面会掩盖上游坏死；凡是按名字注入的框架约定要做静态检查，别靠发请求 |
| 「P0-8 要在 compose 里新增三个应用服务，X1 才算起来」 | **前提被 2026-10-13 的定案推翻**（容器只跑中间件）。X1 判据、X2 的 R4、M0.0/M0.4 的写法、P0-8 的输出清单都已按此改写，台账 C6 作废、遗留冲突记 C29。**别照着旧卡片去加 compose 服务** |
| 「文档里的数量/命令面是按机器现状写的」 | **不是**（2026-10-12 扫了一遍，12 处过期，详见上面"第二轮"那条 C19）。还修掉一处**互相矛盾**的记录：`p0-environment.md §4` 曾让人把 `TEMP`/`TMP` 指到工作区**内**，与 §5 的"必须指到工作区外"正相反——以 §5 为准 |
| 「测试基线 448 / 333 / 307 / 515 / 547 / 572 项」 | **都过期过**。读数一律 `uv run python -m pytest -q` **现场取**，别抄任何文档里的数字（沿革见上面那条） |

### 附 B-1：踩过的操作坑（一次就够）

- `psql` 里 `extract(epoch from …)` 这类表达式**必须带 `SELECT`**（`probe_timestamps.py` 第一版就栽在这，
  报 `syntax error at or near "extract"`）。
- 看列名**别凭印象猜**：曾把 `chat_messages` 的分组键猜成 `session_id`，实际是 `session_ref_id`，一跑就 `UndefinedColumn`。
- Docker 数据盘是 VHDX，**删数据不会自动缩小**；真正回收要压缩/稀疏化。
- 受限沙箱下 docker 的命名管道、uv 的缓存、git 写 `.git/index.lock` 都可能被拒；**跑全量测试必须把
  `TEMP`/`TMP` 指到工作区外的空目录**，否则 41–42 个 `tmp_path` 用例会以 `PermissionError: [WinError 5]`
  **假失败**（表现为 `407 passed, 42 errors`，不是仓库缺陷）；也**不要**用 `--basetemp` 指到工作区内。
  这些临时目录会带上创建时的完整性标签，策略切换后可能变成**谁都删不掉的毒目录**。
- BuildKit 取 `# syntax=docker/dockerfile:1` **不走 Docker Desktop 代理**：Docker Hub 不可达时必挂；
  先用 daemon 把 `docker/dockerfile:1`、`node:20-alpine`、`python:3.12-slim`、`nginx:alpine` 拉到本地即可。
- **2026-10-11 历史重写**之后，此前的提交 SHA 全部改变。外部笔记/Issue 里更老的 SHA 一律按
  "`git log --all --grep=<提交标题>` 重新定位"处理，不要直接 `git show`；`docs/reference/00-audit.md` 与
  `docs/archive/` 里的死引用按 `AGENTS.md §7` **故意保留**（dated 事实与归档件正文逐字不改）。
