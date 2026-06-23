"""RAG 检索工具库 —— 混合检索、精排、Auto-merging、上下文扩展、HyDE、Step-back。

核心检索流程:
    Hybrid/Dense 检索 → Rerank（本地/API双轨） → Auto-merge(三级合并)
    → Context Expansion(兄弟块+相邻父块) → 返回结果

查询重写策略:
    - step_back: 生成抽象退步问题，检索通用原理
    - hyde: 生成假设性文档，以学术风格文本检索
    - complex: 同时执行 step_back + hyde

所有函数通过全局单例共享 embedding_service，保证 BM25 统计一致性。
"""

import json
from collections import defaultdict
from typing import Any

import requests

from backend.core.config import (
    AUTO_MERGE_ENABLED,
    AUTO_MERGE_THRESHOLD,
    ENABLE_CONTEXT_EXPANSION,
    EXPAND_MAX_TOTAL_CHUNKS,
    EXPAND_NEXT_PARENT,
    EXPAND_PREV_PARENT,
    LEAF_RETRIEVE_LEVEL,
    LOCAL_RERANKER,
    RERANK_API_KEY,
    RERANK_BINDING_HOST,
    RERANK_MODEL,
)
from backend.core.budget import record_llm_call
from backend.core.config import LLM_TIMEOUT_SECONDS
from backend.core.dependencies import (
    get_embedding_service,
    get_local_reranker,
    get_milvus_manager,
    get_parent_chunk_store,
    get_stepback_model,
)
from backend.core.logging_config import get_logger
from backend.rag.citation_extractor import extract_citation_refs
from backend.rag.formula_index import get_formula_lsh_index
from backend.rag.formula_normalizer import extract_formulas, normalize_formula

logger = get_logger(__name__)


# ── Rerank 基础设施 ──────────────────────────────────────────────


def _get_rerank_endpoint() -> str:
    """构建 Jina Rerank API 端点 URL。

    支持直接传入完整 URL 或仅传入 host（自动追加 /v1/rerank）。
    """
    if not RERANK_BINDING_HOST:
        return ""
    host = RERANK_BINDING_HOST.strip().rstrip("/")
    return host if host.endswith("/v1/rerank") else f"{host}/v1/rerank"


# ── Auto-merging（三级分块合并）──────────────────────────────────

def _merge_to_parent_level(
    docs: list[dict], threshold: int = 2
) -> tuple[list[dict], int]:
    """将叶子 chunk 按 parent_chunk_id 分组，满足阈值后替换为父块。

    当同一父块下的子块数 >= threshold 时，从 ParentChunkStore 拉取父块文本，
    替换所有子块（保留最高检索得分）。父块文本更长、语义更完整。

    Args:
        docs: 检索返回的文档列表（含 parent_chunk_id 字段）。
        threshold: 触发合并的最小子块数，默认 2。

    Returns:
        (merged_docs, merged_count): 合并后的文档列表和实际替换的父块数。
    """
    # 按 parent_chunk_id 分组
    groups: dict[str, list[dict]] = defaultdict(list)
    for doc in docs:
        parent_id = (doc.get("parent_chunk_id") or "").strip()
        if parent_id:
            groups[parent_id].append(doc)

    # 筛选出满足阈值条件的 parent
    merge_parent_ids = [
        pid for pid, children in groups.items()
        if len(children) >= threshold
    ]
    if not merge_parent_ids:
        return docs, 0

    # 从 DocStore 批量拉取父块
    parent_docs = get_parent_chunk_store().get_documents_by_ids(merge_parent_ids)
    parent_map = {
        item.get("chunk_id", ""): item
        for item in parent_docs if item.get("chunk_id")
    }

    merged_docs: list[dict] = []
    merged_count = 0

    for doc in docs:
        parent_id = (doc.get("parent_chunk_id") or "").strip()
        if not parent_id or parent_id not in parent_map:
            # 不在合并范围内，保留原样
            merged_docs.append(doc)
            continue

        parent_doc = dict(parent_map[parent_id])
        # 保留最高检索得分
        score = doc.get("score")
        if score is not None:
            parent_doc["score"] = max(
                float(parent_doc.get("score", score)), float(score)
            )
        parent_doc["merged_from_children"] = True
        parent_doc["merged_child_count"] = len(groups[parent_id])
        merged_docs.append(parent_doc)
        merged_count += 1

    # 去重（同一父块可能被多个子块命中）
    deduped: list[dict] = []
    seen = set()
    for item in merged_docs:
        key = item.get("chunk_id") or (
            item.get("filename"), item.get("page_number"), item.get("text")
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped, merged_count


def _auto_merge_documents(
    docs: list[dict], top_k: int
) -> tuple[list[dict], dict[str, Any]]:
    """两阶段 Auto-merging: L3→L2 再 L2→L1。

    每阶段独立判断阈值，不可合并的 chunk 保留原级别。
    最终按 score 降序排列并截断至 top_k。

    Args:
        docs: 检索结果列表。
        top_k: 最终返回数量上限。

    Returns:
        (merged_docs, merge_meta): 合并后的文档和元信息。
    """
    if not AUTO_MERGE_ENABLED or not docs:
        return docs[:top_k], {
            "auto_merge_enabled": AUTO_MERGE_ENABLED,
            "auto_merge_applied": False,
            "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
            "auto_merge_replaced_chunks": 0,
            "auto_merge_steps": 0,
        }

    # Stage 1: L3 → L2
    merged_docs, merged_l3_l2 = _merge_to_parent_level(
        docs, threshold=AUTO_MERGE_THRESHOLD
    )
    # Stage 2: L2 → L1
    merged_docs, merged_l2_l1 = _merge_to_parent_level(
        merged_docs, threshold=AUTO_MERGE_THRESHOLD
    )

    # 按得分降序 + 截断
    merged_docs.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    merged_docs = merged_docs[:top_k]

    replaced = merged_l3_l2 + merged_l2_l1
    logger.debug(
        "Auto-merge: %d→%d docs (L3→L2: %d, L2→L1: %d, threshold=%d)",
        len(docs), len(merged_docs), merged_l3_l2, merged_l2_l1, AUTO_MERGE_THRESHOLD,
    )

    return merged_docs, {
        "auto_merge_enabled": AUTO_MERGE_ENABLED,
        "auto_merge_applied": replaced > 0,
        "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
        "auto_merge_replaced_chunks": replaced,
        "auto_merge_steps": int(merged_l3_l2 > 0) + int(merged_l2_l1 > 0),
    }


# ── Rerank（双轨：本地 Cross-Encoder + Jina API）─────────────────

def _rerank_documents(
    query: str, docs: list[dict], top_k: int
) -> tuple[list[dict], dict[str, Any]]:
    """对候选文档进行精排。

    策略选择（优先级从高到低）:
        1. LOCAL_RERANKER=true → 本地 BGE-Reranker-v2-M3 Cross-Encoder
        2. RERANK_API_KEY 已配置 → Jina Rerank API
        3. 均未配置 → 跳过精排，直接按原始检索得分截断

    本地模式优势: 无网络延迟、无 API 调用成本、适合内网环境
    API 模式优势: 模型更新及时、无需 GPU 资源

    Args:
        query: 用户查询文本。
        docs: 候选文档列表（含 rrf_rank 排名）。
        top_k: 精排后保留数量。

    Returns:
        (reranked_docs, rerank_meta): 精排后文档和元信息。
    """
    # 附加 RRF 排名信息
    docs_with_rank = [{**doc, "rrf_rank": i} for i, doc in enumerate(docs, 1)]

    meta: dict[str, Any] = {
        "rerank_enabled": bool(
            (RERANK_MODEL and RERANK_API_KEY and RERANK_BINDING_HOST) or LOCAL_RERANKER
        ),
        "rerank_applied": False,
        "rerank_model": RERANK_MODEL or "BAAI/bge-reranker-v2-m3",
        "rerank_endpoint": _get_rerank_endpoint() if not LOCAL_RERANKER else "local",
        "rerank_error": None,
        "candidate_count": len(docs_with_rank),
    }

    if not docs_with_rank or not meta["rerank_enabled"]:
        return docs_with_rank[:top_k], meta

    # ── 本地 Cross-Encoder 模式 ──────────────────────────────────
    if LOCAL_RERANKER:
        try:
            meta["rerank_applied"] = True
            model = get_local_reranker()
            pairs = [[query, doc.get("text", "")] for doc in docs_with_rank]
            scores = model.predict(pairs, show_progress_bar=False)
            # 按分数降序排列
            scored = sorted(
                zip(docs_with_rank, scores), key=lambda x: x[1], reverse=True
            )
            reranked = []
            for doc, score in scored[:top_k]:
                doc = dict(doc)
                doc["rerank_score"] = float(score)
                reranked.append(doc)
            logger.debug("本地 Reranker 精排: %d→%d docs", len(docs), len(reranked))
            return reranked[:top_k], meta
        except Exception as e:
            logger.warning("本地 Reranker 失败: %s", e)
            meta["rerank_error"] = str(e)
            return docs_with_rank[:top_k], meta

    # ── Jina Rerank API 模式 ─────────────────────────────────────
    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": [doc.get("text", "") for doc in docs_with_rank],
        "top_n": min(top_k, len(docs_with_rank)),
        "return_documents": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RERANK_API_KEY}",
    }

    try:
        meta["rerank_applied"] = True
        resp = requests.post(
            meta["rerank_endpoint"], headers=headers, json=payload, timeout=15,
        )
        if resp.status_code >= 400:
            meta["rerank_error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning("Jina Rerank API 错误: %s", meta["rerank_error"])
            return docs_with_rank[:top_k], meta

        items = resp.json().get("results", [])
        reranked = []
        for item in items:
            idx = item.get("index")
            if isinstance(idx, int) and 0 <= idx < len(docs_with_rank):
                doc = dict(docs_with_rank[idx])
                score = item.get("relevance_score")
                if score is not None:
                    doc["rerank_score"] = score
                reranked.append(doc)

        if reranked:
            logger.debug("Jina Rerank API 精排: %d→%d docs", len(docs), len(reranked))
            return reranked[:top_k], meta

        meta["rerank_error"] = "empty_rerank_results"
        return docs_with_rank[:top_k], meta
    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.warning("Jina Rerank API 异常: %s", e)
        meta["rerank_error"] = str(e)
        return docs_with_rank[:top_k], meta


# ── 上下文扩展（Context Expansion）────────────────────────────────

def _expand_context(docs: list[dict]) -> tuple[list[dict], dict[str, Any]]:
    """对检索后的文档执行上下文扩展。

    扩展策略:
        1. 从命中文档提取 (filename, parent_idx) 集合
        2. 对每个命中父块，拉取其全部子块（兄弟块）
        3. 含定理/证明的父块额外拉取相邻父块的子块（向前 EXPAND_PREV_PARENT、
           向后 EXPAND_NEXT_PARENT）
        4. 按 (parent_idx, child_idx) 排序保证语义连续
        5. 截断至 EXPAND_MAX_TOTAL_CHUNKS，定理块优先保留

    这样在定理命题被拆到不同 chunk 的场景下，仍能保证完整的定理陈述
    和证明过程一并返回给 LLM。

    Args:
        docs: 已合并/精排后的文档列表。

    Returns:
        (expanded_docs, expand_meta): 扩展后的文档和元信息。
    """
    meta: dict[str, Any] = {
        "context_expansion_enabled": ENABLE_CONTEXT_EXPANSION,
        "context_expansion_applied": False,
        "expand_prev_parent": EXPAND_PREV_PARENT,
        "expand_next_parent": EXPAND_NEXT_PARENT,
        "expand_max_chunks": EXPAND_MAX_TOTAL_CHUNKS,
        "expanded_chunk_count": 0,
    }
    if not ENABLE_CONTEXT_EXPANSION or not docs:
        return docs, meta

    # 1. 收集待扩展的 (filename, parent_idx)，标记是否含定理/证明
    expand_set: dict[tuple, bool] = {}
    for doc in docs:
        filename = doc.get("filename", "")
        pi = doc.get("parent_idx")
        if filename and pi is not None:
            key = (filename, int(pi))
            has_tp = (
                doc.get("has_theorem_in_parent", False)
                or doc.get("has_proof_in_parent", False)
            )
            if key not in expand_set:
                expand_set[key] = has_tp
            elif has_tp:
                expand_set[key] = True

    if not expand_set:
        return docs, meta

    # 2. 对含定理/证明的父块，扩展相邻父块
    all_parents: dict[tuple, bool] = dict(expand_set)
    if EXPAND_PREV_PARENT > 0 or EXPAND_NEXT_PARENT > 0:
        for (filename, pi), has_tp in expand_set.items():
            if has_tp:
                for offset in range(1, EXPAND_PREV_PARENT + 1):
                    p = pi - offset
                    if p >= 0:
                        all_parents.setdefault((filename, p), False)
                for offset in range(1, EXPAND_NEXT_PARENT + 1):
                    all_parents.setdefault((filename, pi + offset), False)

    # 3. 批量查询 Milvus 获取扩展子块
    all_children: dict[str, dict] = {}
    for (filename, pi) in all_parents:
        try:
            escaped = filename.replace('"', '\\"')
            filter_expr = f'filename == "{escaped}" && parent_idx == {pi}'
            rows = get_milvus_manager().query_all(
                filter_expr=filter_expr,
                output_fields=[
                    "text", "filename", "file_type", "page_number",
                    "chunk_id", "parent_chunk_id", "root_chunk_id",
                    "chunk_level", "chunk_idx",
                    "parent_idx", "child_idx", "num_children",
                    "has_theorem_in_parent", "has_proof_in_parent",
                ],
            )
            for row in rows:
                cid = row.get("chunk_id", "")
                if cid and cid not in all_children:
                    all_children[cid] = {
                        "text": row.get("text", ""),
                        "filename": row.get("filename", ""),
                        "file_type": row.get("file_type", ""),
                        "page_number": row.get("page_number", 0),
                        "chunk_id": cid,
                        "parent_chunk_id": row.get("parent_chunk_id", ""),
                        "root_chunk_id": row.get("root_chunk_id", ""),
                        "chunk_level": row.get("chunk_level", 0),
                        "chunk_idx": row.get("chunk_idx", 0),
                        "parent_idx": row.get("parent_idx", 0),
                        "child_idx": row.get("child_idx", 0),
                        "num_children": row.get("num_children", 0),
                        "has_theorem_in_parent": row.get("has_theorem_in_parent", False),
                        "has_proof_in_parent": row.get("has_proof_in_parent", False),
                        "score": 0.0,
                    }
        except Exception as e:
            logger.debug("上下文扩展查询失败 [%s, p%d]: %s", filename, pi, e)
            continue

    # 4. 合并：扩展结果 + 原始命中（原始命中覆盖以保留检索得分）
    result_map: dict[str, dict] = {}
    for cid, doc in all_children.items():
        result_map[cid] = doc
    for doc in docs:
        cid = doc.get("chunk_id", "")
        if cid:
            result_map[cid] = doc

    # 5. 按章节坐标排序，保证语义连贯
    result = list(result_map.values())
    result.sort(
        key=lambda d: (d.get("parent_idx", 0), d.get("child_idx", 0))
    )

    # 6. 截断：定理/证明块优先保留
    if len(result) > EXPAND_MAX_TOTAL_CHUNKS:
        theorem_docs = [
            d for d in result
            if d.get("has_theorem_in_parent") or d.get("has_proof_in_parent")
        ]
        other_docs = [
            d for d in result
            if not (d.get("has_theorem_in_parent") or d.get("has_proof_in_parent"))
        ]
        if len(theorem_docs) >= EXPAND_MAX_TOTAL_CHUNKS:
            result = theorem_docs[:EXPAND_MAX_TOTAL_CHUNKS]
        else:
            result = (
                theorem_docs
                + other_docs[:EXPAND_MAX_TOTAL_CHUNKS - len(theorem_docs)]
            )

    meta["context_expansion_applied"] = True
    meta["expanded_chunk_count"] = len(result)
    logger.debug(
        "上下文扩展: %d hits → %d expanded (limit=%d, prev=%d, next=%d)",
        len(docs), len(result), EXPAND_MAX_TOTAL_CHUNKS,
        EXPAND_PREV_PARENT, EXPAND_NEXT_PARENT,
    )
    return result, meta


# ── 查询重写模型 ─────────────────────────────────────────────────


def _generate_step_back_question(query: str) -> str:
    """生成抽象的'退步问题'——从具体问题中提炼通用原理。

    退步问题（Step-Back Question）是 LangGraph 论文中提出的技术：
    将用户的具体问题向上抽象一层，先回答通用原理问题，
    再利用原理知识指导具体问题的回答。

    Args:
        query: 用户原始问题。

    Returns:
        退步问题文本，或空字符串（模型不可用时）。
    """
    model = get_stepback_model()
    if not model:
        return ""
    prompt = (
        "请将用户的具体问题抽象成更高层次、更概括的'退步问题'，"
        "用于探寻背后的通用原理或核心概念。只输出退步问题一句话，不要解释。\n"
        f"用户问题：{query}"
    )
    try:
        result = (model.invoke(prompt, config={"timeout": LLM_TIMEOUT_SECONDS}).content or "").strip()
        record_llm_call(estimated_tokens=150)
        return result
    except Exception as e:
        logger.warning("退步问题生成失败: %s", e)
        return ""


def _answer_step_back_question(step_back_question: str) -> str:
    """回答退步问题——提供通用原理/背景知识（120 字以内）。

    Args:
        step_back_question: 退步问题文本。

    Returns:
        简短答案文本。
    """
    model = get_stepback_model()
    if not model or not step_back_question:
        return ""
    prompt = (
        "请简要回答以下退步问题，提供通用原理/背景知识，"
        "控制在120字以内。只输出答案，不要列出推理过程。\n"
        f"退步问题：{step_back_question}"
    )
    try:
        result = (model.invoke(prompt, config={"timeout": LLM_TIMEOUT_SECONDS}).content or "").strip()
        record_llm_call(estimated_tokens=100)
        return result
    except Exception as e:
        logger.warning("退步问题回答失败: %s", e)
        return ""


def generate_hypothetical_document(query: str) -> str:
    """HyDE (Hypothetical Document Embeddings) —— 生成假设性学术文档。

    先让 LLM 生成一段假设性回答（风格贴近论文正文），再以此文本进行
    向量检索。假设回答的措辞风格更接近目标论文，能有效弥合
    "口语提问 ↔ 学术术语"之间的语义鸿沟。

    Args:
        query: 用户问题。

    Returns:
        假设性文档文本，或空字符串（模型不可用时）。
    """
    model = get_stepback_model()
    if not model:
        return ""
    prompt = (
        "请基于用户问题生成一段'假设性文档'，内容应像真实资料片段，"
        "用于帮助检索相关信息。文档可以包含合理推测，但需与问题语义相关。"
        "只输出文档正文，不要标题或解释。\n"
        f"用户问题：{query}"
    )
    try:
        result = (model.invoke(prompt, config={"timeout": LLM_TIMEOUT_SECONDS}).content or "").strip()
        record_llm_call(estimated_tokens=200)
        return result
    except Exception as e:
        logger.warning("HyDE 生成失败: %s", e)
        return ""


def step_back_expand(query: str) -> dict:
    """Step-back 查询扩展：生成退步问题 + 回答 → 合并到扩展查询。

    Args:
        query: 原始用户问题。

    Returns:
        {"step_back_question", "step_back_answer", "expanded_query"}
    """
    step_back_question = _generate_step_back_question(query)
    step_back_answer = _answer_step_back_question(step_back_question)
    if step_back_question or step_back_answer:
        expanded_query = (
            f"{query}\n\n"
            f"退步问题：{step_back_question}\n"
            f"退步问题答案：{step_back_answer}"
        )
        logger.debug("Step-back 扩展: %s → %s", query[:40], step_back_question[:60])
    else:
        expanded_query = query
    return {
        "step_back_question": step_back_question,
        "step_back_answer": step_back_answer,
        "expanded_query": expanded_query,
    }


# ── 核心检索入口 ─────────────────────────────────────────────────

def _formula_search(query: str, top_k: int = 3) -> list[dict]:
    """执行公式感知检索：提取查询中的 LaTeX 公式 → LSH 匹配 → Milvus 查询。

    若查询中不含公式，返回空列表。公式检索结果通过 `chunk_id` 精确匹配
    从 Milvus 获取完整的 chunk 数据。

    Args:
        query: 用户查询文本。
        top_k: 返回的最大公式匹配 chunk 数。

    Returns:
        匹配的 chunk 字典列表（与 hybrid/dense 检索的输出格式一致）。
    """
    formulas = extract_formulas(query)
    if not formulas:
        return []

    index = get_formula_lsh_index()
    seen_chunk_ids: set[str] = set()
    results: list[dict] = []

    for formula in formulas:
        norm = normalize_formula(formula)
        if not norm:
            continue
        candidates = index.query(norm, top_k=top_k * 2)

        for formula_id, similarity in candidates:
            # formula_id 格式: {chunk_id}::f{idx}
            chunk_id = formula_id.split("::")[0]
            if chunk_id in seen_chunk_ids or not chunk_id:
                continue
            seen_chunk_ids.add(chunk_id)

            try:
                rows = get_milvus_manager().query(
                    filter_expr=f'chunk_id == "{chunk_id}"',
                    output_fields=[
                        "text", "filename", "file_type", "page_number",
                        "chunk_id", "parent_chunk_id", "root_chunk_id",
                        "chunk_level", "chunk_idx",
                        "parent_idx", "child_idx", "num_children",
                        "has_theorem_in_parent", "has_proof_in_parent",
                    ],
                    limit=1,
                )
                if rows:
                    doc = {
                        "text": rows[0].get("text", ""),
                        "filename": rows[0].get("filename", ""),
                        "file_type": rows[0].get("file_type", ""),
                        "page_number": rows[0].get("page_number", 0),
                        "chunk_id": rows[0].get("chunk_id", ""),
                        "parent_chunk_id": rows[0].get("parent_chunk_id", ""),
                        "root_chunk_id": rows[0].get("root_chunk_id", ""),
                        "chunk_level": rows[0].get("chunk_level", 0),
                        "chunk_idx": rows[0].get("chunk_idx", 0),
                        "parent_idx": rows[0].get("parent_idx", 0),
                        "child_idx": rows[0].get("child_idx", 0),
                        "num_children": rows[0].get("num_children", 0),
                        "has_theorem_in_parent": rows[0].get("has_theorem_in_parent", False),
                        "has_proof_in_parent": rows[0].get("has_proof_in_parent", False),
                        "score": similarity,
                        "formula_match": True,
                    }
                    results.append(doc)
            except Exception as ex:
                logger.debug("公式查询 chunk_id=%s 失败: %s", chunk_id, ex)
                continue

        if len(results) >= top_k:
            break

    return results[:top_k]


def _build_formula_index(docs: list[dict]) -> None:
    """从文档分块中提取公式并构建 LSH 索引。

    通常在文档入库后调用。根据 chunk 的 `formulas` 元数据字段，
    将每个公式标准化后写入 LSH 索引。

    Args:
        docs: 文档分块列表（来自 DocumentLoader.load_document）。
    """
    index = get_formula_lsh_index()
    count = 0
    for doc in docs:
        formulas = doc.get("formulas", [])
        chunk_id = doc.get("chunk_id", "")
        if not formulas or not chunk_id:
            continue
        for i, raw in enumerate(formulas):
            norm = normalize_formula(raw)
            if norm:
                formula_id = f"{chunk_id}::f{i}"
                index.add(norm, formula_id)
                count += 1
    if count:
        logger.info("公式 LSH 索引已构建: %d 个公式", count)


def _citation_boost(docs: list[dict], query: str) -> list[dict]:
    """引文相关 chunk 优先级提升：对检索结果中包含查询中引用的 chunk 提高排序。

    当查询包含 [1]、[Author, Year] 等引用标记时，
    将同样包含这些引文的 chunk 在结果中前移。

    Args:
        docs: 检索结果列表。
        query: 用户查询文本。

    Returns:
        重排序后的文档列表（引文匹配在前）。
    """
    refs = extract_citation_refs(query)
    if not refs:
        return docs
    if not docs:
        return docs

    target_refs = set(refs)
    cited: list[dict] = []
    others: list[dict] = []

    for doc in docs:
        chunk_refs = extract_citation_refs(doc.get("text", ""))
        if set(chunk_refs) & target_refs:
            cited.append(doc)
        else:
            others.append(doc)

    return cited + others


def retrieve_documents(query: str, top_k: int = 5) -> dict[str, Any]:
    """核心检索函数：Hybrid 检索 → Formula 检索 → Rerank → Auto-merge → Context Expansion。

    完整的五阶段检索流程:
        1. Formula Search: 检测查询中 LaTeX 公式，LSH 索引匹配候选 chunk
        2. Hybrid Search: Dense(BGE-M3) + Sparse(BM25) + RRF 融合，候选量 = top_k * 3
        3. Rerank: 本地 Cross-Encoder 或 Jina API 精排至 top_k
        4. Auto-merge: L3→L2→L1 三级合并，减少碎片化
        5. Context Expansion: 拉取兄弟块 + 相邻父块，定理块优先

    降级策略:
        - Formula 检索无匹配 → 跳过公式路径
        - Hybrid 失败 → 自动降级为 Dense-only 检索
        - Rerank 失败/未配置 → 跳过精排，直接截断
        - 全部失败 → 返回空结果 + 完整 meta

    Args:
        query: 检索查询文本。
        top_k: 最终返回文档数，默认 5。

    Returns:
        {"docs": [...], "meta": {...}}，包含文档列表和完整检索元信息。
    """
    candidate_k = max(top_k * 3, top_k)
    filter_expr = f"chunk_level == {LEAF_RETRIEVE_LEVEL}"

    # ── Formula 感知检索（查询含 LaTeX 时启用）────────────────────
    formula_docs = _formula_search(query, top_k=top_k)
    formula_match = len(formula_docs) > 0

    # ── 文本检索（Hybrid 优先，Dense 降级）─────────────────────────
    result: dict[str, Any] | None = None
    try:
        _es = get_embedding_service()
        de = _es.get_embeddings([query])[0]
        se = _es.get_sparse_embedding(query)
        retrieved = get_milvus_manager().hybrid_retrieve(
            dense_embedding=de, sparse_embedding=se,
            top_k=candidate_k, filter_expr=filter_expr,
        )
        reranked, rm = _rerank_documents(query, retrieved, top_k)
        merged, mm = _auto_merge_documents(reranked, top_k)
        expanded, em = _expand_context(merged)
        rm["retrieval_mode"] = "hybrid"
        rm["formula_match"] = formula_match
        rm["formula_result_count"] = len(formula_docs)
        result = {"docs": expanded, "meta": rm}
    except Exception as e:
        logger.warning("Hybrid 检索失败，降级为 Dense-only: %s", e)

    if result is None:
        try:
            _es = get_embedding_service()
            de = _es.get_embeddings([query])[0]
            retrieved = get_milvus_manager().dense_retrieve(
                dense_embedding=de, top_k=candidate_k, filter_expr=filter_expr,
            )
            reranked, rm = _rerank_documents(query, retrieved, top_k)
            merged, mm = _auto_merge_documents(reranked, top_k)
            expanded, em = _expand_context(merged)
            rm["retrieval_mode"] = "dense_fallback"
            rm["formula_match"] = formula_match
            rm["formula_result_count"] = len(formula_docs)
            result = {"docs": expanded, "meta": rm}
        except Exception as e2:
            logger.error("Dense 检索也失败: %s", e2)
            result = _empty_retrieve_result(candidate_k)

    # ── 融合 formula 结果到文本结果 ───────────────────────────────
    if formula_match and result.get("docs"):
        seen = {d.get("chunk_id") for d in result["docs"]}
        for fd in formula_docs:
            if fd.get("chunk_id") not in seen:
                result["docs"].append(fd)
        logger.debug("Formula 检索融合: +%d docs (共 %d)", len(formula_docs), len(result["docs"]))

    # ── 引文优先级提升 ───────────────────────────────────────────
    result["docs"] = _citation_boost(result["docs"], query)

    return result


def _empty_retrieve_result(candidate_k: int) -> dict[str, Any]:
    """构建空检索结果的 meta（所有功能标记为未应用）。"""
    return {
        "docs": [],
        "meta": {
            "rerank_enabled": bool(
                RERANK_MODEL and (RERANK_API_KEY or LOCAL_RERANKER)
            ),
            "rerank_applied": False,
            "rerank_model": RERANK_MODEL or "BAAI/bge-reranker-v2-m3",
            "rerank_endpoint": _get_rerank_endpoint() if not LOCAL_RERANKER else "local",
            "rerank_error": "retrieve_failed",
            "retrieval_mode": "failed",
            "candidate_k": candidate_k,
            "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
            "auto_merge_enabled": AUTO_MERGE_ENABLED,
            "auto_merge_applied": False,
            "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
            "auto_merge_replaced_chunks": 0,
            "auto_merge_steps": 0,
            "context_expansion_enabled": ENABLE_CONTEXT_EXPANSION,
            "context_expansion_applied": False,
            "candidate_count": 0,
            "formula_match": False,
            "formula_result_count": 0,
        },
    }
