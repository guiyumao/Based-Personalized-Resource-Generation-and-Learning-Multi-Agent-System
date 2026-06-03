<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isCollapsed = ref(localStorage.getItem('sidebar-collapsed') === '1')

interface MenuItem {
  key: string
  label: string
  icon: string
  route: string
  roles: string[]
}

const menuItems: MenuItem[] = [
  { key: 'dashboard',      label: '学习概览',   icon: '📊', route: '/student/dashboard',      roles: ['student', 'teacher', 'admin'] },
  { key: 'learning-path',  label: '学习路径',   icon: '🗺️', route: '/student/learning-path',  roles: ['student', 'teacher', 'admin'] },
  { key: 'courseware',     label: '课件中心',   icon: '📚', route: '/student/courseware',     roles: ['student', 'teacher', 'admin'] },
  { key: 'exercise',       label: '练习测评',   icon: '✏️', route: '/student/exercise',       roles: ['student', 'teacher', 'admin'] },
  { key: 'mistakes',       label: '错题本',     icon: '📝', route: '/student/mistakes',       roles: ['student', 'teacher', 'admin'] },
  { key: 'knowledge-graph',label: '知识图谱',   icon: '🔗', route: '/student/knowledge-graph',roles: ['student', 'teacher', 'admin'] },
  { key: 'report',         label: '学习报告',   icon: '📈', route: '/student/report',         roles: ['student', 'teacher', 'admin'] },
  { key: 'qa',             label: '智能问答',   icon: '💬', route: '/student/qa',             roles: ['student', 'teacher', 'admin'] },
]

const visibleItems = computed(() =>
  menuItems.filter(m => m.roles.includes(authStore.user?.role ?? 'student'))
)

function isActive(item: MenuItem) {
  if (item.key === 'dashboard') {
    return route.path === '/student/dashboard' || route.path === '/student'
  }
  return route.path.startsWith(item.route)
}

function navigate(item: MenuItem) {
  router.push(item.route)
}

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  localStorage.setItem('sidebar-collapsed', isCollapsed.value ? '1' : '0')
}
</script>

<template>
  <aside class="app-sidebar" :class="{ collapsed: isCollapsed }">
    <div class="sidebar-brand">
      <div class="brand-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
      </div>
      <span class="brand-text">智学平台</span>
    </div>

    <nav class="sidebar-nav">
      <button
        v-for="item in visibleItems"
        :key="item.key"
        class="nav-item"
        :class="{ active: isActive(item) }"
        @click="navigate(item)"
        :title="isCollapsed ? item.label : ''"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-label">{{ item.label }}</span>
      </button>
    </nav>

    <div class="sidebar-footer">
      <button class="collapse-btn" @click="toggleCollapse">
        <span style="font-size:16px">{{ isCollapsed ? '▶' : '◀' }}</span>
        <span class="nav-label">{{ isCollapsed ? '' : '收起菜单' }}</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  width: 260px;
  min-width: 260px;
  height: 100vh;
  background: linear-gradient(180deg, var(--panel-strong), var(--panel));
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  transition: width 0.28s cubic-bezier(0.33, 1, 0.68, 1),
              min-width 0.28s cubic-bezier(0.33, 1, 0.68, 1);
  position: relative;
  z-index: 10;
  overflow: hidden;
}

.app-sidebar.collapsed {
  width: 72px;
  min-width: 72px;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 22px 20px;
  border-bottom: 1px solid var(--line);
}

.brand-icon {
  width: 36px; height: 36px; min-width: 36px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 20px color-mix(in srgb, var(--accent) 30%, transparent);
}

.brand-icon svg { width: 20px; height: 20px; }

.brand-text {
  font-size: 18px; font-weight: 750; letter-spacing: 0.03em;
  white-space: nowrap;
  background: linear-gradient(135deg, var(--text), var(--accent));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
  transition: opacity 0.28s ease;
}

.collapsed .brand-text { opacity: 0; }

.sidebar-nav {
  flex: 1; overflow-y: auto; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 2px;
}

.sidebar-nav::-webkit-scrollbar { width: 0; }

.nav-item {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; border-radius: 12px;
  cursor: pointer; color: var(--muted);
  font-size: 14px; font-weight: 500;
  white-space: nowrap; transition: all 0.2s ease;
  position: relative; border: none; background: none;
  width: 100%; text-align: left;
  font-family: inherit;
}

.nav-item:hover {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  color: var(--text);
}

.nav-item.active {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent); font-weight: 650;
}

.nav-item.active::before {
  content: "";
  position: absolute; left: 0; top: 50%;
  transform: translateY(-50%);
  width: 3px; height: 22px; border-radius: 3px;
  background: var(--accent);
  box-shadow: 0 0 10px color-mix(in srgb, var(--accent) 40%, transparent);
}

.nav-icon { width: 20px; height: 20px; min-width: 20px; font-size: 16px; opacity: 0.75; }
.nav-item.active .nav-icon { opacity: 1; }
.nav-label { transition: opacity 0.28s ease; }
.collapsed .nav-label { opacity: 0; pointer-events: none; }

.sidebar-footer { padding: 14px 12px; border-top: 1px solid var(--line); }

.collapse-btn {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; border-radius: 10px;
  cursor: pointer; color: var(--muted); font-size: 13px;
  border: none; background: none; width: 100%;
  transition: all 0.2s ease; font-family: inherit;
}

.collapse-btn:hover { background: color-mix(in srgb, var(--accent) 6%, transparent); color: var(--text); }
</style>
