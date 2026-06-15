<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo-icon">🐱</div>
      <h2>喵喵助手</h2>
    </div>
    <nav class="sidebar-nav">
      <button @click="$emit('newChat')" :class="['nav-btn', { active: activeNav === 'newChat' }]">
        <i class="fas fa-plus"></i> 新建会话
      </button>
      <button v-if="isAuthenticated" @click="$emit('showHistory')" :class="['nav-btn', { active: activeNav === 'history' }]">
        <i class="fas fa-history"></i> 历史记录
      </button>
      <button v-if="isAdmin" @click="$emit('showSettings')" :class="['nav-btn', { active: activeNav === 'settings' }]">
        <i class="fas fa-cog"></i> 设置
      </button>
    </nav>
    <div class="sidebar-footer">
      <button v-if="isAuthenticated" @click="$emit('clearChat')" class="danger-btn">
        <i class="fas fa-trash-alt"></i> 清空当前对话
      </button>
      <div v-if="isAuthenticated" class="user-badge">
        <span>{{ username }}</span>
        <small>{{ role }}</small>
      </div>
      <button v-if="isAuthenticated" @click="$emit('logout')" class="danger-btn logout-btn">
        <i class="fas fa-right-from-bracket"></i> 退出登录
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
