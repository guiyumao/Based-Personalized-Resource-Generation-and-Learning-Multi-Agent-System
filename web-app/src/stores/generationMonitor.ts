import { reactive } from 'vue'
import { agentApi } from '../api/http'

export type GenerationTask = {
  key: string; id: number; source: string; status: string; label: string; topic: string; current_step: string
  created_at?: string; started_at?: string | null; task_type?: string; route?: string
  learning_context_id?: string | null; plan_id?: number | null; module_id?: string | null; task_key?: string | null
  progress?: { completed: number; total: number; unit: string } | null
}
export const generationMonitor = reactive({ userId: 0, items: [] as GenerationTask[], error: '', loading: false })
let epoch = 0
let timer: ReturnType<typeof setTimeout> | undefined
let running = false

export function stopGenerationMonitor() {
  epoch++; clearTimeout(timer); timer = undefined; running = false
  generationMonitor.userId = 0; generationMonitor.items = []; generationMonitor.error = ''; generationMonitor.loading = false
}
export function startGenerationMonitor(userId: number) {
  stopGenerationMonitor()
  generationMonitor.userId = userId; running = true
  void refreshGenerationMonitor()
}
export async function refreshGenerationMonitor() {
  if (!running || generationMonitor.loading) return
  clearTimeout(timer)
  const requestEpoch = epoch
  generationMonitor.loading = true
  try {
    const { data } = await agentApi.get('/generation/tasks')
    if (epoch !== requestEpoch) return
    generationMonitor.items = Array.isArray(data.items) ? data.items : []
    generationMonitor.error = ''
  } catch {
    if (epoch === requestEpoch) generationMonitor.error = '任务进度暂时无法同步，正在重试；上次状态可能已变化。'
  } finally {
    if (epoch === requestEpoch) {
      generationMonitor.loading = false
      timer = setTimeout(() => void refreshGenerationMonitor(), 3000)
    }
  }
}
