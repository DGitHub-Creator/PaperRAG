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
import type { NavGroup } from "../composables/useNav"
import { useAuth } from "../composables/useAuth"

defineEmits<{ logout: [] }>()

const { username, role, isAdmin } = useAuth()

// 设置页只对管理员出现（As-Is：文档管理是 admin 功能，见 docs/rules/14-feature-modules.md M1）
const groups = computed<NavGroup[]>(() =>
  NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => item.key !== "settings" || isAdmin.value),
  })).filter((group) => group.items.length > 0),
)

const initial = computed(() => (username.value.slice(0, 1) || "?").toUpperCase())
</script>
