<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowDown, ArrowLeftBold, ArrowRightBold, Close, SwitchButton, House } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { navigationForRole } from '../config/navigation'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{ mobileOpen?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isCollapsed = ref(localStorage.getItem('sidebar-collapsed') === '1')
const narrow = ref(window.matchMedia('(max-width:900px)').matches)
const compact = computed(() => isCollapsed.value && !narrow.value)
const sidebar = ref<HTMLElement>()
const expanded = ref<string[]>([])
const isAdmin = computed(() => authStore.user?.role === 'admin')
const media = window.matchMedia('(max-width:900px)')
const resize = () => { narrow.value = media.matches; emit('close') }
onMounted(() => media.addEventListener('change', resize))
onBeforeUnmount(() => media.removeEventListener('change', resize))
function toggleGroup(group: string) {
  if (compact.value) {
    isCollapsed.value = false
    localStorage.setItem('sidebar-collapsed', '0')
    if (!expanded.value.includes(group)) expanded.value.push(group)
    return
  }
  expanded.value = expanded.value.includes(group) ? expanded.value.filter(x => x !== group) : [...expanded.value, group]
}
function keyboard(event: KeyboardEvent) {
  if (!props.mobileOpen) return
  if (event.key === 'Escape') { event.preventDefault(); emit('close') }
  if (event.key === 'Tab') {
    const elements = [...(sidebar.value?.querySelectorAll<HTMLElement>('button, a') ?? [])].filter(x => x.offsetParent !== null)
    const first = elements[0], last = elements.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}
watch(() => props.mobileOpen, async open => {
  if (open) { await nextTick(); sidebar.value?.querySelector<HTMLElement>('.mobile-close')?.focus() }
})
async function logout() { authStore.clear(); await router.push('/login') }

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
watch(() => route.name, () => {
  const active = visibleItems.value.find(item => item.routeName === route.name)
  if (active && !expanded.value.includes(active.group)) expanded.value.push(active.group)
}, { immediate: true })
</script>

<template>
  <aside ref="sidebar" class="app-sidebar" :class="{ collapsed: compact, 'mobile-open': props.mobileOpen }" :inert="narrow && !props.mobileOpen" :aria-label="isAdmin ? '管理员导航' : '工作台导航'" @keydown="keyboard">
    <div class="sidebar-brand">
      <div class="brand-icon" aria-hidden="true"><span></span><span></span><span></span></div>
      <div class="brand-copy"><strong>智学平台</strong><small>Learning OS</small></div>
      <button class="mobile-close" type="button" aria-label="关闭导航" @click="emit('close')">
        <el-icon><Close /></el-icon>
      </button>
    </div>

    <nav class="sidebar-nav" aria-label="主导航">
      <section v-for="([group, items], index) in groupedItems" :key="group" class="nav-group">
        <button v-if="isAdmin" type="button" class="nav-item group-toggle" :class="{ 'group-active': items.some(item => isActive(item.route)) }" :aria-expanded="expanded.includes(group) && !compact" :aria-controls="`nav-group-${index}`" :title="group" @click="toggleGroup(group)">
          <span class="nav-icon"><component :is="items[0]?.icon" /></span><span class="nav-label">{{ group }}</span><el-icon v-if="!compact" class="group-chevron" :class="{ open: expanded.includes(group) }"><ArrowDown /></el-icon>
        </button>
        <div v-else class="nav-group-title">{{ group }}</div>
        <div v-show="!isAdmin || (!compact && expanded.includes(group))" :id="`nav-group-${index}`" :class="{ 'nav-children': isAdmin }">
        <button
          v-for="item in items"
          :key="item.key"
          class="nav-item"
          :class="{ active: isActive(item.route) }"
          :aria-current="isActive(item.route) ? 'page' : undefined"
          :title="isCollapsed ? `${item.label} - ${item.description}` : item.description"
          type="button"
          @click="navigate(item.route)"
        >
          <span class="nav-icon"><component :is="item.icon" /></span>
          <span class="nav-label">{{ item.label }}</span>
        </button>
        </div>
      </section>
    </nav>

    <div class="sidebar-footer">
      <template v-if="isAdmin">
        <div v-if="!compact" class="admin-identity">{{ authStore.user?.username }} · 管理员</div>
        <button class="nav-item" type="button" title="返回平台首页" @click="navigate('/')"><span class="nav-icon"><House /></span><span class="nav-label">返回平台首页</span></button>
        <button class="nav-item" type="button" title="退出登录" @click="logout"><span class="nav-icon"><SwitchButton /></span><span class="nav-label">退出登录</span></button>
      </template>
      <button class="collapse-btn" type="button" :aria-label="compact ? '展开导航' : '收起导航'" :title="compact ? '展开导航' : '收起导航'" @click="toggleCollapse">
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
.group-toggle { color:var(--text); font-weight:650; }
.group-active { color:var(--accent); }
.collapsed .nav-label,.collapsed .brand-copy { display:none; }
.collapsed .group-active { background:var(--accent-soft); border-left:3px solid var(--accent); }
.group-chevron { margin-left:auto; transition:transform .18s; }
.group-chevron.open { transform:rotate(180deg); }
.nav-children { margin:4px 0 0 15px; padding-left:7px; border-left:1px solid var(--line); }
.nav-children .nav-item { font-size:13px; gap:8px; }
.nav-group:has(.group-toggle) + .nav-group { margin-top:8px; }
.admin-identity { padding:5px 10px; color:var(--muted); font-size:12px; overflow-wrap:anywhere; }
button:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }

@media (max-width:900px) {
  .app-sidebar,.app-sidebar.collapsed { width:min(84vw,292px); min-width:min(84vw,292px); position:fixed; inset:0 auto 0 0; transform:translateX(-104%); box-shadow:24px 0 60px rgba(15,23,42,.2); }
  .app-sidebar.mobile-open { transform:translateX(0); }
  .collapsed .brand-copy,.collapsed .nav-label { opacity:1; pointer-events:auto; }
  .collapsed .nav-group-title { height:auto; padding:0 12px 7px; margin:0; background:none; color:var(--muted); }
  .collapsed .nav-item { justify-content:flex-start; padding-inline:12px; }
  .sidebar-footer { padding:8px 12px; }
  .collapse-btn { display:none; }
  .mobile-close { width:36px; height:36px; margin-left:auto; display:grid; place-items:center; border:0; border-radius:10px; color:var(--muted); background:var(--surface-soft); cursor:pointer; }
}

@media (prefers-reduced-motion:reduce) { .app-sidebar,.nav-item,.nav-label { transition:none; } }
</style>
