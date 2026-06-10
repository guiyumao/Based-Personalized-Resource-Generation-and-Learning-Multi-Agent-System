<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useTheme, type ThemeName } from '../composables/useTheme'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { currentTheme, setTheme } = useTheme()

const showThemePicker = ref(false)
const isStudent = computed(() => authStore.user?.role === 'student')

const pageLabel = computed(() => {
  const labels: Record<string, string> = {
    dashboard: '学习概览',
    'learning-path': '学习路径',
    courseware: '课件中心',
    exercise: '练习测评',
    mistakes: '错题本',
    'knowledge-graph': '知识图谱',
    report: '学习报告',
    qa: '智能问答',
    resources: '学习资源',
    'student-resources': '学习资源',
    'student-dashboard': '学习概览',
    'student-learning-path': '学习路径',
    'student-courseware': '课件中心',
    'student-knowledge-base': '大学知识库',
    'student-exercise': '练习测评',
    'student-mistakes': '错题本',
    'student-knowledge-graph': '知识图谱',
    'student-report': '学习报告',
    'student-qa': '智能问答',
    'teacher-overview': '教师总览',
    'teacher-classes': '班级管理',
    'teacher-knowledge-base': '课程知识库',
    'teacher-scopes': '学习范围',
    'teacher-students': '学生洞察',
    'teacher-analytics': '教学分析',
    'teacher-homework': '作业管理',
    admin: '管理控制台',
  }
  const name = (route.name as string) || ''
  return labels[name] || name
})

const themes: { key: ThemeName; name: string; color: string }[] = [
  { key: null, name: '默认', color: '#b5542f' },
  { key: 'ocean', name: '深海科技', color: '#00c8aa' },
  { key: 'warm', name: '暖金学术', color: '#e8924a' },
  { key: 'cosmic', name: '暗夜紫穹', color: '#a78bfa' },
  { key: 'minimal', name: '极简晨光', color: '#2563eb' },
  { key: 'forest', name: '森林绿洲', color: '#48c884' },
]

function handleThemeClick(theme: ThemeName) {
  setTheme(theme)
  showThemePicker.value = false
}

function handleLogout() {
  authStore.clear()
  router.push('/login')
}
</script>

<template>
  <header class="app-topbar">
    <div class="topbar-left">
      <span class="breadcrumb-text">
        工作台
        <template v-if="pageLabel"> / <strong>{{ pageLabel }}</strong></template>
      </span>
    </div>

    <div class="topbar-right">
      <button
        v-if="isStudent"
        class="topbar-btn"
        title="查看/重建学习画像"
        style="font-size:14px"
        @click="$router.push('/profile-setup')"
      >
        🧠
      </button>

      <div class="theme-switcher-wrapper">
        <button class="topbar-btn" title="切换主题" @click="showThemePicker = !showThemePicker">
          🎨
        </button>
        <div v-if="showThemePicker" class="theme-dropdown" @mouseleave="showThemePicker = false">
          <button
            v-for="t in themes"
            :key="t.name"
            class="theme-option-btn"
            :class="{ active: currentTheme === t.key }"
            @click="handleThemeClick(t.key)"
          >
            <span class="theme-dot" :style="{ background: t.color }"></span>
            <span>{{ t.name }}</span>
          </button>
        </div>
      </div>

      <button class="topbar-btn" title="通知">
        🔔
      </button>

      <div class="user-info">
        <span class="user-name">{{ authStore.user?.username ?? '用户' }}</span>
        <span class="user-role-tag">{{ authStore.user?.role ?? '' }}</span>
      </div>

      <button class="topbar-btn logout-btn" title="退出登录" @click="handleLogout">
        ⏻
      </button>
    </div>
  </header>
</template>

<style scoped>
.app-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 28px;
  border-bottom: 1px solid var(--line);
  background: var(--panel-strong);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  z-index: 5;
  min-height: 60px;
}

.breadcrumb-text {
  font-size: 14px;
  color: var(--muted);
}

.breadcrumb-text strong {
  color: var(--accent);
  font-weight: 650;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.topbar-btn {
  width: 38px; height: 38px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--panel);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
  transition: all 0.2s ease;
  position: relative;
}

.topbar-btn:hover {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  border-color: color-mix(in srgb, var(--accent) 30%, transparent);
}

.logout-btn { font-size: 14px; }

.theme-switcher-wrapper { position: relative; }

.theme-dropdown {
  position: absolute;
  top: 46px; right: 0;
  background: var(--panel-strong);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 6px;
  min-width: 160px;
  box-shadow: var(--shadow);
  z-index: 100;
  display: flex; flex-direction: column; gap: 2px;
}

.theme-option-btn {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 14px; border-radius: 10px;
  border: none; background: none;
  cursor: pointer; color: var(--text);
  font-size: 13px; font-family: inherit; font-weight: 500;
  transition: all 0.15s ease;
  text-align: left; width: 100%;
}

.theme-option-btn:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }

.theme-option-btn.active {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent);
}

.theme-dot {
  width: 14px; height: 14px; border-radius: 50%;
  flex-shrink: 0;
}

.user-info {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; border-radius: 10px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.user-name { font-size: 13px; font-weight: 600; color: var(--text); }

.user-role-tag {
  font-size: 10px; letter-spacing: 0.06em;
  padding: 2px 8px; border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent); font-weight: 600;
  text-transform: uppercase;
}
</style>
