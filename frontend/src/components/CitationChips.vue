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
  margin-top: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

.citations-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #666;
}

.citations-title {
  font-weight: 500;
}

.citation-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.citation-chip {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-family: monospace;
}

.citation-chip.verified {
  background: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.citation-chip.unsupported {
  background: #fff3cd;
  color: #856404;
  border: 1px solid #ffeeba;
  text-decoration: line-through;
}

.unsupported-section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e9ecef;
}

.unsupported-label {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
  display: block;
}
</style>
