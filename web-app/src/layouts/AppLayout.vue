<script setup lang="ts">
import { ref } from 'vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppTopbar from '../components/AppTopbar.vue'

const navigationOpen = ref(false)
</script>

<template>
  <div class="app-layout">
    <AppSidebar :mobile-open="navigationOpen" @close="navigationOpen = false" />
    <button
      v-if="navigationOpen"
      class="navigation-backdrop"
      type="button"
      aria-label="关闭导航"
      @click="navigationOpen = false"
    ></button>
    <div class="app-main">
      <AppTopbar @toggle-navigation="navigationOpen = !navigationOpen" />
      <div class="app-content">
        <router-view v-slot="{ Component, route }">
          <transition name="page" mode="out-in">
            <component :is="Component" :key="route.fullPath" />
          </transition>
        </router-view>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: grid;
  grid-template-columns: auto 1fr;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
}

.app-main {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  overflow: hidden;
  min-width: 0;
}

.app-content {
  flex: 1;
  overflow-y: auto;
  padding: 26px clamp(18px, 2.2vw, 34px) 38px;
  background: var(--bg);
  scroll-behavior: smooth;
}

.app-content::-webkit-scrollbar {
  width: 6px;
}

.app-content::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--muted) 30%, transparent);
  border-radius: 3px;
}

.navigation-backdrop { display: none; }
.page-enter-active,
.page-leave-active { transition: opacity .18s ease, transform .18s ease; }
.page-enter-from { opacity: 0; transform: translateY(7px); }
.page-leave-to { opacity: 0; transform: translateY(-3px); }

@media (max-width: 900px) {
  .app-layout { grid-template-columns: 1fr; }
  .app-content { padding: 18px 14px 30px; }
  .navigation-backdrop { display: block; position: fixed; inset: 0; z-index: 25; border: 0; background: rgba(15, 23, 42, .42); backdrop-filter: blur(2px); }
}

@media (prefers-reduced-motion: reduce) {
  .page-enter-active,
  .page-leave-active { transition: none; }
}
</style>
