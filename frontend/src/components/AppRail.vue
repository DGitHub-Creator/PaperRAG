<template>
  <aside class="rail">
    <div class="rail-brand">
      <div class="mark">R</div>
      <div class="brand-text">
        <div class="name">{{ $t("app.short_title") }}</div>
        <div class="tagline">{{ $t("app.tagline") }}</div>
      </div>
    </div>

    <nav class="rail-nav">
      <div v-for="group in groups" :key="group.labelKey" class="rail-group">
        <div class="rail-group-label">{{ $t(group.labelKey) }}</div>
        <RouterLink v-for="item in group.items" :key="item.key" class="rail-link" :to="{ name: item.key }">
          <Icon :name="item.icon" :size="15" />
          <span class="label">{{ $t(`nav.items.${item.key}`) }}</span>
          <span v-if="item.badgeKey" class="rail-badge">{{ $t(item.badgeKey) }}</span>
        </RouterLink>
      </div>
    </nav>

    <div class="rail-footer">
      <div class="rail-user">
        <div class="avatar">{{ initial }}</div>
        <div class="who">
          <div class="u">{{ username }}</div>
          <div class="r">{{ $t(`nav.roles.${role}`) }}</div>
        </div>
        <button class="rail-icon-btn" :title="$t('auth.logout')" @click="$emit('logout')">
          <Icon name="logout" :size="15" />
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue"
import Icon from "./Icon.vue"
import { NAV_GROUPS } from "../composables/useNav"
import { useAuth } from "../composables/useAuth"

defineEmits<{ logout: [] }>()

const { username, role } = useAuth()

// 设置页对所有人可见（2026-10-14）：它已从"管理员专用的文档管理"变成账号/偏好/外观/安全，
// 管理员额外多看一块「知识库管理」（见 views/SettingsView.vue）。
const groups = NAV_GROUPS

const initial = computed(() => (username.value.slice(0, 1) || "?").toUpperCase())
</script>
