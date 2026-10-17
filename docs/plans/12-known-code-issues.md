# 12 — 代码问题台账

> 性质：动态整改清单。核验日期：2026-10-16，对应本轮重构工作区。
> 历史问题叙述与当时判定保留在 [整理前快照](../archive/2026-10-16-12-known-code-issues.md)。
> 本表不代替阶段任务状态；进度见 [progress.json](../progress.json)，验收读数见 [WORKLOG](../WORKLOG.md)。

## A. 未解决或尚缺验收

| ID | 当前结论 | 后续工作与验收 |
| --- | --- | --- |
| C7 | 数据可信化未完成：全文仍受 Milvus 字段长度限制，学术元数据未完整入库 | 按 P2 设计构建 PG 正文真相与位置映射；真实 PDF 全文、公式和引用回溯验收 |
| C9 | 上传/删除任务有内存与 Redis 两种状态实现；终态及并发更新已修，执行恢复未实现 | Go/PG 编排仍属计划；验证进程退出后的任务恢复，不能把 Redis 状态存留当执行续跑 |
| C10 | 双图与 Evidence Registry 未完成；存在模型或页面不等于能力实现 | 按已确认版本范围实施，真实读写与证据定位验收 |

| C28 | 曾出现 etcd 磁盘停顿致 Milvus 退出；本轮未复验长时间索引负载 | 检查磁盘与日志，隔离环境做长时读写；不要未经迁移直接换卷丢元数据 |
| C30 | ACL 已区分 present/planned 并与迁移机检；当前写入偏差已登记 | 索引必要性、未穷尽调用方和 PG 实际 GRANT 仍待审查，present 不代表目标权限已执行 |


| C36 | 注册 role 的缺省/null/空串/root 与 admin 关闭分支已真实对拍 | 有效/错误邀请码、重复用户及其余非法入参仍须逐项对拍，不能据此删除旧面 |
| C37 | AIExecution 已落既有 PG 表，幂等/租约/终态及重新实例化读取通过；执行恢复仍缺 | 验证进程中断、重启后的调度与恢复；不能把记录持久化等同于可靠任务投递 |
| Q5 | Python 首组 8 包已升级；当前安装环境审计仍有 24 包/118 条公告，待逐项核对适用性/兼容修复 | 见规范化 TODO R12 分组与清单；前端已修到 npm 报告 0 不代表后端安全 |
| Q1 | 文档索引跨 PG/Milvus/文件/BM25 不具备原子提交 | 当前解析失败不删旧索引，但写入阶段失败仍可能留下部分状态；需恢复策略与故障注入验收 |
| Q2 | SSE 当前为完整答案事件，非逐 token 输出 | 确认产品要求后实现与验证首 token 延迟、取消、存储失败语义，保持对外口径准确 |
| Q3 | 部分超长解析/检索/脚本模块仍需职责审查 | 根据重复、复杂度和实际故障拆分，不为行数制造新层 |

## B. 已修复的实现问题

“已修复”只覆盖本行范围；不据此把所属 P1/P2 卡片整体标为 done。

| ID | 当前结论 | 证据入口 |
| --- | --- | --- |
| C1 | live 导出含列，离线校验长度/空值/默认值有无；ORM 比较另含默认值内容 | scripts/audit_schema.py、schema_compare.py、tests/unit/test_audit_schema.py；离线不等于当前库一致 |
| C2 | up/down 注释处理已统一 | test_audit_schema.py |
| C3–C4 | sqlc 已由临时 schema 切换到迁移基线，默认值不由 Go 类型 diff 证明 | server/sqlc.yaml、dev.py gen --check、audit_schema.py |
| C5 | ai_executions 迁移已存在并执行；当前 PG 存储证据见 C37 | server/migrations/000002、verify_storage.py |
| C8 | 已有 chain/e2e 用例；本轮未启动完整 RAG 时相关用例会跳过 | tests/chain、frontend/e2e；零收集或 skipped 均不能作为真实验收 |
| C12 | 环境模板行内注释问题已修 | .env.example |
| C13 | 旧多阶段镜像 target 问题已处置；开发形态已变更 | dev/prod compose 与 check_nginx_routes.py |
| C14 | 过期环境状态已纠正 | progress.json；不要再复制旧读数 |
| C16–C17 | 验收脚本已存在；包缺失、选择器零收集的退出码不能忽略 | scripts/ 与相关单元测试 |
| C18 | Go 迁移执行器已接线，显式 migrate-go | server/cmd/migrate、scripts/verify_storage.py |
| C19 | 现行文档入口本轮再次整理，动态资料移出规则层 | docs/README.md、AGENTS.md、check_repository.py；不代表每段历史描述变成现状 |
| C22 | Go 测试判据已补包路径 | 当前任务卡与 server/internal/auth |
| C23 | 对外错误信封大小写等兼容要求有回归 | Go auth/httpapi 与链路用例 |
| C25 | PG/Redis 镜像在 dev/prod 均钉 digest | 两份 compose；其余版本镜像不据此推定供应链审查已完成 |
| C26 | compose 顶层固定项目名 | 两份 compose |
| C27 | 生产插值须显式 --env-file；生产密钥文件不入库 | prod compose 头说明、.gitignore |
| C29 | dev compose 仅中间件，部署形态单列 | check_nginx_routes.py |
| C31 | 路由归属检查已补；不再假定 Python 与 Go 探针路径完全相同 | contracts/route-ownership.md、check_route_ownership.py；可达性仍需运行验证 |
| C32 | Python 限流端点签名已修并有静态回归 | tests/unit/test_rate_limit_signatures.py |
| C35 | 已移除会话缓存，Go 删除后 Python 直接读 PG，不再等待 TTL | conversation_storage.py、test_conversation_postgres.py；全栈 HTTP 并发仍需补验 |

### 本批新增修复

| ID | 当前结论 | 证据入口 |
| --- | --- | --- |
| C21 | 注册 role 契约、TS 与 Python DTO 对齐；缺省/null/空串/root 折叠为 user，admin 关闭分支两侧一致 | check_contracts.py 漂移负向用例、真实 register_parity |
| C33 | Go/Python 真实登录第 21 次 429，伪造 X-Forwarded-For 无效；所有项目启动入口禁用 Uvicorn 代理头重写 | verify_storage.py --http、rate_limit chain、dev CLI 回归 |
| C34 | 新追踪写前校验并投影；坏历史仅追踪置 null，保留正文且告警；引用随答案保存并历史回显 | 真实 go_read_legacy_trace、HTTP 与浏览器回归 |
| Q4 | 修复先 Go 迁移再启动 Python 的重复建表；clean 版本 ≥3 只读检查，旧库保留 Alembic | 真空库启动测试、database 单测、隔离 HTTP 全链 |

## C. 澄清与环境历史

| ID | 结论 |
| --- | --- |
| C6 | dev 中没有 Go 应用容器符合源码运行约定；prod 容器部署另算 |
| C11 | 端口、IPv6 监听与代理前缀是配置事实，操作前读现行配置，不写死为机器通则 |
| C15 | 历史临时目录权限问题不是产品缺陷；保留忽略规则，不在工作区生成受污染的 basetemp |
| C20 | 早期原库曾丢失，不能用后来重建的库证明那个原库兼容；本轮备份只覆盖本轮开发库 |
| C24 | 项目目前使用 versitygw 提供 S3；曾经的镜像取回失败只作为历史，不宣称当前所有源均不可用 |

## 维护规则

新增问题给出复现、影响、修复范围和验收入口；修复后移动状态，不保留多个互相矛盾的“当前结论”。
未运行、跳过和未实现分别记录。历史证据原文保留在档案，当前台账只维护可行动结论。
