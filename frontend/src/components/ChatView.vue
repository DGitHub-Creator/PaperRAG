<template>
  <div v-show="activeNav !== 'settings'" class="chat-area">
    <header class="chat-header">
      <div class="header-info"><div class="status-dot"></div><span>喵喵在线中...</span></div>
      <div class="header-actions"><button class="icon-btn" title="更多"><i class="fas fa-ellipsis-h"></i></button></div>
    </header>

    <div class="chat-container" ref="chatContainer">
      <div v-if="!messages.length" class="welcome-screen">
        <div class="big-avatar">🐱</div>
        <h3>你好呀！我是喵喵</h3>
        <p>我可以帮你写代码、回答问题，或者只是陪你聊天~ 喵！</p>
      </div>

      <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.isUser ? 'user-message' : 'bot-message']">
        <div v-if="!msg.isUser && msg.isThinking && !msg.text" class="message-content thinking-content">
          <div class="thinking-header">
            <div class="thinking-dots"><span class="tdot"></span><span class="tdot"></span><span class="tdot"></span></div>
            <span class="thinking-text">{{ msg.ragSteps?.length ? msg.ragSteps[msg.ragSteps.length - 1].label : '正在思考中...' }}</span>
          </div>
          <div v-if="msg.ragSteps?.length" class="thinking-trace-lines">
            <div v-for="(step, sIdx) in msg.ragSteps" :key="sIdx" class="thinking-trace-line">
              <span class="thinking-trace-icon">{{ step.icon || '▶' }}</span>
              <span class="thinking-trace-label">{{ step.label }}</span>
              <span v-if="step.detail" class="thinking-trace-detail">{{ step.detail }}</span>
            </div>
          </div>
        </div>
        <div v-else class="message-content" v-html="msg.isUser ? escapeHtml(msg.text) : parseMarkdown(msg.text)"></div>
        <div v-if="!msg.isUser && msg.ragTrace" class="message-meta">
          <details class="reasoning-details">
            <summary>检索过程</summary>
            <div class="reasoning-content">
              <RagTracePanel :trace="msg.ragTrace" />
            </div>
          </details>
        </div>
      </div>
    </div>

    <div class="input-area-wrapper">
      <div class="input-area">
        <button class="attach-btn"><i class="fas fa-paperclip"></i></button>
        <textarea
          v-model="userInput"
          @keydown="handleKeyDown"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          @input="autoResize"
          placeholder="和喵喵说点什么吧... (Shift+Enter 换行)"
          rows="1"
          ref="textareaRef"
        ></textarea>
        <button v-if="isLoading" @click="stop" class="send-btn stop-btn" title="终止回答">
          <i class="fas fa-stop"></i>
        </button>
        <button v-else @click="handleSend" class="send-btn" title="发送">
          <i class="fas fa-paper-plane"></i>
        </button>
      </div>
      <div class="footer-text">AI 生成的内容可能包含错误，请仔细甄别。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import RagTracePanel from "./RagTracePanel.vue"
import { useChat } from "../composables/useChat"
import { parseMarkdown, escapeHtml } from "../utils/markdown"

const { messages, isLoading, send, stop } = useChat()

defineProps({ activeNav: { type: String, default: "newChat" } })
const userInput = ref("")
const isComposing = ref(false)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

function handleKeyDown(e: KeyboardEvent): void {
  if (e.key === "Enter" && !e.shiftKey && !isComposing.value) {
    e.preventDefault()
    handleSend()
  }
}

function handleSend(): void {
  const text = userInput.value.trim()
  if (!text || isLoading.value || isComposing.value) return
  userInput.value = ""
  send(text)
}

function autoResize(e: Event): void {
  const ta = e.target as HTMLTextAreaElement
  ta.style.height = "auto"
  ta.style.height = ta.scrollHeight + "px"
}
</script>
