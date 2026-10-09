// 统一 API 前缀：后端路由全部挂在 /api/v1 下
// 所有 authFetch / fetch 调用都必须经过 BASE，避免路径漂移
export const BASE = "/api/v1"

function getToken(): string {
  return localStorage.getItem("accessToken") || ""
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getToken()
  if (token) extra["Authorization"] = `Bearer ${token}`
  return extra
}

export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const opts = { ...options }
  opts.headers = authHeaders((opts.headers as Record<string, string>) || {})
  const response = await fetch(BASE + url, opts)
  if (response.status === 401) {
    localStorage.removeItem("accessToken")
    localStorage.removeItem("currentUser")
    window.dispatchEvent(new CustomEvent("auth-expired"))
    throw new Error("登录已过期")
  }
  return response
}

/** 无认证请求（登录/注册），同样走统一前缀。 */
export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  return fetch(BASE + url, options)
}

export function getFileIcon(fileType: string): string {
  if (fileType === "PDF") return "fas fa-file-pdf"
  if (fileType === "Word") return "fas fa-file-word"
  if (fileType === "Excel") return "fas fa-file-excel"
  return "fas fa-file"
}
