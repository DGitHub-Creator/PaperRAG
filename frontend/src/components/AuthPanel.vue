<template>
  <div class="auth-panel">
    <div class="auth-head">
      <h2>{{ mode === "login" ? $t("auth.login_title") : $t("auth.register_title") }}</h2>
      <p>{{ mode === "login" ? $t("auth.login_tip") : $t("auth.register_tip") }}</p>
    </div>

    <div class="auth-tabs">
      <button :class="['auth-tab', { active: mode === 'login' }]" @click="mode = 'login'">
        {{ $t("auth.tab_login") }}
      </button>
      <button :class="['auth-tab', { active: mode === 'register' }]" @click="mode = 'register'">
        {{ $t("auth.tab_register") }}
      </button>
    </div>

    <form class="auth-form" @submit.prevent="submit">
      <label class="field">
        <span class="field-label">{{ $t("auth.username") }}</span>
        <span class="field-input">
          <Icon name="users" :size="15" />
          <input v-model="form.username" type="text" autocomplete="username" :placeholder="$t('auth.username_placeholder')" />
        </span>
      </label>

      <label class="field">
        <span class="field-label">{{ $t("auth.password") }}</span>
        <span class="field-input">
          <Icon name="shield" :size="15" />
          <input v-model="form.password" type="password" autocomplete="current-password" :placeholder="$t('auth.password_placeholder')" />
        </span>
      </label>

      <template v-if="mode === 'register'">
        <label class="field">
          <span class="field-label">{{ $t("auth.role") }}</span>
          <span class="field-input">
            <Icon name="tag" :size="15" />
            <select v-model="form.role">
              <option value="user">{{ $t("auth.role_user") }}</option>
              <option value="admin">{{ $t("auth.role_admin") }}</option>
            </select>
          </span>
        </label>
        <label v-if="form.role === 'admin'" class="field">
          <span class="field-label">{{ $t("auth.admin_code") }}</span>
          <span class="field-input">
            <Icon name="shield" :size="15" />
            <input v-model="form.admin_code" type="password" :placeholder="$t('auth.admin_code_placeholder')" />
          </span>
        </label>
      </template>

      <button type="submit" class="btn-primary auth-submit" :disabled="loading">
        <span v-if="loading" class="spinner"></span>
        <Icon v-else name="logout" :size="15" />
        {{ loading ? $t("auth.submitting") : mode === "login" ? $t("auth.login_btn") : $t("auth.register_btn") }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue"
import Icon from "./Icon.vue"
import { useAuth } from "../composables/useAuth"
import type { AuthMode } from "../composables/useAuth"
import type { Role } from "../api/types"
import { t } from "../i18n"
import { alertDialog } from "../utils/dialog"
import { describeError } from "../utils/errors"

/** 登录/注册成功后通知外壳：会话初始化与 WS 接线是外壳的事，本组件不知道也不需要知道 */
const emit = defineEmits<{ authenticated: [] }>()

const { submit: submitAuth } = useAuth()
const mode = ref<AuthMode>("login")
const form = reactive({ username: "", password: "", role: "user" as Role, admin_code: "" })
const loading = ref(false)

async function submit(): Promise<void> {
  if (!form.username.trim() || !form.password.trim()) {
    alertDialog(t("auth.username_required"))
    return
  }
  loading.value = true
  try {
    await submitAuth({
      mode: mode.value,
      username: form.username.trim(),
      password: form.password.trim(),
      role: form.role,
      admin_code: form.admin_code || null,
    })
    form.password = ""
    form.admin_code = ""
    emit("authenticated")
  } catch (err: unknown) {
    alertDialog(describeError(err))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-head h2 { font-size: 18px; color: var(--text-strong); }
.auth-head p { margin-top: 6px; font-size: 12.5px; color: var(--text-muted); line-height: 1.55; }

.auth-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  margin: 18px 0 16px;
  padding: 3px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}
.auth-tab {
  padding: 7px 10px;
  font-size: 13px;
  font-family: inherit;
  font-weight: 550;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-radius: 7px;
  cursor: pointer;
  transition: var(--transition);
}
.auth-tab:hover { color: var(--text-color); }
.auth-tab.active { background: var(--bg-surface); color: var(--accent); box-shadow: var(--shadow-sm); }

.auth-form { display: flex; flex-direction: column; gap: 13px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; font-weight: 550; color: var(--text-muted); }
.field-input {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 11px;
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: var(--text-faint);
  transition: var(--transition);
}
.field-input:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); color: var(--accent); }
.field-input input,
.field-input select {
  flex: 1;
  min-width: 0;
  padding: 9px 0;
  font-size: 13px;
  font-family: inherit;
  color: var(--text-color);
  background: transparent;
  border: none;
  outline: none;
}
.field-input select { cursor: pointer; }
.field-input input::placeholder { color: var(--text-faint); }

.auth-submit {
  justify-content: center;
  width: 100%;
  margin-top: 4px;
  padding: 10px 14px;
  font-size: 13.5px;
}
</style>
