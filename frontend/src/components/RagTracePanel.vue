<template>
  <div class="rag-trace-panel">
    <div class="trace-section" v-if="trace?.retrieved_chunks?.length">
      <div class="trace-section-title">Retrieved Chunks</div>
      <div
        v-for="(chunk, i) in trace.retrieved_chunks"
        :key="i"
        :class="['trace-item', 'trace-item--chunk', { 'trace-item--highlighted': highlightedChunk === i + 1 }]"
        :data-index="i + 1"
      >
        <span class="trace-index">[{{ i + 1 }}]</span>
        <span class="trace-filename">{{ chunk.filename }}</span>
        <span v-if="chunk.page_number" class="trace-page">p.{{ chunk.page_number }}</span>
        <span v-if="chunk.score" class="trace-score">{{ (chunk.score * 100).toFixed(1) }}%</span>
        <span v-if="chunk.rerank_score" class="trace-rerank">rerank: {{ (chunk.rerank_score * 100).toFixed(1) }}%</span>
      </div>
    </div>

    <div class="trace-section" v-if="trace?.citations?.length">
      <div class="trace-section-title">Citations Used</div>
      <div
        v-for="cit in trace.citations"
        :key="cit.index"
        :class="['trace-item', 'trace-item--citation']"
      >
        <span class="trace-index citation-badge">[{{ cit.index }}]</span>
        <span class="trace-filename">{{ cit.filename }}</span>
        <span v-if="cit.page" class="trace-page">p.{{ cit.page }}</span>
      </div>
    </div>

    <div class="trace-section" v-if="trace?.query">
      <div class="trace-section-title">Query</div>
      <div class="trace-item trace-item--meta">
        <span class="trace-label">Original:</span>
        <span class="trace-value">{{ trace.query }}</span>
      </div>
      <div v-if="trace.expanded_query && trace.expanded_query !== trace.query" class="trace-item trace-item--meta">
        <span class="trace-label">Expanded:</span>
        <span class="trace-value">{{ trace.expanded_query }}</span>
      </div>
    </div>

    <div class="trace-section" v-if="trace?.retrieval_mode">
      <div class="trace-section-title">Pipeline</div>
      <div class="trace-item trace-item--meta">
        <span class="trace-label">Mode:</span>
        <span class="trace-value">{{ trace.retrieval_mode }}</span>
      </div>
      <div v-if="trace.rerank_applied" class="trace-item trace-item--meta">
        <span class="trace-label">Rerank:</span>
        <span class="trace-value">{{ trace.rerank_model }} ({{ trace.rerank_endpoint }})</span>
      </div>
      <div v-if="trace.auto_merge_applied" class="trace-item trace-item--meta">
        <span class="trace-label">Auto-merge:</span>
        <span class="trace-value">{{ trace.auto_merge_replaced_chunks }} chunks merged (threshold={{ trace.auto_merge_threshold }})</span>
      </div>
      <div v-if="trace.context_expansion_applied" class="trace-item trace-item--meta">
        <span class="trace-label">Context expansion:</span>
        <span class="trace-value">{{ trace.expanded_chunk_count }} chunks (prev={{ trace.expand_prev_parent }}, next={{ trace.expand_next_parent }})</span>
      </div>
    </div>

    <div v-if="!trace?.retrieved_chunks?.length && !trace?.query" class="trace-empty">
      No trace data available.
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RAGTraceEntry } from "../composables/useChat"

const props = defineProps<{
  trace: RAGTraceEntry[] | Record<string, any> | null
  highlightedChunk?: number | null
}>()
</script>

<style scoped>
.rag-trace-panel {
  font-size: 0.85rem;
  color: var(--text-secondary, #666);
}

.trace-section {
  margin-bottom: 12px;
}

.trace-section-title {
  font-weight: 600;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted, #999);
  margin-bottom: 6px;
}

.trace-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.3s;
}

.trace-item--chunk {
  cursor: default;
}

.trace-item--highlighted {
  background-color: rgba(59, 130, 246, 0.15);
  outline: 1px solid rgba(59, 130, 246, 0.4);
}

.trace-index {
  font-weight: 700;
  color: var(--accent, #3b82f6);
  flex-shrink: 0;
}

.citation-badge {
  background: rgba(59, 130, 246, 0.12);
  padding: 1px 4px;
  border-radius: 3px;
}

.trace-filename {
  font-weight: 500;
}

.trace-page {
  color: var(--text-muted, #999);
}

.trace-score, .trace-rerank {
  margin-left: auto;
  font-size: 0.8rem;
}

.trace-label {
  color: var(--text-muted, #999);
  flex-shrink: 0;
}

.trace-value {
  word-break: break-word;
}

.trace-empty {
  color: var(--text-muted, #999);
  font-style: italic;
  padding: 8px;
}
</style>
