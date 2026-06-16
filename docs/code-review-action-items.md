# PaperRAG 代码审查改进计划

> 基于对项目架构的深入分析，针对 7 项具体缺点制定的可执行改进方案。

---

## 优先级总览

| 优先级 | 缺点 | 预估工作量 | 影响范围 |
|--------|------|-----------|---------|
| P0 | 全局状态耦合 | 2-3 天 | 并发安全 |
| P0 | 前端无构建体系 | 5-7 天 | 可维护性 |
| P1 | Rerank 元数据冗余 | 0.5 天 | 可维护性 |
| P1 | config.py 职责过重 | 1 天 | 可靠性 |
| P1 | 缓存一致性风险 | 1-2 天 | 稳定性 |
| P2 | 测试覆盖 | 3-5 天 | 质量保障 |
| P2 | LLM 调用成本 | 1-2 天 | 成本控制 |

---

## P0-1: 全局状态耦合重构

### 现状

- `agent.py:430` 模块级单例 `agent, model = create_agent_instance()`
- `tools.py` 全局变量 `_RAG_STEP_QUEUE` / `_RAG_STEP_LOOP` 跨线程通信
- `emit_rag_step` 依赖模块级全局变量，多 worker 下完全失效

### 改进方案

#### 1. Agent 实例改为 FastAPI 依赖注入

```python
# backend/core/dependencies.py — 扩展为 Agent 工厂
from contextvars import ContextVar

_agent_instance: ContextVar = ContextVar("_agent_instance")

def get_agent():
    """每次请求从 ContextVar 获取，支持多 worker。"""
    agent = _agent_instance.get(None)
    if agent is None:
        agent, model = create_agent_instance()
        _agent_instance.set(agent)
    return agent
```

#### 2. RAG 步骤队列改为请求级 ContextVar

```python
# backend/services/tools.py — 用 ContextVar 替代全局变量
import contextvars

_rag_step_queue_cv: contextvars.ContextVar[asyncio.Queue | None] = contextvars.ContextVar(
    "_rag_step_queue_cv", default=None
)

def set_rag_step_queue(queue):
    _rag_step_queue_cv.set(queue)

def emit_rag_step(icon, label, detail=""):
    q = _rag_step_queue_cv.get()
    if q is None:
        return
    q.put_nowait({"icon": icon, "label": label, "detail": detail})
```

#### 3. 去掉 `call_soon_threadsafe` 跨线程方案

改用 `asyncio.Queue` 直接在异步上下文中投递（RAG 工具本身在异步链路中执行时无需跨线程）。

### 涉及文件

- `backend/services/tools.py`
- `backend/services/agent.py`
- `backend/core/dependencies.py`

### 验收标准

- 无模块级可变状态
- 并发请求隔离
- 无 `global` 关键字

---

## P0-2: 前端迁移至 Vite + Vue 3 SFC

### 现状

- CDN 方式引入 Vue 3，`frontend/script.js` 单文件 800+ 行
- 无 TypeScript 类型安全，无组件化开发能力

### 改进方案

#### 1. 脚手架搭建

```bash
npm create vite@latest frontend -- --template vue
# 安装依赖：marked, highlight.js, katex, fontawesome
```

#### 2. 模块拆分

```
frontend/src/
├── views/
│   ├── ChatView.vue          # 主聊天界面
│   ├── DocumentsView.vue     # 文档管理
│   └── LoginView.vue         # 登录
├── components/
│   ├── MessageBubble.vue     # 消息气泡 (含 KaTeX)
│   ├── RAGTracePanel.vue     # RAG 追踪折叠面板
│   ├── DocumentUpload.vue    # 上传组件
│   └── StreamingText.vue     # SSE 流式渲染
├── composables/
│   ├── useSSE.ts             # SSE 连接管理
│   ├── useAuth.ts            # JWT 鉴权
│   └── useSessions.ts        # 会话管理
├── stores/
│   └── chat.ts               # Pinia 状态管理
└── App.vue
```

#### 3. 构建产物集成

`vite.config.js` 配置 `build.outDir: 'dist'`，`app.py:89` 已支持 `frontend/dist/` 优先挂载，无需改后端。

#### 4. 迁移节奏

1. 先搭脚手架 + 路由
2. 逐个视图迁移（ChatView 优先）
3. 保持旧 `script.js` 兼容直到所有功能迁移完成

### 涉及文件

- 重写整个 `frontend/` 目录

### 验收标准

- TypeScript 类型安全
- 组件化开发
- 构建产物 <200KB gzip

---

## P1-1: Rerank 元数据汇总抽象

### 现状

`rag_pipeline.py:451-495` 和 `498-542` 是两段近乎相同的 meta 合并代码，约 100 行重复逻辑。

### 改进方案

```python
def _merge_retrieval_meta(target: dict, source: dict, prefix: str = "") -> dict:
    """合并检索元数据到目标字典，避免重复赋值。"""
    for key in (
        "rerank_enabled", "rerank_applied", "rerank_model",
        "rerank_endpoint", "rerank_error", "retrieval_mode",
        "candidate_k", "leaf_retrieve_level", "auto_merge_enabled",
        "auto_merge_applied", "auto_merge_threshold",
        "auto_merge_replaced_chunks", "auto_merge_steps",
        "context_expansion_enabled", "context_expansion_applied",
        "expand_prev_parent", "expand_next_parent",
        "expand_max_chunks", "expanded_chunk_count",
    ):
        val = source.get(key)
        if val is not None:
            existing = target.get(key)
            if key == "rerank_error" and val:
                errors = target.setdefault("_rerank_errors", [])
                errors.append(f"{prefix}:{val}")
            elif key.endswith("_chunks") and isinstance(val, (int, float)):
                target[key] = int(target.get(key) or 0) + int(val)
            else:
                target[key] = existing if existing is not None else val
    return target
```

### 涉及文件

- `backend/rag/rag_pipeline.py`

### 验收标准

- `retrieve_expanded` 中 meta 合并代码从 ~100 行缩减至 ~10 行
- 逻辑无变化

---

## P1-2: config.py 拆分与校验

### 现状

140+ 行集中配置文件，所有模块的 `os.getenv` 混在一起，无分组/校验，缺少类型提示和环境校验。

### 改进方案

#### 1. 按职责拆分为子模块

```
backend/core/
├── config/
│   ├── __init__.py          # 统一导出
│   ├── llm.py               # LLM 模型配置
│   ├── embedding.py         # 嵌入/Rerank 配置
│   ├── database.py          # PostgreSQL/Redis/Milvus
│   ├── retrieval.py         # 检索参数
│   ├── auth.py              # 认证配置
│   └── paths.py             # 路径常量
```

#### 2. 添加启动校验

```python
# backend/core/config/__init__.py
def validate_config():
    """应用启动前校验必填配置，缺失则 fail-fast。"""
    required = {
        "LLM_API_KEY": LLM_API_KEY,
        "LLM_MODEL": LLM_MODEL,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"缺少必填环境变量: {', '.join(missing)}")
```

#### 3. 在 app.py 启动时调用

```python
@app.on_event("startup")
async def _startup():
    validate_config()
    init_db()
```

### 涉及文件

- `backend/core/config.py`（拆分）
- `backend/app.py`（添加校验调用）

### 验收标准

- 缺少 API Key 时启动即报错而非运行时失败
- 配置按职责分离

---

## P1-3: 缓存一致性与降级

### 现状

- Redis 挂掉时缓存操作静默失败但无重试/熔断
- save 操作中清缓存+写缓存非原子

### 改进方案

#### 1. Cache 类添加重试与熔断

```python
# backend/services/cache.py
import time

class Cache:
    _failure_count = 0
    _circuit_open_until = 0.0
    CIRCUIT_THRESHOLD = 5
    CIRCUIT_TIMEOUT = 60.0  # 秒

    def _is_circuit_open(self) -> bool:
        if self._failure_count >= self.CIRCUIT_THRESHOLD:
            if time.time() < self._circuit_open_until:
                return True
            self._failure_count = 0  # 半开状态
        return False

    def _on_failure(self):
        self._failure_count += 1
        if self._failure_count >= self.CIRCUIT_THRESHOLD:
            self._circuit_open_until = time.time() + self.CIRCUIT_TIMEOUT
            logger.warning("Redis 熔断开启，%ds 后重试", self.CIRCUIT_TIMEOUT)

    def get_json(self, key: str):
        if self._is_circuit_open():
            return None
        try:
            result = ...
            self._failure_count = 0  # 成功重置
            return result
        except Exception:
            self._on_failure()
            return None
```

#### 2. 对话保存改为先写后清

```python
# agent.py ConversationStorage.save
# 先写新缓存，再清旧缓存（减少不一致窗口）
cache.set_json(self._messages_cache_key(...), serialized)
cache.set_json(self._sessions_cache_key(user_id), new_session_list)  # 重建列表
# 不再先 delete 再 set
```

### 涉及文件

- `backend/services/cache.py`
- `backend/services/agent.py`

### 验收标准

- Redis 故障时应用正常降级（走数据库）
- 连续失败后自动熔断避免雪崩

---

## P2-1: 测试覆盖

### 现状

无 `tests/` 目录，零测试。

### 改进方案

#### 目录结构

```
tests/
├── conftest.py              # fixtures: 测试 DB、Mock Redis、Mock Milvus
├── test_rag_pipeline.py     # RAG 状态图单元测试（mock LLM）
├── test_academic_cleaner.py # 学术清洗规则测试（fixture PDF 片段）
├── test_document_loader.py  # 分块逻辑测试
├── test_embedding.py        # BM25 增量更新测试
├── test_agent.py            # Agent 对话流程测试（mock LLM）
├── test_cache.py            # 缓存读写与降级测试
├── test_auth.py             # JWT 鉴权测试
└── test_api.py              # API 端点集成测试（httpx AsyncClient）
```

#### 关键策略

- LLM 调用全部 mock（`unittest.mock.patch`），确保测试快速且无外部依赖
- 数据库测试使用 SQLite in-memory 或 testcontainers
- RAG pipeline 测试用 fixture 验证 grade→rewrite→retrieve 循环逻辑

### 涉及文件

- 新增 `tests/` 目录
- 修改 `pyproject.toml`（确认 test 依赖）

### 验收标准

- 核心模块覆盖 >70%
- CI 可运行

---

## P2-2: LLM 调用成本控制

### 现状

- 最坏情况 10+ 次 LLM 调用/查询，无预算控制
- 每轮查询最多调用 4 次 LLM（grader + router + HyDE/stepback + 最终生成）
- `MAX_RAG_RETRIES=3` 意味着最坏情况 12+ 次 LLM 调用

### 改进方案

#### 1. 添加调用计数器与预算

```python
# backend/core/config.py
MAX_LLM_CALLS_PER_QUERY = int(os.getenv("MAX_LLM_CALLS_PER_QUERY", "6"))
LLM_COST_PER_1K_TOKENS = float(os.getenv("LLM_COST_PER_1K_TOKENS", "0.01"))
MAX_COST_PER_QUERY = float(os.getenv("MAX_COST_PER_QUERY", "0.05"))
```

#### 2. 在 RAG pipeline 注入预算检查

```python
class RAGBudgetExceeded(Exception):
    pass

def check_budget(state: RAGState):
    calls = state.get("llm_call_count", 0)
    if calls >= MAX_LLM_CALLS_PER_QUERY:
        logger.warning("LLM 调用预算耗尽 (%d/%d)", calls, MAX_LLM_CALLS_PER_QUERY)
        emit_rag_step("💰", "已达调用预算上限，跳过重写")
        return "generate_answer"
    return state.get("route")
```

#### 3. 简化重写策略

复杂问题跳过 step_back+hyde 双重消耗：

```python
# rewrite_question_node 中
if strategy == "complex":
    # complex 策略消耗 2 次 LLM（step_back + hyde），预算不足时降级为 hyde
    if state.get("llm_call_count", 0) >= MAX_LLM_CALLS_PER_QUERY - 2:
        strategy = "hyde"
```

### 涉及文件

- `backend/core/config.py`
- `backend/rag/rag_pipeline.py`
- `backend/services/tools.py`

### 验收标准

- 单次查询 LLM 调用不超过配置上限
- 可选的 token/成本追踪日志

---

## 实施顺序建议

```
Week 1:  P0-1 全局状态耦合重构（阻塞并发能力）
         P1-2 config.py 拆分校验（基础设施）
Week 2:  P0-2 前端迁移脚手架 + 路由（启动前端重构）
         P1-1 Rerank 元数据抽象（快速收益）
Week 3:  P1-3 缓存降级
         P2-2 LLM 成本控制
Week 4+: P0-2 前端逐视图迁移
         P2-1 测试覆盖（持续投入）
```
