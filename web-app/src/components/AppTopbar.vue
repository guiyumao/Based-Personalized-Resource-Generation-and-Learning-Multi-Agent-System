<script setup lang="ts">
import { computed, ref } from 'vue'
import NotificationCard from './notifications/NotificationCard.vue'
import { ArrowDown, Brush, House, MagicStick, Menu, Search, SwitchButton } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { navigationForRole, navigationItemForRoute } from '../config/navigation'
import { useAuthStore } from '../stores/auth'
import { useTheme, type ThemeName } from '../composables/useTheme'

defineEmits<{ 'toggle-navigation': [] }>()

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { currentTheme, setTheme } = useTheme()
const searchQuery = ref('')
const searchOpen = ref(false)
const showThemePicker = ref(false)
const showUserMenu = ref(false)

const pageItem = computed(() => navigationItemForRoute(String(route.name ?? '')))
const pageLabel = computed(() => pageItem.value?.label ?? '工作台')
const pageDescription = computed(() => pageItem.value?.description ?? '个性化资源生成与学习多智能体系统')
const roleLabel = computed(() => ({ student: '学生', teacher: '教师', admin: '管理员' })[authStore.user?.role ?? 'student'])
const userInitial = computed(() => (authStore.user?.username || '用户').trim().slice(0, 1).toUpperCase())
const searchResults = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  const items = navigationForRole(authStore.user?.role)
  if (!query) return items.slice(0, 6)
  return items.filter((item) => `${item.label}${item.description}${item.group}`.toLowerCase().includes(query))
})

const themes: { key: ThemeName; name: string; color: string }[] = [
  { key: null, name: '靛蓝云台', color: '#4f46e5' },
  { key: 'ocean', name: '深海科技', color: '#00b8a0' },
  { key: 'warm', name: '暖金学术', color: '#d97745' },
  { key: 'cosmic', name: '暗夜紫穹', color: '#8b5cf6' },
  { key: 'minimal', name: '极简晨光', color: '#2563eb' },
  { key: 'forest', name: '森林绿洲', color: '#35b978' },
]

async function navigateFromSearch(path: string) {
  searchOpen.value = false
  searchQuery.value = ''
  await router.push(path)
}

function selectTheme(theme: ThemeName) {
  setTheme(theme)
  showThemePicker.value = false
}

async function handleLogout() {
  authStore.clear()
  await router.push('/login')
}
</script>

<template>
  <header class="app-topbar">
    <div class="topbar-heading">
      <button class="mobile-menu-button" type="button" aria-label="打开导航" @click="$emit('toggle-navigation')">
        <el-icon><Menu /></el-icon>
      </button>
      <div>
        <div class="breadcrumb-line"><span>{{ pageItem?.group ?? '工作台' }}</span><b>/</b><strong>{{ pageLabel }}</strong></div>
        <p>{{ pageDescription }}</p>
      </div>
    </div>

    <div class="topbar-actions">
      <slot name="assistant" />
      <div class="global-search" :class="{ open: searchOpen }">
        <el-icon><Search /></el-icon>
        <input
          v-model="searchQuery"
          type="search"
          placeholder="搜索功能"
          aria-label="搜索工作台功能"
          @focus="searchOpen = true"
          @keydown.esc="searchOpen = false"
        />
        <div v-if="searchOpen" class="search-popover" @mouseleave="searchOpen = false">
          <div class="popover-title">{{ searchQuery ? '搜索结果' : '快速前往' }}</div>
          <button v-for="item in searchResults" :key="item.key" type="button" @click="navigateFromSearch(item.route)">
            <span class="search-result-icon"><component :is="item.icon" /></span>
            <span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
          </button>
          <div v-if="!searchResults.length" class="search-empty">未找到匹配功能</div>
        </div>
      </div>

      <NotificationCard :key="authStore.user?.userId" />
      <div class="topbar-popover-wrap">
        <button class="icon-button" type="button" title="切换主题" @click="showThemePicker = !showThemePicker">
          <el-icon><Brush /></el-icon>
        </button>
        <div v-if="showThemePicker" class="theme-popover" @mouseleave="showThemePicker = false">
          <div class="popover-title">外观主题</div>
          <button v-for="theme in themes" :key="theme.name" type="button" :class="{ active: currentTheme === theme.key }" @click="selectTheme(theme.key)">
            <span class="theme-swatch" :style="{ background: theme.color }"></span><span>{{ theme.name }}</span>
          </button>
        </div>
      </div>

      <div class="topbar-popover-wrap">
        <button class="user-button" type="button" @click="showUserMenu = !showUserMenu">
          <span class="user-avatar">{{ userInitial }}</span>
          <span class="user-copy"><strong>{{ authStore.user?.username ?? '用户' }}</strong><small>{{ roleLabel }}</small></span>
          <el-icon class="user-arrow"><ArrowDown /></el-icon>
        </button>
        <div v-if="showUserMenu" class="user-popover" @mouseleave="showUserMenu = false">
          <button v-if="authStore.user?.role === 'student'" type="button" @click="router.push('/student/profile'); showUserMenu = false">
            <el-icon><MagicStick /></el-icon><span>学习画像</span>
          </button>
          <button type="button" @click="router.push('/'); showUserMenu = false">
            <el-icon><House /></el-icon><span>返回首页</span>
          </button>
          <button class="danger" type="button" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon><span>退出登录</span>
          </button>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-topbar { min-height:76px; display:flex; align-items:center; justify-content:space-between; gap:20px; padding:12px 26px; border-bottom:1px solid var(--line); background:var(--panel-strong); position:relative; z-index:20; }
.topbar-heading,.topbar-actions,.breadcrumb-line,.user-button { display:flex; align-items:center; }
.topbar-heading { min-width:0; gap:12px; }
.breadcrumb-line { gap:7px; font-size:15px; }
.breadcrumb-line span,.breadcrumb-line b { color:var(--muted); font-weight:500; }
.breadcrumb-line strong { color:var(--text); }
.topbar-heading p { margin:4px 0 0; max-width:560px; overflow:hidden; color:var(--muted); font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.topbar-actions { gap:9px; }
.mobile-menu-button,.icon-button { width:40px; height:40px; border:1px solid var(--line); border-radius:11px; display:grid; place-items:center; color:var(--muted); background:var(--panel); cursor:pointer; }
.mobile-menu-button { display:none; }
.icon-button:hover,.mobile-menu-button:hover { color:var(--accent); border-color:color-mix(in srgb,var(--accent) 35%,var(--line)); background:var(--accent-soft); }
.global-search { width:220px; height:40px; display:flex; align-items:center; gap:8px; padding:0 12px; border:1px solid var(--line); border-radius:11px; color:var(--muted); background:var(--panel); position:relative; transition:border-color .18s ease,box-shadow .18s ease,width .18s ease; }
.global-search.open { width:280px; border-color:color-mix(in srgb,var(--accent) 45%,var(--line)); box-shadow:0 0 0 3px var(--accent-soft); }
.global-search input { width:100%; min-width:0; border:0; outline:0; color:var(--text); background:transparent; }
.global-search input::placeholder { color:var(--muted); }
.search-popover,.theme-popover,.user-popover { position:absolute; top:calc(100% + 10px); right:0; border:1px solid var(--line); border-radius:14px; padding:7px; background:var(--panel-strong); box-shadow:var(--shadow); }
.search-popover { width:360px; max-height:420px; overflow:auto; }
.popover-title { padding:8px 10px 6px; color:var(--muted); font-size:11px; font-weight:750; letter-spacing:.08em; }
.search-popover button { width:100%; display:grid; grid-template-columns:36px 1fr; gap:10px; align-items:center; padding:10px; border:0; border-radius:10px; color:var(--text); background:transparent; text-align:left; cursor:pointer; }
.search-popover button:hover { background:var(--accent-soft); }
.search-result-icon { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:var(--accent); background:var(--accent-soft); }
.search-result-icon :deep(svg) { width:17px; }
.search-popover strong,.search-popover small { display:block; }
.search-popover strong { font-size:13px; }
.search-popover small { margin-top:3px; color:var(--muted); font-size:11px; }
.search-empty { padding:24px; color:var(--muted); font-size:13px; text-align:center; }
.topbar-popover-wrap { position:relative; }
.theme-popover { width:180px; }
.theme-popover button,.user-popover button { width:100%; display:flex; align-items:center; gap:10px; padding:9px 10px; border:0; border-radius:9px; color:var(--text); background:transparent; cursor:pointer; text-align:left; }
.theme-popover button:hover,.theme-popover button.active,.user-popover button:hover { background:var(--accent-soft); color:var(--accent); }
.theme-swatch { width:14px; height:14px; border-radius:5px; box-shadow:inset 0 0 0 1px rgba(255,255,255,.24); }
.user-button { min-height:42px; gap:9px; padding:4px 8px 4px 5px; border:1px solid var(--line); border-radius:12px; color:var(--text); background:var(--panel); cursor:pointer; }
.user-avatar { width:32px; height:32px; border-radius:9px; display:grid; place-items:center; color:#fff; background:linear-gradient(145deg,var(--accent),var(--accent-deep)); font-size:13px; font-weight:800; }
.user-copy { min-width:76px; display:grid; gap:1px; text-align:left; }
.user-copy strong { max-width:112px; overflow:hidden; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.user-copy small { color:var(--muted); font-size:10px; }
.user-arrow { color:var(--muted); font-size:11px; }
.user-popover { min-width:166px; }
.user-popover .danger { color:var(--red); }

@media (max-width:900px) { .app-topbar { min-height:68px; padding:10px 16px; } .mobile-menu-button { display:grid; } .topbar-heading p { display:none; } .global-search { width:42px; padding:0; justify-content:center; } .global-search input { position:absolute; width:1px; opacity:0; pointer-events:none; } .global-search.open { width:240px; padding:0 12px; justify-content:flex-start; } .global-search.open input { position:static; width:100%; opacity:1; pointer-events:auto; } .search-popover { width:min(360px,calc(100vw - 32px)); } .user-copy,.user-arrow { display:none; } }
@media (max-width:560px) { .breadcrumb-line span,.breadcrumb-line b { display:none; } .topbar-actions { gap:6px; } .global-search.open { position:absolute; left:16px; right:16px; top:13px; width:auto; z-index:3; } }
</style>

<style scoped>
@media(max-width:560px){.topbar-heading{flex:1}.breadcrumb-line{display:none}.global-search,.topbar-actions>.topbar-popover-wrap:has(.theme-popover),.topbar-actions>.topbar-popover-wrap:has(.icon-button){display:none}.app-topbar{gap:6px;padding-left:10px;padding-right:10px}}
</style>
