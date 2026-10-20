import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { evaluationApi } from '../api/http'

// A mounted tab gets a fresh identity (sessionStorage can be cloned by a new tab).
// The server arbitrates ownership across tabs/devices; client locks are insufficient.
export function useStudyActivity() {
  const route = useRoute()
  const auth = useAuthStore()
  const tabId = crypto.randomUUID()
  const learningPages = new Set(['courseware', 'exercise', 'learning-path', 'resources', 'study-tools', 'knowledge-graph', 'qa'])
  let lastInput = 0
  let sequence = 0
  let running = false
  let unavailable = false
  let wasActive = false
  let timer: ReturnType<typeof setInterval> | undefined

  async function heartbeat() {
    if (running || unavailable || auth.user?.role !== 'student') return
    const rawPage = route.path.split('/')[2] ?? ''
    const page = rawPage === 'workspace' ? 'learning-path' : rawPage
    const active = learningPages.has(page) && document.visibilityState === 'visible'
      && document.hasFocus() && Date.now() - lastInput < 60_000
    if (!active && !wasActive) return
    running = true
    wasActive = active
    try {
      await evaluationApi.post('/evaluation/activity/heartbeat', {
        tab_id: tabId, sequence: ++sequence, active,
        page: learningPages.has(page) ? page : 'learning-path',
      }, { timeout: 10_000 })
    } catch (error: any) {
      // An old backend/schema must not cause an endless request storm.
      if ([401, 403, 404, 503].includes(error?.response?.status)) unavailable = true
    } finally { running = false }
  }
  const input = (event: Event) => {
    if (!event.isTrusted) return
    const idle = Date.now() - lastInput >= 60_000
    lastInput = Date.now()
    if (idle) void heartbeat()
  }
  const visibility = () => { void heartbeat() }
  const events = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const
  onMounted(() => {
    for (const name of events) window.addEventListener(name, input, { passive: true })
    document.addEventListener('visibilitychange', visibility)
    window.addEventListener('blur', visibility)
    timer = setInterval(() => void heartbeat(), 15_000)
  })
  onUnmounted(() => {
    for (const name of events) window.removeEventListener(name, input)
    document.removeEventListener('visibilitychange', visibility)
    window.removeEventListener('blur', visibility)
    clearInterval(timer)
  })
}
