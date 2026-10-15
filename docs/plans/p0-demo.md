# P0 演示脚本（P0-9 输出）

> 30 秒能把 P0 的成果**跑给人看**的那条路径，以及每一步"看到了什么才算数"。
> 这不是测试清单（判据在 `progress.json` 的 X1–X8），是**演示**：一条链走通、看得见反馈。

## 1. 起栈（约 2 分钟，不含镜像构建）

```bash
uv run python scripts/dev.py doctor                 # 前置自检：Docker 在跑 / .env 三必填 / 端口没被占
uv run python scripts/dev.py up postgres redis      # 演示只需要这两个中间件，别顺手 infra 起六个
uv run python scripts/dev.py migrate-go             # Go 侧建表（决策 D8：显式动作，不进启动路径）
AICORE_INTERNAL_TOKEN=<本机随机值> uv run python scripts/dev.py serve --no-reload   # 宿主 Python
uv run python scripts/dev.py go-serve               # go-api :8080 —— dev 的唯一公开入口
cd frontend && npm run dev                          # vite :5173，/api 代理到 :8080
```

⚠️ 两个"看起来是坑其实是设计"的点：
- **`--no-reload` 不是保守，是必要**：带 `--reload` 时任何写进 `backend/data/documents/` 的动作都会热重载，
  把演示中途打断（第十七轮实测：带 reload 跑全量 7 条 chain 红，`--no-reload` 全量 644 passed）。
- **`attu` 在 3001 不是笔误**：8080 让给 go-api，也是 X1 判据的落点。

## 2. 演示的六步（浏览器里，全部走 `vite → go-api`）

| # | 操作 | 看到什么算数 | 这一步证明的是 |
| --- | --- | --- | --- |
| 1 | 打开 `http://localhost:5173/history` | 被弹回 `/login`，标题「登录 ResearchPilot」 | 路由守卫在，未登录不渲染业务面 |
| 2 | 切「注册」页签，填用户名 + 口令，提交 | 落到 `/chat`，侧栏出现用户名与「普通用户」 | Go 原生 register（P0-6）+ PBKDF2/JWT 与 Python 互认（X4/X5） |
| 3 | 进「设置」，点「深色」 | 整站立刻变暗，`html[data-theme="dark"]` | 偏好面 Go 原生读写（P0-6 的自助面），无保存按钮也能持久 |
| 4 | 「偏好设置」选「历史会话」→ 保存 | toast「已保存」 | `PUT /me/preferences` 落 PG（迁移 `000003`） |
| 5 | 侧栏退出 → 用同一口令重新登录 | 直接落在 `/history` | 偏好**真的存住了**：`start_view` 只在登录后跳（第十二轮口径） |
| 6 | 「修改密码」→ 先填错旧口令，再填对 | 前者 toast「修改失败」，后者「密码已修改」；退出后旧口令登不上、新口令能登 | 旧口令错回 **400 而不是 401**（不被当成会话过期踢人）+ 改密真的落库 |

## 3. 命令行侧的对照（演示时同屏跑，说服力强）

```bash
curl -s http://localhost:8080/api/v1/ready | python -m json.tool   # checks.database / checks.redis 都 ok/connected
curl -s http://localhost:8000/health | head -c 120                 # 上游自己也在，但它不是入口
uv run python scripts/check_nginx_routes.py                          # R1–R5：入口链与两份 compose 的形态
uv run python scripts/check_route_ownership.py                       # 每条面归谁、Python 那条还在不在
uv run python -m pytest -q -m chain                                  # 27 项跨语言对拍（要 serve + go-serve）
cd frontend && npm run test:e2e                                      # 9 项 Playwright 结构级（E2E_BROWSER_CHANNEL 见 AGENTS §5）
```

## 4. P0 演示**不**包含的事（别在演示里说成已就位）

- **文档摄取与问答**：`documents` / `chat` / `ws` 仍是 Python 实现，Go 只做门面（归属表里的 17 行 `proxy`）；
  文档真相还在文件系统 + Milvus，没进 PG（P1-3/P2-1 的前置）。
- **会话删除的 UI**：需要一条真会话，而创建会话要走 chat → LLM（属 P1-4 之后的 e2e）。
  chain 层已有 sessions 列表/删除的逐字对拍，但没有浏览器级删除演示。
- **限流**：Go 侧一条限流都没有（台账 C33），登录/注册已经被 Go 接管的面**已经丢了** Python 那侧的限流。
  演示里连打 6 次登录不会被拦——这不是缺陷被隐藏，是它本来就不存在。
- **prod 全栈实跑**：X2 的证据是静态配置级（`check_nginx_routes.py` exit 0），没在这台机器上起过
  `docker-compose.prod.yml`（要构建 16.5 GB 的 backend 镜像），属部署阶段。
- **`go-worker`**：只验到"进程能起 + 暴露探针"，调度器属 P3。

## 5. 收口读数（第十七轮，2026-10-15 现场取）

```
全量测试        644 passed（unit 527 / integration 57 / chain 27 / e2e 0 in pytest；Playwright 另有 9 项）
退出标准 X1–X8  pass 8 / fail 0 —— X2 于本轮转 pass（静态配置级）
P0 卡片         P0-0…P0-5、P0-6、P0-7、P0-8 done；P0-9 done（e2e 结构级）
门禁            sync_progress --check / check_contracts / check_frontend / check_route_ownership
                / audit_schema --check-baseline / 两份 golden --check / dev.py gen --check / go vet + go test
```

读数一律现场取。这张表会过期，命令不会。
