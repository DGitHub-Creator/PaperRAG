"""
Pydantic 数据模型定义 —— API 请求/响应的 Schema。

本模块定义了所有 API 端点的请求体和响应体格式，
使用 Pydantic v2 进行数据验证和序列化。

分类：
  认证相关:   RegisterRequest, LoginRequest, AuthResponse, CurrentUserResponse
  会话相关:   ChatRequest, SessionInfo, SessionListResponse,
              SessionMessagesResponse, SessionDeleteResponse
  消息相关:   MessageInfo, ChatResponse, RetrievedChunk, RagTrace
  文档上传:   DocumentUploadResponse, DocumentUploadStartResponse,
              UploadStepInfo, DocumentUploadJobResponse
  文档删除:   DocumentDeleteStartResponse, DocumentDeleteJobResponse,
              DocumentDeleteResponse
  文档列表:   DocumentInfo, DocumentListResponse
  增量导入:   IncrementalIngestRequest, IncrementalIngestResponse
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


# ═══════════════════════════════════════════════════════════════════
# 认证相关 Schema
# ═══════════════════════════════════════════════════════════════════


class RegisterRequest(BaseModel):
    """用户注册请求。

    Fields:
        username: 用户名（必填，非空）。
        password: 密码（必填，非空）。
        role: 可选角色，默认为 "user"。可通过 admin_code 升级为 "admin"。
        admin_code: 管理员邀请码，匹配 ADMIN_INVITE_CODE 时角色设为 admin。
    """
    username: str
    password: str
    role: Optional[str] = "user"
    admin_code: Optional[str] = None


class LoginRequest(BaseModel):
    """用户登录请求。

    Fields:
        username: 用户名。
        password: 密码。
    """
    username: str
    password: str


class AuthResponse(BaseModel):
    """认证成功响应（注册/登录通用）。

    Fields:
        access_token: JWT 访问令牌。
        token_type: 令牌类型，固定为 "bearer"。
        username: 用户名。
        role: 用户角色（"user" 或 "admin"）。
    """
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class CurrentUserResponse(BaseModel):
    """当前登录用户信息响应。

    Fields:
        username: 用户名。
        role: 用户角色。
    """
    username: str
    role: str


# ═══════════════════════════════════════════════════════════════════
# 会话/对话相关 Schema
# ═══════════════════════════════════════════════════════════════════


class ChatRequest(BaseModel):
    """对话请求。

    Fields:
        message: 用户输入的文本消息。
        session_id: 会话 ID，用于多轮对话上下文关联。默认 "default_session"。
    """
    message: str
    session_id: Optional[str] = "default_session"


class RetrievedChunk(BaseModel):
    """检索到的文档分块信息。

    Fields:
        filename: 来源文档文件名。
        page_number: 页码（可选）。
        text: 分块文本内容（可选）。
        score: 检索得分（可选）。
        rrf_rank: RRF（倒数排名融合）排名（可选）。
        rerank_score: 重排序后得分（可选）。
        parent_idx: 父级分块索引（可选）。
        child_idx: 子级分块索引（可选）。
        has_theorem_in_parent: 父块中是否包含定理（可选）。
        has_proof_in_parent: 父块中是否包含证明（可选）。
        chapter_path: 章节路径（可选）。
    """
    filename: str
    page_number: Optional[str | int] = None
    text: Optional[str] = None
    score: Optional[float] = None
    rrf_rank: Optional[int] = None
    rerank_score: Optional[float] = None
    parent_idx: Optional[int] = None
    child_idx: Optional[int] = None
    has_theorem_in_parent: Optional[bool] = None
    has_proof_in_parent: Optional[bool] = None
    chapter_path: Optional[str] = None


class RagTrace(BaseModel):
    """RAG 检索追踪信息 —— 记录检索流水线各阶段的详细参数和结果。

    用于前端展示检索过程（搜索了什么 -> 如何扩展 -> 重排序 -> 合并）。

    Fields:
        tool_used: 是否使用了检索工具。
        tool_name: 使用的工具名称。
        query: 原始查询。
        expanded_query: 扩展后的查询。
        step_back_question: 后退式问题（由 LLM 生成的一般性问题）。
        step_back_answer: 后退式问题的答案。
        expansion_type: 查询扩展类型（如 "hyde", "step_back", "rewrite"）。
        hypothetical_doc: HyDE 生成的假设性文档。
        retrieval_stage: 检索阶段标识。
        grade_score: 检索结果评分。
        grade_route: 评分后路由决策。
        rewrite_needed: 是否需要重写查询。
        rewrite_strategy: 查询重写策略。
        rewrite_query: 重写后的查询。
        rerank_enabled: 是否启用重排序。
        rerank_applied: 是否实际执行了重排序。
        rerank_model: 重排序模型名称。
        rerank_endpoint: 重排序服务端点。
        rerank_error: 重排序错误信息（如有）。
        retrieval_mode: 检索模式（如 "hybrid"）。
        candidate_k: 粗召回候选数量。
        leaf_retrieve_level: 叶子分块检索层级。
        auto_merge_enabled: 是否启用自动合并。
        auto_merge_applied: 是否实际执行了自动合并。
        auto_merge_threshold: 自动合并阈值。
        auto_merge_replaced_chunks: 自动合并替换的分块数。
        auto_merge_steps: 自动合并执行的步数。
        context_expansion_enabled: 是否启用上下文扩展。
        context_expansion_applied: 是否实际执行了上下文扩展。
        expand_prev_parent: 向前扩展的父块数。
        expand_next_parent: 向后扩展的父块数。
        expand_max_chunks: 上下文扩展最大分块数。
        expanded_chunk_count: 扩展后的总分块数。
        retrieved_chunks: 最终检索到的分块列表。
        initial_retrieved_chunks: 初始检索到的分块列表（扩展前）。
        expanded_retrieved_chunks: 扩展后的检索分块列表。
        citations: 从 Agent 响应中提取的引用列表。
            每个元素包含 index（检索结果序号）、filename、page、chunk_idx。
    """
    tool_used: bool
    tool_name: str
    query: Optional[str] = None
    expanded_query: Optional[str] = None
    step_back_question: Optional[str] = None
    step_back_answer: Optional[str] = None
    expansion_type: Optional[str] = None
    hypothetical_doc: Optional[str] = None
    retrieval_stage: Optional[str] = None
    grade_score: Optional[str] = None
    grade_route: Optional[str] = None
    rewrite_needed: Optional[bool] = None
    rewrite_strategy: Optional[str] = None
    rewrite_query: Optional[str] = None
    rerank_enabled: Optional[bool] = None
    rerank_applied: Optional[bool] = None
    rerank_model: Optional[str] = None
    rerank_endpoint: Optional[str] = None
    rerank_error: Optional[str] = None
    retrieval_mode: Optional[str] = None
    candidate_k: Optional[int] = None
    leaf_retrieve_level: Optional[int] = None
    auto_merge_enabled: Optional[bool] = None
    auto_merge_applied: Optional[bool] = None
    auto_merge_threshold: Optional[int] = None
    auto_merge_replaced_chunks: Optional[int] = None
    auto_merge_steps: Optional[int] = None
    context_expansion_enabled: Optional[bool] = None
    context_expansion_applied: Optional[bool] = None
    expand_prev_parent: Optional[int] = None
    expand_next_parent: Optional[int] = None
    expand_max_chunks: Optional[int] = None
    expanded_chunk_count: Optional[int] = None
    retrieved_chunks: Optional[List[RetrievedChunk]] = None
    initial_retrieved_chunks: Optional[List[RetrievedChunk]] = None
    expanded_retrieved_chunks: Optional[List[RetrievedChunk]] = None
    citations: Optional[List[dict]] = None


class ChatResponse(BaseModel):
    """对话响应（非流式）。

    Fields:
        response: Agent 的文本响应。
        rag_trace: RAG 检索追踪信息（仅在使用了知识库检索时提供）。
    """
    response: str
    rag_trace: Optional[RagTrace] = None


class MessageInfo(BaseModel):
    """会话中的单条消息信息。

    Fields:
        type: 消息类型（"human" / "ai" / "system"）。
        content: 消息文本内容。
        timestamp: ISO 8601 格式的时间戳。
        rag_trace: 与该消息关联的 RAG 追踪信息（可选，仅 AI 消息可能包含）。
    """
    type: str
    content: str
    timestamp: str
    rag_trace: Optional[RagTrace] = None


class SessionMessagesResponse(BaseModel):
    """会话消息列表响应。

    Fields:
        messages: 消息列表。
    """
    messages: List[MessageInfo]


class SessionInfo(BaseModel):
    """会话摘要信息。

    Fields:
        session_id: 会话 ID。
        updated_at: 最后更新时间（ISO 8601）。
        message_count: 会话中的消息总数。
    """
    session_id: str
    updated_at: str
    message_count: int


class SessionListResponse(BaseModel):
    """会话列表响应。

    Fields:
        sessions: 会话摘要列表。
    """
    sessions: List[SessionInfo]


class SessionDeleteResponse(BaseModel):
    """会话删除响应。

    Fields:
        session_id: 被删除的会话 ID。
        message: 删除结果描述。
    """
    session_id: str
    message: str


# ═══════════════════════════════════════════════════════════════════
# 文档管理相关 Schema
# ═══════════════════════════════════════════════════════════════════


class DocumentInfo(BaseModel):
    """文档基本信息（用于文档列表）。

    Fields:
        filename: 文件名。
        file_type: 文件类型（如 "pdf", "docx"）。
        chunk_count: 该文档的向量分块总数。
        uploaded_at: 上传时间（可选）。
    """
    filename: str
    file_type: str
    chunk_count: int
    uploaded_at: Optional[str] = None


class DocumentListResponse(BaseModel):
    """文档列表响应。

    Fields:
        documents: 文档信息列表。
    """
    documents: List[DocumentInfo]


class DocumentUploadResponse(BaseModel):
    """同步文档上传完成响应（旧版同步接口）。

    Fields:
        filename: 文件名。
        chunks_processed: 处理的叶子分块总数。
        message: 结果描述消息。
    """
    filename: str
    chunks_processed: int
    message: str


class DocumentUploadStartResponse(BaseModel):
    """异步文档上传启动响应。

    Fields:
        job_id: 后台任务 ID，用于轮询进度。
        filename: 文件名。
        message: 状态描述消息。
    """
    job_id: str
    filename: str
    message: str


class UploadStepInfo(BaseModel):
    """上传/处理任务的单个步骤信息。

    Fields:
        key: 步骤键标识（如 "parse", "vector_store"）。
        label: 步骤显示名称（如 "解析与分块"）。
        percent: 进度百分比（0-100）。
        status: 步骤状态（"pending" / "running" / "completed" / "failed"）。
        message: 步骤状态描述消息。
    """
    key: str
    label: str
    percent: int
    status: str
    message: str = ""


class DocumentUploadJobResponse(BaseModel):
    """上传/处理任务进度响应。

    Fields:
        job_id: 任务 ID。
        filename: 文件名。
        status: 任务整体状态。
        current_step: 当前正在执行的步骤键。
        message: 当前状态描述消息。
        total_chunks: 总分块数。
        processed_chunks: 已处理分块数。
        error: 错误信息（失败时）。
        created_at: 任务创建时间（ISO 8601）。
        updated_at: 任务最后更新时间（ISO 8601）。
        steps: 各步骤详情列表。
    """
    job_id: str
    filename: str
    status: str
    current_step: str
    message: str
    total_chunks: int = 0
    processed_chunks: int = 0
    error: Optional[str] = None
    created_at: str
    updated_at: str
    steps: List[UploadStepInfo]


class DocumentDeleteStartResponse(BaseModel):
    """异步文档删除启动响应。

    Fields:
        job_id: 后台任务 ID。
        filename: 要删除的文件名。
        message: 状态描述消息。
    """
    job_id: str
    filename: str
    message: str


class DocumentDeleteJobResponse(DocumentUploadJobResponse):
    """文档删除任务进度响应 —— 结构与上传任务相同，继承 DocumentUploadJobResponse。

    所有字段含义与父类一致，不再重复定义。
    """
    pass


class DocumentDeleteResponse(BaseModel):
    """同步文档删除完成响应（旧版同步接口）。

    Fields:
        filename: 被删除的文件名。
        chunks_deleted: 删除的向量分块数量。
        message: 操作结果描述。
    """
    filename: str
    chunks_deleted: int
    message: str


# ═══════════════════════════════════════════════════════════════════
# 增量导入相关 Schema
# ═══════════════════════════════════════════════════════════════════


class IncrementalIngestRequest(BaseModel):
    """增量导入请求 —— 扫描指定目录中的 PDF，仅处理新增或修改的文件。

    Fields:
        directory: 要扫描的目录路径。若为 None，则使用默认的 UPLOAD_DIR。
        full_rebuild: 是否执行全量重建。为 True 时会重新处理所有文件，
                      忽略已有的摄入状态记录。
    """
    directory: Optional[str] = None
    full_rebuild: bool = False


class IncrementalIngestResponse(BaseModel):
    """增量导入响应 —— 返回批量导入任务的启动状态。

    Fields:
        job_id: 后台导入任务 ID（空字符串表示无需处理）。
        message: 状态描述消息。
        files_total: 扫描到的 PDF 文件总数。
        files_new: 新增文件数。
        files_modified: 修改文件数。
        files_skipped: 跳过（已是最新）的文件数。
        files_deleted: 从状态中移除（原文件已不存在）的文件数。
    """
    job_id: str
    message: str
    files_total: int = 0
    files_new: int = 0
    files_modified: int = 0
    files_skipped: int = 0
    files_deleted: int = 0


# ═══════════════════════════════════════════════════════════════════
# 工作空间相关 Schema
# ═══════════════════════════════════════════════════════════════════


class WorkspaceCreate(BaseModel):
    """创建工作空间请求。

    Fields:
        name: 工作空间名称（必填，非空）。
    """
    name: str


class WorkspaceResponse(BaseModel):
    """工作空间信息响应。

    Fields:
        id: 工作空间 ID。
        name: 工作空间名称。
        owner_id: 所有者用户 ID。
        created_at: 创建时间。
        updated_at: 更新时间。
    """
    id: int
    name: str
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceMemberAdd(BaseModel):
    """添加工作空间成员请求。

    Fields:
        user_id: 要添加的用户 ID。
        role: 成员角色（默认 "member"）。
    """
    user_id: int
    role: str = "member"


class WorkspaceMemberResponse(BaseModel):
    """工作空间成员信息响应。

    Fields:
        id: 成员记录 ID。
        user_id: 用户 ID。
        username: 用户名。
        role: 成员角色。
        created_at: 加入时间。
    """
    id: int
    user_id: int
    username: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class WorkspaceListResponse(BaseModel):
    """工作空间列表响应。

    Fields:
        workspaces: 工作空间列表。
    """
    workspaces: List[WorkspaceResponse]


class WorkspaceMemberListResponse(BaseModel):
    """工作空间成员列表响应。

    Fields:
        members: 成员列表。
    """
    members: List[WorkspaceMemberResponse]
