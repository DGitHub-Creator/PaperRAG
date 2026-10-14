// 视图状态（无路由，单页三个视图 + 历史面板开合）：枚举化避免裸字符串拼错（`docs/rules/10-frontend-structure.md` R10）。
import { ref } from "vue"

export type NavKey = "newChat" | "history" | "settings"

const activeNav = ref<NavKey>("newChat")
const historyOpen = ref(false)

export function useNav() {
  function reset(): void {
    activeNav.value = "newChat"
    historyOpen.value = false
  }

  return { activeNav, historyOpen, reset }
}
