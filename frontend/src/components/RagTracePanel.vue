<template>
  <div class="rag-trace-panel">
    <div v-for="row in rows" :key="row.key" class="trace-item">
      <span class="trace-step">{{ row.key }}</span>
      <span class="trace-msg">{{ row.value }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { t } from "../i18n"
import type { RagTrace } from "../api/types"

const props = defineProps<{ trace: RagTrace }>()

// 契约只锁 tool_used / tool_name，其余键随 Python 侧演进，所以按"有什么显示什么"渲染。
// 此前这里假设 rag_trace 是数组，实际是对象，面板因此恒空白（docs/refactor/10 F7）。
function describe(value: unknown): string {
  if (value === null || value === undefined) return ""
  if (Array.isArray(value)) return t("chat.trace_count", { count: value.length })
  if (typeof value === "object") return t("chat.trace_count", { count: Object.keys(value).length })
  return String(value)
}

const rows = computed(() =>
  Object.entries(props.trace)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => ({ key, value: describe(value) })),
)
</script>
