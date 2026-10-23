/**
 * Background owner of the async learning-path coordination task.
 *
 * `/agents/coordinate/async` returns a task id immediately and the server worker
 * keeps generating, so the client side must not depend on the LearningPathView
 * component staying mounted. This module is a framework-free singleton: it keeps
 * polling, persists the pending task id so a reload can resume, and writes the
 * finished courseware/exercise artifacts into the student workspace cache even
 * when the learner has already navigated to another page.
 */
import { reactive } from 'vue'
import {
  agentApi,
  type CoordinationResponse,
  type ExerciseGenerationResponse,
  type LearningPathResponse,
  type ResourceResult,
} from '../api'
import {
  clearStudentWorkspaceArtifacts,
  COURSEWARE_STORAGE_KEY,
  EXERCISE_STORAGE_KEY,
  sameWorkspaceTopic,
  writeStudentWorkspaceContext,
} from '../utils/studentWorkspace'

export type PathGenerationPhase = 'idle' | 'queued' | 'running' | 'succeeded' | 'failed'

export type PathGenerationMeta = {
  userId: number
  subject: string
  knowledgePoint: string
  /** Topic the learner typed in the form; compared with `previousTopic`. */
  requestedTopic: string
  /** Topic the workspace showed before this request, used to clear stale artifacts. */
  previousTopic: string
}

export type PathGenerationState = {
  phase: PathGenerationPhase
  taskId: number
  userId: number
  subject: string
  knowledgePoint: string
  error: string
  result: CoordinationResponse | null
  startedAt: number
  /** Increments whenever a result or failure lands so views can react once. */
  revision: number
}

type PendingTask = PathGenerationMeta & { taskId: number; startedAt: number }

type SettledListener = (phase: 'succeeded' | 'failed') => void

const STORAGE_PREFIX = 'student-path-generation-pending'
const POLL_INTERVAL_MS = 1500
const POLL_DEADLINE_MS = 30 * 60 * 1000
const KNOWLEDGE_RETRY_INTERVAL_MS = 3000
const KNOWLEDGE_WAIT_DEADLINE_MS = 10 * 60 * 1000
/** A task record older than this is treated as abandoned instead of resumed. */
const MAX_PENDING_AGE_MS = 6 * 60 * 60 * 1000

export const pathGenerationState = reactive<PathGenerationState>({
  phase: 'idle',
  taskId: 0,
  userId: 0,
  subject: '',
  knowledgePoint: '',
  error: '',
  result: null,
  startedAt: 0,
  revision: 0,
})

let token = 0
let timer: ReturnType<typeof setTimeout> | null = null
let currentMeta: PathGenerationMeta | null = null
const listeners = new Set<SettledListener>()

export function isPathGenerationBusy(): boolean {
  return pathGenerationState.phase === 'queued' || pathGenerationState.phase === 'running'
}

export function onPathGenerationSettled(listener: SettledListener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function pendingPathTaskKey(userId: number): string {
  return `${STORAGE_PREFIX}:${userId}`
}

/**
 * The task id lives in localStorage, not sessionStorage: the server task is
 * durable, so closing the page or the whole browser must not lose the ability
 * to pick the result up later.
 */
export function readPendingPathTask(userId: number): PendingTask | null {
  if (typeof window === 'undefined' || !Number.isFinite(userId) || userId <= 0) {
    return null
  }
  try {
    const raw = window.localStorage.getItem(pendingPathTaskKey(userId))
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as Partial<PendingTask>
    if (parsed.userId !== userId || !Number.isFinite(parsed.taskId) || Number(parsed.taskId) <= 0) {
      return null
    }
    return {
      userId,
      taskId: Number(parsed.taskId),
      subject: typeof parsed.subject === 'string' ? parsed.subject : '',
      knowledgePoint: typeof parsed.knowledgePoint === 'string' ? parsed.knowledgePoint : '',
      requestedTopic: typeof parsed.requestedTopic === 'string' ? parsed.requestedTopic : '',
      previousTopic: typeof parsed.previousTopic === 'string' ? parsed.previousTopic : '',
      startedAt: Number.isFinite(parsed.startedAt) ? Number(parsed.startedAt) : Date.now(),
    }
  } catch {
    return null
  }
}

/**
 * Queue one coordination request and keep it alive across navigation.
 *
 * Resolves as soon as the server accepted the task (or a public-knowledge wait
 * finishes). Task-level failures land in `pathGenerationState`, never as a
 * rejected promise, so an unmounted caller cannot swallow them.
 */
export async function startPathGeneration(
  body: Record<string, unknown>,
  meta: PathGenerationMeta,
): Promise<void> {
  if (isPathGenerationBusy()) {
    return
  }
  token += 1
  const requestToken = token
  currentMeta = meta
  Object.assign(pathGenerationState, {
    phase: 'queued',
    taskId: 0,
    userId: meta.userId,
    subject: meta.subject,
    knowledgePoint: meta.knowledgePoint,
    error: '',
    result: null,
    startedAt: Date.now(),
  })

  try {
    await enqueue(body, meta, requestToken)
  } catch (error) {
    if (requestToken !== token) {
      return
    }
    if (isPublicKnowledgeProcessing(error)) {
      await waitForPublicKnowledge(body, meta, requestToken)
      return
    }
    fail(error, true)
  }
}

/**
 * Pick up a task left behind by an earlier visit (or a page reload) and keep
 * polling it. Does nothing when this module already owns a live task.
 */
export async function resumePathGeneration(userId: number): Promise<void> {
  if (!Number.isFinite(userId) || userId <= 0) {
    return
  }
  if (pathGenerationState.userId && pathGenerationState.userId !== userId) {
    resetPathGeneration()
  }
  if (isPathGenerationBusy()) {
    return
  }
  const pending = readPendingPathTask(userId)
  if (!pending) {
    return
  }
  if (Date.now() - pending.startedAt > MAX_PENDING_AGE_MS) {
    // Do not resurrect an abandoned task (and its stale error) hours later.
    clearPending(userId)
    return
  }

  token += 1
  currentMeta = {
    userId: pending.userId,
    subject: pending.subject,
    knowledgePoint: pending.knowledgePoint,
    requestedTopic: pending.requestedTopic,
    previousTopic: pending.previousTopic,
  }
  Object.assign(pathGenerationState, {
    phase: 'running',
    taskId: pending.taskId,
    userId: pending.userId,
    subject: pending.subject,
    knowledgePoint: pending.knowledgePoint,
    error: '',
    result: null,
    startedAt: pending.startedAt || Date.now(),
  })
  schedulePoll()
}

/** Drop the in-flight task (account switch, explicit cancel or tests). */
export function resetPathGeneration(): void {
  token += 1
  stopPolling()
  const userId = pathGenerationState.userId
  if (userId) {
    clearPending(userId)
  }
  currentMeta = null
  Object.assign(pathGenerationState, {
    phase: 'idle',
    taskId: 0,
    userId: 0,
    subject: '',
    knowledgePoint: '',
    error: '',
    result: null,
    startedAt: 0,
  })
}

async function enqueue(
  body: Record<string, unknown>,
  meta: PathGenerationMeta,
  requestToken: number,
): Promise<void> {
  const { data } = await agentApi.post<{ task_id?: number }>('/agents/coordinate/async', body)
  if (requestToken !== token) {
    return
  }
  const taskId = Number(data?.task_id)
  if (!Number.isFinite(taskId) || taskId <= 0) {
    throw new Error('后台任务创建失败，请稍后重试')
  }
  pathGenerationState.taskId = taskId
  pathGenerationState.phase = 'running'
  pathGenerationState.startedAt = Date.now()
  persist({ ...meta, taskId, startedAt: pathGenerationState.startedAt })
  schedulePoll()
}

async function waitForPublicKnowledge(
  body: Record<string, unknown>,
  meta: PathGenerationMeta,
  requestToken: number,
): Promise<void> {
  pathGenerationState.phase = 'running'
  const deadline = Date.now() + KNOWLEDGE_WAIT_DEADLINE_MS
  while (requestToken === token && Date.now() < deadline) {
    await sleep(KNOWLEDGE_RETRY_INTERVAL_MS)
    if (requestToken !== token) {
      return
    }
    try {
      const { data } = await agentApi.post<{ ready?: boolean }>('/paths/preflight', {
        subject: meta.subject,
        knowledge_point: meta.knowledgePoint,
      })
      if (data?.ready) {
        await enqueue(body, meta, requestToken)
        return
      }
    } catch (error) {
      if (!isPublicKnowledgeProcessing(error)) {
        fail(error, true)
        return
      }
    }
  }
  if (requestToken === token) {
    fail(new Error('公共知识建设超时，请稍后重新生成。'), true)
  }
}

function schedulePoll(): void {
  stopPolling()
  timer = setTimeout(() => {
    timer = null
    void pollOnce()
  }, POLL_INTERVAL_MS)
}

function stopPolling(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

async function pollOnce(): Promise<void> {
  const requestToken = token
  const taskId = pathGenerationState.taskId
  if (!taskId || requestToken !== token) {
    return
  }
  try {
    const { data } = await agentApi.get<{
      status?: string
      result?: CoordinationResponse
      error_message?: string
      error_code?: string
    }>(`/agents/coordinate/tasks/${taskId}`)
    if (requestToken !== token) {
      return
    }
    const status = String(data?.status ?? '').toUpperCase()
    if (status === 'SUCCEEDED') {
      succeed(data?.result)
      return
    }
    if (status === 'FAILED') {
      fail(new Error(String(data?.error_message || data?.error_code || '学习路径生成失败')), true)
      return
    }
    if (status) {
      pathGenerationState.phase = 'running'
    }
    if (Date.now() - pathGenerationState.startedAt >= POLL_DEADLINE_MS) {
      // Keep the persisted task so coming back to the page resumes polling; the
      // server worker may still be running.
      stopPolling()
      pathGenerationState.phase = 'failed'
      pathGenerationState.error = '生成仍在后台进行，请稍后回到本页查看结果。'
      pathGenerationState.revision += 1
      notifyListeners('failed')
      return
    }
    schedulePoll()
  } catch {
    if (requestToken !== token) {
      return
    }
    // Transient network/auth hiccups must not kill a long-running generation.
    schedulePoll()
  }
}

function succeed(result: CoordinationResponse | null | undefined): void {
  stopPolling()
  pathGenerationState.result = result ?? null
  pathGenerationState.phase = 'succeeded'
  pathGenerationState.error = ''
  const meta = currentMeta
  currentMeta = null
  if (meta) {
    clearPending(meta.userId)
    if (result) {
      persistArtifacts(result, meta)
    }
  }
  pathGenerationState.revision += 1
  notifyListeners('succeeded')
}

function fail(error: unknown, clearPendingTask: boolean): void {
  stopPolling()
  pathGenerationState.phase = 'failed'
  pathGenerationState.error = describeError(error)
  if (clearPendingTask && currentMeta) {
    clearPending(currentMeta.userId)
  }
  currentMeta = null
  pathGenerationState.revision += 1
  notifyListeners('failed')
}

/**
 * Write the finished artifacts where every student page reads them, so a
 * generation that completed while the learner was elsewhere is still visible.
 */
function persistArtifacts(result: CoordinationResponse, meta: PathGenerationMeta): void {
  const path = result.outputs?.path_planning_agent?.learning_path as LearningPathResponse | undefined
  if (!path) {
    return
  }
  try {
    const nextTopic = path.knowledge_point || meta.requestedTopic
    if (!sameWorkspaceTopic(meta.previousTopic, nextTopic)) {
      clearStudentWorkspaceArtifacts(meta.userId, {
        clearCourseware: true,
        clearExercises: true,
        clearPracticeSession: true,
        clearContext: false,
      })
    }

    const hasTeacherScope = Boolean(path.teacher_scope)
    const resourceResult = result.outputs?.resource_generation_agent?.resource as ResourceResult | undefined
    if (!hasTeacherScope && resourceResult) {
      const selectedVariantId =
        resourceResult.variants?.find((variant) => variant.is_recommended)?.variant_id
        ?? resourceResult.variants?.[0]?.variant_id
        ?? ''
      window.sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify({
        subject: path.subject,
        topic: path.knowledge_point,
        goal: path.overview,
        selectedVariantId,
        generatedAt: Date.now(),
        resourceResult,
      }))
    }

    const exerciseSet = result.outputs?.exercise_generation_agent?.exercise_set as ExerciseGenerationResponse | undefined
    if (exerciseSet) {
      window.sessionStorage.setItem(EXERCISE_STORAGE_KEY, JSON.stringify({
        generatedAt: Date.now(),
        source: 'learning_path',
        exerciseSet,
      }))
    }

    writeStudentWorkspaceContext({
      userId: meta.userId,
      subject: path.subject,
      topic: path.knowledge_point,
      goal: path.overview,
      generatedAt: Date.now(),
    })
  } catch {
    // A storage quota/private-mode failure must never hide a finished task.
  }
}

function notifyListeners(phase: 'succeeded' | 'failed'): void {
  for (const listener of [...listeners]) {
    try {
      listener(phase)
    } catch {
      // One broken listener must not break the others.
    }
  }
}

function persist(record: PendingTask): void {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.localStorage.setItem(pendingPathTaskKey(record.userId), JSON.stringify(record))
  } catch {
    // Resume is a bonus; the live poll still owns completion in this session.
  }
}

function clearPending(userId: number): void {
  if (typeof window === 'undefined' || !userId) {
    return
  }
  try {
    window.localStorage.removeItem(pendingPathTaskKey(userId))
  } catch {
    // Ignore storage failures.
  }
}

function isPublicKnowledgeProcessing(error: unknown): boolean {
  return describeError(error).includes('PUBLIC_KNOWLEDGE_PROCESSING')
}

function describeError(error: unknown): string {
  const candidate = error as {
    response?: { data?: { detail?: unknown } }
    message?: string
  }
  const detail = candidate?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }
  if (detail && typeof detail === 'object') {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) {
      return message.trim()
    }
  }
  return candidate?.message?.trim() || '未知错误'
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
