"""单次检索图的组装与执行；节点实现位于 rag_pipeline。"""

from langgraph.graph import END, StateGraph
from backend.core.logging_config import get_logger
from backend.rag.state import RAGState
from backend.rag.rag_pipeline import retrieve_initial, grade_documents_node, rewrite_question_node, retrieve_expanded

logger = get_logger(__name__)


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

    logger.info("RAG 状态图编译完成（单次执行，不保留进程内 checkpoint）")
    return graph.compile()



def run_rag_graph(question: str, conversation_history: str = "") -> dict:
    """执行完整 RAG 工作流。

    图只保存本次执行的临时状态，避免进程内 checkpoint 无界增长及标识复用。

    Args:
        question: 用户问题文本。
        conversation_history: 历史对话摘要（最近 2 轮 Q&A），用于上下文感知检索。

    Returns:
        完整的 RAGState 字典，含 docs、context、rag_trace 等字段。
        rag_trace 包含每阶段的检索元数据，前端可通过折叠面板查看详情。
    """
    from backend.core.dependencies import get_rag_graph

    # 注意：预算由调用方（Agent 入口）统一 reset，此处不再清零，
    # 使 intent_router / Agent 主调用 / RAG 内部调用共享同一预算。
    logger.info("RAG 工作流启动: %s", question[:80])
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
    )
    logger.info(
        "RAG 工作流完成: %d docs, 评分=%s, 策略=%s",
        len(result.get("docs", [])),
        (result.get("rag_trace") or {}).get("grade_score", "N/A"),
        result.get("expansion_type", "N/A"),
    )
    return result

