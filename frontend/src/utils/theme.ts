// 主题落到 DOM 的唯一出口：R3 不允许状态层碰 document，所以这一步放在 utils（与 utils/dialog.ts 同一个套路）。
// theme 的三种取值与三处真相同源——迁移 CHECK（server/migrations/000003_user_preferences.up.sql）、
// Go 常量（server/internal/auth/preferences.go）与契约 enum（contracts/openapi.yaml）——
// 想加第四种必须三处一起改，否则前端切得动、后端 400。
import type { Theme } from "../api/types"

export const THEMES: readonly Theme[] = ["light", "dark", "system"]

export function isTheme(value: string): value is Theme {
  return (THEMES as readonly string[]).includes(value)
}

/** system 交给操作系统偏好决定；其余原样。结果写在 <html data-theme>，variables.css 按它覆盖令牌。 */
export function applyTheme(theme: Theme): void {
  const resolved = theme === "system" ? (prefersDark() ? "dark" : "light") : theme
  document.documentElement.dataset.theme = resolved
}

function prefersDark(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}
