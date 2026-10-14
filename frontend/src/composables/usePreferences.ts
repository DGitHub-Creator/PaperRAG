// 用户偏好（模块级单例）：theme 与 start_view 的唯一所有者，跨页面共用（设置页改、顶栏/登录页读）。
// 主题落到 DOM 的那一步委托 utils/theme.ts —— R3 不允许状态层出现 document。
import { ref } from "vue"
import * as api from "../api/client"
import { applyTheme } from "../utils/theme"
import type { UserPreferences } from "../api/types"

/** 与后端 `user_preferences` 的列默认值一致（迁移 000003：theme='system' / start_view='chat'） */
export const DEFAULT_PREFERENCES: UserPreferences = { theme: "system", start_view: "chat" }

const preferences = ref<UserPreferences>({ ...DEFAULT_PREFERENCES })
const isLoading = ref(false)
const isSaving = ref(false)

export function usePreferences() {
  /** 拉自己的偏好并立刻应用主题；失败由调用方决定（设置页提示、启动期静默回默认） */
  async function load(): Promise<void> {
    isLoading.value = true
    try {
      const next = await api.getPreferences()
      preferences.value = next
      applyTheme(next.theme)
    } finally {
      isLoading.value = false
    }
  }

  async function save(next: UserPreferences): Promise<void> {
    isSaving.value = true
    try {
      const saved = await api.putPreferences(next)
      preferences.value = saved
      applyTheme(saved.theme)
    } finally {
      isSaving.value = false
    }
  }

  /** 登出与 401 收尾：回到默认并卸掉主题覆盖 */
  function reset(): void {
    preferences.value = { ...DEFAULT_PREFERENCES }
    applyTheme(DEFAULT_PREFERENCES.theme)
  }

  return { preferences, isLoading, isSaving, load, save, reset }
}
