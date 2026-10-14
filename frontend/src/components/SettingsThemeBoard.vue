<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>{{ $t("settings.appearance_title") }}</h3>
        <div class="sub">{{ $t("settings.appearance_desc") }}</div>
      </div>
      <Icon name="eye" :size="16" />
    </div>
    <div class="card-body">
      <div class="theme-picker">
        <button
          v-for="opt in THEME_OPTIONS"
          :key="opt.value"
          type="button"
          :class="['theme-option', { active: draft.theme === opt.value }]"
          :disabled="isSaving"
          @click="choose(opt.value)"
        >
          <Icon :name="opt.icon" :size="16" />
          <span class="theme-name">{{ $t(opt.labelKey) }}</span>
          <span class="theme-hint">{{ $t(opt.hintKey) }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// 外观·主题板块：即时生效，没有「保存」按钮。
// `system` 取值由 utils/theme.ts 用 matchMedia 解析**一次**——不监听系统偏好变化，
// 理由是"用户手动选的这一次"和"操作系统后来变了"该给出不同结果（后者不该悄悄改掉前者的选择）。
import Icon from "./Icon.vue"
import { usePreferences } from "../composables/usePreferences"
import { alertDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"
import { t } from "../i18n"
import type { Theme } from "../api/types"

const { draft, isSaving, pickTheme } = usePreferences()

// value 必须与迁移 CHECK / Go 常量 / 契约 enum 三处同值（见 utils/theme.ts 顶部）
const THEME_OPTIONS: { value: Theme; icon: string; labelKey: string; hintKey: string }[] = [
  { value: "light", icon: "sun", labelKey: "settings.theme_light", hintKey: "settings.theme_light_hint" },
  { value: "dark", icon: "moon", labelKey: "settings.theme_dark", hintKey: "settings.theme_dark_hint" },
  { value: "system", icon: "monitor", labelKey: "settings.theme_system", hintKey: "settings.theme_system_hint" },
]

async function choose(theme: Theme): Promise<void> {
  try {
    await pickTheme(theme)
  } catch (err: unknown) {
    alertDialog(`${t("settings.save_failed")}${describeError(err)}`)
  }
}
</script>

<style scoped>
.theme-picker { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
@media (max-width: 560px) { .theme-picker { grid-template-columns: minmax(0, 1fr); } }
.theme-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  font-family: inherit;
  text-align: center;
  color: var(--text-muted);
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  cursor: pointer;
  transition: var(--transition);
}
.theme-option:hover:not(:disabled) { background: var(--bg-hover); }
.theme-option:disabled { opacity: .6; cursor: not-allowed; }
.theme-option.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
.theme-name { font-size: 13px; font-weight: 600; color: var(--text-strong); }
.theme-option.active .theme-name { color: var(--accent); }
.theme-hint { font-size: 11px; color: var(--text-faint); line-height: 1.4; }
.theme-option.active .theme-hint { color: var(--text-muted); }
</style>
