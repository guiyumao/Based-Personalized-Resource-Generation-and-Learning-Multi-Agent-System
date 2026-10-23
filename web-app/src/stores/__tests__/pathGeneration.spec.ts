import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api', () => ({
  agentApi: { post: vi.fn(), get: vi.fn() },
}))

import { agentApi } from '../../api'
import {
  isPathGenerationBusy,
  pathGenerationState,
  pendingPathTaskKey,
  readPendingPathTask,
  resetPathGeneration,
  resumePathGeneration,
  startPathGeneration,
  type PathGenerationMeta,
} from '../pathGeneration'

const agentPost = vi.mocked(agentApi.post)
const agentGet = vi.mocked(agentApi.get)

const COURSEWARE_KEY = 'student-workspace-courseware'
const EXERCISE_KEY = 'student-workspace-exercise-set'

const meta: PathGenerationMeta = {
  userId: 9,
  subject: '数据结构',
  knowledgePoint: '栈',
  requestedTopic: '栈',
  previousTopic: '队列',
}

function coordinationResult() {
  return {
    status: 'success',
    selected_agents: [],
    route_reason: '',
    outputs: {
      path_planning_agent: {
        status: 'completed',
        learning_path: {
          user_id: 9,
          subject: '数据结构',
          knowledge_point: '栈',
          overview: '掌握栈',
          estimated_days: 3,
          stages: [],
        },
      },
      resource_generation_agent: {
        status: 'completed',
        resource: {
          user_id: 9,
          knowledge_point: '栈',
          resource_type: 'courseware',
          resource_style: 'interactive',
          content: '# 栈\n\n先进后出。',
          variants: [
            {
              variant_id: 'default',
              title: '默认版本',
              summary: '',
              resource_style: 'interactive',
              content: '# 栈\n\n先进后出。',
              is_recommended: true,
            },
          ],
        },
      },
      exercise_generation_agent: {
        status: 'completed',
        exercise_set: { exercise_id: 1, questions: [] },
      },
    },
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  resetPathGeneration()
  window.localStorage.clear()
  window.sessionStorage.clear()
  agentPost.mockReset()
  agentGet.mockReset()
})

afterEach(() => {
  resetPathGeneration()
  vi.useRealTimers()
})

describe('pathGeneration 后台生成', () => {
  it('页面离开后仍完成轮询，并写入课件与练习快照', async () => {
    agentPost.mockResolvedValue({ data: { task_id: 77 } })
    agentGet.mockResolvedValue({ data: { status: 'SUCCEEDED', result: coordinationResult() } })

    await startPathGeneration({}, meta)

    expect(isPathGenerationBusy()).toBe(true)
    expect(readPendingPathTask(9)?.taskId).toBe(77)

    await vi.advanceTimersByTimeAsync(1600)

    expect(pathGenerationState.phase).toBe('succeeded')
    expect(isPathGenerationBusy()).toBe(false)
    expect(readPendingPathTask(9)).toBeNull()
    expect(window.sessionStorage.getItem(COURSEWARE_KEY)).toContain('先进后出')
    expect(window.sessionStorage.getItem(EXERCISE_KEY)).toContain('exerciseSet')
  })

  it('重新进入页面时续接已持久化的任务，不重复提交', async () => {
    window.localStorage.setItem(pendingPathTaskKey(9), JSON.stringify({
      userId: 9,
      taskId: 55,
      subject: '数据结构',
      knowledgePoint: '队列',
      requestedTopic: '队列',
      previousTopic: '队列',
      startedAt: Date.now(),
    }))
    agentGet.mockResolvedValue({ data: { status: 'SUCCEEDED', result: coordinationResult() } })

    await resumePathGeneration(9)

    expect(agentPost).not.toHaveBeenCalled()
    expect(pathGenerationState.taskId).toBe(55)
    expect(isPathGenerationBusy()).toBe(true)

    await vi.advanceTimersByTimeAsync(1600)

    expect(pathGenerationState.phase).toBe('succeeded')
    expect(agentGet).toHaveBeenCalledWith('/agents/coordinate/tasks/55')
  })

  it('超过时限的遗留任务不再续接，直接清理', async () => {
    window.localStorage.setItem(pendingPathTaskKey(9), JSON.stringify({
      userId: 9,
      taskId: 42,
      subject: '数据结构',
      knowledgePoint: '队列',
      requestedTopic: '队列',
      previousTopic: '队列',
      startedAt: Date.now() - 7 * 60 * 60 * 1000,
    }))

    await resumePathGeneration(9)

    expect(agentGet).not.toHaveBeenCalled()
    expect(isPathGenerationBusy()).toBe(false)
    expect(readPendingPathTask(9)).toBeNull()
  })

  it('任务失败时给出原因并清理待续接记录', async () => {
    agentPost.mockResolvedValue({ data: { task_id: 88 } })
    agentGet.mockResolvedValue({
      data: { status: 'FAILED', error_code: 'AI_INFERENCE_TIMEOUT', error_message: '模型调用超时' },
    })

    await startPathGeneration({}, meta)
    await vi.advanceTimersByTimeAsync(1600)

    expect(pathGenerationState.phase).toBe('failed')
    expect(pathGenerationState.error).toContain('模型调用超时')
    expect(readPendingPathTask(9)).toBeNull()
  })

  it('短暂的网络错误不会中断长时间生成', async () => {
    agentPost.mockResolvedValue({ data: { task_id: 99 } })
    agentGet
      .mockRejectedValueOnce(new Error('Network Error'))
      .mockResolvedValue({ data: { status: 'SUCCEEDED', result: coordinationResult() } })

    await startPathGeneration({}, meta)
    await vi.advanceTimersByTimeAsync(1600)
    expect(pathGenerationState.phase).toBe('running')

    await vi.advanceTimersByTimeAsync(1600)
    expect(pathGenerationState.phase).toBe('succeeded')
  })
})
