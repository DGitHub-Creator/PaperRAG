<template>
  <div class="auth-panel">
    <h2>{{ mode === 'login' ? $t('auth.login_title') : $t('auth.register_title') }}</h2>
    <p>{{ mode === 'login' ? $t('auth.login_tip') : $t('auth.register_tip') }}</p>
    <div class="auth-form">
      <input v-model="form.username" type="text" :placeholder="$t('auth.username')" />
      <input v-model="form.password" type="password" :placeholder="$t('auth.password')" />
      <select v-if="mode === 'register'" v-model="form.role">
        <option value="user">{{ $t('auth.role_user') }}</option>
        <option value="admin">{{ $t('auth.role_admin') }}</option>
      </select>
      <input v-if="mode === 'register' && form.role === 'admin'" v-model="form.admin_code" type="password" :placeholder="$t('auth.admin_code')" />
      <button class="send-btn auth-submit" :disabled="loading" @click="submit">
        {{ loading ? $t('auth.submitting') : (mode === 'login' ? $t('auth.login_btn') : $t('auth.register_btn')) }}
      </button>
      <button class="auth-switch" @click="mode = mode === 'login' ? 'register' : 'login'">
        {{ mode === 'login' ? $t('auth.switch_to_register') : $t('auth.switch_to_login') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue"
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
