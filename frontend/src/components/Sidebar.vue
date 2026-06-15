<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo-icon">PaperRAG</div>
      <h2>学术知识库</h2>
    </div>
    <nav class="sidebar-nav">
      <button class="nav-btn" @click="$emit('newChat')">
        <i class="fas fa-plus"></i> 新建会话
      </button>
      <button class="nav-btn" @click="$emit('showHistory')">
        <i class="fas fa-history"></i> 历史记录
      </button>
      <button v-if="isAdmin" class="nav-btn" @click="$emit('showSettings')">
        <i class="fas fa-cog"></i> 设置
      </button>
    </nav>
    <div class="sidebar-footer">
      <button class="danger-btn" @click="$emit('clearChat')">
        <i class="fas fa-trash-alt"></i> 清空当前对话
      </button>
      <div v-if="isAuthenticated" class="user-badge">
        <span>{{ username }}</span>
        <small>{{ role }}</small>
      </div>
    </div>
  </aside>
</template>

<script setup>
defineProps({ isAdmin: Boolean, isAuthenticated: Boolean, username: String, role: String });
defineEmits(["newChat", "showHistory", "showSettings", "clearChat"]);
</script>
