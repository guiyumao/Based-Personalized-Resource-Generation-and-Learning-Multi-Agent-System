<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, MagicStick, Upload } from '@element-plus/icons-vue'
import { evaluationApi, type ApiEnvelope, type TranscriptAnalysis, type TranscriptParseResponse, type TranscriptRow } from '../api'
import { useAuthStore } from '../stores/auth'
import LearningAtmosphere from '../components/LearningAtmosphere.vue'
import LearningContent from '../components/LearningContent.vue'

const authStore = useAuthStore()
const router = useRouter()
const isTeacher = computed(() => authStore.user?.role === 'teacher' || authStore.user?.role === 'admin')
const fileInput = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const analyzing = ref(false)
const error = ref('')
const preview = ref<TranscriptParseResponse | null>(null)
const analysis = ref<TranscriptAnalysis | null>(null)
const scope = ref<'student' | 'class'>(isTeacher.value ? 'class' : 'student')
const selectedStudentKey = ref('')
const chatQuestion = ref('')
const chatAnswer = ref('')

const lowConfidenceColumns = computed(() => new Set((preview.value?.low_confidence_cells ?? []).map((cell) => `${cell.row}:${cell.column}`)))
const studentOptions = computed(() => {
  const options = new Map<string, { key: string; no: string; name: string; label: string }>()
  for (const row of preview.value?.rows ?? []) {
    const no = row.student_no.trim()
    const name = row.student_name.trim()
    if (!no && !name) continue
    const key = no ? `no:${no}` : `name:${name}`
    if (!options.has(key)) options.set(key, { key, no, name, label: `${name || '未填写姓名'}${no ? `（${no}）` : ''}` })
  }
  return [...options.values()]
})
const needsStudentSelection = computed(() => studentOptions.value.length > 1 ||
  (studentOptions.value.length > 0 && (preview.value?.rows ?? []).some((row) => !row.student_no.trim() && !row.student_name.trim())))

function chooseFile() {
  fileInput.value?.click()
}

async function parseFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  loading.value = true
  error.value = ''
  analysis.value = null
  selectedStudentKey.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const response = await evaluationApi.post<ApiEnvelope<TranscriptParseResponse>>('/evaluation/transcripts/parse', form)
    preview.value = response.data.data
    ElMessage.success(`已识别 ${preview.value.rows.length} 条成绩记录，请检查黄色单元格。`)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '解析失败，请检查文件格式或表头。'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
    input.value = ''
  }
}

async function analyze() {
  if (!preview.value?.rows.length) return
  const selectedStudent = studentOptions.value.find((student) => student.key === selectedStudentKey.value)
  if (scope.value === 'student' && needsStudentSelection.value && !selectedStudent) {
    error.value = '成绩单包含多名或身份不完整的学生，请先选择个人分析对象。'
    ElMessage.warning(error.value)
    return
  }
  analyzing.value = true
  error.value = ''
  try {
    const response = await evaluationApi.post<ApiEnvelope<TranscriptAnalysis>>('/evaluation/transcripts/analyze', {
      import_id: preview.value.import_id,
      file_name: preview.value.file_name,
      file_type: preview.value.file_type,
      headers: preview.value.headers,
      rows: preview.value.rows,
      field_mapping: preview.value.field_mapping,
      scope: scope.value,
      target_student_no: scope.value === 'student' ? selectedStudent?.no || undefined : undefined,
      target_student_name: scope.value === 'student' && !selectedStudent?.no ? selectedStudent?.name || undefined : undefined,
    })
    analysis.value = response.data.data
    ElMessage.success(analysis.value.cache_hit ? '已返回本账号相同成绩单的缓存分析。' : scope.value === 'student' && !isTeacher.value ? '分析完成，画像已同步。' : '分析完成。')
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '分析失败，请稍后重试。'
    ElMessage.error(error.value)
  } finally {
    analyzing.value = false
  }
}

async function askReport() {
  if (!analysis.value || !chatQuestion.value.trim()) return
  try {
    const response = await evaluationApi.post<ApiEnvelope<{ answer: string }>>('/evaluation/transcripts/chat', { analysis_id: analysis.value.analysis_id, question: chatQuestion.value })
    chatAnswer.value = response.data.data.answer
    chatQuestion.value = ''
  } catch {
    ElMessage.error('报告追问失败。')
  }
}

function download(format: 'docx' | 'pdf') {
  if (!analysis.value) return
  window.open(`${evaluationApi.defaults.baseURL}/evaluation/transcripts/analysis/${analysis.value.analysis_id}/export?format=${format}`, '_blank')
}

function planFromTranscript() {
  if (!analysis.value || analysis.value.scope !== 'student' || isTeacher.value) return
  void router.push({ name: 'student-learning-path', query: { transcript_analysis_id: String(analysis.value.analysis_id) } })
}
</script>

<template>
  <div class="transcript-page">
    <section class="transcript-hero">
      <div>
        <span class="section-kicker">成绩单智能解析 · 多智能体学情引擎</span>
        <h1>把一次考试，变成下一周的学习行动。</h1>
        <p>支持表格、文档、PDF 与图片导入。先校正结构化数据，再由统计、画像、薄弱点、资源和习题智能体协同生成方案。</p>
      </div>
      <LearningAtmosphere variant="hero" />
      <button class="primary-action" type="button" :disabled="loading" @click="chooseFile"><el-icon><Upload /></el-icon>{{ loading ? '正在解析…' : '上传成绩单' }}</button>
      <input ref="fileInput" class="hidden-input" type="file" accept=".xlsx,.xls,.csv,.docx,.pdf,.jpg,.jpeg,.png" @change="parseFile">
    </section>

    <section v-if="!preview" class="empty-atmosphere panel">
      <LearningAtmosphere variant="empty" />
      <div><span class="section-kicker">Ready when you are</span><h2>还没有成绩单记录</h2><p>上传一次考试成绩，系统会把分数变化、薄弱科目和下一步学习任务串起来。</p></div>
    </section>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <section v-if="preview" class="panel preview-panel">
      <header class="panel-header">
        <div><span class="section-kicker">Step 01 / 校正</span><h2>{{ preview.file_name }}</h2><p>识别质量 {{ Math.round(preview.quality_score * 100) }}% · {{ preview.ocr_mode ? 'OCR 表格识别' : '原生文本表格解析' }}</p></div>
        <div class="header-actions">
          <el-radio-group v-model="scope" size="small">
            <el-radio-button label="student">个人分析</el-radio-button>
            <el-radio-button v-if="isTeacher" label="class">班级分析</el-radio-button>
          </el-radio-group>
          <el-select v-if="scope === 'student' && needsStudentSelection" v-model="selectedStudentKey" placeholder="选择个人分析对象" size="small" style="width: 210px">
            <el-option v-for="student in studentOptions" :key="student.key" :label="student.label" :value="student.key" />
          </el-select>
          <button class="primary-action compact" type="button" :disabled="analyzing" @click="analyze"><el-icon><MagicStick /></el-icon>{{ analyzing ? '多智能体分析中…' : '生成分析方案' }}</button>
        </div>
      </header>
      <div v-if="preview.warnings.length" class="warning-list"><span v-for="warning in preview.warnings" :key="warning">{{ warning }}</span></div>
      <div class="table-scroll">
        <table class="score-table">
          <thead><tr><th>姓名</th><th>学号</th><th>班级</th><th>科目</th><th>得分</th><th>满分</th><th>考试日期</th><th>章节 / 知识点</th></tr></thead>
          <tbody>
            <tr v-for="(row, index) in preview.rows" :key="`${row.student_no}-${row.subject}-${index}`">
              <td><input v-model="row.student_name" :class="{ 'low-confidence': lowConfidenceColumns.has(`${index + 2}:姓名`) }"></td>
              <td><input v-model="row.student_no"></td>
              <td><input v-model="row.class_name"></td>
              <td><input v-model="row.subject"></td>
              <td><input v-model.number="row.score" type="number" min="0" :max="row.max_score"></td>
              <td><input v-model.number="row.max_score" type="number" min="1"></td>
              <td><input v-model="row.exam_date"></td>
              <td><input v-model="row.chapter" placeholder="可选"></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="analysis" class="analysis-layout">
      <div class="analysis-main">
        <div class="panel report-summary"><span class="section-kicker">Step 02 / 主智能体汇总</span><h2>{{ analysis.report.title }}</h2><LearningContent class="report-summary-body" :content="analysis.report.summary" /><small>{{ analysis.report.quality_note }}</small></div>
        <div class="metric-grid"><article><strong>{{ analysis.score_statistics.overall_average }}</strong><span>整体均分</span></article><article><strong>{{ analysis.score_statistics.record_count }}</strong><span>有效记录</span></article><article><strong>{{ analysis.student_profile.learning_style }}</strong><span>学习风格</span></article><article><strong>{{ analysis.weakness_diagnosis.weak_points.length }}</strong><span>优先薄弱点</span></article></div>
        <div class="panel"><header class="panel-header"><div><span class="section-kicker">Serial agents</span><h2>学情诊断</h2></div></header><div class="diagnosis-grid"><div><h3>优势学科</h3><p>{{ analysis.student_profile.strong_subjects.join('、') || '待积累数据' }}</p></div><div><h3>薄弱学科</h3><p class="weak-text">{{ analysis.student_profile.weak_subjects.join('、') || '暂无明确薄弱科目' }}</p></div><div><h3>失分原因分布</h3><p>{{ Object.entries(analysis.student_profile.loss_reason_distribution).map(([key, value]) => `${key} ${value}%`).join(' · ') }}</p></div></div></div>
        <div class="panel"><header class="panel-header"><div><span class="section-kicker">Weakness diagnosis agent</span><h2>薄弱知识点清单</h2></div></header><div class="weak-point-list"><article v-for="point in analysis.weakness_diagnosis.weak_points" :key="point.knowledge_point"><div><strong>{{ point.knowledge_point }}</strong><span>{{ point.chapter }} · {{ point.importance_tag }}</span></div><b>{{ point.mastery }}<small>掌握度</small></b></article></div></div>
      </div>
      <aside class="analysis-side"><div class="panel"><span class="section-kicker">Parallel agents</span><h2>7天学习路径</h2><LearningAtmosphere class="plan-atmosphere" variant="path" /><ol class="plan-list"><li v-for="item in analysis.resource_recommendations.seven_day_plan" :key="item.day"><b>Day {{ item.day }}</b><span>{{ item.focus }}</span><small>{{ item.minutes }} 分钟 · {{ item.goal }}</small></li></ol><button v-if="!isTeacher && analysis.scope === 'student'" type="button" class="primary-action compact" @click="planFromTranscript">根据成绩生成可跟踪计划</button></div><div class="panel"><span class="section-kicker">Layered exercises</span><h2>分层习题推荐</h2><div class="tier-row"><span>基础 60%</span><span>提升 30%</span><span>拔高 10%</span></div><p>{{ analysis.exercise_recommendations.items.length }} 道可执行练习，核心薄弱点已配套变式题。</p></div><div class="panel"><h2>导出与追问</h2><div class="export-actions"><button type="button" @click="download('pdf')">导出 PDF</button><button type="button" @click="download('docx')">导出 Word</button></div><div class="chat-box"><input v-model="chatQuestion" placeholder="例如：我该先补哪一科？" @keydown.enter="askReport"><button type="button" @click="askReport">发送</button><LearningContent v-if="chatAnswer" class="chat-answer" :content="chatAnswer" /></div></div></aside>
    </section>
  </div>
</template>

<style scoped>
.transcript-page { max-width:1440px; margin:0 auto; padding:26px 30px 52px; color:var(--text); }
.transcript-hero { display:grid; grid-template-columns:minmax(0,1fr) minmax(320px,560px) auto; align-items:end; gap:20px; padding:30px; border:1px solid var(--line); border-radius:22px; background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel-strong)),var(--panel-strong)); box-shadow:var(--shadow); }
.transcript-hero h1 { max-width:760px; margin:8px 0; font-size:clamp(26px,3.6vw,46px); letter-spacing:-.04em; }
.transcript-hero p { max-width:760px; margin:0; color:var(--muted); line-height:1.8; }
.section-kicker { color:var(--accent); font-size:11px; font-weight:800; letter-spacing:.11em; text-transform:uppercase; }
.empty-atmosphere { display:grid; grid-template-columns:1fr 1fr; align-items:center; gap:18px; margin-top:20px; background:linear-gradient(135deg,var(--panel),color-mix(in srgb,var(--accent) 5%,var(--panel))); }.empty-atmosphere h2 { margin:6px 0; }.empty-atmosphere p { max-width:420px; margin:0; color:var(--muted); line-height:1.8; }
.primary-action { border:0; border-radius:11px; padding:12px 17px; display:inline-flex; align-items:center; gap:7px; color:#fff; background:linear-gradient(135deg,var(--accent),var(--accent-deep)); font-weight:750; cursor:pointer; white-space:nowrap; }
.primary-action:disabled { opacity:.6; cursor:wait; }.primary-action.compact { padding:9px 13px; font-size:12px; }
.hidden-input { display:none; }.error-banner,.warning-list { margin-top:16px; padding:12px 15px; border-radius:12px; }.error-banner { color:var(--red); background:color-mix(in srgb,var(--red) 9%,var(--panel)); }.warning-list { display:flex; gap:8px; flex-wrap:wrap; color:#9a6700; background:#fff8dc; font-size:12px; }.warning-list span { padding:4px 8px; border-radius:7px; background:#ffefae; }
.panel { padding:22px; border:1px solid var(--line); border-radius:18px; background:var(--panel); box-shadow:var(--shadow); }.preview-panel { margin-top:20px; }.panel-header { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }.panel-header h2,.panel h2 { margin:5px 0 4px; font-size:20px; }.panel-header p,.panel small { margin:0; color:var(--muted); }.header-actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; justify-content:flex-end; }
.table-scroll { margin-top:18px; overflow:auto; border:1px solid var(--line); border-radius:12px; }.score-table { width:100%; min-width:900px; border-collapse:collapse; font-size:12px; }.score-table th { padding:11px 10px; color:var(--muted); background:var(--surface-soft); text-align:left; font-size:11px; }.score-table td { padding:8px 10px; border-top:1px solid var(--line); }.score-table input { width:100%; min-width:76px; box-sizing:border-box; border:1px solid transparent; border-radius:7px; padding:7px; color:var(--text); background:transparent; outline:none; }.score-table input:focus { border-color:var(--accent); background:var(--panel-strong); }.score-table input.low-confidence { background:#fff0f0; border-color:#e99; }
.analysis-layout { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(300px,.75fr); gap:20px; margin-top:20px; }.analysis-main,.analysis-side { display:grid; gap:20px; align-content:start; }.report-summary { background:linear-gradient(135deg,var(--accent-soft),var(--panel)); }.report-summary h2 { font-size:26px; }.report-summary p { margin:10px 0; line-height:1.8; }.report-summary .report-summary-body { margin:10px 0; line-height:1.8; }.metric-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }.metric-grid article { padding:18px; border:1px solid var(--line); border-radius:15px; background:var(--panel); }.metric-grid strong,.metric-grid span { display:block; }.metric-grid strong { font-size:23px; }.metric-grid span { margin-top:5px; color:var(--muted); font-size:12px; }.diagnosis-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }.diagnosis-grid div { padding:14px; border-radius:12px; background:var(--surface-soft); }.diagnosis-grid h3 { margin:0 0 8px; font-size:12px; color:var(--muted); }.diagnosis-grid p { margin:0; line-height:1.7; }.weak-text { color:var(--red); }.weak-point-list { display:grid; gap:9px; }.weak-point-list article { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:13px 15px; border:1px solid var(--line); border-radius:12px; }.weak-point-list strong,.weak-point-list span { display:block; }.weak-point-list span { margin-top:4px; color:var(--muted); font-size:11px; }.weak-point-list b { color:var(--accent); font-size:22px; text-align:right; }.weak-point-list b small { display:block; color:var(--muted); font-size:10px; font-weight:500; }.plan-list { display:grid; gap:12px; padding:0; margin:18px 0 0; list-style:none; }.plan-list li { display:grid; grid-template-columns:46px 1fr; gap:3px 10px; padding-bottom:12px; border-bottom:1px solid var(--line); }.plan-list b { grid-row:span 2; color:var(--accent); font-size:12px; }.plan-list span { font-size:13px; font-weight:700; }.plan-list small { color:var(--muted); font-size:11px; line-height:1.5; }.tier-row { display:flex; gap:5px; margin:16px 0 10px; }.tier-row span { padding:6px 8px; border-radius:7px; background:var(--accent-soft); color:var(--accent); font-size:11px; }.export-actions { display:flex; gap:8px; margin:14px 0; }.export-actions button,.chat-box button { border:1px solid var(--line); border-radius:8px; padding:8px 10px; color:var(--text); background:var(--surface-soft); cursor:pointer; }.chat-box { display:flex; flex-wrap:wrap; gap:7px; }.chat-box input { flex:1; min-width:150px; border:1px solid var(--line); border-radius:8px; padding:8px; color:var(--text); background:var(--panel-strong); outline:none; }.chat-box p { width:100%; margin:8px 0 0; color:var(--muted); font-size:12px; line-height:1.7; }.chat-box .chat-answer { width:100%; margin-top:8px; color:var(--muted); font-size:12px; line-height:1.7; }
.plan-atmosphere { height:110px; margin:-4px 0 -2px; opacity:.9; }
@media (max-width:1100px) { .transcript-hero { grid-template-columns:1fr minmax(280px,430px); }.transcript-hero .primary-action { grid-column:1 / -1; justify-self:start; } }
@media (max-width:900px) { .transcript-page { padding:18px 16px 40px; }.transcript-hero,.panel-header { align-items:stretch; }.transcript-hero { display:flex; flex-direction:column; }.transcript-hero .learning-atmosphere { align-self:center; }.analysis-layout { grid-template-columns:1fr; }.metric-grid { grid-template-columns:repeat(2,1fr); }.diagnosis-grid { grid-template-columns:1fr; }.header-actions { justify-content:flex-start; }.empty-atmosphere { grid-template-columns:1fr; } }
</style>
