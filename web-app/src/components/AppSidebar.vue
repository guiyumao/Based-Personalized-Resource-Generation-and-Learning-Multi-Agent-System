<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeftBold, ArrowRightBold, Close } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { navigationForRole } from '../config/navigation'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{ mobileOpen?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isCollapsed = ref(localStorage.getItem('sidebar-collapsed') === '1')

const visibleItems = computed(() => navigationForRole(authStore.user?.role))
const groupedItems = computed(() => {
  const groups = new Map<string, typeof visibleItems.value>()
  visibleItems.value.forEach((item) => {
    const current = groups.get(item.group) ?? []
    current.push(item)
    groups.set(item.group, current)
  })
  return Array.from(groups.entries())
})

function isActive(path: string) {
  return route.path === path || (path === '/student/dashboard' && route.path === '/student')
}

async function navigate(path: string) {
  await router.push(path)
  emit('close')
}

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  localStorage.setItem('sidebar-collapsed', isCollapsed.value ? '1' : '0')
}

watch(() => route.fullPath, () => emit('close'))
</script>

<template>
  <aside class="app-sidebar" :class="{ collapsed: isCollapsed, 'mobile-open': props.mobileOpen }">
    <div class="sidebar-brand">
      <div class="brand-icon" aria-hidden="true"><span></span><span></span><span></span></div>
      <div class="brand-copy"><strong>智学平台</strong><small>Learning OS</small></div>
      <button class="mobile-close" type="button" aria-label="关闭导航" @click="emit('close')">
        <el-icon><Close /></el-icon>
      </button>
    </div>

    <nav class="sidebar-nav" aria-label="主导航">
      <section v-for="([group, items]) in groupedItems" :key="group" class="nav-group">
        <div class="nav-group-title">{{ group }}</div>
        <button
          v-for="item in items"
          :key="item.key"
          class="nav-item"
          :class="{ active: isActive(item.route) }"
          :title="isCollapsed ? `${item.label} - ${item.description}` : item.description"
          type="button"
          @click="navigate(item.route)"
        >
          <span class="nav-icon"><component :is="item.icon" /></span>
          <span class="nav-label">{{ item.label }}</span>
        </button>
      </section>
    </nav>

    <div class="sidebar-footer">
      <button class="collapse-btn" type="button" @click="toggleCollapse">
        <el-icon><ArrowRightBold v-if="isCollapsed" /><ArrowLeftBold v-else /></el-icon>
        <span class="nav-label">收起导航</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar { width:256px; min-width:256px; height:100dvh; border-right:1px solid var(--line); background:color-mix(in srgb,var(--panel-strong) 96%,transparent); display:flex; flex-direction:column; position:relative; z-index:30; overflow:hidden; box-shadow:14px 0 36px color-mix(in srgb,var(--text) 5%,transparent); transition:width .24s ease,min-width .24s ease,transform .24s ease; }
.app-sidebar.collapsed { width:80px; min-width:80px; }
.sidebar-brand { min-height:76px; display:flex; align-items:center; gap:12px; padding:16px 18px; border-bottom:1px solid var(--line); }
.brand-icon { width:40px; height:40px; min-width:40px; border-radius:13px; display:grid; place-content:center; gap:3px; background:linear-gradient(145deg,var(--accent),var(--accent-deep)); box-shadow:0 10px 24px color-mix(in srgb,var(--accent) 24%,transparent); }
.brand-icon span { display:block; width:18px; height:3px; border-radius:3px; background:rgba(255,255,255,.94); transform:skewY(-16deg); }
.brand-copy { min-width:0; display:grid; gap:2px; white-space:nowrap; }
.brand-copy strong { color:var(--text); font-size:17px; letter-spacing:.02em; }
.brand-copy small { color:var(--muted); font-size:10px; letter-spacing:.14em; text-transform:uppercase; }
.collapsed .brand-copy { opacity:0; pointer-events:none; }
.sidebar-nav { flex:1; overflow-y:auto; padding:14px 12px; scrollbar-width:thin; scrollbar-color:color-mix(in srgb,var(--muted) 20%,transparent) transparent; }
.nav-group + .nav-group { margin-top:16px; }
.nav-group-title { padding:0 12px 7px; color:var(--muted); font-size:11px; font-weight:700; letter-spacing:.08em; white-space:nowrap; }
.collapsed .nav-group-title { height:1px; padding:0; margin:7px 14px; background:var(--line); color:transparent; }
.nav-item,.collapse-btn { width:100%; border:0; background:transparent; color:var(--muted); font-family:inherit; cursor:pointer; }
.nav-item { min-height:44px; display:flex; align-items:center; gap:12px; padding:9px 12px; border-radius:11px; position:relative; text-align:left; font-size:14px; font-weight:560; transition:background .18s ease,color .18s ease,transform .18s ease; }
.nav-item + .nav-item { margin-top:3px; }
.nav-item:hover { color:var(--text); background:var(--surface-soft); transform:translateX(2px); }
.nav-item.active { color:var(--accent); background:var(--accent-soft); font-weight:700; }
.nav-item.active::after { content:''; width:3px; height:22px; border-radius:3px; background:var(--accent); position:absolute; left:0; top:50%; transform:translateY(-50%); }
.nav-icon { width:20px; height:20px; min-width:20px; display:grid; place-items:center; }
.nav-icon :deep(svg) { width:19px; height:19px; }
.nav-label { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; transition:opacity .18s ease; }
.collapsed .nav-label { opacity:0; pointer-events:none; }
.collapsed .nav-item { justify-content:center; padding-inline:0; }
.sidebar-footer { padding:12px; border-top:1px solid var(--line); }
.collapse-btn { min-height:40px; display:flex; align-items:center; justify-content:center; gap:10px; border-radius:10px; }
.collapse-btn:hover { color:var(--text); background:var(--surface-soft); }
.mobile-close { display:none; }

@media (max-width:900px) {
  .app-sidebar,.app-sidebar.collapsed { width:min(84vw,292px); min-width:min(84vw,292px); position:fixed; inset:0 auto 0 0; transform:translateX(-104%); box-shadow:24px 0 60px rgba(15,23,42,.2); }
  .app-sidebar.mobile-open { transform:translateX(0); }
  .collapsed .brand-copy,.collapsed .nav-label { opacity:1; pointer-events:auto; }
  .collapsed .nav-group-title { height:auto; padding:0 12px 7px; margin:0; background:none; color:var(--muted); }
  .collapsed .nav-item { justify-content:flex-start; padding-inline:12px; }
  .sidebar-footer { display:none; }
  .mobile-close { width:36px; height:36px; margin-left:auto; display:grid; place-items:center; border:0; border-radius:10px; color:var(--muted); background:var(--surface-soft); cursor:pointer; }
}

@media (prefers-reduced-motion:reduce) { .app-sidebar,.nav-item,.nav-label { transition:none; } }
</style>
