// 唯一与后端对话的出口（`docs/rules/10-frontend-structure.md` R1/R2/R5）：
// BASE、鉴权头、错误信封解析、401 处理只在这里实现一次；上层拿到的是 DTO 或 ApiError。
// check_frontend.py 会拒绝任何其它文件出现 fetch / XMLHttpRequest / .json()。
import { clearSession, readToken } from "./token"
import { emitAppEvent } from "./events"
import type { DetailError } from "./types"

export const BASE = "/api/v1"

/** 传输层失败的原因码：api 层不产人类文案，翻译交给 utils/errors.ts（`docs/rules/10-frontend-structure.md` R9） */
export const REASON_EMPTY_BODY = "empty_response_body"
export const REASON_UPLOAD_FAILED = "upload_failed"
export const REASON_UPLOAD_TIMEOUT = "upload_timeout"
export const REASON_UPLOAD_ABORTED = "upload_aborted"

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE"

export interface RequestOptions {
  method?: HttpMethod
  /** 传对象即可，序列化与 Content-Type 由本层负责 */
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
  /** 默认 true；register/login 传 false（契约里它们是 security: []） */
  auth?: boolean
}

export interface UploadOptions {
  method: HttpMethod
  signal?: AbortSignal
  onProgress?: (percent: number) => void
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401
}

function authHeaders(extra: Record<string, string>, withAuth: boolean): Record<string, string> {
  const headers: Record<string, string> = { ...extra }
  const token = withAuth ? readToken() : ""
  if (token) headers["Authorization"] = `Bearer ${token}`
  return headers
}

/** 401 只有一个动作：清掉本地登录态并广播，收尾交给订阅方（App.vue） */
function expireSession(): void {
  clearSession()
  emitAppEvent("auth-expired")
}

/** 错误信封全仓只有 {"detail": "..."} 一种（决策 K1/K4）；缺键或非 JSON 时退回状态码 */
function detailFromJson(raw: string, status: number): string {
  try {
    const body = JSON.parse(raw) as Partial<DetailError>
    return typeof body.detail === "string" && body.detail ? body.detail : `HTTP ${status}`
  } catch (_) {
    // 网关直接回 HTML 之类，原样透出反而更好排查
    return raw || `HTTP ${status}`
  }
}

function toApiError(res: Response): Promise<ApiError> {
  return res.text().then((raw) => new ApiError(res.status, detailFromJson(raw, res.status)))
}

function jsonInit(opts: RequestOptions): RequestInit {
  const headers = authHeaders(opts.headers || {}, opts.auth !== false)
  const init: RequestInit = { method: opts.method || "GET", headers }
  if (opts.body !== undefined) {
    init.headers = { ...headers, "Content-Type": "application/json" }
    init.body = JSON.stringify(opts.body)
  }
  if (opts.signal) init.signal = opts.signal
  return init
}

async function handle(res: Response): Promise<Response> {
  if (res.status === 401) {
    const err = await toApiError(res)
    expireSession()
    throw err
  }
  if (!res.ok) throw await toApiError(res)
  return res
}

/** 发一次请求并把 JSON 响应解成 DTO；非 2xx 一律抛 ApiError */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await handle(await fetch(BASE + path, jsonInit(opts)))
  return (await res.json()) as T
}

/** SSE：直接交出可读流，分帧由 api/sse.ts 处理；响应没有 body 时按错误处理而不是让上层判空 */
export async function openStream(path: string, opts: RequestOptions = {}): Promise<ReadableStream<Uint8Array>> {
  const res = await handle(await fetch(BASE + path, jsonInit(opts)))
  if (!res.body) throw new ApiError(res.status, REASON_EMPTY_BODY)
  return res.body
}

/**
 * multipart 上传走 XHR 而不是 fetch：浏览器只在 XHR 的 upload 事件上给得出传输进度。
 * 调用方必须显式写 method，因为 check_contracts.py 靠同一语句里的 method 字面量判定动词。
 */
export function uploadFile<T>(path: string, file: File, opts: UploadOptions): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append("file", file)
    xhr.open(opts.method, BASE + path)
    xhr.timeout = 120_000
    const token = readToken()
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`)
    xhr.upload.onprogress = (e: ProgressEvent) => {
      if (e.lengthComputable && opts.onProgress) opts.onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      const failed = xhr.status < 200 || xhr.status >= 300
      if (xhr.status === 401) expireSession()
      if (failed) {
        reject(new ApiError(xhr.status, detailFromJson(xhr.responseText, xhr.status)))
        return
      }
      try { resolve(JSON.parse(xhr.responseText || "{}") as T) }
      catch (_) { reject(new ApiError(xhr.status, "invalid_response")) }
    }
    xhr.onerror = () => reject(new ApiError(0, REASON_UPLOAD_FAILED))
    xhr.ontimeout = () => reject(new ApiError(0, REASON_UPLOAD_TIMEOUT))
    xhr.onabort = () => reject(new ApiError(0, REASON_UPLOAD_ABORTED))
    const abort = () => xhr.abort()
    xhr.onloadend = () => opts.signal?.removeEventListener("abort", abort)
    if (opts.signal?.aborted) {
      reject(new ApiError(0, REASON_UPLOAD_ABORTED))
      return
    }
    opts.signal?.addEventListener("abort", abort, { once: true })
    xhr.send(form)
  })
}
