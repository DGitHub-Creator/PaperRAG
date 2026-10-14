<template>
  <div class="page-inner">
    <div class="page-header">
      <div class="ph-text">
        <h2><Icon name="clock" :size="19" />{{ $t("views.history.title") }}</h2>
        <p>{{ $t("views.history.desc") }}</p>
      </div>
      <div class="ph-actions">
        <button class="btn-secondary" :disabled="isLoading" @click="reload">
          <Icon name="refresh" :size="14" />{{ $t("settings.refresh") }}
        </button>
      </div>
    </div>

    <div class="card">
      <div v-if="isLoading" class="empty-state"><span class="spinner"></span><span>{{ $t("app.loading") }}</span></div>
      <div v-else-if="!sessions.length" class="empty-state">
        <Icon name="inbox" :size="26" />
        <span>{{ $t("history.empty") }}</span>
      </div>
      <div v-else class="list">
        <div v-for="s in sessions" :key="s.session_id" class="list-item" :class="{ current: s.session_id === sessionId }">
          <div class="li-icon"><Icon name="message" :size="16" /></div>
          <div class="li-main">
            <div class="li-title mono">{{ s.session_id }}</div>
            <div class="li-sub">
              <span>{{ s.message_count }} {{ $t("history.messages") }}</span>
              <span>{{ new Date(s.updated_at).toLocaleString() }}</span>
            </div>
          </div>
          <button class="btn-ghost" @click="openSession(s.session_id)">
            <Icon name="chevron-right" :size="14" />{{ $t("views.history.open") }}
          </button>
          <button class="btn-danger" :title="$t('history.delete')" @click="removeSession(s.session_id)">
            <Icon name="trash" :size="14" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import Icon from "../components/Icon.vue"
import { useSessions } from "../composables/useSessions"
import { useChat } from "../composables/useChat"
import { t } from "../i18n"
import { alertDialog, confirmDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"

const router = useRouter()
const { sessions, refresh, load, remove } = useSessions()
const { sessionId, selectSession, loadHistory, newChat } = useChat()
const isLoading = ref(false)

onMounted(() => { void reload() })

async function reload(): Promise<void> {
  isLoading.value = true
  try {
    await refresh()
  } catch (err: unknown) {
    alertDialog(`${t("history.load_failed")}${describeError(err)}`)
  } finally {
    isLoading.value = false
  }
}

async function openSession(id: string): Promise<void> {
  selectSession(id)
  try {
    const data = await load(id)
    loadHistory(data.messages || [])
    void router.push({ name: "chat" })
  } catch (err: unknown) {
    alertDialog(`${t("history.load_session_failed")}${describeError(err)}`)
  }
}

async function removeSession(id: string): Promise<void> {
  if (!(await confirmDialog(t("history.delete_confirm")))) return
  try {
    await remove(id)
  } catch (err: unknown) {
    alertDialog(`${t("history.delete_failed")}${describeError(err)}`)
    return
  }
  // 删掉的是当前会话就开一段新的，否则聊天视图会指向一个已不存在的 session_id
  if (sessionId.value === id) newChat()
}
</script>

<style scoped>
.li-icon {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  color: var(--text-muted);
}
.list-item.current { background: var(--accent-soft); }
.list-item.current .li-icon { background: #dbe8fd; color: var(--accent); }
</style>
