<template>
  <div class="app-wrapper">
    <Sidebar
      :isAdmin="isAdmin"
      :isAuthenticated="isAuthenticated"
      :username="username"
      :role="role"
      :activeNav="activeNav"
      @newChat="handleNewChat"
      @showHistory="handleHistory"
      @showSettings="handleSettings"
      @clearChat="handleClearChat"
      @logout="handleLogout"
    />
    <main class="main-content">
      <AuthPanel v-if="!isAuthenticated" @authenticated="handleAuthenticated" />
      <SettingsView v-else-if="activeNav === 'settings' && isAdmin" />
      <HistorySidebar
        v-else-if="historyOpen"
        :sessions="sessions"
        :currentSessionId="sessionId"
        @load="handleLoadSession"
        @delete="handleDeleteSession"
        @close="historyOpen = false"
      />
      <ChatView v-show="activeNav !== 'settings'" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, watch } from "vue"
import Sidebar from "./components/Sidebar.vue"
import ChatView from "./components/ChatView.vue"
import AuthPanel from "./components/AuthPanel.vue"
import SettingsView from "./components/SettingsView.vue"
import HistorySidebar from "./components/HistorySidebar.vue"
import { useAuth } from "./composables/useAuth"
import { useChat } from "./composables/useChat"
import { useDocuments } from "./composables/useDocuments"
import { useNav } from "./composables/useNav"
import { useSessions } from "./composables/useSessions"
import { onAppEvent } from "./api/events"
import { t } from "./i18n"
import { alertDialog, confirmDialog } from "./utils/dialog"
import { describeError } from "./utils/errors"

const { token, isAuthenticated, isAdmin, username, role, fetchMe, logout } = useAuth()
const { sessionId, newChat, clearChat, loadHistory, selectSession, connectWs, reset: resetChat } = useChat()
const { sessions, refresh: refreshSessions, load: loadSession, remove: removeSession, reset: resetSessions } = useSessions()
const { reset: resetDocuments } = useDocuments()
const { activeNav, historyOpen, reset: resetNav } = useNav()

// 401 由 api 层广播，这里订阅一次并在卸载时退订（此前是无名函数常驻 window，重挂载就重复注册）
let offUnauthorized: (() => void) | null = null

function handleLogout(): void {
  logout()
  resetChat()
  resetSessions()
  resetDocuments()
}

/** 登录后（含刷新页面恢复的登录态）要做的三件事：开新会话、回到聊天视图、接上 WS */
function handleAuthenticated(): void {
  newChat()
  resetNav()
  connectWs(token.value)
}

onMounted(() => {
  offUnauthorized = onAppEvent("auth-expired", handleLogout)
  if (!token.value) return
  // token 失效是启动期的常态：清干净回到登录面板即可，不额外弹窗
  fetchMe()
    .then(handleAuthenticated)
    .catch(handleLogout)
})

onUnmounted(() => {
  if (offUnauthorized) offUnauthorized()
  offUnauthorized = null
})

watch(isAuthenticated, (value: boolean) => {
  if (!value) resetNav()
})

function handleNewChat(): void {
  newChat()
  resetNav()
}

function handleClearChat(): void {
  if (confirmDialog(t("nav.clear_confirm"))) clearChat()
}

async function handleHistory(): Promise<void> {
  activeNav.value = "history"
  historyOpen.value = true
  try {
    await refreshSessions()
  } catch (err: unknown) {
    alertDialog(`${t("history.load_failed")}${describeError(err)}`)
  }
}

function handleSettings(): void {
  activeNav.value = "settings"
  historyOpen.value = false
}

async function handleLoadSession(id: string): Promise<void> {
  selectSession(id)
  activeNav.value = "newChat"
  historyOpen.value = false
  try {
    const data = await loadSession(id)
    loadHistory(data.messages || [])
  } catch (err: unknown) {
    alertDialog(`${t("history.load_session_failed")}${describeError(err)}`)
  }
}

async function handleDeleteSession(id: string): Promise<void> {
  if (!confirmDialog(t("history.delete_confirm"))) return
  try {
    await removeSession(id)
  } catch (err: unknown) {
    alertDialog(`${t("history.delete_failed")}${describeError(err)}`)
    return
  }
  // 删掉的是当前会话就开一段新的，否则消息列表会指向一个已不存在的 session_id
  if (sessionId.value === id) newChat()
}
</script>
