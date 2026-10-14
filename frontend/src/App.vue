<template>
  <RouterView />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from "vue"
import { useRouter } from "vue-router"
import { useAuth } from "./composables/useAuth"
import { useAppSession } from "./composables/useAppSession"
import { onAppEvent } from "./api/events"

// 根组件只做一件事：全局登录态生命周期（启动探测 / 401 广播），页面本身由路由承载。
const router = useRouter()
const { token, fetchMe } = useAuth()
const { signOut, onSignedIn } = useAppSession()

// 401 由 api 层广播，这里订阅一次并在卸载时退订（此前是无名函数常驻 window，重挂载就重复注册）
let offUnauthorized: (() => void) | null = null

function backToLogin(): void {
  signOut()
  void router.replace({ name: "login" })
}

onMounted(() => {
  offUnauthorized = onAppEvent("auth-expired", backToLogin)
  if (!token.value) return
  // token 失效是启动期的常态：清干净回到登录页即可，不额外弹窗
  fetchMe()
    .then(() => onSignedIn(token.value))
    .catch(backToLogin)
})

onUnmounted(() => {
  if (offUnauthorized) offUnauthorized()
  offUnauthorized = null
})
</script>
