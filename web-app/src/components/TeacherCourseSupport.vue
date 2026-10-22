<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { teacherApi, type ApiEnvelope, type CourseResourceDelivery, type ReinforcementQuestion, type ReinforcementAttempt } from '../api'
import LearningContent from './LearningContent.vue'
import ReinforcementResult from './ReinforcementResult.vue'

const props = defineProps<{ classId: number; className: string }>()
const emit = defineEmits<{ published: [] }>()
type Member = { user_id: number; username: string }
type Evidence = { platform_study_seconds: number | null; course_answer_seconds: number | null; answer_count: number; correct_rate: number | null; mistake_count: number; homework_average_score: number | null; diagnostic_only: boolean; missing: string[] }
type Draft = { id: number; student_user_id: number; status: string; error: string; rationale: string; evidence_json: Evidence; questions: ReinforcementQuestion[]; model_name: string; assignment_id: number | null }
const members = ref<Member[]>([])
const catalog = ref<{ id: number; title: string; knowledge_point: string }[]>([])
const deliveries = ref<CourseResourceDelivery[]>([])
const drafts = ref<Draft[]>([])
const attempts = ref<ReinforcementAttempt[]>([])
const retrying = ref(0)
const loadError = ref('')
const busy = ref(false)
const sending = ref(false)
const generating = ref(false)
const selectedResource = ref<number | null>(null)
const recipient = ref<number | null>(null)
const resourceTitle = ref('')
const resourceContent = ref('')
const pointText = ref('')
const target = ref<number | null>(null)
const materialIds = ref<number[]>([])
const count = ref(3)
const teacherNote = ref('')
const facts = ref<Evidence | null>(null)
const reviewing = ref(false)
const selectedDraft = ref<Draft | null>(null)
const saving = ref(false)
const publishTitle = ref('')
const dueAt = ref<string | null>(null)
let evidenceVersion = 0
const availableMaterials = computed(() => deliveries.value.filter(d => !d.student_user_id || d.student_user_id === target.value))
const nameOf = (id: number | null) => members.value.find(m => m.user_id === id)?.username || (id ? `学生 ${id}` : '全班')
function errorText(error: any) {
  const detail = error?.response?.data?.detail
  return typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d => d.msg).join('；') : '请求未完成，请刷新查看状态后重试'
}
async function refresh() {
  busy.value = true
  loadError.value = ''
  try {
    const [m, c, r, d, a] = await Promise.all([
      teacherApi.get<ApiEnvelope<Member[]>>(`/teacher/classes/${props.classId}/members`),
      teacherApi.get<ApiEnvelope<typeof catalog.value>>(`/teacher/classes/${props.classId}/resource-catalog`),
      teacherApi.get<ApiEnvelope<CourseResourceDelivery[]>>(`/teacher/classes/${props.classId}/course-resources`),
      teacherApi.get<ApiEnvelope<Draft[]>>(`/teacher/classes/${props.classId}/reinforcements`),
      teacherApi.get<ApiEnvelope<ReinforcementAttempt[]>>(`/teacher/classes/${props.classId}/reinforcement-attempts`),
    ])
    members.value = m.data.data; catalog.value = c.data.data; deliveries.value = r.data.data; drafts.value = d.data.data
    attempts.value = a.data.data
  } catch (error) { loadError.value = errorText(error) }
  finally { busy.value = false }
}
async function sendResource() {
  if (!selectedResource.value && (!resourceTitle.value.trim() || !resourceContent.value.trim() || !pointText.value.trim())) return ElMessage.warning('请填写资源标题、正文与课程知识点，或选择已有资源')
  sending.value = true
  try {
    await teacherApi.post(`/teacher/classes/${props.classId}/course-resources`, {
      request_id: crypto.randomUUID(), student_user_id: recipient.value, resource_id: selectedResource.value,
      title: resourceTitle.value, content: resourceContent.value,
      knowledge_points: pointText.value.split(/[,，、\n]/).map(p => p.trim()).filter(Boolean),
    })
    ElMessage.success('课程资源已发送，学生可在我的课堂阅读')
    await refresh()
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { sending.value = false }
}
watch(target, async id => {
  const version = ++evidenceVersion
  facts.value = null; materialIds.value = []
  if (!id) return
  try {
    const { data } = await teacherApi.get<ApiEnvelope<Evidence>>(`/teacher/classes/${props.classId}/students/${id}/reinforcement-evidence`)
    if (version === evidenceVersion) facts.value = data.data
  } catch (error) { if (version === evidenceVersion) ElMessage.error(errorText(error)) }
})
async function generate() {
  if (!target.value || !materialIds.value.length) return ElMessage.warning('请选择学生和已发送给该学生的课程资源')
  generating.value = true
  try {
    const { data } = await teacherApi.post<ApiEnvelope<Draft>>(`/teacher/classes/${props.classId}/reinforcements`, {
      request_id: crypto.randomUUID(), student_user_id: target.value, delivery_ids: materialIds.value,
      question_count: count.value, teacher_note: teacherNote.value,
    }, { timeout: 240000 })
    if (data.data.status === 'failed') ElMessage.error(data.data.error)
    else if (data.data.status === 'ready') openDraft(data.data)
    await refresh()
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { generating.value = false }
}
function openDraft(draft: Draft) {
  selectedDraft.value = JSON.parse(JSON.stringify(draft))
  publishTitle.value = `${props.className} · ${nameOf(draft.student_user_id)}补强练习`.slice(0, 160)
  dueAt.value = null
  reviewing.value = true
}
async function saveDraft() {
  if (!selectedDraft.value) return
  const { data } = await teacherApi.put<ApiEnvelope<Draft>>(`/teacher/reinforcements/${selectedDraft.value.id}`, {
    questions: selectedDraft.value.questions, rationale: selectedDraft.value.rationale,
  })
  selectedDraft.value = data.data
}
async function save() {
  saving.value = true
  try { await saveDraft(); ElMessage.success('草稿已保存'); await refresh() }
  catch (error) { ElMessage.error(errorText(error)) }
  finally { saving.value = false }
}
async function publish() {
  if (!selectedDraft.value || !publishTitle.value.trim()) return ElMessage.warning('请填写作业标题')
  try { await ElMessageBox.confirm(`将审阅后的题目作为作业发送给「${nameOf(selectedDraft.value.student_user_id)}」，其他学生不会收到。`, '确认发送补强作业') }
  catch { return }
  saving.value = true
  try {
    await saveDraft()
    await teacherApi.post(`/teacher/reinforcements/${selectedDraft.value.id}/publish`, { title: publishTitle.value, due_at: dueAt.value })
    ElMessage.success('补强作业已下发，请在作业管理中查看提交并批改')
    reviewing.value = false
    await refresh(); emit('published')
  } catch (error) { ElMessage.error(errorText(error)) }
  finally { saving.value = false }
}
const stateLabel = (state: string) => ({ ready: '待教师审阅', generating: '生成中', failed: '生成失败', published: '已下发' }[state] || state)
async function retryFeedback(id: number) {
  retrying.value = id
  try { await teacherApi.post(`/teacher/reinforcement-attempts/${id}/analyze`); ElMessage.success('分析任务已提交'); await refresh() }
  catch (error) { ElMessage.error(errorText(error)) }
  finally { retrying.value = 0 }
}
let feedbackPoll: ReturnType<typeof setInterval> | undefined
onMounted(refresh)
onMounted(() => { feedbackPoll = setInterval(async () => {
  try { attempts.value = (await teacherApi.get<ApiEnvelope<ReinforcementAttempt[]>>(`/teacher/classes/${props.classId}/reinforcement-attempts`)).data.data }
  catch { /* Normal refresh preserves the error recovery path. */ }
}, 5000) })
onUnmounted(() => clearInterval(feedbackPoll))
</script>

<template>
  <div class="course-support">
    <div class="support-head"><div><h2>课程资源与个性化补强</h2><p>{{ className }}：发送课程资料，结合真实学情生成补强作业，再由教师审阅下发。</p></div><el-button :loading="busy" @click="refresh">刷新资源与草稿</el-button></div>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" />
    <el-tabs>
      <el-tab-pane label="发送课程资源">
        <el-form label-position="top" class="support-form">
          <el-form-item label="接收学生"><el-select v-model="recipient" clearable placeholder="全班学生" @clear="recipient = null"><el-option v-for="member in members" :key="member.user_id" :label="member.username" :value="member.user_id" /></el-select></el-form-item>
          <el-form-item label="选择已有课程资源（可选）"><el-select v-model="selectedResource" clearable filterable placeholder="也可以在下方编写教师专属资料" @clear="selectedResource = null"><el-option v-for="resource in catalog" :key="resource.id" :label="resource.title" :value="resource.id" /></el-select></el-form-item>
          <template v-if="!selectedResource"><el-form-item label="资源标题"><el-input v-model="resourceTitle" maxlength="160" placeholder="例如：二叉树遍历讲义" /></el-form-item><el-form-item label="课程资源正文"><el-input v-model="resourceContent" type="textarea" :rows="5" placeholder="粘贴教师讲义、例题或课程资料正文，支持Markdown" /></el-form-item></template>
          <el-form-item label="课程知识点"><el-input v-model="pointText" placeholder="多个知识点用顿号分隔；已有资源会自动带入其知识点" /></el-form-item>
          <el-button type="primary" :loading="sending" @click="sendResource">发送课程资源</el-button>
        </el-form>
        <div v-for="delivery in deliveries" :key="delivery.id" class="support-card"><h3>{{ delivery.title }}</h3><p>发送给：{{ nameOf(delivery.student_user_id) }} · {{ delivery.knowledge_points.join('、') }}</p><details><summary>查看已发送的资源</summary><LearningContent :content="delivery.content" /></details></div>
      </el-tab-pane>
      <el-tab-pane label="生成补强作业">
        <el-form label-position="top" class="support-form">
          <el-form-item label="补强学生"><el-select v-model="target" filterable placeholder="选择本班学生"><el-option v-for="member in members" :key="member.user_id" :label="member.username" :value="member.user_id" /></el-select></el-form-item>
          <div v-if="facts" class="evidence-panel"><strong>最近30天真实学情</strong><p>平台总学习时长：{{ facts.platform_study_seconds === null ? '暂无记录' : `${Math.round(facts.platform_study_seconds / 60)}分钟` }}（未归属具体课程）</p><p>本课程作答：{{ facts.answer_count }} 次 · 错题 {{ facts.mistake_count }} 次 · 正确率 {{ facts.correct_rate === null ? '暂无' : `${facts.correct_rate}%` }} · 作答耗时 {{ facts.course_answer_seconds === null ? '暂无' : `${facts.course_answer_seconds}秒` }}</p><p>本课程作业均分：{{ facts.homework_average_score ?? '暂无已评分作业' }}</p><el-alert v-if="facts.diagnostic_only" title="当前缺少本课程有效作答证据，将生成诊断练习，不判定学生薄弱点。" type="info" :closable="false" /></div>
          <el-form-item label="依据的课程资源"><el-select v-model="materialIds" multiple placeholder="先在“发送课程资源”中发送资料，再选择用于出题的资源"><el-option v-for="material in availableMaterials" :key="material.id" :label="material.title" :value="material.id" /></el-select></el-form-item>
          <el-form-item label="题目数量"><el-input-number v-model="count" :min="1" :max="10" /></el-form-item>
          <el-form-item label="教师补充要求"><el-input v-model="teacherNote" type="textarea" :rows="2" maxlength="1500" placeholder="例如：围绕错题设计变式题，先基础再应用" /></el-form-item>
          <el-button type="primary" :loading="generating" @click="generate">用模型生成补强题</el-button><p v-if="generating">正在基于课程资源和学情生成，草稿会保存，可稍后刷新查看。</p>
        </el-form>
        <div v-for="draft in drafts" :key="draft.id" class="support-card"><div class="support-head"><strong>{{ nameOf(draft.student_user_id) }} · {{ stateLabel(draft.status) }}</strong><el-button v-if="['ready', 'published'].includes(draft.status)" @click="openDraft(draft)">{{ draft.status === 'ready' ? '审阅题目' : '查看已下发题目' }}</el-button></div><p v-if="draft.error">{{ draft.error }}</p><p v-if="draft.assignment_id">作业编号：{{ draft.assignment_id }}，可在作业管理查看提交和批改。</p></div>
      </el-tab-pane>
      <el-tab-pane label="学生错题与模型分析">
        <el-empty v-if="!attempts.length" description="学生提交补强练习后，将在这里展示逐题作答、错题和模型分析" />
        <article v-for="attempt in attempts" :key="attempt.id" class="support-card"><div class="support-head"><h3>{{ nameOf(attempt.student_user_id) }} · 补强作答 #{{ attempt.id }}</h3><el-button v-if="attempt.status !== 'completed'" :loading="retrying === attempt.id" @click="retryFeedback(attempt.id)">重试模型分析</el-button></div><ReinforcementResult :result="attempt" /></article>
      </el-tab-pane>
    </el-tabs>
    <el-dialog v-model="reviewing" title="教师审阅补强题" width="min(900px, 94vw)" append-to-body>
      <template v-if="selectedDraft"><el-tag>{{ stateLabel(selectedDraft.status) }}</el-tag><p>接收学生：{{ nameOf(selectedDraft.student_user_id) }} · 模型：{{ selectedDraft.model_name }}</p><LearningContent :content="selectedDraft.rationale" />
        <el-form label-position="top" :disabled="selectedDraft.status !== 'ready'">
          <article v-for="(question, index) in selectedDraft.questions" :key="index" class="support-card"><h3>第{{ index + 1 }}题 · {{ question.knowledge_point }}</h3><el-form-item label="题干"><el-input v-model="question.prompt" type="textarea" :rows="3" /></el-form-item><el-form-item v-for="(_, optionIndex) in question.options" :key="optionIndex" :label="`选项${optionIndex + 1}`"><el-input v-model="question.options[optionIndex]" /></el-form-item><el-form-item label="参考答案（学生提交后立即展示）"><el-input v-model="question.answer" type="textarea" :rows="2" /></el-form-item><el-form-item label="解析"><el-input v-model="question.analysis" type="textarea" :rows="3" /></el-form-item><small>关联错题记录：{{ question.evidence_ids?.join('、') || '诊断或迁移练习，无直接错题引用' }}</small></article>
          <el-form-item label="作业标题"><el-input v-model="publishTitle" maxlength="160" /></el-form-item><el-form-item label="截止时间（可选）"><el-date-picker v-model="dueAt" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" /></el-form-item>
        </el-form>
      </template>
      <template #footer><el-button @click="reviewing = false">关闭</el-button><template v-if="selectedDraft?.status === 'ready'"><el-button :loading="saving" @click="save">保存草稿</el-button><el-button type="primary" :loading="saving" @click="publish">审阅通过并发送作业</el-button></template></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.course-support{display:grid;gap:18px;min-width:0}.support-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}.course-support h2,.course-support h3{margin:0}.course-support p{color:var(--muted);line-height:1.7}.support-form{padding:12px 0;max-width:900px}.support-form :deep(.el-select){width:100%}.support-card,.evidence-panel{padding:18px;border:1px solid var(--line);border-radius:14px;background:var(--surface-soft);margin:14px 0;overflow-wrap:anywhere}.support-card details{margin-top:12px}.support-card small{color:var(--muted)}
</style>
