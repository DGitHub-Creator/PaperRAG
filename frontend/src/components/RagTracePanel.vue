<template>
  <details class="rag-trace">
    <summary>RAG 检索详情</summary>
    <div v-for="(step, i) in steps" :key="i" class="trace-step">
      <strong>{{ step.label }}</strong>
      <p>{{ step.detail }}</p>
    </div>
  </details>
</template>

<script setup>
defineProps({ steps: Array });
</script>
