<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { navigationItemForRoute } from '../config/navigation'
import AppSidebar from '../components/AppSidebar.vue'
import AppTopbar from '../components/AppTopbar.vue'
import AssistantPet from '../components/AssistantPet.vue'
import { useStudyActivity } from '../composables/useStudyActivity'

useStudyActivity()

const navigationOpen = ref(false)
const route = useRoute()
const page = computed(() => navigationItemForRoute(String(route.name ?? '')))
watch(navigationOpen, async (open, previous) => {
  if (!open && previous) { await nextTick(); document.querySelector<HTMLElement>('.mobile-menu-button')?.focus() }
})
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
    <div class="app-main" :inert="navigationOpen">
      <AppTopbar @toggle-navigation="navigationOpen = !navigationOpen"><template #assistant><AssistantPet v-show="!navigationOpen" /></template></AppTopbar>
      <div class="app-content" :class="{'dashboard-content':route.name === 'admin'}">
        <header v-if="page?.roles.includes('admin') && route.name !== 'admin'" class="admin-page-heading"><span>LEARNING OS · 管理后台</span><h1>{{ page.label }}</h1><p>{{ page.description }}</p></header>
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
.dashboard-content{padding-top:16px}
.admin-page-heading { margin-bottom:22px; }
.admin-page-heading span { color:var(--accent); font-size:11px; letter-spacing:.08em; }
.admin-page-heading h1 { margin:8px 0; color:var(--text); font-size:28px; }
.admin-page-heading p { margin:0; color:var(--muted); line-height:1.7; }
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
