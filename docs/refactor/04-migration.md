# 04 — 迁移路线

> 路线：**A0 基线修复与数据可信化 → A Go 主后端接管 → B Frontier 与科研 Agent → C 双图及自主探索**。
> 排期前提（决策 Q8）：solo，每周 15–20 小时。计划原文的 8 周按全职强度估算，**在本投入下应读作 14–18 周**，且不含 A0。

## 0. 为什么插入 A0

计划的里程碑 A 验收是"原有论文问答功能保持可用"。审计证明当前主干：登录/注册在浏览器里抛 `ReferenceError`、异步上传 URL 打不通、chunk 正文只存在于会截断的 Milvus 字段里（03 §1–2）。

不修的后果：Go 接管后无法区分**迁移引入的回归**与**既有故障**，"测试全绿"失去信号价值（现状 280 项 mock 测试对这三处完全盲），里程碑 A 的验收标准客观上不可判定。A0 的目标就是把验收标准变成可判定的。

## 1. 里程碑总表

| 里程碑 | 目标 | 进入条件 | 退出条件（全部可机检） | 估时 |
| --- | --- | --- | --- | --- |
| **A0** 基线修复与数据可信化 | 旧系统真的可用 + chunk 真相进 PG + 真实链路测试存在 | 无 | ① `npm run typecheck` 0 error 且进 CI；② 浏览器 E2E：登录→上传→入库→检索→问答→引用展示 全绿；③ `paper_chunks` 覆盖全部叶子块且 `content_hash` 可校验；④ 无静默 `create_all`；⑤ refresh-token 混用与默认密钥/邀请码问题关闭；⑥ 公式链路测试通过 | 3–4 周 |
| **A** Go 主后端接管 | 13 条业务接口 + SSE/WS 由 Go 服务，Python 退为内网 AI Core | A0 退出条件全绿 | ① Go 覆盖 13 条 + `health/ready/metrics`；② 跨语言契约测试（`contracts/`）通过；③ 旧 Python API 只内网可达；④ A0 的 E2E **不改测试代码**在 Go 后端上复跑全绿；⑤ 弃用接口逐条留有调用方审计记录 | 4–5 周 |
| **B** Frontier 与科研 Agent | Run/Task 三层 + Frontier + Worker + Planner/Discovery/Reader/Writer + 报告 | A 退出 + 学术检索 Provider 可用 | ① 固定多阶段工作流端到端跑通并产出带引用报告；② 崩溃恢复测试（Go/Python 强杀）通过；③ 幂等：重复派发不产生重复实体；④ 暂停/继续/取消正常；⑤ 预算耗尽产出 `PARTIAL` 报告并列出未解决问题 | 5–6 周 |
| **C** 双图与自主探索 | Knowledge/Exploration 双图 + Analyst/Verifier/Explorer | B 退出 | ① 任一发现可回溯 研究问题→任务→论文→结论→证据→PDF 原文；② 强语义关系 100% 绑定 evidence；③ Explorer 上线前已有稳定的固定工作流基线 | 4+ 周 |

**先 A、B 再双图与自主 Explorer**（计划 §末尾建议，已采纳）。里程碑 A 明确要求**跨语言契约测试**（决策 Q8）。

## 2. A0 详细任务

见 [06-milestone-a0.md](06-milestone-a0.md)（文件级清单、依赖顺序、验收标准）。

## 3. 里程碑 A 的切换策略（L5 渐进）

### 3.1 单一写者原则

任何时刻，同一份业务状态只允许一个进程写。切换按**接口逐个**完成，不按"整体替换"：

```
阶段 1  Go 反向代理      浏览器 → Go → Python        Go 只做鉴权透传与 trace_id 注入，验证路由/错误信封/流式形状
阶段 2  Go 接管读接口    /auth/me /sessions /documents（Go 直读 PG）
阶段 3  Go 接管写接口    /auth/register /login /sessions DELETE
阶段 4  Go 接管流式      /chat/stream + /ws/chat（Go 门面，内部调 AI Core execute）
阶段 5  Python 退内网    移除静态挂载(app.py:141)、移除业务 API、只留 /internal/v1/ai/*
```

每阶段一个独立提交、一次 E2E 复跑、一次回滚演练。

### 3.2 必须逐字节保持的兼容语义（01 §6）

`{"detail": ...}` 错误信封（429 是否统一为 `detail` 在 A0 结束后定案，因为改了会影响 `useChat.ts`/`AuthPanel` 的错误处理）· 无分页的全量列表形状 · PBKDF2 哈希格式（Go 必须能验旧密码）· JWT claims（`sub`=用户名、`role`、`exp`、refresh 带 `type`）· localStorage 键名 `accessToken`/`currentUser` · WS query `token` · SSE 事件 `content/rag_step/citations/trace/error` + `[DONE]` · `rag_trace` 的两种形状（REST 过滤 / 流式原样）。

### 3.3 数据兼容

PostgreSQL 结构收编与 chunk 重建见 [05-database-migration.md](05-database-migration.md)。Milvus 保持"可重建"定位：Go 侧记录 `index_state`，索引失败**不影响**文献元数据（计划 §10.4）。

## 4. 回滚设计

| 里程碑 | 回滚点 | 手段 |
| --- | --- | --- |
| A0 | 每个提交即回滚点；chunk 重建脚本写新表不动旧表 | `docker compose` 起旧镜像；重建脚本支持 `--dry-run` 与按 filename 删除本次写入 |
| A | 阶段 4/5 前保留 `backend` 面向浏览器的完整能力 | 切 nginx `location /api/` upstream 从 go-api 回 Python（一条配置，非代码回退）；Go 写的表 Python 侧只读，不冲突 |
| B | Frontier 关闭时退回"固定顺序执行"开关（同一 worker 二进制，`scheduler.mode=sequential`） | 事件日志与任务表保留，重放即可 |
| C | Explorer/双图关闭后 B 的报告链路不受影响（图只读增强） | `knowledge.enabled=false` |

**禁止的回滚方式**：删表、清 Milvus 集合后重建、`git reset --hard` 丢掉迁移脚本。

## 5. 兼容性风险登记

| 风险 | 触发 | 缓解 |
| --- | --- | --- |
| Go 验不了旧密码 | PBKDF2 base64 编码差异（标准 vs urlsafe）、盐长度 | A0 写一份"旧哈希 golden vectors"，Go 单测必须逐条通过后才允许接管 `users` |
| SSE 形状漂移 | Go 侧缓冲/flush 策略、nginx `X-Accel-Buffering`（现由 `chat.py:75-79` 显式关掉） | 契约测试对比 Python 与 Go 的字节级帧序列 |
| 同一 Run 双写 | 阶段 2–4 期间 Python 仍在写 `chat_messages` | 切换窗口内对该接口只允许单边写；用 feature flag + 写路径断言 |
| 旧库无 `alembic_version` | `init_db` 曾静默 `create_all` | 05 §2 的先核查后收编，禁止重复建表 |
| naive 时间戳语义不明 | 历史数据混用 `utcnow()` 与 `now(UTC)` | 05 §4 的先验证后转换 |
| 弃用接口打破外部使用者 | 直接删 12 条无人调用接口 | 03 §5 的逐条调用方审计记录，先返回 `Deprecation` 头再下线 |
| 前端只依赖 13 条 | 误判其余接口无用 | 以 `useAuth/useChat/useDocuments/useSessions/useWebSocket` 的实调为唯一依据（01 §3 表） |

## 6. 每阶段工作纪律（计划 §15，采纳并加严）

1. 读相关源码 → 2. 列出本阶段真实涉及文件与接口 → 3. 说明改动原因与影响面 → 4. **先写测试或基线** → 5. 最小可运行改动 → 6. 跑单测 + 集成 + E2E → 7. 复查旧 RAG 功能 → 8. 更新 `contracts/` 与架构文档 → 9. **独立提交**（按关注点分批，一个提交一件事）→ 10. 汇总完成内容/测试/风险/下一步。

原则：不以重构名义删除成熟功能 · 不引入不必要框架 · 不大量复制旧代码 · 不建两个全局调度器 · 不把 LangGraph State 当业务库 · 不把模型输出当可信事实 · **不在没有真实链路测试的情况下宣布重构完成**。

提交与推送节奏沿用既有约定：本轮改动先按关注点分批提交，统一 push 前 `git fetch`；跨分叉时 rebase 而非合并提交（需先确认）。

## 7. 排期压缩选项

若需缩短：A0 内 G1–G6、G9（前端 2 项 + 鉴权 3 项 + 限流 + 静默建表，合计约 S/M 档）与真实 E2E 骨架是**不可压缩项**，因为它们决定后续所有验收的可判定性；G10–G12、G16、G18（chunk 可信化，约 L 档）可以推到 A 的阶段 3 之前，但期间**不得**开始任何 evidence/定位相关的功能开发（否则会把截断文本当原文用）。
