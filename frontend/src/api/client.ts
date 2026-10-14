// 契约里的每条操作对应这里的一个函数（`docs/rules/10-frontend-structure.md` R1/R6）。
// 路径字面量只出现在这个文件：check_contracts.py 从这些字面量现场抽取「前端实调集合」，
// 与 contracts/openapi.yaml 双向比对，所以新增接口必须同时改契约与本文件，两边都会机检。
import { openStream, request, uploadFile } from "./http"
import { readSse } from "./sse"
import type {
  AuthResponse,
  ChatRequest,
  CurrentUserResponse,
  DocumentListResponse,
  JobStartResponse,
  JobStatusResponse,
  LoginRequest,
  RegisterRequest,
  SessionDeleteResponse,
  SessionListResponse,
  SessionMessagesResponse,
  StreamEvent,
} from "./types"

export function register(input: RegisterRequest): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/register", { method: "POST", auth: false, body: input })
}

export function login(input: LoginRequest): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", { method: "POST", auth: false, body: input })
}

export function me(): Promise<CurrentUserResponse> {
  return request<CurrentUserResponse>("/auth/me")
}

export function listSessions(): Promise<SessionListResponse> {
  return request<SessionListResponse>("/sessions")
}

export function getSession(sessionId: string): Promise<SessionMessagesResponse> {
  return request<SessionMessagesResponse>(`/sessions/${encodeURIComponent(sessionId)}`)
}

export function deleteSession(sessionId: string): Promise<SessionDeleteResponse> {
  return request<SessionDeleteResponse>(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" })
}

/** SSE 问答：事件本体交给 onEvent，终止由调用方通过 signal 触发 */
export async function chatStream(
  input: ChatRequest,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const body = await openStream("/chat/stream", { method: "POST", body: input, signal })
  await readSse(body, onEvent)
}

export function listDocuments(): Promise<DocumentListResponse> {
  return request<DocumentListResponse>("/documents")
}

/** 显式写 method 不是冗余：check_contracts.py 在同一条语句里找 method 字面量来判定动词 */
export function startUploadJob(file: File, onProgress: (percent: number) => void): Promise<JobStartResponse> {
  return uploadFile<JobStartResponse>("/documents/upload/async", file, { method: "POST", onProgress })
}

export function getUploadJob(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/documents/upload/jobs/${encodeURIComponent(jobId)}`)
}

export function startDeleteJob(filename: string): Promise<JobStartResponse> {
  return request<JobStartResponse>(`/documents/delete/async/${encodeURIComponent(filename)}`, { method: "DELETE" })
}

export function getDeleteJob(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/documents/delete/jobs/${encodeURIComponent(jobId)}`)
}
