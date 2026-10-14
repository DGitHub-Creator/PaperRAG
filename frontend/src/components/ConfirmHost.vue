<template>
  <div v-if="pending" class="confirm-mask" @click.self="settle(false)">
    <div class="confirm-box" role="dialog" aria-modal="true">
      <h3>{{ $t(pending.titleKey || "common.confirm_title") }}</h3>
      <p>{{ pending.message }}</p>
      <div class="confirm-actions">
        <button class="btn-secondary" @click="settle(false)">{{ $t(pending.cancelKey || "common.cancel") }}</button>
        <button :class="pending.danger === false ? 'btn-primary' : 'btn-primary danger'" @click="settle(true)">
          {{ $t(pending.confirmKey || "common.confirm_ok") }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useConfirm } from "../composables/useConfirm"

// 确认框的唯一渲染点：对话框文案由调用方以 i18n 键传入，组件只负责问。
const { pending, settle } = useConfirm()
</script>

<style scoped>
.confirm-mask {
  position: fixed;
  inset: 0;
  z-index: 2100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 34, .42);
}

.confirm-box {
  width: 100%;
  max-width: 400px;
  padding: 20px 22px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

.confirm-box h3 { font-size: 15px; }
.confirm-box p { margin-top: 9px; font-size: 13px; line-height: 1.6; color: var(--text-muted); overflow-wrap: anywhere; }
.confirm-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
.confirm-actions .danger { background: var(--danger); border-color: var(--danger); }
.confirm-actions .danger:hover:not(:disabled) { background: #c13232; border-color: #c13232; }
</style>
