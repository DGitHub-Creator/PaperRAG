// 与 contracts/openapi.yaml 的 components/schemas 一一对应的 DTO。
// 改名规则：schema 名原样搬过来，字段名不翻译——契约与前端必须能逐字对照，
// Go 接管后端后同一份类型直接复用（`docs/rules/10-frontend-structure.md` R6）。

export type Role = "user" | "admin"

/** 全局唯一错误信封（决策 K1/K4） */
export interface DetailError {
  detail: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  password: string
  role?: Role
  admin_code?: string | null
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type?: string
  username: string
  role: Role
}

export interface CurrentUserResponse {
  username: string
  role: Role
}

export interface ChatRequest {
  message: string
  session_id?: string | null
}

/** 契约只锁 tool_used / tool_name，其余字段由 Python 侧透传（openapi.yaml: RagTrace） */
export interface RagTrace {
  tool_used: boolean
  tool_name: string
  [key: string]: unknown
}

/** SSE/WS 共用的步骤帧，三个字段都由 emit_rag_step 实参给出 */
export interface RagStep {
  icon: string
  label: string
  detail: string
}

/** 契约只锁「数组元素是对象」，元素形状由 backend/agent/verify.py 的 _format_citation 演进 */
export interface CitationItem {
  source_label?: string
  filename?: string | null
  page?: number | null
  chunk_id?: string | null
  supported?: boolean
  reason?: string
}

export interface StreamContentEvent {
  type: "content"
  content: string
}

export interface StreamRagStepEvent {
  type: "rag_step"
  step: RagStep
}

export interface StreamCitationsEvent {
  type: "citations"
  citations: CitationItem[]
  unsupported: CitationItem[]
}

export interface StreamTraceEvent {
  type: "trace"
  rag_trace?: RagTrace | null
  source_map?: Record<string, unknown>
}

export interface StreamErrorEvent {
  type: "error"
  content: string
}

/** 仅 WS 通道存在；SSE 靠流结束与字面量 [DONE] 帧 */
export interface StreamDoneEvent {
  type: "done"
}

export type StreamEvent =
  | StreamContentEvent
  | StreamRagStepEvent
  | StreamCitationsEvent
  | StreamTraceEvent
  | StreamErrorEvent
  | StreamDoneEvent

export interface MessageInfo {
  /** 实测 human/ai/system，后端不校验 */
  type: string
  content: string
  timestamp: string
  rag_trace?: RagTrace | null
}

export interface SessionInfo {
  session_id: string
  updated_at: string
  message_count: number
}

export interface SessionListResponse {
  sessions: SessionInfo[]
}

export interface SessionMessagesResponse {
  messages: MessageInfo[]
}

export interface SessionDeleteResponse {
  session_id: string
  message: string
}

export interface DocumentInfo {
  filename: string
  file_type: string
  chunk_count: number
  /** As-Is 恒为 null（openapi.yaml 的 listDocuments 说明），前端不得依赖它有值 */
  uploaded_at?: string | null
}

export interface DocumentListResponse {
  documents: DocumentInfo[]
}

/** 受理响应：没有 status / steps，进度只能查 jobs */
export interface JobStartResponse {
  job_id: string
  filename: string
  message: string
}

export type JobStepStatus = "pending" | "running" | "completed" | "failed"

export interface JobStep {
  key: string
  label: string
  percent: number
  status: JobStepStatus
  message?: string
}

export interface JobStatusResponse {
  job_id: string
  filename?: string
  status: JobStepStatus
  current_step?: string
  message: string
  total_chunks?: number
  processed_chunks?: number
  error?: string | null
  created_at?: string
  updated_at?: string
  steps: JobStep[]
}

export interface HealthResponse {
  status: "ok"
  version?: string
}
