<template>
  <div class="history-sidebar">
    <div class="history-header">
      <h3>{{ $t("history.title") }}</h3>
      <button @click="$emit('close')" class="close-btn"><i class="fas fa-times"></i></button>
    </div>
    <div class="history-list">
      <div v-if="!sessions.length" class="empty-history"><p>{{ $t("history.empty") }}</p></div>
      <div v-for="s in sessions" :key="s.session_id" class="history-item" :class="{ active: s.session_id === currentSessionId }">
        <div class="session-body" @click="$emit('load', s.session_id)">
          <div class="session-info">
            <div class="session-title">{{ s.session_id }}</div>
            <div class="session-meta">
              <span>{{ s.message_count }} {{ $t("history.messages") }}</span>
              <span>{{ s.updated_at ? new Date(s.updated_at).toLocaleString() : '' }}</span>
            </div>
          </div>
        </div>
        <button class="history-delete-btn" title="删除" @click.stop="$emit('delete', s.session_id)">
          <i class="fas fa-trash"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SessionRecord } from "../composables/useSessions"

defineProps<{
  sessions: SessionRecord[]
  currentSessionId: string
}>()
defineEmits<{
  load: [id: string]
  delete: [id: string]
  close: []
}>()
</script>
