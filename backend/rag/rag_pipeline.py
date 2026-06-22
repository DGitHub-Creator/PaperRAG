"""RAG 工作流状态图 —— 基于 LangGraph 的检索-评分-重写-扩展管道。

工作流节点:
    1. retrieve_initial  — 混合检索 + Rerank + Auto-merge + Context Expansion
    2. grade_documents   — 结构化输出评分（yes/no），判定相关性
    3. rewrite_question  — 路由选择重写策略（step_back / hyde / complex）
    4. retrieve_expanded — 多策略扩展检索 + 去重 + 统一元数据

多轮检索:
    grade_documents → rewrite_question → retrieve_expanded → grade_documents → ...
    最多循环 MAX_RAG_RETRIES（默认 3）次，达到上限后强制进入 END。

流程图:
    retrieve_initial → grade_documents ──[yes]→ END(生成回答)
                                      ──[no]→ rewrite_question → retrieve_expanded ──→ grade_documents(循环)
                                    [已达上限] → END
"""

from typing import Literal, TypedDict

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from backend.core.config import MAX_RAG_RETRIES
from backend.core.dependencies import get_grader_model, get_router_model
from backend.core.logging_config import get_logger
from backend.rag.rag_utils import (
    generate_hypothetical_document,
    retrieve_documents,
    step_back_expand,
)
from backend.services.tools import emit_rag_step

load_dotenv()
logger = get_logger(__name__)

# ── Prompt 与结构化输出 ───────────────────────────────────────────

# 相关性评分 Prompt：判断检索文档与用户问题的语义/关键词关联
GRADE_PROMPT = (
    "You are a grader assessing relevance of a retrieved document to a user question. \n "
    "Here is the retrieved document: \n\n {context} \n\n"
    "Here is the user question: {question} \n"
    "If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n"
    "Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question."
)


class GradeDocuments(BaseModel):
    """相关性评分结构化输出 —— binary yes/no。"""

    binary_score: str = Field(
        description="Relevance score: 'yes' if relevant, or 'no' if not relevant"
    )


class RewriteStrategy(BaseModel):
    """查询扩展策略选择 —— step_back / hyde / complex 三选一。"""

    strategy: Literal["step_back", "hyde", "complex"]


# ── RAG 状态 ──────────────────────────────────────────────────────

class RAGState(TypedDict):
    """LangGraph 状态字典 —— 在各节点间传递的公共状态。

    Attributes:
        question: 用户原始问题
        query: 当前检索查询（初始=question，可能被重写覆盖）
        context: 格式化后的检索上下文（拼接所有命中文档）
        docs: 命中的文档列表
        route: 评分后的路由决策 ('generate_answer' | 'rewrite_question')
        expansion_type: 查询扩展策略名称
        expanded_query: 扩展后的查询文本
        step_back_question: 退步问题（step-back 策略）
        step_back_answer: 退步问题答案（step-back 策略）
        hypothetical_doc: 假设性文档（HyDE 策略）
        rag_trace: 完整的 RAG 追踪元数据（返回给前端）
    """
    question: str
    query: str
    context: str
    docs: list[dict]
    route: str | None
    expansion_type: str | None
    expanded_query: str | None
    step_back_question: str | None
    step_back_answer: str | None
    hypothetical_doc: str | None
    rag_trace: dict | None
    retry_count: int
    """当前多轮检索的重试次数（0=初次，达到 MAX_RAG_RETRIES 后强制结束）。"""
    accumulated_docs: list[dict]
    """多轮检索中累积的所有文档（去重后）。"""
    conversation_history: str | None
    """历史对话摘要（最近 2 轮 Q&A），用于上下文感知检索。"""


def _format_docs(docs: list[dict]) -> str:
    """将文档列表格式化为 LLM 可理解的上下文文本。

    每个文档格式: [序号] 文件名 (第N页): 正文 ...
    文档间以 --- 分隔。
    """
    if not docs:
        return ""
    chunks = []
    for i, doc in enumerate(docs, 1):
        source = doc.get("filename", "Unknown")
        page = doc.get("page_number", "N/A")
        text = doc.get("text", "")
        chunks.append(f"[{i}] {source} (Page {page}):\n{text}")
    return "\n\n---\n\n".join(chunks)


# ── 节点 1: 初始检索 ─────────────────────────────────────────────

def retrieve_initial(state: RAGState) -> RAGState:
    """初次检索节点：执行完整的四阶段检索流程。

    流程:
        1. 若有历史对话，拼接历史摘要 → 增强查询语境
        2. 调用 retrieve_documents(query) → Hybrid/Dense + Rerank + Merge + Expand
        3. 格式化检索结果为 LLM 上下文
        4. 构建 RAG trace（检索元数据）
        5. 通过 emit_rag_step 实时推送步骤到前端

    Args:
        state: RAGState（从 question 字段读取用户问题，可含 conversation_history）。

    Returns:
        更新后的 state（含 docs、context、rag_trace）。
    """
    query = state["question"]
    history = state.get("conversation_history") or ""

    # 拼接历史上下文（增强检索语境）
    augmented_query = query
    if history:
        augmented_query = f"{history}\n\n当前问题: {query}"
        emit_rag_step("📜", "检测到历史对话上下文", "已拼接至查询")
        logger.debug("拼接历史上下文: history_len=%d chars", len(history))
    emit_rag_step("\U0001f50d", "正在检索知识库...", f"查询: {query[:50]}")

    # 执行完整检索流程（使用增强查询）
    retrieved = retrieve_documents(augmented_query, top_k=5)
    results = retrieved.get("docs", [])
    retrieve_meta = retrieved.get("meta", {})

    # 格式化上下文
    context = _format_docs(results)

    # 推送检索步骤细节
    emit_rag_step(
        "\U0001f9f1", "三级分块检索",
        (
            f"叶子层 L{retrieve_meta.get('leaf_retrieve_level', 3)} 召回，"
            f"候选 {retrieve_meta.get('candidate_k', 0)}"
        ),
    )
    emit_rag_step(
        "\U0001f9e9", "Auto-merging 合并",
        (
            f"启用: {bool(retrieve_meta.get('auto_merge_enabled'))}，"
            f"应用: {bool(retrieve_meta.get('auto_merge_applied'))}，"
            f"替换片段: {retrieve_meta.get('auto_merge_replaced_chunks', 0)}"
        ),
    )
    if retrieve_meta.get("context_expansion_applied"):
        emit_rag_step(
            "\U0001f4d6", "上下文扩展",
            f"扩展至 {retrieve_meta.get('expanded_chunk_count', 0)} 块"
        )

    emit_rag_step(
        "✅", f"检索完成，找到 {len(results)} 个片段",
        f"模式: {retrieve_meta.get('retrieval_mode', 'hybrid')}",
    )

    # 构建完整 RAG trace
    rag_trace = {
        "tool_used": True,
        "tool_name": "search_knowledge_base",
        "query": query,
        "expanded_query": query,
        "retrieved_chunks": results,
        "initial_retrieved_chunks": results,
        "retrieval_stage": "initial",
        "rerank_enabled": retrieve_meta.get("rerank_enabled"),
        "rerank_applied": retrieve_meta.get("rerank_applied"),
        "rerank_model": retrieve_meta.get("rerank_model"),
        "rerank_endpoint": retrieve_meta.get("rerank_endpoint"),
        "rerank_error": retrieve_meta.get("rerank_error"),
        "retrieval_mode": retrieve_meta.get("retrieval_mode"),
        "candidate_k": retrieve_meta.get("candidate_k"),
        "leaf_retrieve_level": retrieve_meta.get("leaf_retrieve_level"),
        "auto_merge_enabled": retrieve_meta.get("auto_merge_enabled"),
        "auto_merge_applied": retrieve_meta.get("auto_merge_applied"),
        "auto_merge_threshold": retrieve_meta.get("auto_merge_threshold"),
        "auto_merge_replaced_chunks": retrieve_meta.get("auto_merge_replaced_chunks"),
        "auto_merge_steps": retrieve_meta.get("auto_merge_steps"),
        "context_expansion_enabled": retrieve_meta.get("context_expansion_enabled"),
        "context_expansion_applied": retrieve_meta.get("context_expansion_applied"),
        "expand_prev_parent": retrieve_meta.get("expand_prev_parent"),
        "expand_next_parent": retrieve_meta.get("expand_next_parent"),
        "expand_max_chunks": retrieve_meta.get("expand_max_chunks"),
        "expanded_chunk_count": retrieve_meta.get("expanded_chunk_count"),
    }

    logger.info("初次检索完成: %d docs, mode=%s", len(results), retrieve_meta.get("retrieval_mode"))
    return {
        "query": query,
        "docs": results,
        "context": context,
        "rag_trace": rag_trace,
        "retry_count": 0,
        "accumulated_docs": results,
    }


# ── 节点 2: 相关性评分门控 ───────────────────────────────────────

def grade_documents_node(state: RAGState) -> RAGState:
    """相关性评分节点：使用 LLM 结构化输出判断检索质量。

    评分逻辑:
        - 若 grader 模型不可用 → 默认走 rewrite_question 路径
        - 若 binary_score == 'yes' → 直接进入 END（生成回答）
        - 若 binary_score == 'no' → 进入 rewrite_question 节点
        - 若重试次数已达 MAX_RAG_RETRIES → 强制进入 END（避免无限循环）

    Args:
        state: RAGState（含 question、context、retry_count 字段）。

    Returns:
        更新后的 state（含 route 决策和评分结果）。
    """
    grader = get_grader_model()
    retry_count = state.get("retry_count", 0)

    # 已达最大重试次数 → 强制生成回答
    if retry_count >= MAX_RAG_RETRIES:
        emit_rag_step("🔄", f"已达最大重试次数（{MAX_RAG_RETRIES}），强制进入生成")
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update({
            "grade_score": "max_retries",
            "grade_route": "generate_answer",
            "rewrite_needed": False,
            "retry_count": retry_count,
        })
        logger.info("多轮检索已达上限（%d），强制生成回答", MAX_RAG_RETRIES)
        return {"route": "generate_answer", "rag_trace": rag_trace}

    emit_rag_step("\U0001f4ca", "正在评估文档相关性...")

    if not grader:
        # 无评分模型时默认重写（保守策略）
        grade_update = {
            "grade_score": "unknown",
            "grade_route": "rewrite_question",
            "rewrite_needed": True,
        }
        rag_trace = state.get("rag_trace", {}) or {}
        rag_trace.update(grade_update)
        logger.info("评分模型不可用，默认进入重写流程")
        return {"route": "rewrite_question", "rag_trace": rag_trace, "retry_count": retry_count + 1}

    question = state["question"]
    context = state.get("context", "")

    # 结构化输出评分
    prompt = GRADE_PROMPT.format(question=question, context=context)
    response = grader.with_structured_output(GradeDocuments).invoke(
        [{"role": "user", "content": prompt}]
    )

    score = (response.binary_score or "").strip().lower()
    route = "generate_answer" if score == "yes" else "rewrite_question"

    if route == "generate_answer":
        emit_rag_step("✅", "文档相关性评估通过", f"评分: {score}")
    else:
        emit_rag_step("⚠️", "文档相关性不足，将重写查询", f"评分: {score}")

    grade_update = {
        "grade_score": score,
        "grade_route": route,
        "rewrite_needed": route == "rewrite_question",
    }
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update(grade_update)

    logger.info("相关性评分: %s → %s (第 %d 轮)", score, route, retry_count)
    return {"route": route, "rag_trace": rag_trace, "retry_count": retry_count + 1}


# ── 节点 3: 查询重写 ─────────────────────────────────────────────

def rewrite_question_node(state: RAGState) -> RAGState:
    """查询重写节点：根据 LLM 路由选择最佳扩展策略。

    策略说明:
        - step_back: 生成退步问题 + 答案，适合包含具体术语/细节的问题
        - hyde: 生成假设性文档，适合模糊、概念性的问题
        - complex: 同时执行 step_back 和 hyde，适合多步骤复杂问题

    路由失败时默认使用 step_back（最保守、最通用的策略）。
    若有历史对话上下文，会将其拼入路由 prompt 辅助决策。

    Args:
        state: RAGState（含 question 字段，可含 conversation_history）。

    Returns:
        更新后的 state（含 expansion_type、expanded_query、rewrite_strategy 等）。
    """
    question = state["question"]
    history = state.get("conversation_history") or ""
    emit_rag_step("✏️", "正在重写查询...")

    # LLM 路由选择策略
    router = get_router_model()
    strategy = "step_back"

    if router:
        context_hint = ""
        if history:
            context_hint = f"\n历史对话上下文（仅供参考）: {history[:300]}"
        prompt = (
            "请根据用户问题选择最合适的查询扩展策略，仅输出策略名。\n"
            "- step_back：包含具体名称、日期、代码等细节，需要先理解通用概念的问题。\n"
            "- hyde：模糊、概念性、需要解释或定义的问题。\n"
            "- complex：多步骤、需要分解或综合多种信息的复杂问题。\n"
            f"用户问题：{question}{context_hint}"
        )
        try:
            decision = router.with_structured_output(RewriteStrategy).invoke(
                [{"role": "user", "content": prompt}]
            )
            strategy = decision.strategy
            logger.info("路由决策: %s", strategy)
        except Exception as e:
            logger.warning("策略路由失败: %s，默认使用 step_back", e)
            strategy = "step_back"

    # 根据策略执行扩展
    expanded_query = question
    step_back_question = ""
    step_back_answer = ""
    hypothetical_doc = ""

    if strategy in ("step_back", "complex"):
        emit_rag_step("\U0001f9e0", f"使用策略: {strategy}", "生成退步问题")
        step_back = step_back_expand(question)
        step_back_question = step_back.get("step_back_question", "")
        step_back_answer = step_back.get("step_back_answer", "")
        expanded_query = step_back.get("expanded_query", question)

    if strategy in ("hyde", "complex"):
        emit_rag_step("\U0001f4dd", "HyDE 假设性文档生成中...")
        hypothetical_doc = generate_hypothetical_document(question)
        logger.debug("HyDE 文档长度: %d 字符", len(hypothetical_doc))

    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({
        "rewrite_strategy": strategy,
        "rewrite_query": expanded_query,
    })

    return {
        "expansion_type": strategy,
        "expanded_query": expanded_query,
        "step_back_question": step_back_question,
        "step_back_answer": step_back_answer,
        "hypothetical_doc": hypothetical_doc,
        "rag_trace": rag_trace,
    }


# ── 节点 4: 扩展检索 ─────────────────────────────────────────────

def retrieve_expanded(state: RAGState) -> RAGState:
    """扩展检索节点：使用重写后的查询执行多路检索 + 去重合并。

    根据 expansion_type 执行对应策略:
        - hyde/complex: 用假设性文档检索
        - step_back/complex: 用退步问题扩展查询检索
        - 两路结果去重后统一排序

    汇总所有元数据字段到 rag_trace，包括 context_expansion 信息。

    Args:
        state: RAGState（含重写后的查询/文档）。

    Returns:
        更新后的 state（含最终 docs、context、完整 rag_trace）。
    """
    strategy = state.get("expansion_type") or "step_back"
    emit_rag_step("\U0001f504", "使用扩展查询重新检索...", f"策略: {strategy}")

    # ── 汇总变量 ────────────────────────────────────────────────
    results: list[dict] = []
    rerank_applied_any = False
    rerank_enabled_any = False
    rerank_model = None
    rerank_endpoint = None
    rerank_errors: list[str] = []
    retrieval_mode = None
    candidate_k = None
    leaf_retrieve_level = None
    auto_merge_enabled = None
    auto_merge_applied = False
    auto_merge_threshold = None
    auto_merge_replaced_chunks = 0
    auto_merge_steps = 0

    ctx_expansion_enabled = None
    ctx_expansion_applied = False
    expand_prev_parent = None
    expand_next_parent = None
    expand_max_chunks = None
    expanded_chunk_count = 0

    # ── HyDE 路径 ──────────────────────────────────────────────
    if strategy in ("hyde", "complex"):
        hypothetical_doc = (
            state.get("hypothetical_doc")
            or generate_hypothetical_document(state["question"])
        )
        retrieved_hyde = retrieve_documents(hypothetical_doc, top_k=5)
        results.extend(retrieved_hyde.get("docs", []))
        hyde_meta = retrieved_hyde.get("meta", {})

        emit_rag_step(
            "\U0001f9f1", "HyDE 三级检索",
            (
                f"L{hyde_meta.get('leaf_retrieve_level', 3)} 召回，"
                f"候选 {hyde_meta.get('candidate_k', 0)}，"
                f"合并替换 {hyde_meta.get('auto_merge_replaced_chunks', 0)}，"
                f"扩展 {hyde_meta.get('expanded_chunk_count', 0)} 块"
            ),
        )

        # 汇总 HyDE 元数据
        rerank_applied_any = rerank_applied_any or bool(hyde_meta.get("rerank_applied"))
        rerank_enabled_any = rerank_enabled_any or bool(hyde_meta.get("rerank_enabled"))
        rerank_model = rerank_model or hyde_meta.get("rerank_model")
        rerank_endpoint = rerank_endpoint or hyde_meta.get("rerank_endpoint")
        if hyde_meta.get("rerank_error"):
            rerank_errors.append(f"hyde:{hyde_meta.get('rerank_error')}")
        retrieval_mode = retrieval_mode or hyde_meta.get("retrieval_mode")
        candidate_k = candidate_k or hyde_meta.get("candidate_k")
        leaf_retrieve_level = leaf_retrieve_level or hyde_meta.get("leaf_retrieve_level")
        auto_merge_enabled = (
            auto_merge_enabled
            if auto_merge_enabled is not None
            else hyde_meta.get("auto_merge_enabled")
        )
        auto_merge_applied = auto_merge_applied or bool(hyde_meta.get("auto_merge_applied"))
        auto_merge_threshold = auto_merge_threshold or hyde_meta.get("auto_merge_threshold")
        auto_merge_replaced_chunks += int(hyde_meta.get("auto_merge_replaced_chunks") or 0)
        auto_merge_steps += int(hyde_meta.get("auto_merge_steps") or 0)
        ctx_expansion_enabled = hyde_meta.get("context_expansion_enabled")
        ctx_expansion_applied = ctx_expansion_applied or bool(hyde_meta.get("context_expansion_applied"))
        expand_prev_parent = expand_prev_parent or hyde_meta.get("expand_prev_parent")
        expand_next_parent = expand_next_parent or hyde_meta.get("expand_next_parent")
        expand_max_chunks = expand_max_chunks or hyde_meta.get("expand_max_chunks")
        expanded_chunk_count += int(hyde_meta.get("expanded_chunk_count") or 0)

    # ── Step-back 路径 ─────────────────────────────────────────
    if strategy in ("step_back", "complex"):
        expanded_query = state.get("expanded_query") or state["question"]
        retrieved_stepback = retrieve_documents(expanded_query, top_k=5)
        results.extend(retrieved_stepback.get("docs", []))
        step_meta = retrieved_stepback.get("meta", {})

        emit_rag_step(
            "\U0001f9f1", "Step-back 三级检索",
            (
                f"L{step_meta.get('leaf_retrieve_level', 3)} 召回，"
                f"候选 {step_meta.get('candidate_k', 0)}，"
                f"合并替换 {step_meta.get('auto_merge_replaced_chunks', 0)}，"
                f"扩展 {step_meta.get('expanded_chunk_count', 0)} 块"
            ),
        )

        # 汇总 Step-back 元数据
        rerank_applied_any = rerank_applied_any or bool(step_meta.get("rerank_applied"))
        rerank_enabled_any = rerank_enabled_any or bool(step_meta.get("rerank_enabled"))
        rerank_model = rerank_model or step_meta.get("rerank_model")
        rerank_endpoint = rerank_endpoint or step_meta.get("rerank_endpoint")
        if step_meta.get("rerank_error"):
            rerank_errors.append(f"step_back:{step_meta.get('rerank_error')}")
        retrieval_mode = retrieval_mode or step_meta.get("retrieval_mode")
        candidate_k = candidate_k or step_meta.get("candidate_k")
        leaf_retrieve_level = leaf_retrieve_level or step_meta.get("leaf_retrieve_level")
        auto_merge_enabled = (
            auto_merge_enabled
            if auto_merge_enabled is not None
            else step_meta.get("auto_merge_enabled")
        )
        auto_merge_applied = auto_merge_applied or bool(step_meta.get("auto_merge_applied"))
        auto_merge_threshold = auto_merge_threshold or step_meta.get("auto_merge_threshold")
        auto_merge_replaced_chunks += int(step_meta.get("auto_merge_replaced_chunks") or 0)
        auto_merge_steps += int(step_meta.get("auto_merge_steps") or 0)
        ctx_expansion_enabled = (
            ctx_expansion_enabled
            if ctx_expansion_enabled is not None
            else step_meta.get("context_expansion_enabled")
        )
        ctx_expansion_applied = ctx_expansion_applied or bool(step_meta.get("context_expansion_applied"))
        expand_prev_parent = expand_prev_parent or step_meta.get("expand_prev_parent")
        expand_next_parent = expand_next_parent or step_meta.get("expand_next_parent")
        expand_max_chunks = expand_max_chunks or step_meta.get("expand_max_chunks")
        expanded_chunk_count += int(step_meta.get("expanded_chunk_count") or 0)

    # ── 去重 ──────────────────────────────────────────────────
    deduped = []
    seen = set()
    for item in results:
        key = (item.get("filename"), item.get("page_number"), item.get("text"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    # 统一重排展示名次
    for idx, item in enumerate(deduped, 1):
        item["rrf_rank"] = idx

    context = _format_docs(deduped)
    emit_rag_step("✅", f"扩展检索完成，共 {len(deduped)} 个片段")

    # ── 构建完整 RAG trace ────────────────────────────────────
    rag_trace = state.get("rag_trace", {}) or {}
    rag_trace.update({
        "expanded_query": state.get("expanded_query") or state["question"],
        "step_back_question": state.get("step_back_question", ""),
        "step_back_answer": state.get("step_back_answer", ""),
        "hypothetical_doc": state.get("hypothetical_doc", ""),
        "expansion_type": strategy,
        "retrieved_chunks": deduped,
        "expanded_retrieved_chunks": deduped,
        "retrieval_stage": "expanded",
        "rerank_enabled": rerank_enabled_any,
        "rerank_applied": rerank_applied_any,
        "rerank_model": rerank_model,
        "rerank_endpoint": rerank_endpoint,
        "rerank_error": "; ".join(rerank_errors) if rerank_errors else None,
        "retrieval_mode": retrieval_mode,
        "candidate_k": candidate_k,
        "leaf_retrieve_level": leaf_retrieve_level,
        "auto_merge_enabled": auto_merge_enabled,
        "auto_merge_applied": auto_merge_applied,
        "auto_merge_threshold": auto_merge_threshold,
        "auto_merge_replaced_chunks": auto_merge_replaced_chunks,
        "auto_merge_steps": auto_merge_steps,
        "context_expansion_enabled": ctx_expansion_enabled,
        "context_expansion_applied": ctx_expansion_applied,
        "expand_prev_parent": expand_prev_parent,
        "expand_next_parent": expand_next_parent,
        "expand_max_chunks": expand_max_chunks,
        "expanded_chunk_count": expanded_chunk_count,
    })

    logger.info(
        "扩展检索完成: 策略=%s, %d docs (HyDE=%d, StepBack=%d)",
        strategy, len(deduped),
        sum(1 for _ in [1] if strategy in ("hyde", "complex")),
        sum(1 for _ in [1] if strategy in ("step_back", "complex")),
    )

    # 累积到历史文档池（后续轮次去重参考）
    accumulated = list(state.get("accumulated_docs") or [])
    seen_acc = {(d.get("filename"), d.get("page_number"), d.get("text")) for d in accumulated}
    for d in deduped:
        key = (d.get("filename"), d.get("page_number"), d.get("text"))
        if key not in seen_acc:
            seen_acc.add(key)
            accumulated.append(d)

    return {"docs": deduped, "context": context, "rag_trace": rag_trace, "accumulated_docs": accumulated}


# ── 图构建 ────────────────────────────────────────────────────────

def build_rag_graph():
    """构建 LangGraph 状态图（支持多轮检索循环）。

    节点:
        - retrieve_initial: 初次检索
        - grade_documents: 相关性评分门控
        - rewrite_question: 查询重写
        - retrieve_expanded: 扩展检索

    边:
        retrieve_initial → grade_documents
        grade_documents → generate_answer(END) | rewrite_question(条件)
        rewrite_question → retrieve_expanded → grade_documents(多轮循环，最多 MAX_RAG_RETRIES 次)

    Returns:
        已编译的 StateGraph 实例。
    """
    graph = StateGraph(RAGState)

    # 注册节点
    graph.add_node("retrieve_initial", retrieve_initial)
    graph.add_node("grade_documents", grade_documents_node)
    graph.add_node("rewrite_question", rewrite_question_node)
    graph.add_node("retrieve_expanded", retrieve_expanded)

    # 设置入口
    graph.set_entry_point("retrieve_initial")

    # 连线
    graph.add_edge("retrieve_initial", "grade_documents")

    # 条件边：评分结果决定走生成还是重写
    graph.add_conditional_edges(
        "grade_documents",
        lambda state: state.get("route"),
        {
            "generate_answer": END,
            "rewrite_question": "rewrite_question",
        },
    )

    graph.add_edge("rewrite_question", "retrieve_expanded")
    graph.add_edge("retrieve_expanded", "grade_documents")  # 多轮循环：回到评分节点

    logger.info("RAG 状态图编译完成（已启用 MemorySaver checkpoint）")
    return graph.compile(checkpointer=MemorySaver())


def run_rag_graph(question: str, conversation_history: str = "") -> dict:
    """执行完整 RAG 工作流。

    每次调用使用唯一 thread_id 确保 checkpoint 隔离。
    线程池场景下 thread_id 基于当前线程名生成。

    Args:
        question: 用户问题文本。
        conversation_history: 历史对话摘要（最近 2 轮 Q&A），用于上下文感知检索。

    Returns:
        完整的 RAGState 字典，含 docs、context、rag_trace 等字段。
        rag_trace 包含每阶段的检索元数据，前端可通过折叠面板查看详情。
    """
    import threading

    from backend.core.dependencies import get_rag_graph

    thread_id = f"rag-{threading.get_ident()}-{id(question)}"
    logger.info("RAG 工作流启动: %s (thread=%s)", question[:80], thread_id)
    result = get_rag_graph().invoke(
        {
            "question": question,
            "query": question,
            "context": "",
            "docs": [],
            "route": None,
            "expansion_type": None,
            "expanded_query": None,
            "step_back_question": None,
            "step_back_answer": None,
            "hypothetical_doc": None,
            "rag_trace": None,
            "retry_count": 0,
            "accumulated_docs": [],
            "conversation_history": conversation_history or None,
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    logger.info(
        "RAG 工作流完成: %d docs, 评分=%s, 策略=%s",
        len(result.get("docs", [])),
        result.get("rag_trace", {}).get("grade_score", "N/A"),
        result.get("expansion_type", "N/A"),
    )
    return result
