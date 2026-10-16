"""检索工作流的数据状态与结构化模型输出。"""

from typing import Literal, TypedDict
from pydantic import BaseModel, Field


class GradeDocuments(BaseModel):
    """相关性评分结构化输出 —— binary yes/no。"""

    binary_score: str = Field(
        description="Relevance score: 'yes' if relevant, or 'no' if not relevant"
    )



class RewriteStrategy(BaseModel):
    """查询扩展策略选择 —— step_back / hyde / complex 三选一。"""

    strategy: Literal["step_back", "hyde", "complex"]



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

