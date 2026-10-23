<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  agentApi,
  evaluationApi,
  resourceApi,
  teacherApi,
  type ApiEnvelope,
  type CoordinationResponse,
  type KnowledgeSubjectCatalogResponse,
  type KnowledgeSubjectOption,
  type LearningPathPayload,
  type LearningPathResponse,
  type LearningTaskItem,
  type ManagedResourceItem,
  type TeachingScopeItem,
  type TranscriptAnalysis,
} from '../../api'
import { writeStudentWorkspaceContext } from '../../utils/studentWorkspace'
import {
  isPathGenerationBusy,
  pathGenerationState,
  resumePathGeneration,
  startPathGeneration,
  type PathGenerationMeta,
} from '../../stores/pathGeneration'
import LearningAtmosphere from '../../components/LearningAtmosphere.vue'
import GenerationProgress from '../../components/GenerationProgress.vue'
import LearningContent from '../../components/LearningContent.vue'
import PlanAdaptationPanel from '../../components/PlanAdaptationPanel.vue'
import PlanFeedbackPanel from '../../components/PlanFeedbackPanel.vue'
import TaskFeedbackButton from '../../components/TaskFeedbackButton.vue'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
const user = authStore.user!

const pathForm = reactive<LearningPathPayload>({
  user_id: user.userId,
  subject: '',
  knowledge_point: '',
  daily_minutes: 45,
  learner_profile: {},
})

const learningPath = ref<LearningPathResponse | null>(null)
// The generation itself is owned by stores/pathGeneration, so leaving this page
// neither aborts the server task nor loses the finished result.
const loading = computed(() => isPathGenerationBusy())
// The coordination task exposes no per-agent step, so surface phase + elapsed time.
const pathJob = computed(() => loading.value ? {
  id: pathGenerationState.taskId,
  status: pathGenerationState.taskId ? 'RUNNING' : 'PENDING',
  current_step: pathGenerationState.taskId ? '正在生成学习路径、课件与配套练习' : '正在提交生成任务',
  created_at: new Date(pathGenerationState.startedAt || Date.now()).toISOString(),
} : null)
const pathError = ref('')
const knowledgeCheck = ref<{ ready: boolean; message: string; reason: string; mode?: string; gap_id?: string } | null>(null)
async function checkKnowledge() {
  const { data } = await agentApi.post('/paths/preflight', { subject: pathForm.subject, knowledge_point: pathForm.knowledge_point })
  knowledgeCheck.value = data
  // Generation builds and model-reviews missing public knowledge before use.
  if (!data.ready && data.mode === 'public_build_pending') {
    ElMessage.info('将自动建设公共知识，经模型审核、发布并验证检索后再生成；内容会保存并自动修订，不需要人工处理。')
    return true
  }
  return Boolean(data.ready)
}
const coordination = ref<CoordinationResponse | null>(null)
const historyItems = ref<PathHistoryItem[]>([])
const historyLoading = ref(false)
const historyError = ref('')
const loadingHistoryId = ref(0)
const activeHistoryId = ref(0)
/** Courseware generated with the currently shown path; opened from history, never regenerated. */
type ActiveCourseware = { id: number; title: string; created_at: string | null }
const activeCourseware = ref<ActiveCourseware | null>(null)
const coursewareOpen = ref(false)
const coursewareLoading = ref(false)
const coursewareDetail = ref<{ id: number; title: string; content: string; created_at: string | null } | null>(null)
const teachingScopes = ref<TeachingScopeItem[]>([])
const scopeLoading = ref(false)
const knowledgeSubjects = ref<KnowledgeSubjectOption[]>([])
const knowledgeSubjectsLoading = ref(false)
const selectedKnowledgeSubject = ref('')
const selectedTeachingScopeId = ref<number | null>(null)
const generateCompanionResources = ref(false)
const transcriptSource = ref<{ id: number; subject: string; average: number } | null>(null)

const selectedAgents = computed(() => coordination.value?.selected_agents ?? [])
const selectedTeachingScope = computed(() =>
  teachingScopes.value.find((scope) => scope.id === selectedTeachingScopeId.value) ?? null,
)
const completedStages = computed(() => learningPath.value?.stages.filter((stage) => stage.tasks.every((task) => task.completed)).length ?? 0)
const totalStages = computed(() => learningPath.value?.stages.length ?? 0)
const progressPct = computed(() => {
  const tasks = learningPath.value?.stages.flatMap(stage => stage.tasks) ?? []
  return tasks.length ? Math.round(1000 * tasks.filter(task => task.completed).length / tasks.length) / 10 : 0
})
const coordinationOutputs = computed(() => coordination.value?.outputs ?? {})
const pathOutput = computed(() => coordinationOutputs.value.path_planning_agent as Record<string, unknown> | undefined)
const resourceOutput = computed(() => coordinationOutputs.value.resource_generation_agent as Record<string, unknown> | undefined)
const exerciseOutput = computed(() => coordinationOutputs.value.exercise_generation_agent as Record<string, unknown> | undefined)
const hasPathResult = computed(() => hasAgentPayload(pathOutput.value, 'learning_path'))
const hasCoursewareResult = computed(() => hasAgentPayload(resourceOutput.value, 'resource'))
const hasExerciseResult = computed(() => hasAgentPayload(exerciseOutput.value, 'exercise_set'))
const coursewareFailureReason = computed(() => describeAgentFailure(resourceOutput.value))
// Auto-backfill outcomes shown to the learner: never present a draft as public
// knowledge, and never hide why an automatic publication did not complete.
const BACKFAIL_REASON_TEXT: Record<string, string> = {
  PUBLISH_FAILED: '自动发布或检索校验未通过，已回滚，未写入公共知识库',
  LOCK_BUSY: '知识库正在被其他写入占用，已跳过本次入库',
  WITHDRAWN_BY_ADMIN: '该知识已被管理员下架，不再自动补建',
  REJECTED_BY_ADMIN: '该知识已被管理员驳回，不再自动补建',
  MISSING_TARGET: '缺少学科或知识点，无法入库',
  SUBJECT_CREATE_FAILED: '学科创建失败，已回滚',
  BACKFILL_UNAVAILABLE: '本次未成功入库（已发布但预检未通过或入库不可用）',
}
const backfillReasonText = computed(
  () => BACKFAIL_REASON_TEXT[learningPath.value?.knowledge_backfill_reason ?? ''] ?? '历史记录尚未进入公共知识，请重新生成以自动完成融入',
)
const publicKnowledgeTitle = computed(() => {
  const versions = learningPath.value?.knowledge_versions?.length ?? 0
  return versions
    ? `本次基于公共知识库资料生成（已引用 ${versions} 个已发布知识版本）`
    : '本次基于公共知识库资料生成'
})
const exerciseFailureReason = computed(() => describeAgentFailure(exerciseOutput.value))
const coordinationWarnings = computed(() => {
  const warnings: string[] = []
  if (pathOutput.value?.status === 'failed') {
    warnings.push(`学习路径生成失败：${describeAgentFailure(pathOutput.value)}`)
  }
  if (resourceOutput.value?.status === 'failed') {
    warnings.push(`课件生成失败：${describeAgentFailure(resourceOutput.value)}`)
  }
  if (exerciseOutput.value?.status === 'failed') {
    warnings.push(`练习生成失败：${describeAgentFailure(exerciseOutput.value)}`)
  }
  return warnings
})
const agentOutputSummary = computed(() => {
  return [
    hasAgentPayload(coordinationOutputs.value.learner_profiling_agent as Record<string, unknown> | undefined, 'learner_profile') ? '画像已合并' : '',
    hasAgentPayload(coordinationOutputs.value.knowledge_graph_agent as Record<string, unknown> | undefined, 'visualization') ? '图谱已分析' : '',
    hasPathResult.value ? '路径已生成' : '',
    hasCoursewareResult.value ? '课件已生成' : '',
    hasExerciseResult.value ? '练习已生成' : '',
  ].filter(Boolean).join(' · ')
})

async function fetchTeachingScopes() {
  scopeLoading.value = true
  try {
    const { data } = await teacherApi.get<ApiEnvelope<TeachingScopeItem[]>>('/teacher/students/me/teaching-scopes')
    teachingScopes.value = data.data
  } catch {
    teachingScopes.value = []
  } finally {
    scopeLoading.value = false
  }
}

async function fetchKnowledgeSubjects() {
  knowledgeSubjectsLoading.value = true
  try {
    const { data } = await agentApi.get<KnowledgeSubjectCatalogResponse>('/knowledge-base/subjects')
    knowledgeSubjects.value = data.subjects.filter((subject) => subject.value.trim() && subject.label.trim())
  } catch {
    knowledgeSubjects.value = []
    ElMessage.error('暂时无法读取知识库学科，请刷新后重试')
  } finally {
    knowledgeSubjectsLoading.value = false
  }
}

function applyTeachingScope(scope: TeachingScopeItem) {
  selectedTeachingScopeId.value = scope.id
  pathForm.knowledge_point = scope.knowledge_points[0] ?? ''
  if (scope.courseware_title.trim()) {
    pathForm.subject = scope.courseware_title.trim()
  }
  pathForm.learner_profile = {
    ...pathForm.learner_profile,
    teacher_scope_id: scope.id,
    teacher_knowledge_points: scope.knowledge_points,
    teacher_learning_direction: scope.learning_direction,
    teacher_teaching_goal: scope.teaching_goal,
    teacher_courseware_title: scope.courseware_title,
    teacher_courseware_content: scope.courseware_content,
  }
  ElMessage.success('已套用教师划定的学习范围')
}

function syncTeacherScopeFromPath(path: LearningPathResponse) {
  if (!path.teacher_scope) {
    return
  }
  // Only register the scope so it stays visible in "教师学习范围". Applying it
  // is now an explicit action: auto-apply used to overwrite the subject/knowledge
  // point inputs (and push the teacher courseware snapshot) whenever a generated
  // or historical path happened to carry a teacher_scope.
  const exists = teachingScopes.value.some((scope) => scope.id === path.teacher_scope!.id)
  if (!exists) {
    teachingScopes.value.unshift(path.teacher_scope)
  }
}

onMounted(async () => {
  void fetchHistory()
  // Reattach to a generation that was queued on an earlier visit: the server
  // worker kept going, so this page only has to resume watching it.
  void resumePathGeneration(user.userId)
  if (pathGenerationState.phase === 'succeeded' && pathGenerationState.result) {
    // It finished while another route was open; show that result immediately
    // instead of waiting for a reload to re-read the saved plan.
    appliedRevision = pathGenerationState.revision
    applyCoordinatedResult(pathGenerationState.result)
  }
  await Promise.all([fetchTeachingScopes(), fetchKnowledgeSubjects()])
  try {
    const { data } = await agentApi.get<LearningPathResponse>(`/paths/${user.userId}`)
    if (data?.stages?.length && !learningPath.value) {
      learningPath.value = data
      // An in-flight generation owns the form inputs; overwriting them would
      // send the learner back to the previous topic while it is still running.
      if (!isPathGenerationBusy()) {
        pathForm.subject = knowledgeSubjects.value.find(
          (subject) => subject.label === data.subject || subject.value === data.subject,
        )?.label ?? data.subject
        selectedKnowledgeSubject.value = knowledgeSubjects.value.find(
          (subject) => subject.label === data.subject || subject.value === data.subject,
        )?.label ?? ''
        pathForm.knowledge_point = data.knowledge_point
      }
      syncTeacherScopeFromPath(data)
    }
  } catch {
    // First visit may not have an active path yet.
  }
  await loadTranscriptSource()
})

async function loadTranscriptSource() {
  const raw = route.query.transcript_analysis_id
  if (typeof raw !== 'string' || !/^\d+$/.test(raw)) return
  const id = Number(raw)
  if (!Number.isSafeInteger(id) || id <= 0) return
  try {
    const { data } = await evaluationApi.get<ApiEnvelope<TranscriptAnalysis>>(`/evaluation/transcripts/analysis/${id}`)
    const analysis = data.data
    if (analysis.scope !== 'student') throw new Error('请选择个人成绩分析。')
    const subjects = Object.entries(analysis.score_statistics.subject_statistics)
      .filter(([, value]) => Number.isFinite(value.average))
      .sort((left, right) => left[1].average - right[1].average)
    if (!subjects.length) throw new Error('成绩分析中没有可用于计划的科目。')
    const [subject, stats] = subjects[0]!
    transcriptSource.value = { id, subject, average: stats.average }
    pathForm.subject = subject
    pathForm.knowledge_point = subject
    pathForm.learner_profile = { transcript_analysis_id: id }
    selectedTeachingScopeId.value = null
    selectedKnowledgeSubject.value = knowledgeSubjects.value.find((item) => item.label === subject)?.label ?? ''
  } catch (err: any) {
    pathError.value = err?.response?.status === 404 ? '成绩分析不存在或无权访问。' : err?.message || '无法读取成绩分析。'
  }
}

async function generateLearningPath() {
  pathForm.subject = pathForm.subject.trim()
  const requestedTopic = pathForm.knowledge_point.trim()
  if (!pathForm.subject) {
    ElMessage.warning('请输入或选择学科')
    return
  }
  if (!requestedTopic) {
    ElMessage.warning('请先输入学习主题')
    return
  }
  if (isPathGenerationBusy()) {
    return
  }

  pathError.value = ''
  coordination.value = null
  try {
    pathForm.user_id = user.userId
    if (!await checkKnowledge()) return
    const previousTopic = learningPath.value?.knowledge_point || pathForm.knowledge_point
    const meta: PathGenerationMeta = {
      userId: user.userId,
      subject: pathForm.subject,
      knowledgePoint: pathForm.knowledge_point,
      requestedTopic,
      previousTopic,
    }
    // Ownership of polling and result persistence lives outside this component:
    // the learner may navigate away before the worker finishes.
    await startPathGeneration(buildCoordinationBody(), meta)
  } catch (error: any) {
    const rawDetail = error?.response?.data?.detail
    const detail = typeof rawDetail === 'string' ? rawDetail : rawDetail?.message ?? error?.message ?? '未知错误'
    pathError.value = `请求失败：${detail}`
    ElMessage.error(pathError.value)
  }
}

function buildCoordinationBody(): Record<string, unknown> {
  const teacherScope = selectedTeachingScope.value
  return {
    user_id: user.userId,
    intent: generateCompanionResources.value
      ? `Generate a personalized learning path, courseware, and exercises for ${pathForm.subject || 'the current subject'}: ${pathForm.knowledge_point}`
      : `Generate a personalized learning path for ${pathForm.subject || 'the current subject'}: ${pathForm.knowledge_point}`,
    knowledge_point: pathForm.knowledge_point,
    payload: {
      ...pathForm,
      execute: true,
      dynamic_knowledge: true,
      allow_web_knowledge: true,
      enrich_knowledge: true,
      include_exercises: generateCompanionResources.value,
      force_agents: generateCompanionResources.value
        ? ['learner_profiling_agent', 'knowledge_graph_agent', 'path_planning_agent', 'resource_generation_agent', 'exercise_generation_agent']
        : ['learner_profiling_agent', 'knowledge_graph_agent', 'path_planning_agent'],
      resource_type: 'courseware',
      resource_style: 'interactive',
      generation_mode: 'self_test',
      exercise_count: 5,
      request_text: teacherScope
        ? `${teacherScope.learning_direction}\n${teacherScope.teaching_goal}\n${teacherScope.courseware_content}`
        : undefined,
      courseware_content: teacherScope?.courseware_content ?? undefined,
      teacher_scope: teacherScope ?? undefined,
    },
  }
}

/**
 * Apply a finished coordination result to this page. The courseware/exercise
 * artifacts are already persisted by the background store, so this only owns
 * the visible plan, the form state and the feedback messages.
 */
function applyCoordinatedResult(result: CoordinationResponse) {
  coordination.value = result
  const coordinatedPath = result.outputs?.path_planning_agent?.learning_path as LearningPathResponse | undefined
  if (!coordinatedPath) {
    pathError.value = `请求失败：${describeAgentFailure(result.outputs?.path_planning_agent)}`
    ElMessage.error(pathError.value)
    return
  }

  learningPath.value = coordinatedPath
  const generatedResource = (
    result.outputs?.resource_generation_agent as Record<string, unknown> | undefined
  )?.resource as { id?: number; title?: string } | undefined
  const generatedResourceId = Number(generatedResource?.id)
  activeCourseware.value = Number.isInteger(generatedResourceId) && generatedResourceId > 0
    ? {
        id: generatedResourceId,
        title: generatedResource?.title || '本次生成课件',
        created_at: null,
      }
    : null
  // Only claim the published version is in use when it actually is: on a
  // personal-draft fallback the model integration has not landed yet and the
  // draft alert has to stay authoritative.
  if (coordinatedPath.knowledge_scope === 'public') {
    knowledgeCheck.value = { ready: true, mode: 'public', reason: 'READY',
      message: '公共知识已由模型自动审核、修订并融入，正在使用已发布版本。' }
  }
  pathForm.subject = coordinatedPath.subject
  pathForm.knowledge_point = coordinatedPath.knowledge_point
  syncTeacherScopeFromPath(coordinatedPath)
  notifyGenerationResult()
  void fetchHistory()
}

let appliedRevision = 0

// The store can finish (or fail) while this page is open or after coming back
// from another route, so react to its revision instead of awaiting the request.
watch(
  () => pathGenerationState.revision,
  () => {
    if (pathGenerationState.revision === appliedRevision) {
      return
    }
    if (pathGenerationState.phase === 'succeeded' && pathGenerationState.result) {
      appliedRevision = pathGenerationState.revision
      applyCoordinatedResult(pathGenerationState.result)
      return
    }
    if (pathGenerationState.phase === 'failed') {
      appliedRevision = pathGenerationState.revision
      pathError.value = pathGenerationState.error
        ? `请求失败：${pathGenerationState.error}`
        : '生成失败，请稍后重试'
      ElMessage.error(pathError.value)
    }
  },
)

type PathHistoryItem = {
  id: number
  status: string
  created_at: string | null
  subject: string
  knowledge_point: string
  overview: string
  estimated_days?: number | null
  stage_count: number
  task_count: number
  teacher_scope_title: string
  courseware_resource_id?: number | null
  courseware_title?: string
  courseware_created_at?: string | null
}

async function fetchHistory() {
  historyLoading.value = true
  historyError.value = ''
  try {
    const { data } = await agentApi.get<{ items: PathHistoryItem[] }>(`/paths/history/${user.userId}`, {
      params: { limit: 8 },
    })
    historyItems.value = data.items ?? []
  } catch {
    historyError.value = '历史生成加载失败'
  } finally {
    historyLoading.value = false
  }
}

async function loadHistoryItem(item: PathHistoryItem) {
  if (loadingHistoryId.value) return
  loadingHistoryId.value = item.id
  try {
    // Full stage/task JSON is fetched only for the clicked record; the list
    // endpoint returns summaries so a long history stays cheap.
    const { data } = await agentApi.get<LearningPathResponse>(`/paths/history/item/${item.id}`)
    if (!data?.stages?.length) {
      ElMessage.warning('该历史记录暂无可用内容')
      return
    }
    learningPath.value = data
    activeHistoryId.value = item.id
    const coursewareId = Number(item.courseware_resource_id)
    activeCourseware.value = Number.isInteger(coursewareId) && coursewareId > 0
      ? {
          id: coursewareId,
          title: item.courseware_title || '本次生成课件',
          created_at: item.courseware_created_at ?? null,
        }
      : null
    pathForm.subject = data.subject
    pathForm.knowledge_point = data.knowledge_point
    syncTeacherScopeFromPath(data)
    persistWorkspaceContext(data)
    knowledgeCheck.value = {
      ready: true,
      mode: 'history',
      reason: 'READY',
      message: '正在查看历史生成的学习路径（不影响当前进度）',
    }
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch {
    ElMessage.error('加载历史路径失败')
  } finally {
    loadingHistoryId.value = 0
  }
}

function openHistoryCourseware(item: PathHistoryItem) {
  const resourceId = Number(item.courseware_resource_id)
  if (!Number.isInteger(resourceId) || resourceId <= 0) {
    ElMessage.info('该历史记录尚未关联已保存课件，可查看学习路径')
    return
  }
  void openCourseware({
    id: resourceId,
    title: item.courseware_title || '本次生成课件',
    created_at: item.courseware_created_at ?? null,
  })
}

function openActiveCourseware() {
  if (activeCourseware.value) {
    void openCourseware(activeCourseware.value)
  }
}

/**
 * Open the courseware that belongs to this path. It is fetched from the
 * resource library by id, so opening history never starts another generation.
 */
async function openCourseware(target: ActiveCourseware) {
  const resourceId = Number(target.id)
  if (!Number.isInteger(resourceId) || resourceId <= 0 || coursewareLoading.value) {
    return
  }
  coursewareOpen.value = true
  coursewareLoading.value = true
  coursewareDetail.value = null
  try {
    const { data } = await resourceApi.get<ApiEnvelope<ManagedResourceItem>>(`/resources/${resourceId}`)
    const resource = data.data
    if (!resource || !resource.id) {
      throw new Error('courseware missing')
    }
    coursewareDetail.value = {
      id: resource.id,
      title: resource.title || target.title || '本次生成课件',
      content: resource.content || '',
      created_at: target.created_at ?? null,
    }
  } catch {
    ElMessage.error('历史课件读取失败，请到资源中心查看')
    coursewareOpen.value = false
  } finally {
    coursewareLoading.value = false
  }
}

function openCoursewareInLibrary() {
  if (!coursewareDetail.value) {
    return
  }
  const resourceId = coursewareDetail.value.id
  coursewareOpen.value = false
  void router.push({ name: 'student-resources', query: { resource: String(resourceId) } })
}

function formatHistoryTime(value: string | null) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function hasAgentPayload(output: Record<string, unknown> | undefined, key: string) {
  return Boolean(output && output.status !== 'failed' && output[key])
}

function persistWorkspaceContext(path: LearningPathResponse) {
  writeStudentWorkspaceContext({
    userId: user.userId,
    subject: path.subject,
    topic: path.knowledge_point,
    goal: path.overview,
    generatedAt: Date.now(),
  })
}

function describeAgentFailure(output: Record<string, unknown> | undefined) {
  const rawError = typeof output?.error === 'string' ? output.error.trim() : ''
  if (!rawError) {
    return '服务暂时不可用'
  }
  if (rawError.includes('No LLM credentials configured')) {
    return '未配置 LLM 凭据，请在后端 .env 中填写对应模型提供商的 API Key'
  }
  return rawError
}

function notifyGenerationResult() {
  if (hasPathResult.value && !generateCompanionResources.value) {
    ElMessage.success('学习路径已生成；课件和练习可在任务中按需生成')
    return
  }
  if (hasPathResult.value && hasCoursewareResult.value && hasExerciseResult.value) {
    ElMessage.success('学习路径、课件和练习已生成')
    return
  }

  if (hasPathResult.value && !hasCoursewareResult.value && hasExerciseResult.value) {
    ElMessage.warning(`学习路径和练习已生成，但课件生成失败：${coursewareFailureReason.value}`)
    return
  }

  if (hasPathResult.value && !hasCoursewareResult.value && !hasExerciseResult.value) {
    ElMessage.warning(`学习路径已生成，但课件和练习未完成。课件失败原因：${coursewareFailureReason.value}`)
    return
  }

  if (hasPathResult.value && hasCoursewareResult.value && !hasExerciseResult.value) {
    ElMessage.warning(`学习路径和课件已生成，但练习生成失败：${exerciseFailureReason.value}`)
    return
  }

  if (hasPathResult.value) {
    ElMessage.success('学习路径已生成')
    return
  }

  ElMessage.warning('本次仅完成了部分协同结果，请查看页面中的失败原因')
}

function resolveTaskRoute(taskType: LearningTaskItem['task_type']) {
  const routeMap: Record<LearningTaskItem['task_type'], string> = {
    courseware: 'student-courseware',
    exercise: 'student-exercise',
    graph: 'student-knowledge-graph',
    review: 'student-mistakes',
  }
  return routeMap[taskType]
}

function getTaskActionLabel(taskType: LearningTaskItem['task_type']) {
  const labelMap: Record<LearningTaskItem['task_type'], string> = {
    courseware: '去学习',
    exercise: '去练习',
    graph: '看图谱',
    review: '去复盘',
  }
  return labelMap[taskType]
}

function navigateToTask(task: LearningTaskItem) {
  // A courseware task inside a path that already has a saved courseware opens
  // that file instead of routing to the courseware page (which would start a
  // new generation when its session snapshot is missing).
  if (task.task_type === 'courseware' && activeCourseware.value) {
    void openCourseware(activeCourseware.value)
    return
  }
  const routeName = resolveTaskRoute(task.task_type)
  const topic = task.knowledge_point || learningPath.value?.knowledge_point || pathForm.knowledge_point

  writeStudentWorkspaceContext({
    userId: user.userId,
    subject: learningPath.value?.subject || pathForm.subject,
    topic,
    goal: task.objective || learningPath.value?.overview || '',
    generatedAt: Date.now(),
  })

  void router.push({ name: routeName })
}

async function adjustTask(taskId: string, action: 'complete' | 'skip') {
  try {
    await agentApi.post('/paths/adjust', { user_id: user.userId, task_id: taskId, action })
    if (learningPath.value) {
      for (const stage of learningPath.value.stages) {
        for (const task of stage.tasks) {
          if (task.task_id === taskId) {
            task.completed = action === 'complete'
            task.status = action === 'complete' ? 'completed' : 'skipped'
          }
        }
      }
    }
    ElMessage.success(action === 'complete' ? '任务已标记完成' : '任务已跳过')
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? ''
    ElMessage.error(`操作失败：${detail}`)
  }
}
</script>

<template>
  <div class="learning-path-page">
    <header class="path-header">
      <div>
        <div class="panel-kicker">Multi-Agent Plan</div>
        <h2>学习路径</h2>
        <p>默认只生成路径；课件与练习可按需生成，避免一次请求触发多个大模型任务。</p>
        <el-button v-if="learningPath" @click="router.push('/student/workspace')">打开三栏学习工作区</el-button>
      </div>
      <LearningAtmosphere class="path-atmosphere" variant="path" />
    </header>

    <div v-if="transcriptSource" class="path-form transcript-source">
      已依据成绩分析 #{{ transcriptSource.id }} 预填 {{ transcriptSource.subject }}（均分 {{ transcriptSource.average }}）。请检查主题后生成；科目成绩不代表具体知识点掌握度。
    </div>

    <section class="path-layout">
      <main class="path-main">
        <div class="path-form">
          <select
            v-model="selectedKnowledgeSubject"
            aria-label="选择知识库已有学科"
            :disabled="knowledgeSubjectsLoading || !knowledgeSubjects.length"
            @change="pathForm.subject = selectedKnowledgeSubject"
          >
            <option value="">知识库学科（可选）</option>
            <option v-for="subject in knowledgeSubjects" :key="subject.value" :value="subject.label">
              {{ subject.label }}
            </option>
          </select>
          <input
            v-model="pathForm.subject"
            aria-label="输入学科"
            placeholder="自定义学科（可选）"
            @input="selectedKnowledgeSubject = ''"
          />
          <input v-model="pathForm.knowledge_point" placeholder="知识点 / 主题" />
          <label class="companion-option">
            <input v-model="generateCompanionResources" type="checkbox" />
            同时生成课件与练习
          </label>
          <button :disabled="loading" @click="generateLearningPath">
            {{ loading ? '正在生成...' : '生成学习路径' }}
          </button>
        </div>

        <GenerationProgress v-if="loading" :job="pathJob" label="学习路径与配套资源"/>

        <div v-if="pathError" class="path-error">{{ pathError }}</div>
        <el-alert v-if="knowledgeCheck" :title="knowledgeCheck.message" :type="knowledgeCheck.ready ? 'success' : (knowledgeCheck.mode === 'public_build_pending' ? 'info' : 'warning')" :closable="false"><span v-if="knowledgeCheck.gap_id && knowledgeCheck.mode !== 'public_build_pending'">公共建设跟踪编号 #{{ knowledgeCheck.gap_id }}，系统自动处理。</span></el-alert>

        <div v-if="learningPath" class="timeline">
          <el-alert
            v-if="learningPath.knowledge_scope === 'public'"
            type="success"
            :closable="false"
            :title="publicKnowledgeTitle"
          />
          <el-alert
            v-if="learningPath.knowledge_scope === 'personal_draft'"
            type="info"
            :closable="false"
            title="历史个人草稿：不是公共知识。请重新生成，经模型审核入公共知识库后使用。"
          >
            <p class="knowledge-draft-reason">未入库原因：{{ backfillReasonText }}</p>
            <div class="knowledge-draft">
              <p>{{ learningPath.knowledge_draft?.description || learningPath.subject }}</p>
              <ul>
                <li v-for="chapter in (learningPath.knowledge_draft?.chapters || [])" :key="chapter.name">
                  <strong>{{ chapter.name }}</strong>：{{ (chapter.points || []).map(point => point.name).join('、') }}
                </li>
              </ul>
              <p v-if="learningPath.knowledge_sources?.length" class="knowledge-sources">
                参考来源：<template v-for="(source, index) in learningPath.knowledge_sources" :key="index">{{ source.title || source.url }}<template v-if="index < learningPath.knowledge_sources.length - 1">；</template></template>
              </p>
            </div>
          </el-alert>
          <article v-if="activeCourseware" class="history-courseware-card">
            <div class="history-courseware-copy">
              <span class="panel-kicker">本次生成课件</span>
              <h3>{{ activeCourseware.title }}</h3>
              <p>
                {{ activeCourseware.created_at ? formatHistoryTime(activeCourseware.created_at) : '已保存' }}
                · 打开的是已生成文件，不会重新调用模型
              </p>
            </div>
            <div class="history-courseware-card-actions">
              <button type="button" @click="openActiveCourseware">查看课件</button>
            </div>
          </article>
          <PlanFeedbackPanel @updated="learningPath = $event" />
          <PlanAdaptationPanel @updated="learningPath = $event" />
          <article v-for="stage in learningPath.stages" :key="stage.stage_id" class="stage-item">
            <span class="stage-dot" :class="{ done: stage.tasks.every((task) => task.completed) }"></span>
            <div class="stage-card">
              <h3>{{ stage.title }}</h3>
              <p>{{ stage.description }}</p>
              <div class="task-list">
                <article
                  v-for="task in stage.tasks"
                  :key="task.task_id"
                  class="task-chip"
                  :class="{ done: task.completed }"
                  role="button"
                  tabindex="0"
                  @click="navigateToTask(task)"
                  @keydown.enter.prevent="navigateToTask(task)"
                  @keydown.space.prevent="navigateToTask(task)"
                >
                  <div>
                    <strong>{{ task.title }}</strong>
                    <span>{{ task.task_type }} · {{ task.estimated_minutes }} 分钟 · {{ task.difficulty }}</span>
                  </div>
                  <div class="task-actions">
                    <button class="task-open-btn" @click.stop="navigateToTask(task)">
                      {{ getTaskActionLabel(task.task_type) }}
                    </button>
                    <button v-if="!task.completed" @click.stop="adjustTask(task.task_id, 'complete')">完成</button>
                    <button v-else @click.stop="adjustTask(task.task_id, 'skip')">撤销</button>
                    <TaskFeedbackButton :task-id="task.task_id" @updated="learningPath = $event" />
                  </div>
                </article>
              </div>
            </div>
          </article>
        </div>

        <div v-else-if="!pathError" class="empty-state">
          选择已建立的学科与知识点。生成前检查正式资料和检索版本；资料不足会记录缺口，交由管理员审核补充。
        </div>
      </main>

      <aside class="path-side">
        <section class="side-panel">
          <h3>教师学习范围</h3>
          <p v-if="scopeLoading">正在同步教师划定的学习范围...</p>
          <div v-else-if="teachingScopes.length" class="scope-list">
            <article
              v-for="scope in teachingScopes"
              :key="scope.id"
              class="scope-card"
              :class="{ active: selectedTeachingScopeId === scope.id }"
            >
              <strong>{{ scope.courseware_title }}</strong>
              <span>{{ scope.knowledge_points.join(' / ') }}</span>
              <p>{{ scope.learning_direction }}</p>
              <p v-if="scope.teaching_goal">{{ scope.teaching_goal }}</p>
              <button @click="applyTeachingScope(scope)">套用</button>
            </article>
          </div>
          <p v-else>暂无教师投放的学习范围。</p>
        </section>

        <section class="side-panel history-panel">
          <div class="history-head">
            <h3>历史生成</h3>
            <button type="button" class="history-refresh" :disabled="historyLoading" @click="fetchHistory">
              {{ historyLoading ? '加载中' : '刷新' }}
            </button>
          </div>
          <p v-if="historyLoading && !historyItems.length">正在读取历史记录...</p>
          <p v-else-if="historyError" class="warning-text">{{ historyError }}</p>
          <div v-else-if="historyItems.length" class="history-list">
            <div
              v-for="item in historyItems"
              :key="item.id"
              class="history-entry"
              :class="{ active: activeHistoryId === item.id }"
            >
              <button
                type="button"
                class="history-item"
                :disabled="coursewareLoading"
                @click="openHistoryCourseware(item)"
              >
                <strong>{{ item.subject || '未命名学科' }}</strong>
                <span class="history-topic">{{ item.knowledge_point || '未标注知识点' }}</span>
                <small>
                  {{ formatHistoryTime(item.created_at) }} · {{ item.stage_count }} 阶段 / {{ item.task_count }} 任务
                </small>
                <span v-if="!item.courseware_resource_id" class="history-loading">暂无关联课件</span>
              </button>
              <button
                v-if="item.courseware_resource_id"
                type="button"
                class="history-courseware-open"
                :disabled="coursewareLoading"
                @click="openHistoryCourseware(item)"
              >
                查看历史课件
              </button>
              <button
                type="button"
                class="history-courseware-open history-path-open"
                :disabled="!!loadingHistoryId"
                @click="loadHistoryItem(item)"
              >
                {{ loadingHistoryId === item.id ? '加载中...' : '查看学习路径' }}
              </button>
            </div>
          </div>
          <p v-else>暂无历史生成记录，生成一次后会出现在这里。</p>
        </section>

        <section class="side-panel">
          <h3>路径统计</h3>
          <div class="progress-line">
            <span>总体进度</span>
            <strong>{{ progressPct }}%</strong>
          </div>
          <div class="progress-track"><div :style="{ width: `${progressPct}%` }"></div></div>
          <div class="stat-grid">
            <article><strong>{{ completedStages }}</strong><span>已完成阶段</span></article>
            <article><strong>{{ Math.max(totalStages - completedStages, 0) }}</strong><span>剩余阶段</span></article>
          </div>
        </section>

        <section v-if="coordination" class="side-panel">
          <h3>智能体协同</h3>
          <div class="agent-list">
            <span v-for="agent in selectedAgents" :key="agent">{{ agent }}</span>
          </div>
          <p>{{ agentOutputSummary || coordination.route_reason }}</p>
          <div v-if="coordinationWarnings.length" class="warning-list">
            <p v-for="warning in coordinationWarnings" :key="warning" class="warning-text">
              {{ warning }}
            </p>
          </div>
          <p v-if="coordination.status !== 'success'" class="warning-text">
            部分智能体未完成，请查看服务日志。
          </p>
        </section>
      </aside>
    </section>

    <el-dialog
      v-model="coursewareOpen"
      :title="coursewareDetail?.title || '本次生成课件'"
      width="min(920px, 94vw)"
      append-to-body
    >
      <div v-if="coursewareLoading" class="history-courseware-loading">正在读取已保存的课件...</div>
      <template v-else-if="coursewareDetail">
        <p class="history-courseware-meta">
          {{ coursewareDetail.created_at ? formatHistoryTime(coursewareDetail.created_at) : '已保存' }}
          · 打开的是生成时落库的原文，不会重新调用模型
        </p>
        <div class="history-courseware-content">
          <LearningContent :content="coursewareDetail.content" empty="该课件正文为空，请到资源中心查看" />
        </div>
      </template>
      <template #footer>
        <el-button @click="coursewareOpen = false">关闭</el-button>
        <el-button type="primary" :disabled="!coursewareDetail" @click="openCoursewareInLibrary">在资源库中打开</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.learning-path-page {
  display: grid;
  gap: 18px;
}

.path-header,
.path-main,
.side-panel {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
}

.path-header {
  padding: 24px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 480px);
  align-items: center;
  gap: 20px;
}

.path-atmosphere {
  width: 100%;
  opacity: .9;
}

.path-header h2 {
  margin: 8px 0;
  font-size: 26px;
}

.path-header p,
.stage-card p,
.side-panel p,
.task-chip span {
  color: var(--muted);
  line-height: 1.7;
}

.path-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, 360px);
  gap: 18px;
}

.path-main,
.side-panel {
  padding: 22px;
}

.path-form {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.transcript-source {
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
  color: var(--text);
}

.path-form input,
.path-form select {
  min-width: 140px;
  flex: 1;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
  color: var(--text);
  padding: 11px 14px;
  font: inherit;
}

.path-form select:disabled {
  cursor: wait;
  opacity: 0.7;
}

.path-form button,
.task-chip button {
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  color: #fff;
  padding: 10px 16px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.path-form button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.path-background-hint {
  margin-bottom: 14px;
  padding: 12px 16px;
  border: 1px solid color-mix(in srgb, var(--accent) 24%, transparent);
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted);
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}

.path-error {
  margin-bottom: 14px;
  padding: 14px 16px;
  border-radius: 12px;
  color: var(--red);
  background: color-mix(in srgb, var(--red) 8%, transparent);
}

.knowledge-draft p {
  margin: 6px 0;
  color: var(--muted);
  line-height: 1.6;
}

.knowledge-draft ul {
  margin: 6px 0 0;
  padding-left: 20px;
  line-height: 1.8;
}

.timeline {
  position: relative;
  display: grid;
  gap: 14px;
  padding-left: 22px;
}

.timeline::before {
  content: "";
  position: absolute;
  left: 7px;
  top: 10px;
  bottom: 10px;
  width: 2px;
  border-radius: 2px;
  background: linear-gradient(180deg, var(--accent), var(--accent-deep), transparent);
}

.stage-item {
  position: relative;
}

.stage-dot {
  position: absolute;
  left: -21px;
  top: 18px;
  width: 14px;
  height: 14px;
  border: 3px solid var(--accent);
  border-radius: 50%;
  background: var(--bg);
}

.stage-dot.done {
  background: var(--accent);
}

.stage-card {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent) 4%, transparent);
}

.stage-card h3,
.side-panel h3 {
  margin: 0 0 10px;
}

.task-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.task-chip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
  cursor: pointer;
  transition: border-color 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.path-form .companion-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: max-content;
  color: var(--muted);
  font-size: 14px;
}

.path-form .companion-option input {
  min-width: auto;
  flex: none;
}

.task-chip.done {
  border-color: color-mix(in srgb, var(--green) 55%, transparent);
}

.task-chip:hover,
.task-chip:focus-visible {
  border-color: color-mix(in srgb, var(--accent) 52%, var(--line));
  background: color-mix(in srgb, var(--accent) 7%, var(--panel));
  transform: translateY(-1px);
  outline: none;
}

.task-chip strong,
.task-chip span {
  display: block;
}

.task-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.task-chip button {
  padding: 7px 12px;
  background: var(--panel-strong);
  color: var(--text);
  border: 1px solid var(--line);
}

.task-chip .task-open-btn {
  background: color-mix(in srgb, var(--accent) 16%, var(--panel-strong));
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 34%, var(--line));
}

.path-side {
  display: grid;
  gap: 16px;
  align-content: start;
}

.progress-line {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.progress-line span {
  color: var(--muted);
}

.progress-line strong {
  color: var(--accent);
}

.progress-track {
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: color-mix(in srgb, var(--muted) 15%, transparent);
}

.progress-track div {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--accent), var(--accent-deep));
}

.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 16px;
}

.stat-grid article {
  text-align: center;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--accent) 5%, transparent);
}

.stat-grid strong {
  display: block;
  color: var(--accent);
  font-size: 28px;
}

.stat-grid span {
  color: var(--muted);
  font-size: 12px;
}

.agent-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.agent-list span {
  padding: 4px 10px;
  border-radius: 999px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  font-size: 11px;
  font-weight: 700;
}

.scope-list {
  display: grid;
  gap: 10px;
}

.scope-card {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--accent) 4%, transparent);
}

.scope-card.active {
  border-color: color-mix(in srgb, var(--accent) 65%, transparent);
}

.scope-card strong,
.scope-card span {
  display: block;
}

.scope-card span,
.scope-card p {
  margin: 0;
  color: var(--muted);
  line-height: 1.5;
}

.scope-card button {
  justify-self: start;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel-strong);
  color: var(--text);
  padding: 7px 12px;
  font: inherit;
  cursor: pointer;
}

.warning-text {
  color: var(--red) !important;
}

.warning-list {
  display: grid;
  gap: 6px;
  margin-top: 10px;
}

.empty-state {
  padding: 44px;
  border: 1px dashed var(--line);
  border-radius: 14px;
  color: var(--muted);
  text-align: center;
}

@media (max-width: 1000px) {
  .path-header {
    grid-template-columns: 1fr;
  }

  .path-layout {
    grid-template-columns: 1fr;
  }
}
/* 历史生成：只用主题变量，六套主题（默认/深海/暖金/暗夜/极简/森林）自动适配 */
.history-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.history-refresh {
  border: 1px solid var(--line);
  background: var(--surface-soft);
  color: var(--muted);
  border-radius: 8px;
  padding: 3px 10px;
  font-size: 11px;
  cursor: pointer;
  transition: border-color .18s ease, color .18s ease, background .18s ease;
}
.history-refresh:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }
.history-refresh:disabled { opacity: .55; cursor: not-allowed; }
.history-list { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
.history-entry {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 9px 11px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--surface-soft);
  transition: border-color .18s ease, background .18s ease;
}
.history-entry:hover { border-color: color-mix(in srgb, var(--accent) 55%, var(--line)); }
.history-entry.active { border-color: var(--accent); background: var(--accent-soft); }
.history-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font-family: inherit;
}
.history-item:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.history-item:disabled { opacity: .65; cursor: progress; }
.history-item strong { font-size: 13px; font-weight: 600; color: var(--text); }
.history-item .history-topic { font-size: 12px; color: var(--accent); }
.history-item small { font-size: 11px; color: var(--muted); }
.history-item small em { font-style: normal; color: var(--accent); }
.history-loading { font-size: 11px; color: var(--accent); }
.history-courseware-open {
  align-self: flex-start;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--accent);
  border-radius: 7px;
  padding: 3px 9px;
  font-size: 11px;
  font-family: inherit;
  cursor: pointer;
  transition: border-color .18s ease, background .18s ease;
}
.history-courseware-open:hover:not(:disabled) { border-color: var(--accent); background: var(--accent-soft); }
.history-courseware-open:disabled { opacity: .55; cursor: progress; }
.history-courseware-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 13px 16px;
  margin: 12px 0;
  border-radius: 13px;
  border: 1px solid var(--line);
  background: var(--panel);
}
.history-courseware-copy h3 { margin: 3px 0; font-size: 15px; color: var(--text); }
.history-courseware-copy p { margin: 0; font-size: 12px; color: var(--muted); }
.history-courseware-card-actions { flex: 0 0 auto; }
.history-courseware-card-actions button {
  border: 1px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
  border-radius: 9px;
  padding: 7px 13px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.history-courseware-card-actions button:hover { background: var(--accent); color: #fff; }
.history-courseware-meta { margin: 0 0 10px; font-size: 12px; color: var(--muted); }
.history-courseware-content { max-height: 62vh; overflow: auto; padding-right: 4px; }
.history-courseware-loading { padding: 18px 4px; color: var(--muted); font-size: 13px; }
</style>
