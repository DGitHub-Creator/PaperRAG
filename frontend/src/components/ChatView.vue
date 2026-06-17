<template>
  <div v-show="activeNav !== 'settings'" class="chat-area">
    <header class="chat-header">
      <div class="header-info"><div class="status-dot"></div><span>{{ $t("chat.online") }}</span></div>
      <div class="header-actions"><button class="icon-btn" title="更多"><i class="fas fa-ellipsis-h"></i></button></div>
    </header>

    <div class="chat-container" ref="chatContainer">
      <div v-if="!messages.length" class="welcome-screen">
        <div class="big-avatar">🐱</div>
        <h3>{{ $t("chat.welcome_title") }}</h3>
        <p>{{ $t("chat.welcome_desc") }}</p>
      </div>

      <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.isUser ? 'user-message' : 'bot-message']">
        <div v-if="!msg.isUser && msg.isThinking && !msg.text" class="message-content thinking-content">
          <div class="thinking-header">
            <div class="thinking-dots"><span class="tdot"></span><span class="tdot"></span><span class="tdot"></span></div>
            <span class="thinking-text">{{ msg.ragSteps?.length ? msg.ragSteps[msg.ragSteps.length - 1].label : $t('chat.thinking') }}</span>
          </div>
          <div v-if="msg.ragSteps?.length" class="thinking-trace-lines">
            <div v-for="(step, sIdx) in msg.ragSteps" :key="sIdx" class="thinking-trace-line">
              <span class="thinking-trace-icon">{{ step.icon || '▶' }}</span>
              <span class="thinking-trace-label">{{ step.label }}</span>
              <span v-if="step.detail" class="thinking-trace-detail">{{ step.detail }}</span>
            </div>
          </div>
        </div>
        <div v-else class="message-content" v-html="msg.isUser ? escapeHtml(msg.text) : renderBotContent(msg.text)"></div>
        <div v-if="!msg.isUser && msg.ragTrace" class="message-meta">
          <details class="reasoning-details">
            <summary>{{ $t("chat.retrieval_process") }}</summary>
            <div class="reasoning-content">
              <RagTracePanel :trace="msg.ragTrace" :highlightedChunk="highlightedChunk" />
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
          :placeholder="$t('chat.placeholder')"
          rows="1"
          ref="textareaRef"
        ></textarea>
        <button v-if="isLoading" @click="stop" class="send-btn stop-btn" :title="$t('chat.stop')">
          <i class="fas fa-stop"></i>
        </button>
        <button v-else @click="handleSend" class="send-btn" :title="$t('chat.send')">
          <i class="fas fa-paper-plane"></i>
        </button>
      </div>
      <div class="footer-text">{{ $t("chat.footer_hint") }}</div>
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
const highlightedChunk = ref<number | null>(null)

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

function renderBotContent(text: string): string {
  const withCitations = text.replace(
    /\[(\d+)\]/g,
    '<span class="citation" data-index="$1" onclick="window.__citationClick && window.__citationClick($1)">[$1]</span>',
  )
  return parseMarkdown(withCitations)
}

function onCitationClick(index: number): void {
  highlightedChunk.value = index
  const details = document.querySelector(".reasoning-details")
  if (details && !details.open) {
    details.open = true
  }
  setTimeout(() => {
    const el = document.querySelector(`.trace-item[data-index="${index}"]`)
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" })
      el.classList.add("trace-item--highlighted")
      setTimeout(() => el.classList.remove("trace-item--highlighted"), 2000)
    }
  }, 100)
}

window.__citationClick = onCitationClick
</script>
