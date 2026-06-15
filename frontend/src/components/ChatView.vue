<template>
  <div class="chat-view">
    <div class="messages" ref="messagesRef">
      <MessageBubble
        v-for="(msg, i) in messages"
        :key="i"
        :role="msg.role"
        :content="msg.content"
      />
    </div>
    <div class="input-area-wrapper">
      <div class="input-area">
        <textarea v-model="input" @keydown.enter.exact="send" placeholder="输入你的研究问题..." rows="1"></textarea>
        <button class="send-btn" @click="send"><i class="fas fa-paper-plane"></i></button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import MessageBubble from "./MessageBubble.vue";
import { useSSE } from "../composables/useSSE.js";

const messages = ref([]);
const input = ref("");
const { sendMessage } = useSSE();

function send() {
  if (!input.value.trim()) return;
  messages.value.push({ role: "user", content: input.value });
  sendMessage(input.value, (chunk) => {
    const last = messages.value[messages.value.length - 1];
    if (last?.role === "assistant") last.content += chunk;
    else messages.value.push({ role: "assistant", content: chunk });
  });
  input.value = "";
}
</script>
