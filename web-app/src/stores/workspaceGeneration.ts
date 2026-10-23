import { reactive } from 'vue'
import { agentApi } from '../api/http'
import { useAuthStore } from './auth'

export type WorkspaceJob = {
  id: number; status: string; current_step: string; task_type?: string
  created_at?: string; started_at?: string | null
  partial_resource?: { id: number; title: string; content: string; structured_json: string }
  result?: { cards?: { learning_context_id?: string }[]; content?: string; evidence?: {
    knowledge_coverage?: { state: string }
    knowledge_supplementation?: { status: string; candidate_ids: number[]; reused: boolean }
  } }
}
type Entry = { job: WorkspaceJob | null; submitting: boolean; error: string }
export const workspaceJobs = reactive<Record<string, Entry>>({})
const timers = new Map<string, ReturnType<typeof setTimeout>>()
export const workspaceJobKey = (userId: number, contextId: string) => `workspace-job:${userId}:${contextId}`
export const jobFinished = (job: WorkspaceJob) => ['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(job.status)
function active(userId: number) { return useAuthStore().user?.userId === userId }
function describe(reason: any) { return reason?.response?.data?.detail?.message || reason?.response?.data?.detail || reason?.message || '暂时无法读取任务进度，正在重试' }

function schedule(userId: number, contextId: string) {
  const key = workspaceJobKey(userId, contextId)
  clearTimeout(timers.get(key))
  timers.set(key, setTimeout(() => void poll(userId, contextId), 2000))
}
async function poll(userId: number, contextId: string) {
  const key = workspaceJobKey(userId, contextId)
  timers.delete(key)
  const entry = workspaceJobs[key]
  if (!active(userId) || !entry?.job || jobFinished(entry.job)) return
  try {
    const { data } = await agentApi.get(`/assistant/tasks/${entry.job.id}`)
    if (!active(userId) || workspaceJobs[key] !== entry) return
    entry.job = data; entry.error = ''
    if (jobFinished(data)) {
      // Keep the receipt until this workspace is opened and displays the result.
      localStorage.setItem(key, String(data.id))
      return
    }
  } catch (reason: any) {
    if (!active(userId)) return
    entry.error = describe(reason)
    if ([401, 403, 404].includes(reason?.response?.status)) {
      if (reason.response.status === 404) { entry.job = null; localStorage.removeItem(key); sessionStorage.removeItem(`workspace-job:${contextId}`) }
      return
    }
  }
  schedule(userId, contextId)
}

export async function resumeWorkspaceJob(userId: number, contextId: string) {
  if (!active(userId)) return
  const key = workspaceJobKey(userId, contextId)
  const existing = workspaceJobs[key]
  if (existing?.submitting || existing?.job && !jobFinished(existing.job)) {
    if (existing.job && !jobFinished(existing.job) && !timers.has(key)) void poll(userId, contextId)
    return
  }
  workspaceJobs[key] = { job: null, submitting: false, error: '' }
  const entry = workspaceJobs[key]!
  const pending = Number(localStorage.getItem(key) || sessionStorage.getItem(`workspace-job:${contextId}`))
  try {
    // Prefer the newest server task over an old completed browser receipt.
    const { data } = await agentApi.get('/assistant/tasks', { params: { learning_context_id: contextId, limit: 1 } })
    if (!active(userId)) return
    if (data[0]) {
      entry.job = data[0]
      localStorage.setItem(key, String(data[0].id))
      if (!jobFinished(data[0])) await poll(userId, contextId)
    } else if (pending > 0) {
      entry.job = { id: pending, status: 'PENDING', current_step: '恢复任务进度' }
      await poll(userId, contextId)
    }
  } catch (reason) {
    if (!active(userId)) return
    entry.error = describe(reason)
    if (pending > 0) {
      entry.job = { id: pending, status: 'PENDING', current_step: '恢复任务进度' }
      await poll(userId, contextId)
    }
  }
}

export async function startWorkspaceJob(userId: number, contextId: string, payload: Record<string, unknown>) {
  if (!active(userId)) return
  const key = workspaceJobKey(userId, contextId)
  const prior = workspaceJobs[key]
  if (prior?.submitting || prior?.job && !jobFinished(prior.job)) return
  workspaceJobs[key] = { job: null, submitting: true, error: '' }
  const entry = workspaceJobs[key]!
  try {
    const { data } = await agentApi.post('/assistant/chat', payload)
    // Save the receipt even when the initiating component has been unmounted.
    localStorage.setItem(key, String(data.task.id))
    entry.job = data.task
    if (active(userId)) schedule(userId, contextId)
  } catch (reason) { entry.error = describe(reason); throw reason }
  finally { entry.submitting = false }
}

export function resetWorkspaceJobs() {
  timers.forEach(clearTimeout); timers.clear()
  for (const key of Object.keys(workspaceJobs)) delete workspaceJobs[key]
}
