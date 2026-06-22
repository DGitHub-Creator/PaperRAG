<template>
  <div class="rag-trace-panel">
    <div v-for="(entry, i) in trace" :key="i" class="trace-item">
      <span class="trace-step">{{ entry.step }}</span>
      <span v-if="entry.label" class="trace-label">{{ entry.label }}</span>
      <span v-if="entry.score" class="trace-score">{{ (entry.score * 100).toFixed(1) }}%</span>
      <span v-if="entry.time_ms" class="trace-time">{{ entry.time_ms }}ms</span>
      <span v-if="entry.message" class="trace-msg">{{ entry.message }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RAGTraceEntry } from "../composables/useChat"

defineProps<{ trace: RAGTraceEntry[] }>()
</script>
