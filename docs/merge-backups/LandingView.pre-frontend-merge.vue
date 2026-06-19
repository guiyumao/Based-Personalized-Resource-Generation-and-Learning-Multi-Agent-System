<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

type ThemeKey = 'ocean' | 'warm' | 'cosmic' | 'minimal' | 'forest'

type ThemeOption = {
  key: ThemeKey
  label: string
  color: string
}

type FeatureCategory = 'all' | 'learning' | 'resource' | 'assessment' | 'insight' | 'collaboration'

type FeatureCard = {
  category: Exclude<FeatureCategory, 'all'>
  icon: string
  title: string
  description: string
  route?: string
  actionLabel: string
}

type FeatureCategoryOption = {
  key: FeatureCategory
  label: string
  description: string
}

const router = useRouter()
const authStore = useAuthStore()

const themeOptions: ThemeOption[] = [
  { key: 'ocean', label: '深海科技', color: '#00c8aa' },
  { key: 'warm', label: '暖金学术', color: '#e8924a' },
  { key: 'cosmic', label: '夜空协同', color: '#a78bfa' },
  { key: 'minimal', label: '极简明亮', color: '#2563eb' },
  { key: 'forest', label: '森林生长', color: '#48c884' },
]

const featureCategoryOptions: FeatureCategoryOption[] = [
  { key: 'all', label: '全部功能', description: '查看完整功能地图' },
  { key: 'learning', label: '学习路径', description: '学习计划与练习入口' },
  { key: 'resource', label: '资源生成', description: '课件与内容生成能力' },
  { key: 'assessment', label: '诊断评估', description: '测评、错题与报告' },
  { key: 'insight', label: '认知洞察', description: '图谱与智能问答分析' },
  { key: 'collaboration', label: '角色协同', description: '多角色工作台联动' },
]

const featureCards = computed<FeatureCard[]>(() => [
  {
    icon: '🗺️',
    title: '个性化学习路径',
    description: '基于掌握度、学习风格和薄弱点动态生成分阶段学习路线，并在学习过程中持续调整。',
    category: 'learning',
    route: authStore.isAuthenticated ? '/student' : '/login',
    actionLabel: authStore.isAuthenticated ? '进入学生工作台' : '登录后进入学生工作台',
  },
  {
    icon: '📘',
    title: '智能课件生成',
    description: '围绕知识点快速生成结构化课件、提炼重点，并支持独立课件页进行完整阅读。',
    category: 'resource',
    route: authStore.isAuthenticated ? '/student/courseware' : '/login',
    actionLabel: authStore.isAuthenticated ? '打开独立课件页' : '登录后体验课件页',
  },
  {
    icon: '✅',
    title: '自适应练习测评',
    description: '自动生成练习题并即时反馈，提交后同步更新掌握度、学习画像和后续推荐。',
    category: 'assessment',
    route: authStore.isAuthenticated ? '/student' : '/login',
    actionLabel: authStore.isAuthenticated ? '进入练习区' : '登录后进入练习区',
  },
  {
    icon: '📒',
    title: '智能错题本',
    description: '集中展示错题、解析和建议动作，支持独立错题页复盘、重练，以及一键清空当前错题本。',
    category: 'assessment',
    route: authStore.isAuthenticated ? '/student/mistakes' : '/login',
    actionLabel: authStore.isAuthenticated ? '进入独立错题页' : '登录后进入错题页',
  },
  {
    icon: '🕸️',
    title: '知识图谱可视化',
    description: '用图谱方式展示知识点依赖关系和当前掌握情况，帮助快速定位薄弱环节。',
    category: 'insight',
    route: authStore.isAuthenticated ? '/student' : '/login',
    actionLabel: authStore.isAuthenticated ? '查看图谱' : '登录后查看图谱',
  },
  {
    icon: '💬',
    title: '多智能体学习问答',
    description: '问答不仅返回答案，还会结合学习语境给出学习建议、知识漏洞和后续行动。',
    category: 'insight',
    route: authStore.isAuthenticated ? '/student' : '/login',
    actionLabel: authStore.isAuthenticated ? '进入问答区' : '登录后进入问答区',
  },
  {
    icon: '📊',
    title: '阶段学习报告',
    description: '汇总真实练习与错题记录，自动生成阶段报告、综合报告与针对性学习建议。',
    category: 'assessment',
    route: authStore.isAuthenticated ? '/student' : '/login',
    actionLabel: authStore.isAuthenticated ? '查看学习报告' : '登录后查看学习报告',
  },
  {
    icon: '👩‍🏫',
    title: '多角色协同',
    description: '学生、教师、管理员分别拥有专属工作台，形成从学习到教学管理的闭环。',
    category: 'collaboration',
    route: authStore.isAuthenticated ? authStore.homeRoute : '/login',
    actionLabel: authStore.isAuthenticated ? `进入${homeRouteLabel.value}` : '登录后进入对应工作台',
  },
])

const activeTheme = ref<ThemeKey>('ocean')
const particleStyles = ref<Array<Record<string, string>>>([])
const isProfileMenuOpen = ref(false)
const profileMenuRef = ref<HTMLElement | null>(null)
const activeFeatureCategory = ref<FeatureCategory>('all')
const currentFeaturePage = ref(1)

const FEATURE_PAGE_SIZE = 6

let animationFrameId = 0
let pointerX = 50
let pointerY = 50
let currentPointerX = 50
let currentPointerY = 50

const isAuthenticated = computed(() => authStore.isAuthenticated)
const navAccountLabel = computed(() => (isAuthenticated.value ? '切换账号' : '注册账号'))
const profileInitial = computed(() => authStore.user?.username?.trim().charAt(0).toUpperCase() ?? 'A')
const heroPrimaryLabel = computed(() => (isAuthenticated.value ? `进入${homeRouteLabel.value}` : '登录后进入工作台'))
const heroSecondaryLabel = computed(() => '了解更多')
const homeRouteLabel = computed(() => {
  if (authStore.user?.role === 'teacher') {
    return '教师工作台'
  }
  if (authStore.user?.role === 'admin') {
    return '管理员工作台'
  }
  return '学生工作台'
})
const navCtaLabel = computed(() => (isAuthenticated.value ? `进入${homeRouteLabel.value}` : '立即登录'))
const profileRoleLabel = computed(() => {
  if (authStore.user?.role === 'teacher') {
    return '教师账号'
  }
  if (authStore.user?.role === 'admin') {
    return '管理员账号'
  }
  return '学生账号'
})
const welcomeTitle = computed(() => {
  if (!authStore.user) {
    return 'AI 驱动的个性化学习系统'
  }
  return `${authStore.user.username}，继续进入${homeRouteLabel.value}`
})
const welcomeDescription = computed(() => {
  if (!authStore.user) {
    return '多智能体协同生成学习路径、课件、练习、错题本与学习报告。进入任意工作台前，需要先登录。'
  }
  return '当前登录身份已保留，你可以直接从首页继续进入对应工作台，或跳转到具体功能页。'
})
const filteredFeatureCards = computed(() => {
  if (activeFeatureCategory.value === 'all') {
    return featureCards.value
  }

  return featureCards.value.filter((feature) => feature.category === activeFeatureCategory.value)
})
const featurePageCount = computed(() => Math.max(1, Math.ceil(filteredFeatureCards.value.length / FEATURE_PAGE_SIZE)))
const visibleFeaturePage = computed(() => Math.min(currentFeaturePage.value, featurePageCount.value))
const paginatedFeatureCards = computed(() => {
  const start = (visibleFeaturePage.value - 1) * FEATURE_PAGE_SIZE
  return filteredFeatureCards.value.slice(start, start + FEATURE_PAGE_SIZE)
})
const featurePagination = computed(() => Array.from({ length: featurePageCount.value }, (_, index) => index + 1))
const glowStyle = computed(() => ({
  background: `
    radial-gradient(
      420px circle at ${currentPointerX}% ${currentPointerY}%,
      color-mix(in srgb, var(--accent) 12%, transparent) 0%,
      color-mix(in srgb, var(--accent3) 6%, transparent) 30%,
      transparent 70%
    ),
    radial-gradient(
      600px circle at ${currentPointerX}% ${currentPointerY}%,
      color-mix(in srgb, var(--accent2) 4%, transparent) 0%,
      transparent 50%
    )
  `,
}))
const gridMaskStyle = computed(() => ({
  '--mx': `${currentPointerX}%`,
  '--my': `${currentPointerY}%`,
}))

function createParticles() {
  particleStyles.value = Array.from({ length: 25 }, () => {
    const size = (Math.random() * 6 + 2).toFixed(2)
    const left = (Math.random() * 100).toFixed(2)
    const delay = (Math.random() * 6).toFixed(2)
    const duration = (Math.random() * 14 + 10).toFixed(2)
    const colors = ['var(--accent)', 'var(--accent2)', 'var(--accent3)']
    const color = colors[Math.floor(Math.random() * colors.length)]
    return {
      width: `${size}px`,
      height: `${size}px`,
      left: `${left}vw`,
      bottom: '-20px',
      background: color,
      boxShadow: `0 0 ${Number(size) * 3}px ${color}`,
      animationDuration: `${duration}s`,
      animationDelay: `${delay}s`,
    }
  })
}

function lerp(start: number, end: number, factor: number) {
  return start + (end - start) * factor
}

function animateGlow() {
  currentPointerX = lerp(currentPointerX, pointerX, 0.06)
  currentPointerY = lerp(currentPointerY, pointerY, 0.06)
  animationFrameId = window.requestAnimationFrame(animateGlow)
}

function handlePointerMove(event: MouseEvent | TouchEvent) {
  if ('touches' in event) {
    if (!event.touches.length) {
      return
    }
    pointerX = (event.touches[0].clientX / window.innerWidth) * 100
    pointerY = (event.touches[0].clientY / window.innerHeight) * 100
    return
  }

  pointerX = (event.clientX / window.innerWidth) * 100
  pointerY = (event.clientY / window.innerHeight) * 100
}

function setTheme(theme: ThemeKey) {
  activeTheme.value = theme
  document.documentElement.setAttribute('data-theme', theme)
}

function scrollToFeatures() {
  document.getElementById('features')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function goToPrimaryCta() {
  void router.push(isAuthenticated.value ? authStore.homeRoute : '/login')
}

function goToSecondaryCta() {
  if (isAuthenticated.value) {
    scrollToFeatures()
    return
  }
  scrollToFeatures()
}

function openRoute(route?: string) {
  if (!route) {
    return
  }
  void router.push(route)
}

function setFeatureCategory(category: FeatureCategory) {
  activeFeatureCategory.value = category
  currentFeaturePage.value = 1
}

function goToFeaturePage(page: number) {
  if (page < 1 || page > featurePageCount.value) {
    return
  }

  currentFeaturePage.value = page
}

function handleNavCta() {
  void router.push(isAuthenticated.value ? authStore.homeRoute : '/login')
}

function toggleProfileMenu() {
  isProfileMenuOpen.value = !isProfileMenuOpen.value
}

function closeProfileMenu() {
  isProfileMenuOpen.value = false
}

function handleGlobalPointerDown(event: Event) {
  if (!isProfileMenuOpen.value || !profileMenuRef.value) {
    return
  }

  const target = event.target
  if (target instanceof Node && !profileMenuRef.value.contains(target)) {
    closeProfileMenu()
  }
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeProfileMenu()
  }
}

function handleAccountAction() {
  closeProfileMenu()
  if (!isAuthenticated.value) {
    void router.push('/register')
    return
  }

  authStore.clear()
  void router.push('/login')
}

function handleLogout() {
  closeProfileMenu()
  authStore.clear()
  void router.push('/')
}

function handleProfileRoute(route: string) {
  closeProfileMenu()
  void router.push(route)
}

watch(featurePageCount, (pageCount) => {
  if (currentFeaturePage.value > pageCount) {
    currentFeaturePage.value = pageCount
  }
})

onMounted(() => {
  createParticles()
  setTheme(activeTheme.value)
  window.addEventListener('mousemove', handlePointerMove)
  window.addEventListener('touchmove', handlePointerMove, { passive: true })
  window.addEventListener('pointerdown', handleGlobalPointerDown)
  window.addEventListener('keydown', handleGlobalKeydown)
  animationFrameId = window.requestAnimationFrame(animateGlow)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', handlePointerMove)
  window.removeEventListener('touchmove', handlePointerMove)
  window.removeEventListener('pointerdown', handleGlobalPointerDown)
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.cancelAnimationFrame(animationFrameId)
})
</script>

<template>
  <div class="landing-shell">
    <div id="mouse-glow" aria-hidden="true">
      <div class="glow-layer" :style="glowStyle" />
      <div class="grid-layer" :style="gridMaskStyle" />
    </div>
    <div id="particles-container" aria-hidden="true">
      <div v-for="(particle, index) in particleStyles" :key="`particle-${index}`" class="particle" :style="particle" />
    </div>

    <nav class="nav-bar">
      <button type="button" class="nav-brand brand-button" @click="scrollToFeatures">
        <div class="brand-dot" />
        智学平台
      </button>
      <div class="nav-links">
        <a href="#features">功能介绍</a>
        <a href="#ai-tech">AI 技术</a>
        <a href="#stats">平台数据</a>
        <button type="button" class="nav-link-button nav-cta" @click="handleNavCta">{{ heroPrimaryLabel }}</button>
        <button
          v-if="!isAuthenticated"
          type="button"
          class="nav-link-button nav-ghost"
          @click="handleAccountAction"
        >
          {{ navAccountLabel }}
        </button>
        <div v-else ref="profileMenuRef" class="profile-menu-wrapper">
          <button
            type="button"
            class="profile-trigger"
            :class="{ active: isProfileMenuOpen }"
            :aria-expanded="isProfileMenuOpen"
            aria-haspopup="menu"
            aria-label="打开个人信息菜单"
            @click="toggleProfileMenu"
          >
            <span class="profile-trigger-text">
              <strong>{{ authStore.user?.username }}</strong>
              <small>{{ profileRoleLabel }}</small>
            </span>
            <span class="profile-avatar">{{ profileInitial }}</span>
          </button>
          <transition name="profile-menu">
            <div v-if="isProfileMenuOpen" class="profile-menu-panel" role="menu" aria-label="个人信息菜单">
              <div class="profile-menu-header">
                <div class="profile-menu-avatar">{{ profileInitial }}</div>
                <div class="profile-menu-meta">
                  <strong>{{ authStore.user?.username }}</strong>
                  <span>{{ profileRoleLabel }}</span>
                  <small>当前登录状态已保留，可直接进入工作台</small>
                </div>
              </div>
              <div class="profile-menu-actions">
                <button type="button" class="profile-menu-item" @click="handleProfileRoute(authStore.homeRoute)">
                  <span class="profile-menu-icon">⌂</span>
                  <span>进入{{ homeRouteLabel }}</span>
                </button>
                <button type="button" class="profile-menu-item" @click="handleProfileRoute('/student/mistakes')">
                  <span class="profile-menu-icon">错</span>
                  <span>错题本</span>
                </button>
                <button type="button" class="profile-menu-item" @click="handleProfileRoute('/student')">
                  <span class="profile-menu-icon">问</span>
                  <span>多智能体问答</span>
                </button>
                <button type="button" class="profile-menu-item" @click="handleProfileRoute('/student')">
                  <span class="profile-menu-icon">报</span>
                  <span>学习报告</span>
                </button>
                <button type="button" class="profile-menu-item" @click="handleAccountAction">
                  <span class="profile-menu-icon">⇄</span>
                  <span>切换账号</span>
                </button>
                <button type="button" class="profile-menu-item danger" @click="handleLogout">
                  <span class="profile-menu-icon">↗</span>
                  <span>退出登录</span>
                </button>
              </div>
            </div>
          </transition>
        </div>
        <div class="theme-dots">
          <button
            v-for="theme in themeOptions"
            :key="theme.key"
            type="button"
            class="theme-dot"
            :class="{ active: activeTheme === theme.key }"
            :title="theme.label"
            :style="{ background: theme.color, color: theme.color }"
            @click="setTheme(theme.key)"
          />
        </div>
      </div>
    </nav>

    <section class="hero-section">
      <div class="hero-eyebrow">AI-Powered Learning Platform</div>
      <h1 class="hero-title">{{ welcomeTitle }}</h1>
      <p class="hero-subtitle">{{ welcomeDescription }}</p>

      <div class="hero-buttons">
        <button class="btn-hero-primary" @click="goToPrimaryCta">{{ heroPrimaryLabel }}</button>
        <button class="btn-hero-secondary" @click="goToSecondaryCta">{{ heroSecondaryLabel }}</button>
      </div>

      <div class="hero-status">
        <div class="status-chip">{{ isAuthenticated ? `当前身份：${homeRouteLabel}` : '当前状态：访客浏览' }}</div>
        <div class="status-chip">{{ isAuthenticated ? `已登录用户：${authStore.user?.username}` : '可先浏览能力，再登录体验' }}</div>
      </div>

      <div class="scroll-hint">
        <span>继续探索</span>
        <div class="line" />
      </div>
    </section>

    <section id="features" class="section">
      <div class="section-inner">
        <div class="section-label">核心功能</div>
        <h2 class="section-title">现有系统能力已经接入这张首页</h2>
        <p class="section-desc">
          这不是单纯展示页。下面每张卡片都接到了当前仓库里已经实现的页面或工作台入口，既能展示产品能力，也能直接进入功能。
        </p>

        <div class="feature-toolbar">
          <div class="feature-nav-bar" role="tablist" aria-label="功能分类导航">
            <button
              v-for="category in featureCategoryOptions"
              :key="category.key"
              type="button"
              class="feature-nav-chip"
              :class="{ active: activeFeatureCategory === category.key }"
              :aria-pressed="activeFeatureCategory === category.key"
              @click="setFeatureCategory(category.key)"
            >
              <strong>{{ category.label }}</strong>
              <span>{{ category.description }}</span>
            </button>
          </div>

          <div class="feature-pagination-bar">
            <span class="feature-pagination-summary">第 {{ visibleFeaturePage }} / {{ featurePageCount }} 页</span>
            <div class="feature-pagination-actions">
              <button
                type="button"
                class="feature-page-button"
                :disabled="visibleFeaturePage === 1"
                @click="goToFeaturePage(visibleFeaturePage - 1)"
              >
                上一页
              </button>
              <button
                v-for="page in featurePagination"
                :key="`feature-page-${page}`"
                type="button"
                class="feature-page-button"
                :class="{ active: visibleFeaturePage === page }"
                :aria-current="visibleFeaturePage === page ? 'page' : undefined"
                @click="goToFeaturePage(page)"
              >
                {{ page }}
              </button>
              <button
                type="button"
                class="feature-page-button"
                :disabled="visibleFeaturePage === featurePageCount"
                @click="goToFeaturePage(visibleFeaturePage + 1)"
              >
                下一页
              </button>
            </div>
          </div>
        </div>

        <div class="feature-grid">
          <article
            v-for="feature in paginatedFeatureCards"
            :key="feature.title"
            class="feature-card clickable-feature-card"
            role="link"
            tabindex="0"
            @click="openRoute(feature.route)"
            @keydown.enter.prevent="openRoute(feature.route)"
            @keydown.space.prevent="openRoute(feature.route)"
          >
            <div class="feature-icon">{{ feature.icon }}</div>
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.description }}</p>
            <div class="card-actions">
              <button class="card-link" type="button" @click.stop="openRoute(feature.route)">{{ feature.actionLabel }}</button>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section id="ai-tech" class="section">
      <div class="section-inner">
        <div class="section-label">AI 技术</div>
        <h2 class="section-title">多智能体协同能力直接服务现有前端功能</h2>
        <p class="section-desc">
          当前首页内容与实际系统保持一致，下面这些能力已经体现在学生工作台、错题页、课件页和教师端的数据流里。
        </p>

        <div class="ai-highlight-grid">
          <article class="ai-highlight-card">
            <div class="ai-icon-lg">🧠</div>
            <h3>多智能体协同</h3>
            <p>资源生成、学习画像、学习路径、问答分析和评估反馈通过多服务协作完成，前端入口已经接到对应工作台。</p>
            <div class="ai-tag-row">
              <span class="ai-tag">LangGraph</span>
              <span class="ai-tag">Multi-Agent</span>
              <span class="ai-tag">FastAPI</span>
            </div>
          </article>

          <article class="ai-highlight-card">
            <div class="ai-icon-lg">📚</div>
            <h3>RAG 资源生成</h3>
            <p>课件、练习和答疑结合知识库与检索增强生成，已经能从学生工作台和独立课件页完整体验。</p>
            <div class="ai-tag-row">
              <span class="ai-tag">ChromaDB</span>
              <span class="ai-tag">Elasticsearch</span>
              <span class="ai-tag">Resource Plan</span>
            </div>
          </article>

          <article class="ai-highlight-card">
            <div class="ai-icon-lg">🕸️</div>
            <h3>知识图谱推理</h3>
            <p>基于 Neo4j 的图谱关系用于展示先修依赖与掌握度变化，已接入学生工作台的图谱可视化区域。</p>
            <div class="ai-tag-row">
              <span class="ai-tag">Neo4j</span>
              <span class="ai-tag">Graph Reasoning</span>
              <span class="ai-tag">vis-network</span>
            </div>
          </article>

          <article class="ai-highlight-card">
            <div class="ai-icon-lg">📈</div>
            <h3>学习画像与评估</h3>
            <p>真实答题记录驱动错题本、阶段报告和学习建议，独立错题页现在也支持清空当前错题本。</p>
            <div class="ai-tag-row">
              <span class="ai-tag">Learner Profile</span>
              <span class="ai-tag">Evaluation</span>
              <span class="ai-tag">Reports</span>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section id="stats" class="section">
      <div class="section-inner">
        <div class="section-label">平台能力</div>
        <h2 class="section-title">和当前项目实现对齐的能力概览</h2>
        <p class="section-desc">这些数字对应你现在仓库里已经存在的功能模块、角色工作台和本地启动服务，不是纯装饰文案。</p>

        <div class="stats-bar">
          <div class="stat-item">
            <div class="stat-num">6+</div>
            <div class="stat-label">多智能体学习能力</div>
          </div>
          <div class="stat-item">
            <div class="stat-num">3</div>
            <div class="stat-label">角色工作台入口</div>
          </div>
          <div class="stat-item">
            <div class="stat-num">8</div>
            <div class="stat-label">核心学习功能模块</div>
          </div>
          <div class="stat-item">
            <div class="stat-num">7</div>
            <div class="stat-label">本地启动服务端口</div>
          </div>
        </div>
      </div>
    </section>

    <section class="cta-section">
      <h2 class="cta-title">{{ isAuthenticated ? '继续进入你的工作台' : '准备开始体验这套学习系统了吗？' }}</h2>
      <p class="cta-desc">
        {{ isAuthenticated
          ? '当前登录态已经保留，你可以直接进入对应身份的工作台，也可以继续浏览首页能力说明。'
          : '先浏览产品能力，再登录或注册进入学生、教师或管理员工作台。' }}
      </p>
      <div class="hero-buttons">
        <button class="btn-hero-primary" @click="goToPrimaryCta">{{ heroPrimaryLabel }}</button>
        <button class="btn-hero-secondary" @click="isAuthenticated ? scrollToFeatures() : openRoute('/login')">
          {{ isAuthenticated ? '查看功能模块' : '先去登录' }}
        </button>
      </div>
    </section>

    <footer class="footer">
      <span>© 2026 智学平台 · AI-Powered Learning</span>
      <span class="footer-links">
        <button type="button" class="footer-link" @click="openRoute(isAuthenticated ? authStore.homeRoute : '/login')">
          {{ isAuthenticated ? homeRouteLabel : '登录' }}
        </button>
        <a href="#features">功能</a>
        <a href="#ai-tech">技术</a>
      </span>
    </footer>
  </div>
</template>

<style scoped>
.landing-shell {
  --bg-deep: #080e1a;
  --bg-surface: #0d1525;
  --bg-card: rgba(16, 26, 44, 0.78);
  --bg-hover: rgba(255, 255, 255, 0.04);
  --border: rgba(80, 160, 190, 0.12);
  --border-focus: rgba(0, 200, 170, 0.28);
  --text: #e2ebf4;
  --text-muted: #7b90a8;
  --accent: #00c8aa;
  --accent2: #ff7b4a;
  --accent3: #4da3e0;
  --shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
  --shadow-sm: 0 8px 24px rgba(0, 0, 0, 0.2);
  --radius: 16px;
  --radius-lg: 22px;
  --transition: 0.28s cubic-bezier(0.33, 1, 0.68, 1);
  position: relative;
  min-height: 100vh;
  background: var(--bg-deep);
  color: var(--text);
  overflow-x: hidden;
  transition: background 0.5s ease, color 0.5s ease;
}

:global(html[data-theme='ocean']) .landing-shell {
  --bg-deep: #080e1a;
  --bg-surface: #0d1525;
  --bg-card: rgba(16, 26, 44, 0.78);
  --bg-hover: rgba(255, 255, 255, 0.04);
  --border: rgba(80, 160, 190, 0.12);
  --border-focus: rgba(0, 200, 170, 0.28);
  --text: #e2ebf4;
  --text-muted: #7b90a8;
  --accent: #00c8aa;
  --accent2: #ff7b4a;
  --accent3: #4da3e0;
}

:global(html[data-theme='warm']) .landing-shell {
  --bg-deep: #1e1814;
  --bg-surface: #28201a;
  --bg-card: rgba(42, 32, 24, 0.78);
  --bg-hover: rgba(255, 240, 220, 0.05);
  --border: rgba(180, 140, 100, 0.15);
  --border-focus: rgba(200, 130, 60, 0.3);
  --text: #f2e6d8;
  --text-muted: #a89480;
  --accent: #e8924a;
  --accent2: #d4745c;
  --accent3: #c9a87c;
}

:global(html[data-theme='cosmic']) .landing-shell {
  --bg-deep: #0d0a1a;
  --bg-surface: #161028;
  --bg-card: rgba(22, 16, 42, 0.72);
  --bg-hover: rgba(255, 255, 255, 0.04);
  --border: rgba(140, 120, 200, 0.14);
  --border-focus: rgba(160, 120, 240, 0.3);
  --text: #e4def8;
  --text-muted: #8b7cb8;
  --accent: #a78bfa;
  --accent2: #f472b6;
  --accent3: #818cf8;
}

:global(html[data-theme='minimal']) .landing-shell {
  --bg-deep: #f0f2f5;
  --bg-surface: #ffffff;
  --bg-card: rgba(255, 255, 255, 0.9);
  --bg-hover: rgba(0, 0, 0, 0.04);
  --border: rgba(0, 0, 0, 0.08);
  --border-focus: rgba(32, 128, 240, 0.28);
  --text: #1a1a2e;
  --text-muted: #6b7280;
  --accent: #2563eb;
  --accent2: #f97316;
  --accent3: #0ea5e9;
  --shadow: 0 12px 40px rgba(0, 0, 0, 0.08);
  --shadow-sm: 0 4px 16px rgba(0, 0, 0, 0.05);
}

:global(html[data-theme='forest']) .landing-shell {
  --bg-deep: #0a1a10;
  --bg-surface: #0f2218;
  --bg-card: rgba(18, 32, 22, 0.72);
  --bg-hover: rgba(255, 255, 255, 0.04);
  --border: rgba(80, 160, 110, 0.14);
  --border-focus: rgba(72, 200, 132, 0.3);
  --text: #ddf0e4;
  --text-muted: #7aaa8e;
  --accent: #48c884;
  --accent2: #e8b84b;
  --accent3: #5eb8e0;
}

#mouse-glow,
#particles-container {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.glow-layer,
.grid-layer {
  position: absolute;
  inset: 0;
}

.grid-layer {
  background-image:
    linear-gradient(rgba(129, 160, 204, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(129, 160, 204, 0.05) 1px, transparent 1px);
  background-size: 32px 32px;
  mask-image: radial-gradient(circle at var(--mx, 50%) var(--my, 50%), rgba(0, 0, 0, 0.5) 0%, transparent 55%);
  -webkit-mask-image: radial-gradient(circle at var(--mx, 50%) var(--my, 50%), rgba(0, 0, 0, 0.5) 0%, transparent 55%);
}

.particle {
  position: fixed;
  border-radius: 999px;
  opacity: 0.35;
  animation: float-up linear infinite;
}

.nav-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 50;
  padding: 14px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  backdrop-filter: blur(20px) saturate(140%);
  background: color-mix(in srgb, var(--bg-deep) 72%, transparent);
  border-bottom: 1px solid var(--border);
}

.brand-button,
.nav-link-button,
.footer-link {
  font: inherit;
  border: 0;
  background: none;
  cursor: pointer;
}

.nav-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--text);
  font-weight: 700;
  font-size: 17px;
  letter-spacing: 0.03em;
}

.brand-dot {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--accent), var(--accent3));
  box-shadow: 0 4px 14px color-mix(in srgb, var(--accent) 40%, transparent);
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.nav-links a,
.nav-link-button {
  color: var(--text-muted);
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 999px;
  transition: all var(--transition);
}

.nav-links a:hover,
.nav-link-button:hover {
  color: var(--text);
  background: var(--bg-hover);
}

.nav-cta {
  background: linear-gradient(135deg, var(--accent), var(--accent3));
  color: #fff;
  font-weight: 700;
  box-shadow: 0 4px 18px color-mix(in srgb, var(--accent) 30%, transparent);
}

.nav-cta:hover {
  color: #fff;
  transform: translateY(-2px);
}

.nav-ghost {
  border: 1px solid var(--border);
}

.profile-menu-wrapper {
  position: relative;
}

.profile-trigger {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-height: 44px;
  padding: 6px 8px 6px 16px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-surface) 82%, transparent);
  color: var(--text);
  cursor: pointer;
  transition: all var(--transition);
}

.profile-trigger:hover,
.profile-trigger.active {
  border-color: var(--border-focus);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--accent) 16%, transparent);
}

.profile-trigger-text {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  text-align: right;
}

.profile-trigger-text strong {
  font-size: 13px;
  line-height: 1.1;
}

.profile-trigger-text small {
  font-size: 11px;
  color: var(--text-muted);
}

.profile-avatar,
.profile-menu-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent3));
  box-shadow: 0 8px 24px color-mix(in srgb, var(--accent) 24%, transparent);
}

.profile-avatar {
  width: 32px;
  height: 32px;
  font-size: 14px;
}

.profile-menu-panel {
  position: absolute;
  top: calc(100% + 12px);
  right: 0;
  width: min(320px, calc(100vw - 32px));
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 16%, transparent), transparent 38%),
    color-mix(in srgb, var(--bg-surface) 94%, transparent);
  box-shadow: 0 26px 60px rgba(0, 0, 0, 0.34);
  backdrop-filter: blur(20px) saturate(140%);
}

.profile-menu-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 8px 14px;
}

.profile-menu-avatar {
  width: 54px;
  height: 54px;
  font-size: 22px;
  flex-shrink: 0;
}

.profile-menu-meta {
  display: grid;
  gap: 4px;
}

.profile-menu-meta strong {
  font-size: 18px;
  line-height: 1.2;
  color: var(--text);
}

.profile-menu-meta span {
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
}

.profile-menu-meta small {
  color: var(--text-muted);
  line-height: 1.5;
}

.profile-menu-actions {
  display: grid;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.profile-menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 0;
  border-radius: 16px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: all var(--transition);
}

.profile-menu-item:hover {
  background: var(--bg-hover);
  transform: translateX(2px);
}

.profile-menu-item.danger {
  color: color-mix(in srgb, #ff8a72 86%, var(--text));
}

.profile-menu-icon {
  width: 22px;
  color: var(--text-muted);
  text-align: center;
  font-size: 15px;
}

.profile-menu-enter-active,
.profile-menu-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.profile-menu-enter-from,
.profile-menu-leave-to {
  opacity: 0;
  transform: translateY(-10px) scale(0.98);
}

.theme-dots {
  display: flex;
  gap: 6px;
  margin-left: 10px;
}

.theme-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid transparent;
  transition: all var(--transition);
}

.theme-dot:hover {
  transform: scale(1.16);
}

.theme-dot.active {
  border-color: var(--text);
  box-shadow: 0 0 8px currentColor;
}

.hero-section,
.section,
.cta-section,
.footer {
  position: relative;
  z-index: 1;
}

.hero-section {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 120px 24px 80px;
}

.hero-eyebrow {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--accent);
}

.hero-eyebrow::before,
.hero-eyebrow::after {
  content: '';
  width: 36px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent));
}

.hero-eyebrow::after {
  background: linear-gradient(90deg, var(--accent), transparent);
}

.hero-title {
  margin: 0 0 20px;
  font-size: clamp(38px, 7vw, 80px);
  font-weight: 850;
  line-height: 1.18;
  letter-spacing: 0.04em;
  max-width: 10em;
  background: linear-gradient(160deg, var(--text) 20%, var(--accent) 45%, var(--accent3) 65%, var(--text) 85%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(0 0 32px color-mix(in srgb, var(--accent) 35%, transparent));
  animation: title-shimmer 6s ease-in-out infinite;
}

.hero-subtitle,
.cta-desc {
  max-width: 42em;
  font-size: clamp(16px, 2.2vw, 20px);
  line-height: 1.8;
  color: var(--text-muted);
}

.hero-buttons {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 36px;
}

.btn-hero-primary,
.btn-hero-secondary,
.card-link {
  border: 0;
  cursor: pointer;
  transition: all var(--transition);
}

.btn-hero-primary {
  padding: 14px 36px;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--accent), var(--accent3));
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  box-shadow: 0 8px 32px color-mix(in srgb, var(--accent) 35%, transparent);
}

.btn-hero-primary:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 42px color-mix(in srgb, var(--accent) 50%, transparent);
}

.btn-hero-secondary {
  padding: 14px 36px;
  border-radius: 999px;
  background: transparent;
  color: var(--text);
  font-size: 16px;
  font-weight: 600;
  border: 1px solid var(--border);
  backdrop-filter: blur(12px);
}

.btn-hero-secondary:hover {
  border-color: var(--border-focus);
  background: var(--bg-hover);
}

.hero-status {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 28px;
}

.status-chip {
  padding: 10px 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 13px;
}

.scroll-hint {
  position: absolute;
  bottom: 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 0.1em;
  animation: bounce-down 2s ease-in-out infinite;
}

.scroll-hint .line {
  width: 1px;
  height: 36px;
  background: linear-gradient(180deg, var(--accent), transparent);
}

.section {
  padding: 80px 24px;
}

.section-inner {
  max-width: 1120px;
  margin: 0 auto;
}

.section-label {
  margin-bottom: 10px;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
}

.section-title,
.cta-title {
  margin: 0 0 12px;
  font-size: clamp(26px, 4vw, 42px);
  font-weight: 750;
  line-height: 1.2;
}

.section-desc {
  max-width: 48em;
  margin-bottom: 40px;
  color: var(--text-muted);
  font-size: 15px;
  line-height: 1.7;
}

.feature-toolbar {
  display: grid;
  gap: 18px;
  margin-bottom: 28px;
}

.feature-nav-bar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.feature-nav-chip,
.feature-page-button {
  font: inherit;
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg-card) 88%, transparent);
  color: var(--text);
  cursor: pointer;
  transition: all var(--transition);
}

.feature-nav-chip {
  display: grid;
  gap: 6px;
  padding: 16px 18px;
  border-radius: 18px;
  text-align: left;
}

.feature-nav-chip strong {
  font-size: 15px;
}

.feature-nav-chip span {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.feature-nav-chip:hover,
.feature-nav-chip.active {
  border-color: var(--border-focus);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.feature-pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.feature-pagination-summary {
  color: var(--text-muted);
  font-size: 13px;
}

.feature-pagination-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.feature-page-button {
  min-width: 42px;
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
}

.feature-page-button:hover:not(:disabled),
.feature-page-button.active {
  border-color: var(--border-focus);
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
}

.feature-page-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}

.feature-card,
.ai-highlight-card,
.stat-item {
  border: 1px solid var(--border);
  backdrop-filter: blur(14px);
  box-shadow: var(--shadow-sm);
}

.feature-card {
  position: relative;
  overflow: hidden;
  display: grid;
  gap: 12px;
  padding: 28px;
  border-radius: var(--radius-lg);
  background: var(--bg-card);
}

.clickable-feature-card {
  cursor: pointer;
}

.clickable-feature-card:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 75%, white 10%);
  outline-offset: 3px;
}

.feature-card:hover {
  transform: translateY(-4px);
  border-color: var(--border-focus);
  box-shadow: var(--shadow);
}

.feature-card::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--accent), var(--accent3));
  opacity: 0;
  transition: opacity var(--transition);
}

.feature-card:hover::after {
  opacity: 1;
}

.feature-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}

.feature-card h3,
.ai-highlight-card h3 {
  margin: 0;
  font-size: 18px;
}

.feature-card p,
.ai-highlight-card p {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.7;
  font-size: 14px;
}

.card-actions {
  margin-top: 8px;
}

.card-link {
  padding: 10px 18px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
}

.card-link:hover {
  transform: translateY(-2px);
  background: color-mix(in srgb, var(--accent) 26%, transparent);
}

.ai-highlight-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.ai-highlight-card {
  padding: 32px;
  border-radius: var(--radius-lg);
  background: var(--bg-card);
}

.ai-highlight-card:hover {
  border-color: var(--border-focus);
  box-shadow: var(--shadow);
}

.ai-icon-lg {
  margin-bottom: 16px;
  font-size: 40px;
}

.ai-tag-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.ai-tag {
  padding: 5px 14px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--accent);
}

.stats-bar {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 20px;
  margin-top: 50px;
}

.stat-item {
  padding: 32px 16px;
  border-radius: var(--radius-lg);
  text-align: center;
  background: var(--bg-card);
}

.stat-num {
  font-size: 42px;
  font-weight: 800;
  background: linear-gradient(135deg, var(--accent), var(--accent3));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.stat-label {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-muted);
}

.cta-section {
  text-align: center;
  padding: 100px 24px;
}

.footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  border-top: 1px solid var(--border);
  padding: 40px 28px;
  color: var(--text-muted);
  font-size: 13px;
}

.footer-links {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.footer a,
.footer-link {
  color: var(--text-muted);
  text-decoration: none;
}

.footer a:hover,
.footer-link:hover {
  color: var(--accent);
}

@keyframes title-shimmer {
  0%,
  100% {
    background-position: 0% center;
  }

  50% {
    background-position: 100% center;
  }
}

@keyframes bounce-down {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(8px);
  }
}

@keyframes float-up {
  0% {
    transform: translateY(0) translateX(0) scale(1);
    opacity: 0;
  }

  10% {
    opacity: 0.35;
  }

  90% {
    opacity: 0.35;
  }

  100% {
    transform: translateY(-105vh) translateX(40px) scale(0.3);
    opacity: 0;
  }
}

@media (max-width: 960px) {
  .feature-nav-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .feature-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ai-highlight-grid {
    grid-template-columns: 1fr;
  }

  .stats-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .nav-bar {
    padding: 12px 16px;
    align-items: flex-start;
  }

  .nav-links {
    gap: 8px;
  }

  .nav-links a:not(.nav-cta) {
    display: none;
  }

  .profile-trigger-text {
    display: none;
  }

  .profile-trigger {
    padding-inline: 6px;
  }

  .profile-menu-panel {
    right: 0;
  }

  .feature-nav-bar {
    grid-template-columns: 1fr;
  }

  .feature-pagination-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .hero-section {
    padding: 116px 18px 72px;
  }

  .section,
  .cta-section {
    padding-inline: 18px;
  }

  .feature-grid,
  .stats-bar {
    grid-template-columns: 1fr;
  }
}
</style>
