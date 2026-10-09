import { ApiError } from "../api/http"
import { t } from "../i18n"

// api 层只产原因码不产文案（R9），这里负责把已知原因码翻成当前语言，
// 其余（后端 detail、网关文本）原样透出——那是服务器给的，不是前端硬编码的。
const REASON_KEYS: Record<string, string> = {
  upload_failed: "errors.upload_failed",
  upload_timeout: "errors.upload_timeout",
  upload_aborted: "errors.upload_aborted",
  empty_response_body: "errors.empty_response_body",
}

/** 把 unknown 错误压成一句可显示的话：所有 catch 分支共用，避免各处重复 instanceof */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export function describeError(err: unknown): string {
  if (err instanceof ApiError && REASON_KEYS[err.message]) return t(REASON_KEYS[err.message])
  return errorMessage(err)
}

/** fetch/XHR 的取消都是 AbortError，业务上属于"用户主动停"，不该走错误分支 */
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError"
}
