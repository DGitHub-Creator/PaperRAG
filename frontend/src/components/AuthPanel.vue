<template>
  <div class="auth-panel">
    <h2>{{ mode === 'login' ? '登录 PaperRAG' : '注册 PaperRAG' }}</h2>
    <p>登录后即可使用聊天和历史记录；管理员可管理文档知识库。</p>
    <div class="auth-form">
      <input v-model="form.username" type="text" placeholder="用户名" />
      <input v-model="form.password" type="password" placeholder="密码" />
      <select v-if="mode === 'register'" v-model="form.role">
        <option value="user">普通用户</option>
        <option value="admin">管理员</option>
      </select>
      <input v-if="mode === 'register' && form.role === 'admin'" v-model="form.admin_code" type="password" placeholder="管理员邀请码" />
      <button class="send-btn auth-submit" :disabled="loading" @click="submit">
        {{ loading ? '提交中...' : (mode === 'login' ? '登录' : '注册') }}
      </button>
      <button class="auth-switch" @click="$emit('switch', mode === 'login' ? 'register' : 'login')">
        {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue"

defineProps<{ mode: string }>()
const emit = defineEmits<{
  switch: [value: string]
  submit: [username: string, password: string, role: string, adminCode: string | null]
}>()
const form = reactive({ username: "", password: "", role: "user", admin_code: "" })
const loading = ref(false)

async function submit(): Promise<void> {
  if (!form.username.trim() || !form.password.trim()) { alert("用户名和密码不能为空"); return }
  loading.value = true
  try {
    emit("submit", form.username.trim(), form.password.trim(), form.role, form.admin_code || null)
    form.password = ""
    form.admin_code = ""
  } catch (e: unknown) { alert(e instanceof Error ? e.message : String(e)) }
  finally { loading.value = false }
}
</script>
