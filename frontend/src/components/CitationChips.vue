<template>
  <div class="citations-section" v-if="citations.length > 0 || unsupported.length > 0">
    <div class="citations-header">
      <span class="citations-icon">📎</span>
      <span class="citations-title">引用来源</span>
    </div>
    <div class="citation-chips" v-if="citations.length > 0">
      <span 
        v-for="(cite, idx) in citations" 
        :key="idx"
        class="citation-chip verified"
      >
        {{ cite }}
      </span>
    </div>
    <div class="unsupported-section" v-if="unsupported.length > 0">
      <span class="unsupported-label">未验证引用:</span>
      <div class="citation-chips unsupported">
        <span 
          v-for="(cite, idx) in unsupported" 
          :key="idx"
          class="citation-chip unsupported"
        >
          {{ cite }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  citations?: string[]
  unsupported?: string[]
}>()
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
