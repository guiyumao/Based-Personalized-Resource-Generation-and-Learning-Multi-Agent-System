import { defineStore } from 'pinia'

type AuthUser = {
  userId: number
  username: string
  role: 'student' | 'teacher' | 'admin'
}

type PersistedAuth = {
  token: string
  user: AuthUser
}

const STORAGE_KEY = 'learning-system-auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '' as string,
    user: null as AuthUser | null,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    homeRoute: (state) => {
      if (state.user?.role === 'teacher') {
        return '/teacher'
      }
      if (state.user?.role === 'admin') {
        return '/admin'
      }
      return '/student'
    },
  },
  actions: {
    restore() {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) {
        return
      }
      try {
        const parsed = JSON.parse(raw) as PersistedAuth
        this.token = parsed.token
        this.user = parsed.user
      } catch {
        this.clear()
      }
    },
    setAuth(payload: PersistedAuth) {
      this.token = payload.token
      this.user = payload.user
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    },
    clear() {
      this.token = ''
      this.user = null
      localStorage.removeItem(STORAGE_KEY)
    },
  },
})
