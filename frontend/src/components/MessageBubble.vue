<template>
  <div :class="['message', role]">
    <div class="message-avatar">
      <i :class="role === 'user' ? 'fas fa-user' : 'fas fa-robot'"></i>
    </div>
    <div class="message-content" v-html="rendered"></div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { marked } from "marked";

const props = defineProps({ role: String, content: String });
const rendered = computed(() => marked(props.content || ""));
</script>
