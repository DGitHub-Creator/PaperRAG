<template>
  <div class="notice">
    <Icon name="info" :size="15" />
    <div>
      <span class="notice-title">{{ $t("common.sample_notice") }}</span>
      <span>{{ $t("common.sample_hint") }}</span>
      <div class="faint">{{ $t("common.module_owner") }}: {{ module }} · {{ card }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from "./Icon.vue"

// 占位页的诚实声明（`docs/rules/10-frontend-structure.md` §7.1）：
// 页面壳已存在但数据是示例，归属模块与卡片号写死在这里，读者一眼知道"这页什么时候会变真"。
defineProps<{ module: string; card: string }>()
</script>
