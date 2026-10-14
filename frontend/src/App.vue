<template>
  <RouterView />
  <ToastHost />
  <ConfirmHost />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from "vue"
import { useRouter } from "vue-router"
import ToastHost from "./components/ToastHost.vue"
import ConfirmHost from "./components/ConfirmHost.vue"
import { useAuth } from "./composables/useAuth"
import { useAppSession } from "./composables/useAppSession"
import { usePreferences } from "./composables/usePreferences"
import { onAppEvent } from "./api/events"

// 根组件只做两件事：全局登录态生命周期（启动探测 / 401 广播）与提示/确认框的唯一挂载点。
const router = useRouter()
const { token, fetchMe } = useAuth()
const { signOut, onSignedIn } = useAppSession()
const { load: loadPreferences } = usePreferences()

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
    .then(async () => {
      onSignedIn(token.value)
      // 主题存在账号上，刷新页面也要先取回来再渲染，否则会先闪一下浅色
      await loadPreferences().catch(() => undefined)
    })
    .catch(backToLogin)
})

onUnmounted(() => {
  if (offUnauthorized) offUnauthorized()
  offUnauthorized = null
})
</script>
