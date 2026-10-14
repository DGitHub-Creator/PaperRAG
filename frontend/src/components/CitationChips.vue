<template>
  <div class="citations-section">
    <div class="citations-header">
      <span class="citations-icon">📎</span>
      <span class="citations-title">{{ $t("chat.citations_title") }}</span>
    </div>
    <div class="citation-chips" v-if="citations.length">
      <span v-for="(cite, idx) in citations" :key="idx" class="citation-chip verified">{{ chipText(cite) }}</span>
    </div>
    <div class="unsupported-section" v-if="unsupported.length">
      <span class="unsupported-label">{{ $t("chat.unsupported_label") }}</span>
      <div class="citation-chips unsupported">
        <span v-for="(cite, idx) in unsupported" :key="idx" class="citation-chip unsupported">{{ chipText(cite) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CitationItem } from "../api/types"

withDefaults(defineProps<{
  citations?: CitationItem[]
  unsupported?: CitationItem[]
}>(), {
  citations: () => [],
  unsupported: () => [],
})

// 引用帧的元素是对象（backend/agent/verify.py:_format_citation），不是字符串
function chipText(cite: CitationItem): string {
  const parts = [cite.source_label || ""]
  if (cite.filename) parts.push(cite.filename)
  if (cite.page !== null && cite.page !== undefined) parts.push(`p.${cite.page}`)
  return parts.filter(Boolean).join(" · ")
}
</script>

<style scoped>
.citations-section {
  margin-top: 10px;
  padding: 11px 12px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.citations-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
}

.citations-title {
  font-weight: 600;
}

.citation-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.citation-chip {
  display: inline-block;
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  font-size: 11.5px;
  font-family: var(--font-mono);
}

.citation-chip.verified {
  background: var(--ok-soft);
  color: var(--ok);
  border: 1px solid #c6ecd2;
}

.citation-chip.unsupported {
  background: var(--warn-soft);
  color: var(--warn);
  border: 1px solid #fbd9bf;
  text-decoration: line-through;
}

.unsupported-section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.unsupported-label {
  display: block;
  margin-bottom: 4px;
  font-size: 11.5px;
  color: var(--text-faint);
}
</style>
