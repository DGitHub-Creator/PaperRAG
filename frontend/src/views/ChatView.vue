<template>
  <div class="chat-area">
    <header class="chat-header">
      <div class="header-info">
        <div class="status-dot" :class="isConnected ? 'on' : 'off'"></div>
        <span>{{ isConnected ? $t("chat.online") : $t("chat.offline") }}</span>
      </div>
      <div class="header-actions">
        <button class="icon-btn" :title="$t('nav.new_chat')" @click="newChat">
          <Icon name="plus" :size="15" />
        </button>
        <button class="icon-btn" :title="$t('nav.clear_chat')" @click="handleClear">
          <Icon name="trash" :size="15" />
        </button>
        <RouterLink class="icon-btn" :title="$t('history.title')" :to="{ name: 'history' }">
          <Icon name="clock" :size="15" />
        </RouterLink>
      </div>
    </header>

    <div ref="chatContainer" class="chat-container">
      <div v-if="!messages.length" class="welcome-screen">
        <div class="big-avatar">R</div>
        <h3>{{ $t("chat.welcome_title") }}</h3>
        <p>{{ $t("chat.welcome_desc") }}</p>
        <div class="welcome-suggestions">
          <button v-for="key in suggestions" :key="key" class="suggestion" @click="useSuggestion($t(key))">
            {{ $t(key) }}
          </button>
        </div>
      </div>

      <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.isUser ? 'user-message' : 'bot-message']">
        <div v-if="!msg.isUser && msg.isThinking && !msg.text" class="message-content thinking-content">
          <div class="thinking-header">
            <div class="thinking-dots"><span class="tdot"></span><span class="tdot"></span><span class="tdot"></span></div>
            <span class="thinking-text">{{ msg.ragSteps.length ? msg.ragSteps[msg.ragSteps.length - 1].label : $t('chat.thinking') }}</span>
          </div>
          <div v-if="msg.ragSteps.length" class="thinking-trace-lines">
            <div v-for="(step, sIdx) in msg.ragSteps" :key="sIdx" class="thinking-trace-line">
              <span class="thinking-trace-icon">{{ step.icon }}</span>
              <span class="thinking-trace-label">{{ step.label }}</span>
              <span v-if="step.detail" class="thinking-trace-detail">{{ step.detail }}</span>
            </div>
          </div>
        </div>
        <div v-else class="message-content" v-html="msg.isUser ? escapeHtml(msg.text) : parseMarkdown(msg.text)"></div>
        <CitationChips
          v-if="!msg.isUser && (msg.citations.length || msg.unsupported.length)"
          :citations="msg.citations"
          :unsupported="msg.unsupported"
        />
        <div v-if="!msg.isUser && msg.ragTrace" class="message-meta">
          <details class="reasoning-details">
            <summary>{{ $t("chat.retrieval_process") }}</summary>
            <div class="reasoning-content">
              <RagTracePanel :trace="msg.ragTrace" />
            </div>
          </details>
        </div>
      </div>
    </div>

    <div class="input-area-wrapper">
      <div class="input-area">
        <button class="attach-btn" :title="$t('chat.attach_hint')">
          <Icon name="paperclip" :size="16" />
        </button>
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
          <Icon name="stop" :size="15" />
        </button>
        <button v-else @click="handleSend" class="send-btn" :title="$t('chat.send')">
          <Icon name="send" :size="16" />
        </button>
      </div>
      <div class="footer-text">{{ $t("chat.footer_hint") }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue"
import RagTracePanel from "../components/RagTracePanel.vue"
import CitationChips from "../components/CitationChips.vue"
import Icon from "../components/Icon.vue"
import { useChat } from "../composables/useChat"
import { useWebSocket } from "../composables/useWebSocket"
import { escapeHtml, parseMarkdown } from "../utils/markdown"
import { confirmDialog } from "../utils/dialog"
import { t } from "../i18n"

const { messages, isLoading, revision, send, stop, newChat, clearChat } = useChat()
const { isConnected } = useWebSocket()

const userInput = ref("")
const isComposing = ref(false)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const chatContainer = ref<HTMLElement | null>(null)

const suggestions = ["chat.suggestion_1", "chat.suggestion_2", "chat.suggestion_3"]

// 状态层只递增 revision，"滚到底"这件事只有持有容器元素的组件说得清
let scrollFrame = 0
watch(revision, () => {
  if (scrollFrame) return
  scrollFrame = requestAnimationFrame(async () => {
    scrollFrame = 0
    await nextTick()
    const el = chatContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
})
onBeforeUnmount(() => {
  if (scrollFrame) cancelAnimationFrame(scrollFrame)
  scrollFrame = 0
})

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
  void send(text)
}

function useSuggestion(text: string): void {
  userInput.value = text
  handleSend()
}

function handleClear(): void {
  if (confirmDialog(t("nav.clear_confirm"))) clearChat()
}

function autoResize(e: Event): void {
  const ta = e.target as HTMLTextAreaElement
  ta.style.height = "auto"
  ta.style.height = ta.scrollHeight + "px"
}
</script>
