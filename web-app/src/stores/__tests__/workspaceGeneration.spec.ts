import { afterEach, beforeEach, expect, it, vi } from 'vitest'
vi.mock('../../api/http', () => ({ agentApi: { get: vi.fn(), post: vi.fn() } }))
const identity = vi.hoisted(() => ({ user: { userId: 104 } }))
vi.mock('../auth', () => ({ useAuthStore: () => identity }))
import { agentApi } from '../../api/http'
import { workspaceJobs, workspaceJobKey, startWorkspaceJob, resumeWorkspaceJob, resetWorkspaceJobs } from '../workspaceGeneration'
const key = workspaceJobKey(104, 'ctx')
beforeEach(() => { vi.useFakeTimers(); localStorage.clear(); sessionStorage.clear(); vi.resetAllMocks(); identity.user.userId = 104 })
afterEach(() => { resetWorkspaceJobs(); vi.useRealTimers() })
it('离开后提交响应仍保存，独立轮询至完成，保留结果供返回时显示', async () => {
  let reply!: (value: any) => void
  vi.mocked(agentApi.post).mockReturnValue(new Promise(resolve => { reply = resolve }))
  const pending = startWorkspaceJob(104, 'ctx', { action: 'courseware' })
  await startWorkspaceJob(104, 'ctx', {})
  expect(agentApi.post).toHaveBeenCalledTimes(1)
  reply({ data: { task: { id: 16, status: 'PENDING' } } }); await pending
  vi.mocked(agentApi.get).mockResolvedValue({ data: { id: 16, status: 'SUCCEEDED', result: { cards: [{ learning_context_id: 'linked' }] } } })
  await vi.advanceTimersByTimeAsync(2000)
  expect(workspaceJobs[key]?.job?.result?.cards?.[0]?.learning_context_id).toBe('linked')
  expect(localStorage.getItem(key)).toBe('16')
})
it('刷新从持久任务号续接，瞬时错误不会结束轮询，超时为终态', async () => {
  localStorage.setItem(key, '16')
  vi.mocked(agentApi.get).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: { id: 16, status: 'TIMED_OUT' } })
  await resumeWorkspaceJob(104, 'ctx')
  expect(workspaceJobs[key]?.error).toBe('offline')
  await vi.advanceTimersByTimeAsync(2000)
  expect(workspaceJobs[key]?.job?.status).toBe('TIMED_OUT')
  await vi.advanceTimersByTimeAsync(6000)
  expect(agentApi.get).toHaveBeenCalledTimes(2)
  expect(agentApi.post).not.toHaveBeenCalled()
})
it('没有浏览器记录也从服务端找回，切换账号停止轮询', async () => {
  vi.mocked(agentApi.get).mockResolvedValueOnce({ data: [{ id: 16, status: 'RUNNING' }] }).mockResolvedValueOnce({ data: { id: 16, status: 'RUNNING' } })
  await resumeWorkspaceJob(104, 'ctx')
  expect(agentApi.get).toHaveBeenCalledWith('/assistant/tasks', { params: { learning_context_id: 'ctx', limit: 1 } })
  identity.user.userId = 6
  await vi.advanceTimersByTimeAsync(4000)
  expect(agentApi.get).toHaveBeenCalledTimes(2)
  await resumeWorkspaceJob(104, 'ctx')
  expect(agentApi.get).toHaveBeenCalledTimes(2)
})
it('提交回执超时后重新进入仍从服务端找回，不重发生成', async () => {
  vi.mocked(agentApi.post).mockRejectedValueOnce(new Error('timeout'))
  await expect(startWorkspaceJob(104, 'ctx', {})).rejects.toThrow('timeout')
  vi.mocked(agentApi.get).mockResolvedValueOnce({ data: [{ id: 16, status: 'SUCCEEDED' }] })
  await resumeWorkspaceJob(104, 'ctx')
  expect(workspaceJobs[key]?.job?.status).toBe('SUCCEEDED')
  expect(agentApi.post).toHaveBeenCalledTimes(1)
})
