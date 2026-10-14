<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h3>{{ $t("settings.account_title") }}</h3>
        <div class="sub">{{ $t("settings.account_desc") }}</div>
      </div>
      <Icon name="users" :size="16" />
    </div>
    <div class="card-body">
      <div class="account-row">
        <div class="account-avatar">{{ initial }}</div>
        <div class="account-id">
          <div class="account-name">{{ username }}</div>
          <span class="badge" :class="{ 'badge-accent': isAdmin }">{{ $t(`nav.roles.${role}`) }}</span>
        </div>
      </div>
      <p class="sb-hint">{{ isAdmin ? $t("settings.account_admin_hint") : $t("settings.account_user_hint") }}</p>
      <div class="sb-actions">
        <button class="btn-secondary" @click="logout">
          <Icon name="logout" :size="14" />{{ $t("settings.account_logout") }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// 账号板块：只读自己的身份 + 退出登录。用户名与角色一律回库取（见 useAuth 的说明），本组件不缓存。
import { computed } from "vue"
import { useRouter } from "vue-router"
import Icon from "./Icon.vue"
import { useAuth } from "../composables/useAuth"
import { useAppSession } from "../composables/useAppSession"

const router = useRouter()
const { username, role, isAdmin } = useAuth()
const { signOut } = useAppSession()

const initial = computed(() => (username.value.slice(0, 1) || "?").toUpperCase())

function logout(): void {
  signOut()
  void router.replace({ name: "login" })
}
</script>

<style scoped>
.account-row { display: flex; align-items: center; gap: 12px; }
.account-avatar {
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 17px;
  font-weight: 650;
  text-transform: uppercase;
}
.account-id { display: flex; flex-direction: column; gap: 5px; align-items: flex-start; min-width: 0; }
.account-name { font-size: 15px; font-weight: 600; color: var(--text-strong); overflow-wrap: anywhere; }
</style>
