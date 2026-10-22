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
const TAB_STORAGE_KEY = 'learning-system-tab-auth'

function parseAuth(raw: string): PersistedAuth | null {
  const value = JSON.parse(raw)
  if (value === null) return null // Explicit logout for this tab.
  if (typeof value?.token !== 'string' || !value.token ||
      !Number.isInteger(value?.user?.userId) || typeof value.user.username !== 'string' ||
      !['student', 'teacher', 'admin'].includes(value.user.role)) throw new Error('Invalid auth cache')
  return value as PersistedAuth
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '' as string,
    user: null as AuthUser | null,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    homeRoute: (state) => {
      if (state.user?.role === 'teacher') {
        return '/teacher/overview'
      }
      if (state.user?.role === 'admin') {
        return '/admin'
      }
      return '/student'
    },
  },
  actions: {
    restore() {
      // Each tab keeps its own login. localStorage is only a default for a new
      // tab, never the source of credentials for an already-open workspace.
      const raw = sessionStorage.getItem(TAB_STORAGE_KEY) ?? localStorage.getItem(STORAGE_KEY)
      if (!raw) {
        return
      }
      try {
        const parsed = parseAuth(raw)
        if (!parsed) { this.token = ''; this.user = null; return }
        this.token = parsed.token
        this.user = parsed.user
        sessionStorage.setItem(TAB_STORAGE_KEY, JSON.stringify(parsed))
      } catch {
        this.clear()
      }
    },
    setAuth(payload: PersistedAuth) {
      this.token = payload.token
      this.user = payload.user
      sessionStorage.setItem(TAB_STORAGE_KEY, JSON.stringify(payload))
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    },
    verifyIdentity(token: string, user: AuthUser) {
      if (this.token !== token) return
      this.user = user
      const payload = { token, user }
      sessionStorage.setItem(TAB_STORAGE_KEY, JSON.stringify(payload))
      // Revalidation must not change the default login belonging to another tab.
      try {
        if (JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')?.token === token)
          localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
      } catch { /* Leave a different or malformed shared default alone. */ }
    },
    clear() {
      const previousToken = this.token
      this.token = ''
      this.user = null
      sessionStorage.setItem(TAB_STORAGE_KEY, 'null')
      try {
        if (JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')?.token === previousToken)
          localStorage.removeItem(STORAGE_KEY)
      } catch { /* Clearing this tab must not erase another account. */ }
    },
  },
})
