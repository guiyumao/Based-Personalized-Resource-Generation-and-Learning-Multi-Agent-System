<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { agentApi, evaluationApi, userApi } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import { renderLearningMarkdown } from '../../utils/renderLearningMarkdown'
import ResourceArtifactPanel from '../../components/ResourceArtifactPanel.vue'
import CoursewareReader from '../../components/CoursewareReader.vue'
import MindmapEditor from '../../components/MindmapEditor.vue'

type Task = { task_id: string; title: string; task_type: string; knowledge_point: string; completed: boolean }
type Stage = { stage_id: string; title: string; tasks: Task[] }
type Plan = { id: number; data: { subject: string; knowledge_point: string; stages: Stage[] } }
type StudyResource = { id: number; title: string; type: string; version: string; content?: string; structured_json?: string; teaching_schema?: string }
type TaskResource = StudyResource & { plan_id: number; module_id: string; task_id: string; context_id: string }
type Quiz = { exercise_id: number; prompt: string; options: string[]; question_type: string; feedback?: { score: number; max_score: number; is_correct: boolean; explanation: string } }
type Snapshot = { id: string; plan_id: number; module_id: string; task_id: string; knowledge_point: string; knowledge_point_id: number; subject: string; plan_revision: number; resource: StudyResource | null; resource_candidates: StudyResource[]; exercises: Quiz[] }
const route = useRoute(); const router = useRouter(); const auth = useAuthStore()
const plans = ref<Plan[]>([]); const planId = ref<number>()
const taskResources = ref<TaskResource[]>([])
const snapshot = ref<Snapshot | null>(null); const loading = ref(false); const error = ref('')
const toolsOpen = ref(true); const outlineOpen = ref(true)
const question = ref(''); const answer = ref(''); const conversationId = ref<number>(); const asking = ref(false)
const noteBody = ref(''); const noteTitle = ref(''); const noteSaved = ref(false)
const answers = ref<Record<number, string>>({}); const attemptIds = ref<Record<number, string>>({})
type Job = { partial_resource?: { id: number; title: string; content: string; structured_json: string }; id: number; status: string; current_step: string; result?: { cards?: { learning_context_id?: string }[]; content?: string; evidence?: { knowledge_coverage?: { state: string }; knowledge_supplementation?: { status: string; candidate_ids: number[]; reused: boolean } } } }
const job = ref<Job | null>(null)
const submitting = ref(false); const allowWeb = ref(true)
const jobBusy = computed(() => submitting.value || !!job.value && !['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.value.status))
const reusableCourseware = computed(() => snapshot.value?.resource_candidates.find(item => item.type === 'courseware' && item.teaching_schema === 'teaching-v2' && taskResources.value.some(binding => binding.id === item.id && binding.plan_id === snapshot.value?.plan_id && binding.module_id === snapshot.value?.module_id && binding.task_id === snapshot.value?.task_id)))
const hasCourseware = computed(() => !!reusableCourseware.value)
const supplementationText = computed(() => {
  const evidence = job.value?.result?.evidence
  const saved = evidence?.knowledge_supplementation
  if (!saved) return ''
  const labels: Record<string, string> = { NOT_NEEDED: '已有资料覆盖当前主题，无需补充', DISABLED: '未启用联网补充', SEARCH_FAILED: '补充检索失败，未新增资料', FETCH_FAILED: '来源正文获取失败，未新增资料', NO_SOURCES: '未找到可用补充来源', UNRESOLVED_POINT: '当前主题尚未关联正式知识点，未自动补库' }
  return saved.status === 'SAVED_PENDING_REVIEW' ? `${saved.reused ? '复用已入库资料' : '补充资料已入库'}：候选 #${saved.candidate_ids.join('、#')}，待审核后进入公共知识库` : labels[saved.status] || saved.status
})
function resourcesFor(stage: Stage, task: Task) { return taskResources.value.filter(item => item.plan_id === planId.value && item.module_id === stage.stage_id && item.task_id === task.task_id) }
let selectionSequence = 0
let timer: ReturnType<typeof setInterval> | undefined
const selectedPlan = computed(() => plans.value.find(plan => plan.id === planId.value))
const resourceHtml = computed(() => renderLearningMarkdown(snapshot.value?.resource?.content ?? ''))
const supportedText = computed(() => ['article', 'courseware', 'notes', 'text', 'summary', 'code_case'].includes(snapshot.value?.resource?.type ?? ''))
function describe(reason: any) { const detail = reason?.response?.data?.detail; return typeof detail === 'string' ? detail : detail?.message ?? reason?.message ?? '服务暂不可用' }
async function catalog() {
  try {
    const { data } = await agentApi.get('/learning/contexts/catalog')
    plans.value = data.plans; taskResources.value = data.task_resources || []
    const requestedPlan = Number(route.query.plan)
    planId.value ??= plans.value.some(plan => plan.id === requestedPlan) ? requestedPlan : plans.value[0]?.id
  }
  catch (reason) { error.value = describe(reason) }
}
async function switchPlan() {
  selectionSequence += 1
  snapshot.value = null
  await router.replace({ path: '/student/workspace', query: { plan: String(planId.value) } })
}
async function load() {
  const contextId = String(route.params.contextId ?? '')
  if (!contextId) { snapshot.value = null; return }
  error.value = ''; loading.value = true
  try {
    const data = (await agentApi.get(`/learning/contexts/${contextId}`)).data
    if (String(route.params.contextId) === contextId) {
      snapshot.value = data; planId.value = data.plan_id
      const pending = Number(sessionStorage.getItem(`workspace-job:${contextId}`))
      if (pending && job.value?.id !== pending) {
        job.value = { id: pending, status: 'PENDING', current_step: '恢复任务进度' }
        clearInterval(timer); timer = setInterval(() => void pollJob(contextId), 2000)
        void pollJob(contextId)
      }
    }
  } catch (reason) { if (String(route.params.contextId) === contextId) { snapshot.value = null; error.value = describe(reason) } }
  finally { if (String(route.params.contextId) === contextId) loading.value = false }
}
async function openTask(stage: Stage, task: Task, resource?: StudyResource) {
  if (!planId.value) return
  resource ??= resourcesFor(stage, task)[0]
  const existing = resource && resourcesFor(stage, task).find(item => item.id === resource!.id && item.version === resource!.version)
  if (existing) { await router.push(`/student/workspace/${existing.context_id}`); return }
  const sequence = ++selectionSequence
  error.value = ''; loading.value = true
  try {
    const { data } = await agentApi.post('/learning/contexts', { client_request_id: crypto.randomUUID(), plan_id: planId.value,
      module_id: stage.stage_id, task_key: task.task_id, resource_id: resource?.id, expected_resource_version: resource?.version })
    if (sequence === selectionSequence) await router.push(`/student/workspace/${data.id}`)
  } catch (reason) { error.value = describe(reason) }
  finally { loading.value = false }
}
async function openResource(resource: StudyResource) {
  const stage = selectedPlan.value?.data.stages.find(stage => stage.stage_id === snapshot.value?.module_id)
  const task = stage?.tasks.find(task => task.task_id === snapshot.value?.task_id)
  if (stage && task) await openTask(stage, task, resource)
}
async function ask() {
  const current = snapshot.value; if (!current || !question.value.trim() || asking.value) return
  asking.value = true; error.value = ''
  try {
    const { data } = await agentApi.post('/assistant/chat', { message: question.value, action: 'qa', conversation_id: conversationId.value,
      learning_context_id: current.id, client_request_id: crypto.randomUUID(), use_learning_context: false })
    if (snapshot.value?.id === current.id) { answer.value = data.message.content; conversationId.value = data.conversation_id }
  } catch (reason) { error.value = describe(reason) }
  finally { asking.value = false }
}
async function saveNote() {
  const current = snapshot.value; if (!current || !noteBody.value.trim()) return
  error.value = ''; noteSaved.value = false
  try {
    await userApi.post('/study/notes', { title: noteTitle.value || current.knowledge_point, body: noteBody.value,
      learning_context_id: current.id, source_resource_id: current.resource?.id, source_locator: 'workspace-user-note' })
    if (snapshot.value?.id === current.id) noteSaved.value = true
  } catch (reason) { error.value = describe(reason) }
}
async function pollJob(contextId: string) {
  if (!job.value || snapshot.value?.id !== contextId) return
  const id = job.value.id
  try {
    const update: Job = (await agentApi.get(`/assistant/tasks/${id}`)).data
    if (snapshot.value?.id !== contextId || job.value?.id !== id) return
    job.value = update
    if (['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(update.status)) {
      clearInterval(timer); sessionStorage.removeItem(`workspace-job:${contextId}`)
      await catalog()
      const linked = update.result?.cards?.find(card => card.learning_context_id)?.learning_context_id
      if (linked && update.status === 'SUCCEEDED') await router.replace(`/student/workspace/${linked}`)
      else await load()
      job.value = update
    }
  } catch (reason) { clearInterval(timer); error.value = describe(reason) }
}
async function generate(action: 'courseware' | 'exercise', force = false) {
  const current = snapshot.value; if (!current) return
  if (jobBusy.value) return
  const reusable = reusableCourseware.value
  if (action === 'courseware' && reusable && !force) { await openResource(reusable); return }
  submitting.value = true
  error.value = ''
  try {
    const { data } = await agentApi.post('/assistant/chat', { message: `${force ? '重新生成' : '生成'}${current.knowledge_point}的${action === 'exercise' ? '3道练习' : '课件'}`,
      action, knowledge_point: current.knowledge_point, learning_context_id: current.id, course_key: current.subject,
      allow_web_knowledge: allowWeb.value, client_request_id: crypto.randomUUID(), exercise_count: 3 })
    if (snapshot.value?.id !== current.id) return
    job.value = data.task
    sessionStorage.setItem(`workspace-job:${current.id}`, String(data.task.id))
    clearInterval(timer)
    timer = setInterval(() => void pollJob(current.id), 2000)
  } catch (reason) { error.value = describe(reason) }
  finally { submitting.value = false }
}
async function submit(quiz: Quiz) {
  const current = snapshot.value; if (!current) return
  error.value = ''; attemptIds.value[quiz.exercise_id] ??= crypto.randomUUID()
  try {
    await evaluationApi.post('/evaluation/practice/submit', { user_id: auth.user!.userId, exercise_id: quiz.exercise_id,
      learning_context_id: current.id, client_request_id: attemptIds.value[quiz.exercise_id], knowledge_point: current.knowledge_point,
      question_type: quiz.question_type, user_answer: answers.value[quiz.exercise_id] ?? '', correct_answer: '', analysis: '', subject: current.subject })
    if (snapshot.value?.id === current.id) await load()
  } catch (reason) { error.value = describe(reason) }
}
watch(() => route.params.contextId, () => {
  snapshot.value = null; conversationId.value = undefined; question.value = ''; answer.value = ''; noteBody.value = ''; noteSaved.value = false
  clearInterval(timer); job.value = null; answers.value = {}; attemptIds.value = {}; void load()
})
onMounted(async () => { await catalog(); await load() })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="study-workspace">
    <header><div><h1>学习工作区</h1><p>学习目录、资源和助手共享服务端校验的上下文</p></div><div><el-button @click="outlineOpen = !outlineOpen">学习目录</el-button><el-button @click="toolsOpen = !toolsOpen">学习工具</el-button><el-button @click="load">刷新上下文</el-button></div></header>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <div class="workspace-columns" :class="{ 'hide-outline': !outlineOpen, 'hide-tools': !toolsOpen }">
      <aside v-if="outlineOpen" class="workspace-outline" aria-label="学习目录">
        <el-select v-model="planId" aria-label="选择学习计划" @change="switchPlan"><el-option v-for="plan in plans" :key="plan.id" :value="plan.id" :label="`${plan.data.subject} · ${plan.data.knowledge_point}`" /></el-select>
        <p v-if="!plans.length">暂无进行中的计划，请先创建学习计划。</p>
        <section v-for="stage in selectedPlan?.data.stages" :key="stage.stage_id"><h3>{{ stage.title }}</h3><div v-for="task in stage.tasks" :key="task.task_id" class="outline-task"><button type="button" :aria-current="snapshot?.task_id === task.task_id ? 'true' : undefined" @click="openTask(stage, task)"><span>{{ task.completed ? '✓' : '○' }} {{ task.title }}</span><small>{{ task.knowledge_point }}</small></button><button v-for="resource in resourcesFor(stage, task)" :key="resource.id" class="outline-resource" :aria-current="snapshot?.resource?.id === resource.id && snapshot?.task_id === task.task_id ? 'true' : undefined" @click="openTask(stage, task, resource)">↳ {{ resource.title }}<small>课件 #{{ resource.id }}</small></button></div></section>
        <el-button @click="router.push('/student/learning-path')">计划管理</el-button>
      </aside>
      <main class="workspace-content" aria-label="学习资源">
        <el-skeleton v-if="loading" :rows="5" animated />
        <template v-else-if="snapshot">
          <h2>{{ selectedPlan?.data.stages.find(stage => stage.stage_id === snapshot?.module_id)?.tasks.find(task => task.task_id === snapshot?.task_id)?.title || snapshot.knowledge_point }}</h2><p class="context-caption">计划 #{{ snapshot.plan_id }} · {{ snapshot.module_id }} · {{ snapshot.task_id }} · revision {{ snapshot.plan_revision }}</p>
          <details class="related-resources"><summary>其他同知识点资源（{{ snapshot.resource_candidates.length }}）</summary><div class="workspace-resources"><el-button v-for="resource in snapshot.resource_candidates" :key="resource.id" size="small" @click="openResource(resource)">{{ resource.title || '资源' }} · #{{ resource.id }}</el-button></div></details>
          <template v-if="snapshot.resource"><h3>{{ snapshot.resource.title }}</h3><p class="context-caption">资源 #{{ snapshot.resource.id }} · 版本 {{ snapshot.resource.version.slice(0, 12) }}</p>
            <CoursewareReader v-if="snapshot.resource.type === 'courseware'" :key="snapshot.id" :content="snapshot.resource.content || ''" :resource-id="snapshot.resource.id" :version="snapshot.resource.version" :structured="snapshot.resource.structured_json" /><div v-else-if="supportedText" class="markdown-content" v-html="resourceHtml" />
            <MindmapEditor v-else-if="snapshot.resource.type === 'mind_map'" :key="snapshot.id" :context-id="snapshot.id" :version="snapshot.resource.version" :structured="snapshot.resource.structured_json || '{}'" @saved="catalog(); snapshot=null; error='导图新版本已保存，请重新选择任务和资源。'"/>
            <el-alert v-else title="此类型请在资源中心使用专用预览；当前未提供工作区播放器。" type="info" :closable="false" />
          </template>
          <p v-else>当前任务尚未选择资源。可打开上方已有资源，或提交课件生成任务。</p>
          <div class="workspace-actions"><el-button :disabled="jobBusy" @click="generate('courseware')">{{ hasCourseware ? '打开已有课件' : '生成课件' }}</el-button><el-button v-if="hasCourseware" :disabled="jobBusy" @click="generate('courseware', true)">重新生成课件</el-button><el-button :disabled="jobBusy" @click="generate('exercise')">生成3道练习</el-button><el-checkbox v-model="allowWeb" :disabled="jobBusy">资料不足时联网补充并保存</el-checkbox></div>
          <section v-if="job?.partial_resource && job.status !== 'SUCCEEDED'" class="partial-courseware"><h3>{{ job.partial_resource.title }} · 已保存章节</h3><p>已完成的章节可先阅读，其余章节继续生成。</p><CoursewareReader :content="job.partial_resource.content" :structured="job.partial_resource.structured_json" /></section>
          <ResourceArtifactPanel v-if="snapshot.resource" :key="snapshot.id" :context-id="snapshot.id"/>
          <el-alert v-if="job" :title="`任务 #${job.id} · ${job.status} · ${job.current_step}`" :type="job.status === 'FAILED' ? 'error' : 'info'" :closable="false"><div v-if="job.result?.content">{{ job.result.content }}</div><p v-if="supplementationText">{{ supplementationText }}</p></el-alert>
          <section v-for="quiz in snapshot.exercises" :key="quiz.exercise_id" class="workspace-quiz"><div class="markdown-content quiz-prompt" v-html="renderLearningMarkdown(quiz.prompt)" /><div v-for="option in quiz.options" :key="option" class="markdown-content quiz-option" v-html="renderLearningMarkdown(option)" /><el-input v-model="answers[quiz.exercise_id]" :aria-label="`题目${quiz.exercise_id}答案`" placeholder="输入你的答案" /><el-button @click="submit(quiz)">提交作答</el-button><el-alert v-if="quiz.feedback" :title="`${quiz.feedback.is_correct ? '回答正确' : '需要复习'} · ${quiz.feedback.score}/${quiz.feedback.max_score}`" :type="quiz.feedback.is_correct ? 'success' : 'warning'" :closable="false"><div v-html="renderLearningMarkdown(quiz.feedback.explanation)" /></el-alert></section>
        </template>
        <p v-else-if="!error">从左侧选择一个学习任务。</p>
      </main>
      <aside v-if="toolsOpen" class="workspace-tools" aria-label="当前上下文与学习工具">
        <template v-if="snapshot"><h2>学习助手</h2><p>{{ snapshot.subject }} / {{ snapshot.knowledge_point }}</p><p class="context-caption">上下文 {{ snapshot.id }}</p><el-input v-model="question" type="textarea" :rows="3" aria-label="围绕当前资源提问" placeholder="围绕当前任务或资源提问" /><el-button :loading="asking" @click="ask">提问</el-button><div v-if="answer" class="workspace-answer" v-html="renderLearningMarkdown(answer)" />
          <h3>当前资源笔记</h3><el-input v-model="noteTitle" aria-label="笔记标题" placeholder="笔记标题" /><el-input v-model="noteBody" type="textarea" :rows="4" aria-label="笔记正文" placeholder="记录想法；保存时关联当前资源及版本" /><el-button @click="saveNote">保存笔记</el-button><p v-if="noteSaved" role="status">笔记已保存并关联当前上下文</p><el-button @click="router.push('/student/study-tools')">笔记与闪卡</el-button>
        </template><p v-else>选择学习任务后启用助手和笔记。</p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.study-workspace { display:grid; gap:18px; min-width:0; } header { display:flex; justify-content:space-between; flex-wrap:wrap; gap:14px; } h1 { margin:0; font-size:26px; } h2 { font-size:20px; } p,.context-caption { color:var(--muted); line-height:1.7; } .context-caption { font-size:12px; overflow-wrap:anywhere; }
.workspace-columns { display:grid; grid-template-columns:230px minmax(0,1fr) 300px; gap:16px; align-items:start; }.workspace-columns.hide-outline { grid-template-columns:minmax(0,1fr) 300px; }.workspace-columns.hide-tools { grid-template-columns:230px minmax(0,1fr); }.workspace-columns.hide-tools.hide-outline { grid-template-columns:minmax(0,1fr); }
.workspace-columns>aside,.workspace-content { min-width:0; border:1px solid var(--line); background:var(--panel); padding:18px; border-radius:14px; overflow-wrap:anywhere; }.workspace-content { max-height:78vh; overflow-y:auto; }.workspace-outline button { display:block; width:100%; text-align:left; margin:8px 0; background:var(--surface-muted); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:10px; cursor:pointer; }.workspace-outline small { display:block; margin-top:6px; color:var(--muted); }.workspace-outline button[aria-current] { border-color:var(--accent); }.workspace-outline .outline-resource { margin-left:12px; width:calc(100% - 12px); background:var(--panel); font-size:12px; } .quiz-prompt { font-weight:600; line-height:1.8; } .quiz-option :deep(p) { margin:6px 0; } .workspace-resources,.workspace-actions { display:flex; gap:8px; flex-wrap:wrap; margin:14px 0; }.workspace-tools { display:grid; gap:12px; }.workspace-quiz { padding:16px 0; border-top:1px solid var(--line); }.workspace-quiz .el-input { margin:12px 0; }.workspace-answer { border-top:1px solid var(--line); padding-top:14px; }.markdown-content :deep(pre) { overflow-x:auto; }
@media(max-width:1150px) { .workspace-columns { grid-template-columns:190px minmax(0,1fr); }.workspace-tools { grid-column:1/-1; }.workspace-columns.hide-outline { grid-template-columns:minmax(0,1fr); } }
@media(max-width:650px) { .workspace-columns,.workspace-columns.hide-tools { grid-template-columns:minmax(0,1fr); }.workspace-content { max-height:none; overflow:visible; } }
</style>
