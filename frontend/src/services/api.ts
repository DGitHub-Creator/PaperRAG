const BASE = ""

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
    window.location.reload()
    throw new Error("登录已过期")
  }
  return response
}

export function getFileIcon(fileType: string): string {
  if (fileType === "PDF") return "fas fa-file-pdf"
  if (fileType === "Word") return "fas fa-file-word"
  if (fileType === "Excel") return "fas fa-file-excel"
  return "fas fa-file"
}
