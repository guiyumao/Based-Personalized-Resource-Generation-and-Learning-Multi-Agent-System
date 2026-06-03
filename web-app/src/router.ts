import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

import AdminView from './views/AdminView.vue'
import CoursewareView from './views/CoursewareView.vue'
import LoginView from './views/LoginView.vue'
import MistakeNotebookView from './views/MistakeNotebookView.vue'
import RegisterView from './views/RegisterView.vue'
import TeacherView from './views/TeacherView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // ── 首页（公开）──
    {
      path: '/',
      name: 'landing',
      component: () => import('./views/LandingView.vue'),
      meta: { requiresAuth: false },
    },

    // ── 画像构建页（需要登录，登录和首页之间）──
    {
      path: '/profile-setup',
      name: 'profile-setup',
      component: () => import('./views/ProfileSetupView.vue'),
      meta: { requiresAuth: true, isProfileSetup: true },
    },

    // ── 认证页（公开）──
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { requiresAuth: false },
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { requiresAuth: false },
    },

    // ── 学生工作台（需要登录）──
    {
      path: '/student',
      meta: { requiresAuth: true, roles: ['student', 'teacher', 'admin'] },
      children: [
        { path: '', redirect: '/student/dashboard' },
        {
          path: 'dashboard',
          name: 'student-dashboard',
          component: () => import('./views/student/DashboardView.vue'),
        },
        {
          path: 'learning-path',
          name: 'student-learning-path',
          component: () => import('./views/student/LearningPathView.vue'),
        },
        {
          path: 'courseware',
          name: 'student-courseware',
          component: CoursewareView,
        },
        {
          path: 'exercise',
          name: 'student-exercise',
          component: () => import('./views/student/ExerciseView.vue'),
        },
        {
          path: 'mistakes',
          name: 'student-mistakes',
          component: MistakeNotebookView,
        },
        {
          path: 'knowledge-graph',
          name: 'student-knowledge-graph',
          component: () => import('./views/student/KnowledgeGraphView.vue'),
        },
        {
          path: 'report',
          name: 'student-report',
          component: () => import('./views/student/ReportView.vue'),
        },
        {
          path: 'qa',
          name: 'student-qa',
          component: () => import('./views/student/QaView.vue'),
        },
        {
          path: 'resources',
          name: 'student-resources',
          component: () => import('./views/student/ResourceView.vue'),
        },
        // Legacy StudentView removed — all features migrated to individual sub-views
      ],
    },

    // ── 教师工作台 ──
    {
      path: '/teacher',
      name: 'teacher',
      component: TeacherView,
      meta: { requiresAuth: true, roles: ['teacher'] },
    },

    // ── 管理控制台 ──
    {
      path: '/admin',
      name: 'admin',
      component: AdminView,
      meta: { requiresAuth: true, roles: ['admin'] },
    },
  ],
})

router.beforeEach((to) => {
  const authStore = useAuthStore()

  // '/' is the public landing page — always allow
  if (to.path === '/') {
    return true
  }

  // If authenticated and trying to access login/register, redirect to home
  if (authStore.isAuthenticated && (to.path === '/login' || to.path === '/register')) {
    return authStore.homeRoute
  }

  // Check auth requirement
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: 'login' }
  }

  // Check role requirement
  const allowedRoles = to.meta.roles as string[] | undefined
  if (allowedRoles && authStore.user && !allowedRoles.includes(authStore.user.role)) {
    return authStore.homeRoute
  }

  return true
})

export default router
