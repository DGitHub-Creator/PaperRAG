<template>
  <div class="app-wrapper">
    <Sidebar />
    <main class="chat-area">
      <ChatView />
    </main>
  </div>
</template>

<script setup>
import Sidebar from "./components/Sidebar.vue";
import ChatView from "./components/ChatView.vue";
</script>
