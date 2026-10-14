<template>
  <div class="page-header">
    <div class="ph-text">
      <h2><Icon :name="icon" :size="19" />{{ $t(titleKey) }}</h2>
      <p v-if="descKey">{{ $t(descKey) }}</p>
    </div>
    <div v-if="$slots.default" class="ph-actions"><slot /></div>
  </div>
</template>

<script setup lang="ts">
import Icon from "./Icon.vue"

defineProps<{ icon: string; titleKey: string; descKey?: string }>()
</script>
