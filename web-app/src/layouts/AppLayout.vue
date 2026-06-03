<script setup lang="ts">
import AppSidebar from '../components/AppSidebar.vue'
import AppTopbar from '../components/AppTopbar.vue'
</script>

<template>
  <div class="app-layout">
    <AppSidebar />
    <div class="app-main">
      <AppTopbar />
      <div class="app-content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: grid;
  grid-template-columns: auto 1fr;
  height: 100vh;
  overflow: hidden;
}

.app-main {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  min-width: 0;
}

.app-content {
  flex: 1;
  overflow-y: auto;
  padding: 28px;
  background: var(--bg);
}

.app-content::-webkit-scrollbar {
  width: 6px;
}

.app-content::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--muted) 30%, transparent);
  border-radius: 3px;
}
</style>
