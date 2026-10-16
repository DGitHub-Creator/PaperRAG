# P0 环境与复验说明

> 性质：现行运行参考。安装和启动命令统一维护在 [根 README §3](../../README.md#3-安装与开发运行)。
> 旧容器启动序列、实跑表与机器特例已移到 [历史环境记录](../archive/2026-10-16-p0-environment.md)，不作为当前启动指令。

## 1. 前置条件

依赖版本由 .python-version、server/go.mod、package-lock.json 与 uv.lock 定义。
Docker Desktop 必须运行，检查 docker info；权限、网络与磁盘问题按实际错误定位。
密钥与地址由环境配置，示例见 .env.example，不提交本机配置。

## 2. 启动序列

按根 README 启动中间件、显式迁移，再分别运行 Python、Go、前端源码。
dev.py up 现在只启动开发中间件，不构建应用；prod compose 属部署形态。
只验 PG/Redis 时只启动这两个服务；真实 RAG 另需 Milvus 及其依赖和有效模型配置。

## 3. 实跑证据

进度状态见 [progress.json](../progress.json)，本轮实测见 [WORKLOG](../WORKLOG.md)。
历史通过仅证明当时环境，重新部署需复验；不会因换机器照抄旧读数而自动取得 real/e2e 证据。
新证据至少记录运行形态、对象、命令、退出码、实际收集数、故障边界与清理结果。

存储专项用 scripts/verify_storage.py，在新隔离库执行 Go 迁移两遍并运行真实 PG/Redis 测试。
空库成功不证明历史存量兼容；开发库修改先备份，保留备份标识，不提交真实业务数据。

## 4. 排错与资源约束

- Docker 管道不存在：先核实引擎是否运行与上下文是否正确，不直接判定缺系统组件。
- 端口被占：盘点已有进程，只停止自己启动且确认属于本任务的实例。
- 网络不可达：检查包源、代理和证书，禁止关闭 TLS 验证或提交设备设置。
- Windows pytest 临时目录 PermissionError：使用工作区外新建的 TEMP/TMP，保留原始错误，不改断言绕过。
- chain/e2e 写上传文件时用 serve --no-reload，避免文件监视器重启被测服务。
- Playwright 浏览器下载受限时可按实际环境设 E2E_BROWSER_CHANNEL=chrome，默认配置不固化机器特例。
- Milvus 长时任务需要复查 etcd/Milvus 日志与存活，曾发生的磁盘停顿不代表每次都会发生。
- 收工停止本轮启动的服务与容器，不删除卷，不使用重建数据库掩盖迁移失败。

## 5. 与计划的关系

任务定义见 [09](09-milestone-p0.md)，当前拓扑见 [13](../reference/13-frontend-backend-architecture.md)。
容器健康、HTTP 探针、真实数据库、模型请求和浏览器业务分别验收，不互相代替。
