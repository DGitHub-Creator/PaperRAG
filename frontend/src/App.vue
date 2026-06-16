<template>
  <div class="app-wrapper">
    <Sidebar
      :isAdmin="isAdmin"
      :isAuthenticated="isAuthenticated"
      :username="username"
      :role="currentUser?.role ?? ''"
      :activeNav="activeNav"
      @newChat="handleNewChat"
      @showHistory="handleHistory"
      @showSettings="handleSettings"
      @clearChat="handleClearChat"
      @logout="logout"
    />
    <main class="main-content">
      <AuthPanel v-if="!isAuthenticated" :mode="authMode" @switch="authMode = $event" @submit="handleAuth" />
      <SettingsView v-else-if="activeNav === 'settings' && isAdmin" />
      <HistorySidebar v-else-if="showHistorySidebar" :sessions="sessions" :currentSessionId="sessionId" @load="handleLoadSession" @delete="handleDeleteSession" @close="showHistorySidebar = false" />
      <ChatView v-show="activeNav !== 'settings'" />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from "vue"
import { t } from "./i18n"
import Sidebar from "./components/Sidebar.vue"
import ChatView from "./components/ChatView.vue"
import AuthPanel from "./components/AuthPanel.vue"
import SettingsView from "./components/SettingsView.vue"
import HistorySidebar from "./components/HistorySidebar.vue"
import { useAuth } from "./composables/useAuth"
import { useChat } from "./composables/useChat"
import { useSessions } from "./composables/useSessions"

const { currentUser, isAuthenticated, isAdmin, username, fetchMe, login, register, logout: authLogout } = useAuth()
const { messages, newChat, clearChat, sessionId, loadMessages, connectWs, disconnectWs } = useChat()
const { sessions, showHistorySidebar, list: listSessions, loadMessages: fetchSessionMsgs, remove: deleteSession } = useSessions()

function logout() {
  disconnectWs()
  authLogout()
  messages.value = []
  sessions.value = []
  activeNav.value = "newChat"
  showHistorySidebar.value = false
}

const activeNav = ref("newChat")
const authMode = ref("login")
let initialized = false

onMounted(async () => {
  const token = localStorage.getItem("accessToken")
  if (token) {
    try { await fetchMe(); initialized = true; connectWs(token) }
    catch (_) { logout() }
  }
})

watch(isAuthenticated, (v: boolean) => { if (!v) { activeNav.value = "newChat"; showHistorySidebar.value = false } })

async function handleAuth(username: string, password: string, role: string, adminCode: string | null): Promise<void> {
  if (authMode.value === "login") await login(username, password)
  else await register(username, password, role, adminCode)
  initialized = true
  newChat()
  activeNav.value = "newChat"
  showHistorySidebar.value = false
  const token = localStorage.getItem("accessToken")
  if (token) connectWs(token)
}

function handleNewChat(): void { newChat(); activeNav.value = "newChat"; showHistorySidebar.value = false }
function handleClearChat(): void { if (confirm(t("nav.clear_confirm"))) clearChat() }
async function handleHistory(): Promise<void> { activeNav.value = "history"; showHistorySidebar.value = true; await listSessions() }
function handleSettings(): void { activeNav.value = "settings"; showHistorySidebar.value = false }

async function handleLoadSession(sid: string): Promise<void> {
  sessionId.value = sid
  showHistorySidebar.value = false
  activeNav.value = "newChat"
  const data = await fetchSessionMsgs(sid)
  if (data) loadMessages(data.messages ?? [])
}

async function handleDeleteSession(sid: string): Promise<void> {
  const ok = await deleteSession(sid)
  if (ok && sessionId.value === sid) { clearChat(); sessionId.value = "session_" + Date.now() }
}
</script>
