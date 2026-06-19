import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

import AdminView from './views/AdminView.vue'
import CoursewareView from './views/CoursewareView.vue'
import LandingView from './views/LandingView.vue'
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
      component: LandingView,
      meta: {
        requiresAuth: false,
      },
    },
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

    // ── 画像构建页（需要登录，登录和首页之间）──
    {
      path: '/profile-setup',
      name: 'profile-setup',
      component: () => import('./views/ProfileSetupView.vue'),
      meta: { requiresAuth: true, isProfileSetup: true },
    },

    // ── 学生工作台（需要登录）──
    {
      path: '/student',
      meta: { requiresAuth: true, roles: ['student'] },
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
          path: 'knowledge-base',
          name: 'student-knowledge-base',
          redirect: '/student/resources',
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
        {
          path: 'profile-analysis',
          name: 'student-profile-analysis',
          component: () => import('./views/student/ProfileAnalysisView.vue'),
        },
        // Legacy StudentView removed — all features migrated to individual sub-views
      ],
    },

    // ── 教师工作台 ──
    {
      path: '/teacher',
      meta: { requiresAuth: true, roles: ['teacher'] },
      children: [
        { path: '', redirect: '/teacher/overview' },
        {
          path: 'overview',
          name: 'teacher-overview',
          component: TeacherView,
        },
        {
          path: 'classes',
          name: 'teacher-classes',
          component: TeacherView,
        },
        {
          path: 'knowledge-base',
          name: 'teacher-knowledge-base',
          component: TeacherView,
        },
        {
          path: 'scopes',
          name: 'teacher-scopes',
          component: TeacherView,
        },
        {
          path: 'students',
          name: 'teacher-students',
          component: TeacherView,
        },
        {
          path: 'analytics',
          name: 'teacher-analytics',
          component: TeacherView,
        },
        {
          path: 'homework',
          name: 'teacher-homework',
          component: TeacherView,
        },
      ],
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

  if (authStore.user?.role === 'teacher' && to.path.startsWith('/student')) {
    return { name: 'teacher-overview' }
  }

  if (authStore.user?.role === 'student' && to.path.startsWith('/teacher')) {
    return { name: 'student-dashboard' }
  }

  // Check role requirement
  const allowedRoles = to.meta.roles as string[] | undefined
  if (allowedRoles && authStore.user && !allowedRoles.includes(authStore.user.role)) {
    return authStore.homeRoute
  }

  return true
})

export default router
