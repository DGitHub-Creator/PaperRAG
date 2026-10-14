<template>
  <div class="toast-host">
    <TransitionGroup name="toast">
      <div v-for="item in toasts" :key="item.id" :class="['toast', `toast-${item.tone}`]" role="status">
        <Icon :name="iconOf(item.tone)" :size="15" />
        <span class="toast-text">{{ item.message }}</span>
        <button class="toast-close" :title="$t('common.dismiss')" @click="dismiss(item.id)">
          <Icon name="x" :size="13" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import Icon from "./Icon.vue"
import { useToast } from "../composables/useToast"
import type { ToastTone } from "../composables/useToast"

// 提示的唯一渲染点（挂在 App.vue 根部，登录页也能看到提示）
const { toasts, dismiss } = useToast()

const ICONS: Record<ToastTone, string> = { info: "info", ok: "check", error: "alert" }

function iconOf(tone: ToastTone): string {
  return ICONS[tone]
}
</script>

<style scoped>
.toast-host {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  gap: 9px;
  max-width: min(380px, calc(100vw - 36px));
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 11px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-left: 3px solid var(--info);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-color);
  pointer-events: auto;
}

.toast :deep(.rp-icon) { margin-top: 2px; color: var(--info); }
.toast-ok { border-left-color: var(--ok); }
.toast-ok :deep(.rp-icon) { color: var(--ok); }
.toast-error { border-left-color: var(--danger); }
.toast-error :deep(.rp-icon) { color: var(--danger); }

.toast-text { flex: 1; overflow-wrap: anywhere; }

.toast-close {
  flex: 0 0 auto;
  padding: 2px;
  border: none;
  background: transparent;
  color: var(--text-faint);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: var(--transition);
}
.toast-close:hover { background: var(--bg-hover); color: var(--text-color); }

.toast-enter-active, .toast-leave-active { transition: opacity .18s ease, transform .18s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(8px); }
</style>
