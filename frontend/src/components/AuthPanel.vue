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
      <button class="auth-switch" @click="$emit('switch', mode === 'login' ? 'register' : 'login')">
        {{ mode === 'login' ? $t('auth.switch_to_register') : $t('auth.switch_to_login') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue"
import { t } from "../i18n"

defineProps<{ mode: string }>()
const emit = defineEmits<{
  switch: [value: string]
  submit: [username: string, password: string, role: string, adminCode: string | null]
}>()
const form = reactive({ username: "", password: "", role: "user", admin_code: "" })
const loading = ref(false)

async function submit(): Promise<void> {
  if (!form.username.trim() || !form.password.trim()) { alert(t("auth.username_required")); return }
  loading.value = true
  try {
    emit("submit", form.username.trim(), form.password.trim(), form.role, form.admin_code || null)
    form.password = ""
    form.admin_code = ""
  } catch (e: unknown) { alert(e instanceof Error ? e.message : String(e)) }
  finally { loading.value = false }
}
</script>
