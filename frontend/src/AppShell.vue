<template>
  <div class="app-shell">
    <AppRail @logout="handleLogout" />
    <div class="workspace">
      <TopBar />
      <main class="page">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router"
import AppRail from "./components/AppRail.vue"
import TopBar from "./components/TopBar.vue"
import { useAppSession } from "./composables/useAppSession"

const router = useRouter()
const { signOut } = useAppSession()

// 手动退出后必须显式回登录页：路由守卫只在"下一次导航"时判定 token，不会因 token 变化自动触发
function handleLogout(): void {
  signOut()
  void router.replace({ name: "login" })
}
</script>
