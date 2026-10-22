import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../auth'

const key = 'learning-system-auth', tabKey = 'learning-system-tab-auth'
const student = { token: 'student-token', user: { userId: 6, username: 'student', role: 'student' as const } }
const teacher = { token: 'teacher-token', user: { userId: 98, username: 'teacher111', role: 'teacher' as const } }
let api: typeof import('../../api/http')
beforeAll(async () => {
  for (const service of ['USER','AGENT','RESOURCE','EVALUATION','TEACHER','SYSTEM']) vi.stubEnv(`VITE_${service}_API_BASE_URL`, 'http://localhost')
  api = await import('../../api/http')
})
beforeEach(() => {
  setActivePinia(createPinia()); localStorage.clear(); sessionStorage.clear()
  window.history.replaceState({}, '', '/login')
})
describe('per-tab authenticated identity', () => {
  it('pins a legacy login to this tab and keeps it after another tab logs in', () => {
    localStorage.setItem(key, JSON.stringify(student))
    useAuthStore().restore()
    localStorage.setItem(key, JSON.stringify(teacher))
    setActivePinia(createPinia())
    const restored = useAuthStore(); restored.restore()
    expect(restored.user?.role).toBe('student'); expect(restored.token).toBe(student.token)
    expect(JSON.parse(sessionStorage.getItem(tabKey)!)).toEqual(student)
  })
  it('HTTP uses the same in-memory identity as the page, not another tab storage', async () => {
    useAuthStore().setAuth(student)
    localStorage.setItem(key, JSON.stringify(teacher))
    let sent: unknown
    await api.teacherApi.get('/teacher/students/me/classes', { adapter: async config => {
      sent = config.headers.Authorization
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    } })
    expect(sent).toBe(`Bearer ${student.token}`)
    expect(useAuthStore().user?.role).toBe('student')
  })
  it('logout does not erase a different tab default login or silently relogin here', () => {
    useAuthStore().setAuth(student)
    localStorage.setItem(key, JSON.stringify(teacher))
    useAuthStore().clear()
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual(teacher)
    setActivePinia(createPinia()); useAuthStore().restore()
    expect(useAuthStore().isAuthenticated).toBe(false)
  })
  it('corrupt tab state cannot fall through to another account', () => {
    sessionStorage.setItem(tabKey, '{bad json'); localStorage.setItem(key, JSON.stringify(teacher))
    useAuthStore().restore()
    expect(useAuthStore().isAuthenticated).toBe(false)
  })
  it('replaces stale displayed identity with the server identity for this token', () => {
    useAuthStore().setAuth({ token: teacher.token, user: student.user })
    useAuthStore().verifyIdentity(teacher.token, teacher.user)
    expect(useAuthStore().user).toEqual(teacher.user)
    expect(JSON.parse(sessionStorage.getItem(tabKey)!)).toEqual(teacher)
  })
  it('an old identity response cannot overwrite a newly switched account or another tab default', () => {
    useAuthStore().setAuth(student)
    localStorage.setItem(key, JSON.stringify(teacher))
    useAuthStore().verifyIdentity(student.token, student.user)
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual(teacher)
    useAuthStore().setAuth(teacher)
    useAuthStore().verifyIdentity(student.token, student.user)
    expect(useAuthStore().user).toEqual(teacher.user)
  })
  it('ignores a late 401 for an old login after switching accounts', async () => {
    useAuthStore().setAuth(student)
    await expect(api.teacherApi.get('/teacher/classes', { adapter: async config => {
      useAuthStore().setAuth(teacher)
      throw { config, response: { status: 401 } }
    } })).rejects.toBeDefined()
    expect(useAuthStore().token).toBe(teacher.token)
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual(teacher)
  })
  it('clears an expired current login and its tab cache', async () => {
    useAuthStore().setAuth(student)
    await expect(api.teacherApi.get('/teacher/classes', { adapter: async config => {
      throw { config, response: { status: 401 } }
    } })).rejects.toBeDefined()
    expect(useAuthStore().isAuthenticated).toBe(false)
    setActivePinia(createPinia()); useAuthStore().restore()
    expect(useAuthStore().isAuthenticated).toBe(false)
  })
})
