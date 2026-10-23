
import { computed, onMounted, reactive, ref, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Collection, Key, Setting, Tickets } from '@element-plus/icons-vue'

import {
  agentApi,
  resourceApi,
  systemApi,
  userApi,
  type ApiEnvelope,
  type AuditLogItem,
  type IllustrateResult,
  type ImageProviderStatus,
  type ManagedResourceItem,
  type PromptTemplateDetail,
  type PromptTemplateSummary,
  type PromptVersionSummary,
  type ResourceIllustration,
  type ResourceRewriteResult,
  type ResourceSection,
  type RoleAssignmentPayload,
  type SubjectItem,
  type SystemConfigItem,
  type SystemConfigUpdatePayload,
} from '../api'
import { useAuthStore } from '../stores/auth'

type AdminDashboard = { total_users: number; active_users: number; total_learning_paths: number; total_resources: number; answers_last_7_days: number; token_usage_available: boolean }
type AdminUser = { id: number; username: string; email: string | null; role: string; is_active: boolean; created_at: string }
type AdminUserPage = { total: number; page: number; size: number; items: AdminUser[] }
type KnowledgeStatus = { available: boolean; corpus: { documents: number; subjects: Record<string, number> }; index: { documents: number; chunks: number; updated_at: string }; sources: { configured: number } }
type KnowledgeSource = { id: string; url: string; subject: string; topic: string; status: string; local_path: string }
type KnowledgeTask = { id: number; operation_type: string; subject: string; status: string; current_step: string; error_code: string; result: Record<string, unknown> }
type CandidateSource = { title: string; url: string; summary: string }
type FetchedSource = { title: string; url: string; content: string; truncated?: boolean }
type MaintenancePlan = { id: number; name: string; subject: string; interval_hours: number | null; enabled: boolean; next_run_at: string | null; last_task_id: number | null }
type KnowledgeCandidate = { id: number; source_task_id: number; subject: string; knowledge_point: string; title: string; content: string; source_url: string; status: string; review_notes: string; published_version_id: number | null; license_name: string; license_evidence_url: string; publication_allowed: boolean }
type ConstructionSubject = { id: number; name: string; code: string | null; status: string }
type ConstructionPoint = { id: number; name: string; chapter: string; status: string }
type OutlineReviewPoint = { name: string; aliases: string[]; prerequisites: string[]; objectives: string[]; kept: boolean }
type OutlineReviewChapter = { name: string; points: OutlineReviewPoint[] }
type OutlineReview = { taskId: number; name: string; code: string; aliases: string[]; description: string; chapters: OutlineReviewChapter[] }
type KnowledgeVersion = { id: number; candidate_id: number; number: number; title: string; content: string; is_active: boolean; published_at: string }


export function useAdminWorkspace(module: string) {
const router = useRouter()
const authStore = useAuthStore()

const subjects = ref<SubjectItem[]>([])
const configs = ref<SystemConfigItem[]>([])
const logs = ref<AuditLogItem[]>([])
const dashboard = ref<AdminDashboard | null>(null)
const userPage = ref<AdminUserPage | null>(null)
const knowledgeStatus = ref<KnowledgeStatus | null>(null)
const knowledgeSources = ref<KnowledgeSource[]>([])
const knowledgeTasks = ref<KnowledgeTask[]>([])
const taskSubject = ref('')
const taskQuery = ref('')
const maintenancePlans = ref<MaintenancePlan[]>([])
const knowledgeCandidates = ref<KnowledgeCandidate[]>([])
const constructionSubjects = ref<ConstructionSubject[]>([])
const constructionPoints = ref<ConstructionPoint[]>([])
const constructionSubjectId = ref<number>()
const constructionSelectedPoints = ref<number[]>([])
const constructionForm = reactive({ name: '', stage: '本科', requirements: '', reference_material: '' })
const outlineReview = ref<OutlineReview | null>(null)
const outlineStatus = ref<'idle' | 'queued' | 'running' | 'ready' | 'failed'>('idle')
const outlineError = ref('')
const outlinePollCount = ref(0)
const outlineTaskId = ref<number>()
const constructionBusy = ref(false)
const manualPoint = reactive({ name: '', chapter: '', objective: '' })
const constructionFocus = ref('')
const knowledgeVersions = ref<KnowledgeVersion[]>([])
const oldVersionId = ref<number>()
const newVersionId = ref<number>()
const versionComparison = ref('')
const maintenanceReport = ref('')
const taskUsage = ref('')
const versionImpact = ref('')
const planForm = reactive({ name: '', firstRun: '', intervalHours: '168', mode: 'INSPECT_ONLY', chapter: '', maxPoints: 3, repairIndex: false })
const knowledgeError = ref('')
const managedResources = ref<ManagedResourceItem[]>([])
const resourceError = ref('')
const resourceFilter = ref('')
const selectedResource = ref<ManagedResourceItem | null>(null)
const userKeyword = ref('')
const userRole = ref('')
const newUser = reactive({ username: '', password: '', email: '', role: 'student' })
const currentUserPage = ref(1)
const selectedConfigKey = ref('resource_generation_timeout')

const roleForm = reactive<RoleAssignmentPayload>({
  user_id: 1,
  role: 'teacher',
})

const configForm = reactive<SystemConfigUpdatePayload>({
  value: '20',
})

const logFilter = ref('')
const roleResult = ref<Record<string, unknown> | null>(null)

// ── P1-07 提示词优化 / 改写 / 图文编排 ──
const prompts = ref<PromptTemplateSummary[]>([])
const selectedPromptName = ref('')
const promptContent = ref('')
const promptPlaceholders = ref<string[]>([])
const promptVersions = ref<PromptVersionSummary[]>([])
const imageProvider = ref<ImageProviderStatus | null>(null)
const imageProviderForm = reactive({ provider: '', model: '' })
const rewriteInstruction = ref('')
const rewriteStyle = ref('plain')
const rewriteResult = ref<ResourceRewriteResult | null>(null)
const rewriteBusy = ref(false)
const resourceSections = ref<ResourceSection[]>([])
const resourceIllustrations = ref<ResourceIllustration[]>([])
const illustratePrompt = ref('')
const illustrateBusy = ref(false)

const loading = reactive({
  role: false,
  subjects: false,
  configs: false,
  updateConfig: false,
  logs: false,
  dashboard: false,
  users: false,
  createUser: false,
  status: false,
  knowledge: false,
  sources: false,
  reindex: false,
  knowledgeTasks: false,
  maintenancePlans: false,
  candidates: false,
  resources: false,
  resourceStatus: false,
  prompts: false,
  imageProvider: false,
})

const configKeys = computed(() => configs.value.map((item) => item.key))
const visibleLogs = computed(() => logs.value)
const visibleResources = computed(() => managedResources.value.filter(item => !resourceFilter.value || item.title.toLowerCase().includes(resourceFilter.value.toLowerCase()) || String(item.id) === resourceFilter.value))
const adminStats = computed<{ label: string; value: number | string; icon: Component; hint: string }[]>(() => [
  { label: '用户总数', value: dashboard.value?.total_users ?? '—', icon: Key, hint: '已注册账号' },
  { label: '启用标记数', value: dashboard.value?.active_users ?? '—', icon: Tickets, hint: '按账号 is_active 字段统计' },
  { label: '学习路径', value: dashboard.value?.total_learning_paths ?? '—', icon: Collection, hint: '已保存路径' },
  { label: '学习资源', value: dashboard.value?.total_resources ?? '—', icon: Setting, hint: '已保存资源' },
])

async function fetchDashboard() {
  loading.dashboard = true
  try {
    const { data } = await systemApi.get<ApiEnvelope<AdminDashboard>>('/system/dashboard')
    dashboard.value = data.data
  } catch {
    ElMessage.error('管理统计获取失败')
  } finally {
    loading.dashboard = false
  }
}

async function fetchUsers(page = currentUserPage.value) {
  loading.users = true
  try {
    const params = new URLSearchParams({ page: String(page), size: '10' })
    if (userKeyword.value.trim()) params.set('keyword', userKeyword.value.trim())
    if (userRole.value) params.set('role', userRole.value)
    const { data } = await systemApi.get<ApiEnvelope<AdminUserPage>>(`/system/users?${params}`)
    userPage.value = data.data
    currentUserPage.value = page
  } catch {
    ElMessage.error('用户列表获取失败')
  } finally {
    loading.users = false
  }
}

function selectUser(item: AdminUser) {
  roleForm.user_id = item.id
  roleForm.role = item.role
}

async function createUser() {
  if (newUser.username.trim().length < 3 || newUser.password.length < 6) {
    ElMessage.error('用户名至少 3 字，密码至少 6 位')
    return
  }
  loading.createUser = true
  try {
    await userApi.post('/users', { ...newUser, email: newUser.email.trim() || null })
    newUser.username = ''
    newUser.password = ''
    newUser.email = ''
    ElMessage.success('账号已创建')
    await Promise.all([fetchUsers(1), fetchDashboard()])
  } catch {
    ElMessage.error('创建账号失败；请检查用户名是否重复')
  } finally {
    loading.createUser = false
  }
}

async function setUserStatus(item: AdminUser) {
  loading.status = true
  try {
    await systemApi.patch(`/system/users/${item.id}/status`, { is_active: !item.is_active })
    ElMessage.success(item.is_active ? '账号已停用' : '账号已启用')
    await Promise.all([fetchUsers(), fetchDashboard(), fetchLogs()])
  } catch {
    ElMessage.error('账号状态更新失败；当前管理员不能停用自身账号')
  } finally {
    loading.status = false
  }
}

async function fetchKnowledgeStatus() {
  loading.knowledge = true
  knowledgeError.value = ''
  try {
    const { data } = await agentApi.get<KnowledgeStatus>('/knowledge-base/status')
    knowledgeStatus.value = data
  } catch {
    knowledgeError.value = '知识库服务当前不可用。'
  } finally {
    loading.knowledge = false
  }
}

async function fetchKnowledgeSources() {
  loading.sources = true
  try {
    const { data } = await agentApi.get<{ total: number; items: KnowledgeSource[] }>('/knowledge-base/sources')
    knowledgeSources.value = data.items
  } catch {
    ElMessage.error('知识库来源列表获取失败')
  } finally {
    loading.sources = false
  }
}

async function reindexKnowledgeBase() {
  try {
    await ElMessageBox.confirm('将根据当前本地语料增量更新向量索引，可能需要一些时间。继续吗？', '重建知识库索引', { type: 'warning' })
  } catch { return }
  loading.reindex = true
  try {
    await startKnowledgeTask('INDEX_REPAIR')
  } catch {
    ElMessage.error('索引更新失败或已有任务运行中')
  } finally {
    loading.reindex = false
  }
}

async function fetchKnowledgeTasks() {
  loading.knowledgeTasks = true
  try {
    const { data } = await agentApi.get<{ items: KnowledgeTask[] }>('/knowledge-base/tasks?limit=10')
    knowledgeTasks.value = data.items
  } catch {
    ElMessage.error('知识任务列表获取失败')
  } finally {
    loading.knowledgeTasks = false
  }
}

async function fetchMaintenancePlans() {
  loading.maintenancePlans = true
  try {
    const { data } = await agentApi.get<{ items: MaintenancePlan[] }>('/knowledge-base/maintenance-plans')
    maintenancePlans.value = data.items
  } catch {
    ElMessage.error('维护计划获取失败')
  } finally {
    loading.maintenancePlans = false
  }
}

async function createMaintenancePlan() {
  if (!planForm.name.trim() || !planForm.firstRun) {
    ElMessage.warning('请填写计划名称和首次执行时间')
    return
  }
  loading.maintenancePlans = true
  try {
    await agentApi.post('/knowledge-base/maintenance-plans', {
      name: planForm.name.trim(),
      subject: taskSubject.value.trim(),
      next_run_at: new Date(planForm.firstRun).toISOString(),
      interval_hours: planForm.intervalHours === 'once' ? null : Number(planForm.intervalHours),
      policy: { mode: planForm.mode, chapter: planForm.chapter, max_supplement_points: planForm.maxPoints, max_search_calls: planForm.maxPoints, max_fetch_calls: planForm.maxPoints, repair_index: planForm.repairIndex },
    })
    ElMessage.success('维护计划已保存')
    planForm.name = ''
    await fetchMaintenancePlans()
  } catch {
    ElMessage.error('维护计划创建失败；请检查首次执行时间')
  } finally {
    loading.maintenancePlans = false
  }
}

async function toggleMaintenancePlan(plan: MaintenancePlan) {
  try {
    await agentApi.patch(`/knowledge-base/maintenance-plans/${plan.id}`, { enabled: !plan.enabled })
    await fetchMaintenancePlans()
  } catch {
    ElMessage.error('计划状态更新失败')
  }
}

async function startKnowledgeTask(operation: 'KNOWLEDGE_HEALTH_CHECK' | 'INDEX_REPAIR') {
  await agentApi.post('/knowledge-base/tasks', {
    client_request_id: crypto.randomUUID(),
    operation_type: operation,
    subject: taskSubject.value.trim(),
  })
  ElMessage.success('知识任务已排队')
  await fetchKnowledgeTasks()
  await fetchMaintenancePlans()
}

function candidateSources(task: KnowledgeTask): CandidateSource[] {
  return Array.isArray(task.result?.sources) ? task.result.sources as CandidateSource[] : []
}

function fetchedSource(task: KnowledgeTask): FetchedSource | null {
  const source = task.result?.source
  return source && typeof source === 'object' ? source as FetchedSource : null
}

async function searchKnowledgeSources() {
  if (!taskQuery.value.trim()) {
    ElMessage.warning('请输入要补充的知识点')
    return
  }
  loading.knowledgeTasks = true
  try {
    await agentApi.post('/knowledge-base/tasks', {
      client_request_id: crypto.randomUUID(),
      operation_type: 'SEARCH_SOURCES',
      subject: taskSubject.value.trim(),
      query: taskQuery.value.trim(),
    })
    ElMessage.success('候选来源搜索已排队')
    await fetchKnowledgeTasks()
  } catch {
    ElMessage.error('搜索任务创建失败')
  } finally {
    loading.knowledgeTasks = false
  }
}

async function fetchCandidateSource(task: KnowledgeTask, index: number) {
  loading.knowledgeTasks = true
  try {
    await agentApi.post('/knowledge-base/tasks', {
      client_request_id: crypto.randomUUID(),
      operation_type: 'FETCH_SOURCE',
      source_task_id: task.id,
      source_index: index,
    })
    ElMessage.success('来源正文抓取已排队')
    await fetchKnowledgeTasks()
  } catch {
    ElMessage.error('抓取任务创建失败')
  } finally {
    loading.knowledgeTasks = false
  }
}

async function cancelKnowledgeTask(task: KnowledgeTask) {
  try {
    await agentApi.post(`/knowledge-base/tasks/${task.id}/request-cancel`)
    await fetchKnowledgeTasks()
  } catch {
    ElMessage.error('任务已结束或取消请求失败')
  }
}

async function viewTaskUsage(task: KnowledgeTask) {
  try { taskUsage.value = JSON.stringify((await agentApi.get(`/knowledge-base/tasks/${task.id}/usage`)).data, null, 2) }
  catch { ElMessage.error('用量记录读取失败') }
}

async function retryKnowledgeTask(task: KnowledgeTask) {
  try { await ElMessageBox.confirm('将复用已完成阶段继续执行，未完成的搜索、抓取或模型调用可能产生费用。继续？', '重试知识任务') }
  catch { return }
  try { await agentApi.post(`/knowledge-base/tasks/${task.id}/retry`); await fetchKnowledgeTasks() }
  catch { ElMessage.error('此任务不允许自动重试或已达到重试上限') }
}

async function viewVersionImpact(item: KnowledgeVersion) {
  try { versionImpact.value = JSON.stringify((await agentApi.get(`/knowledge-base/versions/${item.id}/impact`)).data, null, 2) }
  catch { ElMessage.error('关联资源读取失败') }
}

async function loadConstructionSubjects() {
  try { constructionSubjects.value = (await agentApi.get<{ items: ConstructionSubject[] }>('/knowledge-base/construction/subjects')).data.items }
  catch { ElMessage.error('学科建设目录加载失败') }
}

async function createManualConstructionPoint() {
  if (!constructionSubjectId.value) { ElMessage.warning('请先选择学科'); return }
  try {
    await agentApi.post(`/knowledge-base/construction/subjects/${constructionSubjectId.value}/points`, { name: manualPoint.name, chapter: manualPoint.chapter, objectives: [manualPoint.objective || `理解${manualPoint.name}`] })
    await loadConstructionPoints()
    ElMessage.success('知识点已保存，等待建设')
  } catch { ElMessage.error('知识点保存失败') }
}

function buildOutlineReview(outline: Record<string, any>, taskId: number): OutlineReview {
  return {
    taskId,
    name: String(outline.name ?? ''),
    code: String(outline.code ?? ''),
    aliases: Array.isArray(outline.aliases) ? outline.aliases.map(String) : [],
    description: String(outline.description ?? ''),
    chapters: (Array.isArray(outline.chapters) ? outline.chapters : []).map((chapter: Record<string, any>) => ({
      name: String(chapter.name ?? ''),
      points: (Array.isArray(chapter.points) ? chapter.points : []).map((point: Record<string, any>) => ({
        name: String(point.name ?? ''),
        aliases: Array.isArray(point.aliases) ? point.aliases.map(String) : [],
        prerequisites: Array.isArray(point.prerequisites) ? point.prerequisites.map(String) : [],
        objectives: Array.isArray(point.objectives) ? point.objectives.map(String) : [],
        kept: true,
      })),
    })),
  }
}

async function pollOutline(taskId: number) {
  outlineStatus.value = 'queued'
  outlineError.value = ''
  outlineReview.value = null
  outlinePollCount.value = 0
  for (let attempt = 1; attempt <= 100; attempt++) {
    outlinePollCount.value = attempt
    try {
      const { data } = await agentApi.get<KnowledgeTask>(`/knowledge-base/tasks/${taskId}`)
      if (data.status === 'COMPLETED') {
        const outline = (data.result ?? {}).outline as Record<string, any> | undefined
        if (!outline) { outlineStatus.value = 'failed'; outlineError.value = '规划任务完成但未返回大纲，请到任务监控查看详情'; return }
        outlineReview.value = buildOutlineReview(outline, taskId)
        outlineStatus.value = 'ready'
        return
      }
      if (data.status === 'FAILED' || data.status === 'BLOCKED') {
        outlineStatus.value = 'failed'
        outlineError.value = `大纲规划未完成（${data.error_code || data.status}），可调整要求后重试`
        return
      }
      outlineStatus.value = data.status === 'RUNNING' ? 'running' : 'queued'
    } catch {
      // 网络抖动：继续下一轮，不做中断
    }
    await new Promise(resolve => setTimeout(resolve, 3000))
  }
  outlineStatus.value = 'failed'
  outlineError.value = '等待规划结果超时，请稍后到「AI 用量与任务监控」查看任务状态'
}

function discardOutline() {
  outlineReview.value = null
  outlineStatus.value = 'idle'
  outlineError.value = ''
  outlineTaskId.value = undefined
}

async function planConstructionSubject() {
  constructionBusy.value = true
  try {
    const { data } = await agentApi.post<KnowledgeTask>('/knowledge-base/construction/subject-plans', { ...constructionForm, client_request_id: crypto.randomUUID() })
    outlineTaskId.value = data.id
    ElMessage.success('已提交 AI 规划，正在等待大纲生成')
    await fetchKnowledgeTasks()
    await pollOutline(data.id)
  } catch { ElMessage.error('规划提交失败；请检查名称是否已有确认大纲') }
  finally { constructionBusy.value = false }
}

function keptOutlinePayload(review: OutlineReview) {
  const chapters = review.chapters
    .map(chapter => ({ name: chapter.name, points: chapter.points.filter(point => point.kept) }))
    .filter(chapter => chapter.points.length > 0)
    .map(chapter => ({
      name: chapter.name,
      points: chapter.points.map(({ kept: _kept, ...point }) => point),
    }))
  return { name: review.name, code: review.code, aliases: review.aliases, description: review.description, chapters }
}

async function confirmConstructionOutline() {
  const review = outlineReview.value
  if (!review) return
  const payload = keptOutlinePayload(review)
  if (!payload.chapters.length) { ElMessage.warning('请至少保留一个知识点再确认'); return }
  constructionBusy.value = true
  try {
    await agentApi.post(`/knowledge-base/construction/subject-plans/${review.taskId}/confirm`, payload)
    ElMessage.success(`课程结构已确认：${review.chapters.reduce((sum, ch) => sum + ch.points.filter(p => p.kept).length, 0)} 个知识点等待建设`)
    discardOutline()
    await loadConstructionSubjects()
  } catch { ElMessage.error('确认失败：该学科可能已有确认的课程结构') }
  finally { constructionBusy.value = false }
}

async function loadConstructionPoints() {
  constructionSelectedPoints.value = []
  if (!constructionSubjectId.value) return
  constructionPoints.value = (await agentApi.get<{ items: ConstructionPoint[] }>(`/knowledge-base/construction/subjects/${constructionSubjectId.value}/points`)).data.items
}

async function buildConstructionPoints(mode: 'CREATE_POINT' | 'COMPLETE_POINT' | 'REVISE_POINT') {
  if (!constructionSelectedPoints.value.length || constructionSelectedPoints.value.length > 10) { ElMessage.warning('每批选择 1 至 10 个知识点'); return }
  constructionBusy.value = true
  try {
    await agentApi.post('/knowledge-base/construction/points/build', { client_request_id: crypto.randomUUID(), point_ids: constructionSelectedPoints.value, mode, focus: constructionFocus.value })
    ElMessage.success('知识点建设已排队，每点一次搜索，最多选取两个来源，结果进入候选审核')
    await fetchKnowledgeTasks()
  } catch { ElMessage.error('知识点建设排队失败') }
  finally { constructionBusy.value = false }
}

// 'ALL' keeps the historic behaviour; 'AUTO_APPROVED' isolates knowledge the
// system published on its own, which a human still has to review.
const candidateOriginFilter = ref<'ALL' | 'AUTO_APPROVED'>('ALL')

async function fetchKnowledgeCandidates() {
  loading.candidates = true
  try {
    const params = candidateOriginFilter.value === 'AUTO_APPROVED' ? { status: 'AUTO_APPROVED', limit: 100 } : {}
    const { data } = await agentApi.get<{ items: KnowledgeCandidate[] }>('/knowledge-base/candidates', { params })
    knowledgeCandidates.value = data.items
  } catch { ElMessage.error('候选知识列表获取失败') }
  finally { loading.candidates = false }
}

async function createKnowledgeCandidate(task: KnowledgeTask) {
  if (!taskSubject.value.trim() || !taskQuery.value.trim()) {
    ElMessage.warning('请先填写学科代码和知识点')
    return
  }
  loading.candidates = true
  try {
    await agentApi.post('/knowledge-base/candidates', { source_task_id: task.id, subject: taskSubject.value.trim(), knowledge_point: taskQuery.value.trim() })
    ElMessage.success('已创建候选知识，可继续编辑和送审')
    await fetchKnowledgeCandidates()
  } catch { ElMessage.error('候选创建失败；请确认抓取任务已完成') }
  finally { loading.candidates = false }
}

async function saveCandidate(item: KnowledgeCandidate) {
  try {
    await agentApi.patch(`/knowledge-base/candidates/${item.id}`, { subject: item.subject, knowledge_point: item.knowledge_point, title: item.title, content: item.content, license_name: item.license_name, license_evidence_url: item.license_evidence_url, publication_allowed: item.publication_allowed })
    ElMessage.success('候选内容已保存')
    await fetchKnowledgeCandidates()
  } catch { ElMessage.error('当前状态不能编辑或内容无效') }
}

async function submitCandidate(item: KnowledgeCandidate) {
  try {
    await agentApi.patch(`/knowledge-base/candidates/${item.id}`, { title: item.title, content: item.content, license_name: item.license_name, license_evidence_url: item.license_evidence_url, publication_allowed: item.publication_allowed })
    await agentApi.post(`/knowledge-base/candidates/${item.id}/submit`)
    await fetchKnowledgeCandidates()
  } catch { ElMessage.error('提交审核失败，请检查候选状态和内容') }
}

async function reviewCandidate(item: KnowledgeCandidate, decision: 'APPROVE' | 'REJECT') {
  let notes = '来源与内容已核验'
  if (decision === 'REJECT') {
    try { notes = (await ElMessageBox.prompt('请输入驳回原因', '审核候选知识')).value }
    catch { return }
  }
  try {
    await agentApi.post(`/knowledge-base/candidates/${item.id}/review`, { decision, notes })
    await fetchKnowledgeCandidates()
  } catch { ElMessage.error('审核失败，请刷新候选状态') }
}

async function loadKnowledgeVersions() {
  try { knowledgeVersions.value = (await agentApi.get<{ items: KnowledgeVersion[] }>('/knowledge-base/versions')).data.items }
  catch { ElMessage.error('知识版本获取失败') }
}

async function compareKnowledgeVersions() {
  if (!oldVersionId.value || !newVersionId.value) return
  try { versionComparison.value = (await agentApi.get(`/knowledge-base/versions/${oldVersionId.value}/compare/${newVersionId.value}`)).data.diff || '正文没有变化' }
  catch { ElMessage.error('请选择同一候选知识的两个版本') }
}

async function compareCandidateDraft(item: KnowledgeCandidate) {
  try { versionComparison.value = (await agentApi.get(`/knowledge-base/candidates/${item.id}/diff`)).data.diff || '正文没有变化' }
  catch { ElMessage.error('草稿差异读取失败') }
}

async function rollbackKnowledgeVersion(item: KnowledgeVersion) {
  try { await ElMessageBox.confirm(`将恢复“${item.title}”版本 ${item.number} 并验证索引。关联资源会标记待复核。继续？`, '恢复知识版本', { type: 'warning' }) }
  catch { return }
  loading.candidates = true
  try {
    await agentApi.post(`/knowledge-base/versions/${item.id}/rollback`)
    await Promise.all([loadKnowledgeVersions(), fetchKnowledgeCandidates(), fetchKnowledgeStatus()])
    ElMessage.success('知识版本与索引已恢复')
  } catch { ElMessage.error('恢复未完成，请检查日志') }
  finally { loading.candidates = false }
}

async function startCandidateRevision(item: KnowledgeCandidate) {
  try { await agentApi.post(`/knowledge-base/candidates/${item.id}/revision`); await fetchKnowledgeCandidates() }
  catch { ElMessage.error('创建修订草稿失败') }
}

async function viewMaintenanceReports(plan: MaintenancePlan) {
  try { maintenanceReport.value = JSON.stringify((await agentApi.get(`/knowledge-base/maintenance-plans/${plan.id}/reports`)).data, null, 2) }
  catch { ElMessage.error('维护报告读取失败') }
}

async function publishCandidate(item: KnowledgeCandidate) {
  try { await ElMessageBox.confirm('发布将写入正式语料并更新向量索引，确认继续？', '发布候选知识', { type: 'warning' }) }
  catch { return }
  loading.candidates = true
  try {
    const { data } = await agentApi.post(`/knowledge-base/candidates/${item.id}/publish-task`, { client_request_id: crypto.randomUUID() })
    ElMessage.success(`发布任务 #${data.id} 已排队，可在任务页查看检索验证结果`)
    await Promise.all([fetchKnowledgeCandidates(), fetchKnowledgeStatus(), loadKnowledgeVersions()])
  } catch { ElMessage.error('发布或检索验证失败，候选仍保留为已审核状态，可重试') }
  finally { loading.candidates = false }
}

async function createHealthCheckTask() {
  loading.knowledgeTasks = true
  try {
    await startKnowledgeTask('KNOWLEDGE_HEALTH_CHECK')
  } catch {
    ElMessage.error('知识巡检任务创建失败')
  } finally {
    loading.knowledgeTasks = false
  }
}

async function fetchManagedResources() {
  loading.resources = true
  resourceError.value = ''
  try {
    const { data } = await resourceApi.get<ApiEnvelope<ManagedResourceItem[]>>('/resources/managed')
    managedResources.value = data.data
  } catch {
    resourceError.value = '资源目录获取失败。'
  } finally {
    loading.resources = false
  }
}

async function showResource(item: ManagedResourceItem) {
  try {
    const { data } = await resourceApi.get<ApiEnvelope<ManagedResourceItem>>(`/resources/${item.id}`)
    selectedResource.value = data.data
  } catch {
    ElMessage.error('资源详情获取失败')
  }
}

async function changeResourceStatus(item: ManagedResourceItem, status: 'draft' | 'ready' | 'archived') {
  loading.resourceStatus = true
  try {
    await resourceApi.patch(`/resources/${item.id}/status`, { status })
    await Promise.all([fetchManagedResources(), fetchDashboard()])
    if (selectedResource.value?.id === item.id) selectedResource.value = null
    ElMessage.success('资源状态已更新')
  } catch {
    ElMessage.error('状态更新失败；发布前需通过内容审核')
  } finally {
    loading.resourceStatus = false
  }
}

async function assignRole() {
  loading.role = true
  try {
    const { data } = await systemApi.post<ApiEnvelope<Record<string, unknown>>>('/system/roles/assign', roleForm)
    roleResult.value = data.data
    ElMessage.success('角色分配成功')
    await Promise.all([fetchUsers(), fetchDashboard()])
    await fetchLogs()
  } catch {
    ElMessage.error('角色分配失败')
  } finally {
    loading.role = false
  }
}

async function fetchSubjects() {
  loading.subjects = true
  try {
    const { data } = await systemApi.get<ApiEnvelope<SubjectItem[]>>('/system/subjects')
    subjects.value = data.data
  } catch {
    ElMessage.error('学科列表获取失败')
  } finally {
    loading.subjects = false
  }
}


async function fetchConfigs() {
  loading.configs = true
  try {
    const { data } = await systemApi.get<ApiEnvelope<SystemConfigItem[]>>('/system/configs')
    configs.value = data.data
    if (configs.value.length > 0 && !configKeys.value.includes(selectedConfigKey.value)) {
      selectedConfigKey.value = configs.value[0].key
      configForm.value = configs.value[0].value
    }
  } catch {
    ElMessage.error('系统配置获取失败')
  } finally {
    loading.configs = false
  }
}

function syncSelectedConfigValue() {
  const current = configs.value.find((item) => item.key === selectedConfigKey.value)
  configForm.value = current?.value ?? ''
}

async function updateConfig() {
  loading.updateConfig = true
  try {
    const { data } = await systemApi.put<ApiEnvelope<SystemConfigItem>>(
      `/system/configs/${selectedConfigKey.value}`,
      configForm,
    )
    const targetIndex = configs.value.findIndex((item) => item.key === data.data.key)
    if (targetIndex >= 0) {
      configs.value[targetIndex] = data.data
    } else {
      configs.value.push(data.data)
    }
    ElMessage.success('系统配置更新成功')
    await fetchLogs()
  } catch {
    ElMessage.error('系统配置更新失败')
  } finally {
    loading.updateConfig = false
  }
}

async function fetchLogs() {
  loading.logs = true
  try {
    const query = logFilter.value ? `?level=${encodeURIComponent(logFilter.value)}` : ''
    const { data } = await systemApi.get<ApiEnvelope<AuditLogItem[]>>(`/system/logs${query}`)
    logs.value = data.data
  } catch {
    ElMessage.error('日志获取失败')
  } finally {
    loading.logs = false
  }
}

async function logout() {
  authStore.clear()
  ElMessage.success('已退出登录')
  await router.push({ name: 'login' })
}

async function fetchPrompts() {
  loading.prompts = true
  try {
    const { data } = await agentApi.get<ApiEnvelope<PromptTemplateSummary[]>>('/admin/prompts')
    prompts.value = data.data
  } catch {
    ElMessage.error('提示词列表获取失败')
  } finally {
    loading.prompts = false
  }
}

async function loadPrompt(name: string) {
  selectedPromptName.value = name
  try {
    const { data } = await agentApi.get<ApiEnvelope<PromptTemplateDetail>>(`/admin/prompts/${encodeURIComponent(name)}`)
    promptContent.value = data.data.content
    promptPlaceholders.value = data.data.placeholders
    await loadPromptVersions(name)
  } catch {
    ElMessage.error('提示词读取失败')
  }
}

async function savePrompt() {
  if (!selectedPromptName.value) return
  try {
    await agentApi.put<ApiEnvelope<PromptTemplateDetail>>(
      `/admin/prompts/${encodeURIComponent(selectedPromptName.value)}`,
      { content: promptContent.value },
    )
    ElMessage.success('提示词已保存')
    await Promise.all([fetchPrompts(), loadPrompt(selectedPromptName.value), loadPromptVersions(selectedPromptName.value)])
  } catch {
    ElMessage.error('保存失败：请确认保留了全部占位符')
  }
}

async function loadPromptVersions(name: string) {
  if (!name) return
  try {
    const { data } = await agentApi.get<ApiEnvelope<PromptVersionSummary[]>>(
      `/admin/prompts/${encodeURIComponent(name)}/versions`,
    )
    promptVersions.value = data.data
  } catch {
    promptVersions.value = []
  }
}

async function restorePromptVersion(name: string, version: string) {
  try {
    await agentApi.post<ApiEnvelope<PromptTemplateDetail>>(
      `/admin/prompts/${encodeURIComponent(name)}/versions/${encodeURIComponent(version)}/restore`,
    )
    ElMessage.success('已恢复该版本')
    await Promise.all([fetchPrompts(), loadPrompt(name), loadPromptVersions(name)])
  } catch {
    ElMessage.error('恢复版本失败')
  }
}

async function fetchImageProvider() {
  loading.imageProvider = true
  try {
    const { data } = await agentApi.get<ImageProviderStatus>('/admin/image-provider')
    imageProvider.value = data
    imageProviderForm.provider = data.provider
    imageProviderForm.model = data.model
  } catch {
    ElMessage.error('图片 Provider 状态获取失败')
  } finally {
    loading.imageProvider = false
  }
}

async function updateImageProvider() {
  try {
    const { data } = await agentApi.put<ImageProviderStatus>('/admin/image-provider', imageProviderForm)
    imageProvider.value = data
    ElMessage.success('图片 Provider 配置已保存（凭据需在部署环境配置）')
  } catch {
    ElMessage.error('图片 Provider 配置保存失败')
  }
}

async function rewriteSelectedResource() {
  if (!selectedResource.value) return
  if (!rewriteInstruction.value.trim()) {
    ElMessage.warning('请先填写改写要求')
    return
  }
  rewriteBusy.value = true
  rewriteResult.value = null
  try {
    const { data } = await agentApi.post<ResourceRewriteResult>(
      `/admin/resources/${selectedResource.value.id}/rewrite`,
      { instruction: rewriteInstruction.value.trim(), style: rewriteStyle.value },
    )
    rewriteResult.value = data
    if (data.status === 'blocked') ElMessage.info(data.reason || '改写当前不可用')
    if (data.status === 'failed') ElMessage.error(data.reason || '改写失败')
  } catch {
    ElMessage.error('改写请求失败')
  } finally {
    rewriteBusy.value = false
  }
}

async function applyRewrite() {
  if (!selectedResource.value || !rewriteResult.value?.rewritten_content) return
  try {
    await agentApi.put<{ resource_id: number; resource_version: string }>(
      `/admin/resources/${selectedResource.value.id}/content`,
      { content: rewriteResult.value.rewritten_content, expected_version: '' },
    )
    ElMessage.success('改写已应用到资源并保留上一版本')
    rewriteResult.value = null
    rewriteInstruction.value = ''
    await showResource(selectedResource.value)
  } catch {
    ElMessage.error('应用失败：资源可能已变更，请重新预览')
  }
}

async function loadResourceSections() {
  if (!selectedResource.value) return
  try {
    const { data } = await agentApi.get<{ sections: ResourceSection[]; image_provider: ImageProviderStatus }>(
      `/admin/resources/${selectedResource.value.id}/sections`,
    )
    resourceSections.value = data.sections
    imageProvider.value = data.image_provider
    await loadIllustrations()
  } catch {
    ElMessage.error('资源章节读取失败')
  }
}

async function loadIllustrations() {
  if (!selectedResource.value) return
  try {
    const { data } = await agentApi.get<{ resource_id: number; illustrations: ResourceIllustration[] }>(
      `/admin/resources/${selectedResource.value.id}/illustrations`,
    )
    resourceIllustrations.value = data.illustrations
  } catch {
    resourceIllustrations.value = []
  }
}

async function generateIllustration(sectionTitle: string) {
  if (!selectedResource.value) return
  illustrateBusy.value = true
  try {
    const { data } = await agentApi.post<IllustrateResult>(
      `/admin/resources/${selectedResource.value.id}/illustrations`,
      { section_title: sectionTitle, prompt: illustratePrompt.value.trim() },
    )
    if (data.status === 'generated') ElMessage.success('配图已生成，待审核')
    else if (data.status === 'blocked') ElMessage.info(data.reason || '图片生成当前不可用')
    else if (data.status === 'failed') ElMessage.error(data.reason || '图片生成失败')
    await loadIllustrations()
  } catch {
    ElMessage.error('图片生成请求失败')
  } finally {
    illustrateBusy.value = false
  }
}

async function reviewIllustration(illustrationId: string, approve: boolean) {
  if (!selectedResource.value) return
  try {
    await agentApi.post(
      `/admin/resources/${selectedResource.value.id}/illustrations/${illustrationId}/${approve ? 'approve' : 'reject'}`,
    )
    ElMessage.success(approve ? '已通过审核' : '已拒绝')
    await loadIllustrations()
  } catch {
    ElMessage.error('审核操作失败')
  }
}

async function insertIllustration(illustrationId: string) {
  if (!selectedResource.value) return
  try {
    await agentApi.post(
      `/admin/resources/${selectedResource.value.id}/illustrations/${illustrationId}/insert`,
    )
    ElMessage.success('配图已插入资源并保存版本')
    await Promise.all([loadIllustrations(), showResource(selectedResource.value)])
  } catch {
    ElMessage.error('插入失败：请确认已通过审核')
  }
}


onMounted(async () => {
  switch (module) {
    case 'overview': await fetchDashboard(); break
    case 'users': await fetchUsers(1); break
    case 'subjects': await fetchSubjects(); break
    case 'construction': await loadConstructionSubjects(); break
    case 'knowledge': await fetchKnowledgeStatus(); break
    case 'tasks': await fetchKnowledgeTasks(); break
    case 'review': await Promise.all([fetchKnowledgeCandidates(), loadKnowledgeVersions()]); break
    case 'maintenance': await Promise.all([fetchMaintenancePlans(), fetchSubjects()]); break
    case 'resources': await fetchManagedResources(); break
    case 'settings': await fetchConfigs(); syncSelectedConfigValue(); break
    case 'logs': await fetchLogs(); break
    case 'prompts': await Promise.all([fetchPrompts(), fetchImageProvider()]); break
  }
})
return { router, authStore, candidateOriginFilter, subjects, configs, logs, dashboard, userPage, knowledgeStatus, knowledgeSources, knowledgeTasks, taskSubject, taskQuery, maintenancePlans, knowledgeCandidates, constructionSubjects, constructionPoints, constructionSubjectId, constructionSelectedPoints, constructionForm, outlineReview, outlineStatus, outlineError, outlinePollCount, outlineTaskId, constructionBusy, manualPoint, constructionFocus, knowledgeVersions, oldVersionId, newVersionId, versionComparison, maintenanceReport, taskUsage, versionImpact, planForm, knowledgeError, managedResources, resourceError, resourceFilter, selectedResource, userKeyword, userRole, newUser, currentUserPage, selectedConfigKey, roleForm, configForm, logFilter, roleResult, loading, configKeys, visibleLogs, visibleResources, adminStats, prompts, selectedPromptName, promptContent, promptPlaceholders, promptVersions, imageProvider, imageProviderForm, rewriteInstruction, rewriteStyle, rewriteResult, rewriteBusy, resourceSections, resourceIllustrations, illustratePrompt, illustrateBusy, fetchDashboard, fetchUsers, selectUser, createUser, setUserStatus, fetchKnowledgeStatus, fetchKnowledgeSources, reindexKnowledgeBase, fetchKnowledgeTasks, fetchMaintenancePlans, createMaintenancePlan, toggleMaintenancePlan, startKnowledgeTask, candidateSources, fetchedSource, searchKnowledgeSources, fetchCandidateSource, cancelKnowledgeTask, viewTaskUsage, retryKnowledgeTask, viewVersionImpact, loadConstructionSubjects, createManualConstructionPoint, planConstructionSubject, discardOutline, confirmConstructionOutline, loadConstructionPoints, buildConstructionPoints, fetchKnowledgeCandidates, createKnowledgeCandidate, saveCandidate, submitCandidate, reviewCandidate, loadKnowledgeVersions, compareKnowledgeVersions, compareCandidateDraft, rollbackKnowledgeVersion, startCandidateRevision, viewMaintenanceReports, publishCandidate, createHealthCheckTask, fetchManagedResources, showResource, changeResourceStatus, assignRole, fetchSubjects, fetchConfigs, syncSelectedConfigValue, updateConfig, fetchLogs, fetchPrompts, loadPrompt, savePrompt, loadPromptVersions, restorePromptVersion, fetchImageProvider, updateImageProvider, rewriteSelectedResource, applyRewrite, loadResourceSections, loadIllustrations, generateIllustration, reviewIllustration, insertIllustration, logout }
}
