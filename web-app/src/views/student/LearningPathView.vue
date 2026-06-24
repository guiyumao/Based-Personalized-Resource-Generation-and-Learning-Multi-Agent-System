<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  agentApi,
  teacherApi,
  type ApiEnvelope,
  type CoordinationResponse,
  type ExerciseGenerationPayload,
  type ExerciseGenerationResponse,
  type LearningPathPayload,
  type LearningPathResponse,
  type ResourcePayload,
  type ResourceResult,
  type TeachingScopeItem,
} from '../../api'
import {
  clearStudentWorkspaceArtifacts,
  COURSEWARE_STORAGE_KEY,
  EXERCISE_STORAGE_KEY,
  sameWorkspaceTopic,
  writeStudentWorkspaceContext,
} from '../../utils/studentWorkspace'

const authStore = useAuthStore()
const user = authStore.user!

const pathForm = reactive<LearningPathPayload>({
  user_id: user.userId,
  subject: '',
  knowledge_point: '',
  daily_minutes: 45,
  learner_profile: {},
})

const learningPath = ref<LearningPathResponse | null>(null)
const loading = ref(false)
const pathError = ref('')
const coordination = ref<CoordinationResponse | null>(null)
const teachingScopes = ref<TeachingScopeItem[]>([])
const scopeLoading = ref(false)
const selectedTeachingScopeId = ref<number | null>(null)

const selectedAgents = computed(() => coordination.value?.selected_agents ?? [])
const selectedTeachingScope = computed(() =>
  teachingScopes.value.find((scope) => scope.id === selectedTeachingScopeId.value) ?? null,
)
const completedStages = computed(() => learningPath.value?.stages.filter((stage) => stage.tasks.every((task) => task.completed)).length ?? 0)
const totalStages = computed(() => learningPath.value?.stages.length ?? 0)
const progressPct = computed(() => totalStages.value > 0 ? Math.round((completedStages.value / totalStages.value) * 100) : 0)
const coordinationOutputs = computed(() => coordination.value?.outputs ?? {})
const pathOutput = computed(() => coordinationOutputs.value.path_planning_agent as Record<string, unknown> | undefined)
const resourceOutput = computed(() => coordinationOutputs.value.resource_generation_agent as Record<string, unknown> | undefined)
const exerciseOutput = computed(() => coordinationOutputs.value.exercise_generation_agent as Record<string, unknown> | undefined)
const hasPathResult = computed(() => hasAgentPayload(pathOutput.value, 'learning_path'))
const hasCoursewareResult = computed(() => hasAgentPayload(resourceOutput.value, 'resource'))
const hasExerciseResult = computed(() => hasAgentPayload(exerciseOutput.value, 'exercise_set'))
const coursewareFailureReason = computed(() => describeAgentFailure(resourceOutput.value))
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

function applyTeachingScope(scope: TeachingScopeItem) {
  selectedTeachingScopeId.value = scope.id
  pathForm.knowledge_point = scope.knowledge_points[0] ?? ''
  pathForm.subject = scope.courseware_title
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
  const exists = teachingScopes.value.some((scope) => scope.id === path.teacher_scope!.id)
  if (!exists) {
    teachingScopes.value.unshift(path.teacher_scope)
  }
  applyTeachingScope(path.teacher_scope)
  persistTeacherScopeCourseware(path.teacher_scope, path)
}

function persistTeacherScopeCourseware(scope: TeachingScopeItem, path: LearningPathResponse) {
  if (!scope.courseware_content.trim()) {
    return
  }
  const content = scope.courseware_content.trim().startsWith('#')
    ? scope.courseware_content
    : `# ${scope.courseware_title}\n\n${scope.courseware_content}`
  const resourceResult: ResourceResult = {
    user_id: user.userId,
    knowledge_point: path.knowledge_point,
    resource_type: 'courseware',
    resource_style: 'teacher',
    references: [],
    content,
    variants: [
      {
        variant_id: `teacher-scope-${scope.id}`,
        title: scope.courseware_title,
        summary: scope.learning_direction,
        resource_style: 'interactive',
        content,
        is_recommended: true,
      },
    ],
  }
  window.sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify({
    subject: path.subject,
    topic: path.knowledge_point,
    goal: path.overview,
    selectedVariantId: `teacher-scope-${scope.id}`,
    generatedAt: Date.now(),
    resourceResult,
    teacherScope: scope,
  }))
}

onMounted(async () => {
  await fetchTeachingScopes()
  try {
    const { data } = await agentApi.get<LearningPathResponse>(`/paths/${user.userId}`)
    if (data?.stages?.length) {
      learningPath.value = data
      pathForm.subject = data.subject
      pathForm.knowledge_point = data.knowledge_point
      syncTeacherScopeFromPath(data)
    }
  } catch {
    // First visit may not have an active path yet.
  }
})

async function generateLearningPath() {
  const requestedTopic = pathForm.knowledge_point.trim()
  if (!requestedTopic) {
    ElMessage.warning('请先输入学习主题')
    return
  }

  loading.value = true
  pathError.value = ''
  coordination.value = null
  try {
    clearWorkspaceForNewTopic(requestedTopic)
    pathForm.user_id = user.userId
    await requestCoordination()

    let coordinatedPath = coordination.value?.outputs?.path_planning_agent?.learning_path as LearningPathResponse | undefined
    if (!coordinatedPath) {
      coordinatedPath = await generateFallbackWorkspace()
    } else {
      await ensureWorkspaceArtifacts(coordinatedPath)
    }

    learningPath.value = coordinatedPath
    pathForm.subject = coordinatedPath.subject
    pathForm.knowledge_point = coordinatedPath.knowledge_point
    persistWorkspaceContext(coordinatedPath)
    const hasTeacherScope = Boolean(coordinatedPath.teacher_scope)
    syncTeacherScopeFromPath(coordinatedPath)
    if (!hasTeacherScope) {
      persistCoordinatedCourseware()
    }
    persistCoordinatedExercises()
    notifyGenerationResult()
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    pathError.value = `请求失败：${detail}`
    ElMessage.error(pathError.value)
  } finally {
    loading.value = false
  }
}

async function requestCoordination() {
  const teacherScope = selectedTeachingScope.value
  try {
    const { data } = await agentApi.post<CoordinationResponse>('/agents/coordinate', {
      user_id: user.userId,
      intent: `围绕 ${pathForm.subject || '当前学科'} 中的「${pathForm.knowledge_point}」生成个性化学习路径、课件和练习`,
      knowledge_point: pathForm.knowledge_point,
      payload: {
        ...pathForm,
        execute: true,
        include_exercises: true,
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
    })
    coordination.value = (data as any).data ?? data
  } catch (error: any) {
    coordination.value = {
      status: 'partial',
      selected_agents: [],
      route_reason: error?.response?.data?.detail ?? error?.message ?? '协调器接口不可用，已改用同步接口补齐学习空间。',
      outputs: {},
    }
  }
}

function hasAgentPayload(output: Record<string, unknown> | undefined, key: string) {
  return Boolean(output && output.status !== 'failed' && output[key])
}

function clearWorkspaceForNewTopic(nextTopic: string) {
  const currentTopic = learningPath.value?.knowledge_point || pathForm.knowledge_point
  if (sameWorkspaceTopic(currentTopic, nextTopic)) {
    return
  }
  clearStudentWorkspaceArtifacts(user.userId, {
    clearCourseware: true,
    clearExercises: true,
    clearPracticeSession: true,
    clearContext: false,
  })
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

async function ensureWorkspaceArtifacts(path: LearningPathResponse) {
  if (!hasAgentPayload(coordination.value?.outputs?.resource_generation_agent, 'resource')) {
    await generateFallbackCourseware(path)
  }
  if (!hasAgentPayload(coordination.value?.outputs?.exercise_generation_agent, 'exercise_set')) {
    await generateFallbackExercises(path)
  }
}

async function generateFallbackWorkspace(): Promise<LearningPathResponse> {
  const reason = coordination.value?.outputs?.path_planning_agent?.message === 'task dispatched'
    ? '协调器仅返回了队列派发结果，已改用同步接口补齐学习空间。'
    : '协同智能体未返回学习路径，已改用同步接口补齐学习空间。'
  coordination.value = {
    status: 'partial',
    selected_agents: coordination.value?.selected_agents ?? [],
    route_reason: reason,
    outputs: coordination.value?.outputs ?? {},
  }

  const pathResponse = await agentApi.post<LearningPathResponse>('/paths/generate', pathForm)
  const generatedPath = (pathResponse.data as any).data ?? pathResponse.data
  coordination.value.outputs.path_planning_agent = {
    status: 'completed',
    learning_path: generatedPath,
  }

  await ensureWorkspaceArtifacts(generatedPath)
  return generatedPath
}

async function generateFallbackCourseware(path: LearningPathResponse) {
  const payload: ResourcePayload = {
    user_id: user.userId,
    knowledge_point: path.knowledge_point,
    resource_style: 'interactive',
    resource_type: 'courseware',
    learner_profile: pathForm.learner_profile,
    request_text: `围绕 ${path.subject || '当前学科'} 的 ${path.knowledge_point} 生成可独立阅读的正式课件`,
  }
  try {
    const { data } = await agentApi.post<ResourceResult>('/resources/generate', payload)
    const resource = (data as any).data ?? data
    coordination.value!.outputs.resource_generation_agent = {
      status: 'completed',
      resource,
    }
  } catch (error: any) {
    window.sessionStorage.removeItem(COURSEWARE_STORAGE_KEY)
    coordination.value!.outputs.resource_generation_agent = {
      status: 'failed',
      error: error?.response?.data?.detail ?? error?.message ?? '课件生成失败',
    }
  }
}

async function generateFallbackExercises(path: LearningPathResponse) {
  const courseware = coordination.value?.outputs?.resource_generation_agent?.resource as ResourceResult | undefined
  const payload: ExerciseGenerationPayload = {
    user_id: user.userId,
    knowledge_point: path.knowledge_point,
    resource_style: 'interactive',
    learner_profile: pathForm.learner_profile,
    exercise_count: 5,
    generation_mode: 'self_test',
    courseware_content: courseware?.content ?? '',
  }
  try {
    const { data } = await agentApi.post<ExerciseGenerationResponse>('/exercises/generate', payload)
    const exerciseSet = (data as any).data ?? data
    coordination.value!.outputs.exercise_generation_agent = {
      status: 'completed',
      exercise_set: exerciseSet,
    }
  } catch (error: any) {
    window.sessionStorage.removeItem(EXERCISE_STORAGE_KEY)
    coordination.value!.outputs.exercise_generation_agent = {
      status: 'failed',
      error: error?.response?.data?.detail ?? error?.message ?? '练习生成失败',
    }
  }
}

function persistCoordinatedCourseware() {
  const resourceResult = coordination.value?.outputs?.resource_generation_agent?.resource as ResourceResult | undefined
  if (!resourceResult) {
    return
  }
  const selectedVariantId =
    resourceResult.variants?.find((item) => item.is_recommended)?.variant_id
    ?? resourceResult.variants?.[0]?.variant_id
    ?? ''

  window.sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify({
    subject: pathForm.subject,
    topic: pathForm.knowledge_point,
    goal: learningPath.value?.overview ?? '',
    selectedVariantId,
    generatedAt: Date.now(),
    resourceResult,
  }))
}

function persistCoordinatedExercises() {
  const exerciseSet = coordination.value?.outputs?.exercise_generation_agent?.exercise_set as ExerciseGenerationResponse | undefined
  if (!exerciseSet) {
    return
  }
  window.sessionStorage.setItem(EXERCISE_STORAGE_KEY, JSON.stringify({
    generatedAt: Date.now(),
    source: 'learning_path',
    exerciseSet,
  }))
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
        <p>由画像、知识图谱、路径规划、资源生成和练习生成智能体联合作用。</p>
      </div>
    </header>

    <section class="path-layout">
      <main class="path-main">
        <div class="path-form">
          <input v-model="pathForm.subject" placeholder="学科" />
          <input v-model="pathForm.knowledge_point" placeholder="知识点 / 主题" />
          <button :disabled="loading" @click="generateLearningPath">
            {{ loading ? '协同生成中...' : '协同生成路径' }}
          </button>
        </div>

        <div v-if="pathError" class="path-error">{{ pathError }}</div>

        <div v-if="learningPath" class="timeline">
          <article v-for="stage in learningPath.stages" :key="stage.stage_id" class="stage-item">
            <span class="stage-dot" :class="{ done: stage.tasks.every((task) => task.completed) }"></span>
            <div class="stage-card">
              <h3>{{ stage.title }}</h3>
              <p>{{ stage.description }}</p>
              <div class="task-list">
                <article v-for="task in stage.tasks" :key="task.task_id" class="task-chip" :class="{ done: task.completed }">
                  <div>
                    <strong>{{ task.title }}</strong>
                    <span>{{ task.task_type }} · {{ task.estimated_minutes }} 分钟 · {{ task.difficulty }}</span>
                  </div>
                  <button v-if="!task.completed" @click="adjustTask(task.task_id, 'complete')">完成</button>
                  <button v-else @click="adjustTask(task.task_id, 'skip')">撤销</button>
                </article>
              </div>
            </div>
          </article>
        </div>

        <div v-else-if="!pathError" class="empty-state">
          输入学科和知识点后，系统会一次性生成路径、课件和练习。
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

.path-form input {
  min-width: 140px;
  flex: 1;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
  color: var(--text);
  padding: 11px 14px;
  font: inherit;
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

.path-error {
  margin-bottom: 14px;
  padding: 14px 16px;
  border-radius: 12px;
  color: var(--red);
  background: color-mix(in srgb, var(--red) 8%, transparent);
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
}

.task-chip.done {
  border-color: color-mix(in srgb, var(--green) 55%, transparent);
}

.task-chip strong,
.task-chip span {
  display: block;
}

.task-chip button {
  padding: 7px 12px;
  background: var(--panel-strong);
  color: var(--text);
  border: 1px solid var(--line);
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
  .path-layout {
    grid-template-columns: 1fr;
  }
}
</style>
