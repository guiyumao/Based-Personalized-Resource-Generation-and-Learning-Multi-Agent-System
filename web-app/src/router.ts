import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

import AdminView from './views/AdminView.vue'
import CoursewareView from './views/CoursewareView.vue'
import LoginView from './views/LoginView.vue'
import MistakeNotebookView from './views/MistakeNotebookView.vue'
import RegisterView from './views/RegisterView.vue'
import StudentView from './views/StudentView.vue'
import TeacherView from './views/TeacherView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: {
        requiresAuth: false,
      },
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: {
        requiresAuth: false,
      },
    },
    {
      path: '/',
      redirect: '/login',
    },
    {
      path: '/student',
      name: 'student',
      component: StudentView,
      meta: {
        requiresAuth: true,
        roles: ['student', 'teacher', 'admin'],
      },
    },
    {
      path: '/student/courseware',
      name: 'student-courseware',
      component: CoursewareView,
      meta: {
        requiresAuth: true,
        roles: ['student', 'teacher', 'admin'],
      },
    },
    {
      path: '/student/mistakes',
      name: 'student-mistakes',
      component: MistakeNotebookView,
      meta: {
        requiresAuth: true,
        roles: ['student', 'teacher', 'admin'],
      },
    },
    {
      path: '/teacher',
      name: 'teacher',
      component: TeacherView,
      meta: {
        requiresAuth: true,
        roles: ['teacher'],
      },
    },
    {
      path: '/admin',
      name: 'admin',
      component: AdminView,
      meta: {
        requiresAuth: true,
        roles: ['admin'],
      },
    },
  ],
})

router.beforeEach((to) => {
  const authStore = useAuthStore()

  if (to.path === '/') {
    return authStore.isAuthenticated ? authStore.homeRoute : '/login'
  }

  if (authStore.isAuthenticated && (to.path === '/login' || to.path === '/register')) {
    return authStore.homeRoute
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: 'login' }
  }

  const allowedRoles = to.meta.roles as string[] | undefined
  if (allowedRoles && authStore.user && !allowedRoles.includes(authStore.user.role)) {
    return authStore.homeRoute
  }
  return true
})

export default router
