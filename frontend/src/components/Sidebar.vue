<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo-icon">🐱</div>
      <h2>{{ $t("app.subtitle") }}</h2>
    </div>
    <nav class="sidebar-nav">
      <button @click="$emit('newChat')" :class="['nav-btn', { active: activeNav === 'newChat' }]">
        <i class="fas fa-plus"></i> {{ $t("nav.new_chat") }}
      </button>
      <button v-if="isAuthenticated" @click="$emit('showHistory')" :class="['nav-btn', { active: activeNav === 'history' }]">
        <i class="fas fa-history"></i> {{ $t("nav.history") }}
      </button>
      <button v-if="isAdmin" @click="$emit('showSettings')" :class="['nav-btn', { active: activeNav === 'settings' }]">
        <i class="fas fa-cog"></i> {{ $t("nav.settings") }}
      </button>
    </nav>
    <div class="sidebar-footer">
      <button v-if="isAuthenticated" @click="$emit('clearChat')" class="danger-btn">
        <i class="fas fa-trash-alt"></i> {{ $t("nav.clear_chat") }}
      </button>
      <div v-if="isAuthenticated" class="user-badge">
        <span>{{ username }}</span>
        <small>{{ role }}</small>
      </div>
      <button v-if="isAuthenticated" @click="$emit('logout')" class="danger-btn logout-btn">
        <i class="fas fa-right-from-bracket"></i> {{ $t("auth.logout") }}
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{
  isAdmin: boolean
  isAuthenticated: boolean
  username: string
  role: string
  activeNav: string
}>()
defineEmits<{
  newChat: []
  showHistory: []
  showSettings: []
  clearChat: []
  logout: []
}>()
</script>
