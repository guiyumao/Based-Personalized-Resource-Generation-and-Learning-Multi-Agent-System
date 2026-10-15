<script setup lang="ts">
import { computed, onMounted, reactive, ref, type Component } from 'vue'
import {
  ArrowRight,
  ChatDotRound,
  Collection,
  Connection,
  DataAnalysis,
  EditPen,
  Guide,
  MagicStick,
  Notebook,
  Refresh,
  Timer,
  TrendCharts,
} from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { evaluationApi, resourceApi, serviceEndpoints, userApi, type ApiEnvelope, type LearnerProfileDashboard, type ReportDetail, type ResourceRecommendationItem, type UserProfileRead } from '../../api'
import { useAuthStore } from '../../stores/auth'
import LearningAtmosphere from '../../components/LearningAtmosphere.vue'

type ServiceStatus = { label: string; baseUrl: string; online: boolean; checking: boolean }
type ActivityItem = { text: string; time: string; tone: 'success' | 'primary' }
type DashboardCard = { label: string; value: string; hint: string; icon: Component; tone: string }
type ProfileDimensionItem = { key: string; label: string; value: string }

const authStore = useAuthStore()
const router = useRouter()
const user = authStore.user!
const services = reactive<ServiceStatus[]>([
  { label: '用户服务', baseUrl: serviceEndpoints.user, online: false, checking: true },
  { label: '智能体服务', baseUrl: serviceEndpoints.agent, online: false, checking: true },
  { label: '评估服务', baseUrl: serviceEndpoints.evaluation, online: false, checking: true },
])

const dashboard = ref<LearnerProfileDashboard | null>(null)
const learnerProfile = ref<UserProfileRead | null>(null)
const reportDetail = ref<ReportDetail | null>(null)
const recentActivity = ref<ActivityItem[]>([])
const suggestions = ref<string[]>([])
const mistakeStats = ref<Record<string, unknown> | null>(null)
const resources = ref<ResourceRecommendationItem[]>([])
const dashError = ref('')
const loading = ref(true)
const refreshing = ref(false)

const profileDimensionLabels: Record<string, string> = {
  knowledgeBase: '知识基础', cognitiveStyle: '认知风格', errorPreference: '易错偏好',
  learningSpeed: '学习节奏', interestDirection: '兴趣方向', goalOrientation: '目标导向',
}
const profileDimensionKeys = Object.keys(profileDimensionLabels)
const profileDimensionItems = computed<ProfileDimensionItem[]>(() => profileDimensionKeys.map((key) => ({
  key, label: profileDimensionLabels[key], value: learnerProfile.value?.profile_dimensions?.[key]?.trim() || '',
})))
const filledProfileDimensions = computed(() => profileDimensionItems.value.filter((item) => item.value).length)
const profileCompletionPercent = computed(() => Math.round((filledProfileDimensions.value / profileDimensionKeys.length) * 100))
const visibleRadarMetrics = computed(() => (dashboard.value?.radar_metrics ?? []).filter((metric) => metric.dimension && metric.score > 0))
const hasLearningActivity = computed(() => (reportDetail.value?.evidence?.total_answers ?? 0) > 0)
const masteryPct = computed(() => {
  if (!visibleRadarMetrics.value.length) return null
  return Math.round(visibleRadarMetrics.value.reduce((sum, item) => sum + item.score, 0) / visibleRadarMetrics.value.length)
})
const overviewPercent = computed(() => masteryPct.value ?? profileCompletionPercent.value)
const overviewLabel = computed(() => masteryPct.value == null ? '画像完成度' : '平均掌握度')

function isRealLearningStyle(value?: string) {
  return Boolean(value?.trim() && value.trim().toUpperCase() !== 'VARK')
}

const dashboardCards = computed<DashboardCard[]>(() => {
  const data = dashboard.value
  if (!data) return []
  const cards: DashboardCard[] = []
  if (hasLearningActivity.value && isRealLearningStyle(data.learning_style)) cards.push({ label: '学习风格', value: data.learning_style, hint: '由学习行为与画像综合判断', icon: MagicStick, tone: 'violet' })
  if (hasLearningActivity.value && masteryPct.value !== null) cards.push({ label: '平均掌握度', value: `${masteryPct.value}%`, hint: '当前能力维度平均值', icon: TrendCharts, tone: 'indigo' })
  if (hasLearningActivity.value && data.weekly_focus_minutes > 0) cards.push({ label: '本周专注', value: `${data.weekly_focus_minutes} 分钟`, hint: '本周有效学习时长', icon: Timer, tone: 'cyan' })
  if (hasLearningActivity.value && data.mastery_overview > 0) cards.push({ label: '综合评分', value: `${data.mastery_overview}%`, hint: '练习、错题与报告综合结果', icon: DataAnalysis, tone: 'emerald' })
  return cards
})

const mistakeItems = computed(() => [
  { label: '总错题', value: statisticValue('total', 'count'), tone: 'danger' },
  { label: '已掌握', value: statisticValue('mastered', 'resolved'), tone: 'success' },
  { label: '待重练', value: statisticValue('pending', 'unresolved'), tone: 'warning' },
])

function statisticValue(primary: string, fallback: string) {
  const value = mistakeStats.value?.[primary] ?? mistakeStats.value?.[fallback]
  return typeof value === 'number' || typeof value === 'string' ? String(value) : '-'
}

async function checkHealth(service: ServiceStatus) {
  service.checking = true
  try {
    const response = await fetch(new URL('/health', service.baseUrl))
    const data = await response.json()
    service.online = data.status === 'ok'
  } catch { service.online = false } finally { service.checking = false }
}

async function fetchDashboard() {
  dashError.value = ''
  try {
    const { data } = await userApi.get<LearnerProfileDashboard>(`/users/${user.userId}/profile/dashboard`)
    dashboard.value = data
  } catch (error: any) {
    dashError.value = `画像加载失败：${error?.response?.data?.detail ?? error?.message ?? '未知错误'}`
  }
}

async function fetchLearnerProfile() {
  try { learnerProfile.value = (await userApi.get<UserProfileRead>(`/users/${user.userId}/profile`)).data } catch { learnerProfile.value = null }
}

async function fetchRecentActivity() {
  try {
    const { data } = await evaluationApi.get<ApiEnvelope<ReportDetail>>(`/evaluation/reports/comprehensive/${user.userId}/detail`)
    const report = (data as any).data ?? data
    reportDetail.value = report
    recentActivity.value = buildRecentActivity(report)
  } catch { reportDetail.value = null; recentActivity.value = [] }
}

function buildRecentActivity(report: ReportDetail | null): ActivityItem[] {
  if (!report?.evidence) return []
  const items: ActivityItem[] = []
  if (typeof report.evidence.accuracy === 'number' && report.evidence.total_answers > 0) items.push({ text: `综合正确率 ${report.evidence.accuracy}%`, time: report.title || '最新报告', tone: 'success' })
  if (report.evidence.total_answers > 0) items.push({ text: `已完成 ${report.evidence.total_answers} 道练习`, time: report.summary || '累计统计', tone: 'primary' })
  return items
}

async function fetchSuggestions() {
  try { const { data } = await evaluationApi.get(`/evaluation/reports/suggestions/${user.userId}`); suggestions.value = (data as any).data?.suggestions ?? (data as any).suggestions ?? [] } catch { suggestions.value = [] }
}
async function fetchMistakeStats() {
  try { const { data } = await evaluationApi.get(`/evaluation/mistakes/${user.userId}`); mistakeStats.value = (data as any).data ?? data } catch { mistakeStats.value = null }
}
async function fetchResources() {
  try {
    const { data } = await resourceApi.get<ApiEnvelope<ResourceRecommendationItem[]>>('/resources/recommendations', { params: { limit: 4 } })
    resources.value = data.data ?? []
  } catch { resources.value = [] }
}

function openRecommendedResource(resource: ResourceRecommendationItem) {
  void resourceApi.post(`/resources/${resource.id}/interactions`, { action: 'view' }).catch(() => undefined)
  void router.push({ path: '/student/resources', query: { resource: String(resource.id) } })
}

async function refreshDashboard() {
  refreshing.value = true
  await Promise.all([
    fetchDashboard(), fetchLearnerProfile(), fetchRecentActivity(), fetchSuggestions(), fetchMistakeStats(), fetchResources(),
    ...services.map(checkHealth),
  ])
  loading.value = false
  refreshing.value = false
}

onMounted(() => void refreshDashboard())
</script>

<template>
  <div class="student-dashboard">
    <section class="dashboard-hero">
      <div class="hero-copy">
        <span class="hero-kicker">今日学习工作台</span>
        <h1>欢迎回来，{{ user.username }}</h1>
        <p>从真实学习记录、画像和评估结果中，快速找到当前最值得投入的学习任务。</p>
        <div class="hero-actions">
          <el-button type="primary" @click="router.push('/student/learning-path')"><el-icon><Guide /></el-icon>继续学习</el-button>
          <el-button @click="router.push('/student/qa')"><el-icon><ChatDotRound /></el-icon>智能问答</el-button>
          <el-button text :loading="refreshing" @click="refreshDashboard"><el-icon><Refresh /></el-icon>刷新数据</el-button>
        </div>
        <LearningAtmosphere class="dashboard-atmosphere" variant="side" />
      </div>
      <div class="hero-overview">
        <div class="progress-ring" :style="{ '--progress': `${overviewPercent * 3.6}deg` }">
          <div><strong>{{ overviewPercent }}%</strong><span>{{ overviewLabel }}</span></div>
        </div>
        <div class="service-stack">
          <span v-for="service in services" :key="service.label" :class="{ online: service.online, checking: service.checking }">
            <i></i>{{ service.label }}<b>{{ service.checking ? '检测中' : service.online ? '正常' : '离线' }}</b>
          </span>
        </div>
      </div>
    </section>

    <el-alert v-if="dashError" :title="dashError" type="error" show-icon :closable="false" class="dashboard-alert">
      <template #default><el-button size="small" @click="refreshDashboard">重试</el-button></template>
    </el-alert>

    <el-skeleton v-if="loading" :rows="7" animated class="dashboard-skeleton" />
    <template v-else>
      <section v-if="dashboardCards.length" class="metric-grid">
        <article v-for="card in dashboardCards" :key="card.label" class="metric-card-new" :data-tone="card.tone">
          <span class="metric-icon-new"><component :is="card.icon" /></span>
          <div><span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.hint }}</small></div>
        </article>
      </section>
      <section v-else class="first-step-card">
        <span class="metric-icon-new"><EditPen /></span>
        <div><strong>完成第一次练习，开启数据概览</strong><p>掌握度、专注时长和综合评分会基于真实作答记录生成。</p></div>
        <el-button type="primary" plain @click="router.push('/student/exercise')">去练习<el-icon><ArrowRight /></el-icon></el-button>
      </section>

      <section class="dashboard-grid">
        <article class="dashboard-panel profile-panel">
          <header><div><span class="section-kicker">学习画像</span><h2>六维个性化信息</h2><p>画像智能体从你的回答中持续沉淀，用于路径、课件与练习的个性化。</p></div><button class="text-link" type="button" @click="router.push('/profile-setup')">{{ filledProfileDimensions ? '继续完善' : '开始构建' }}<el-icon><ArrowRight /></el-icon></button></header>
          <div class="profile-completion"><div><span>已完善 {{ filledProfileDimensions }}/{{ profileDimensionKeys.length }} 维</span><strong>{{ profileCompletionPercent }}%</strong></div><div class="thin-progress"><i :style="{ width: `${profileCompletionPercent}%` }"></i></div></div>
          <div class="profile-dimension-grid">
            <button v-for="item in profileDimensionItems" :key="item.key" type="button" :class="{ filled: item.value }" @click="router.push('/profile-setup')">
              <span><b>{{ item.label }}</b><em>{{ item.value ? '已记录' : '待完善' }}</em></span><p>{{ item.value || '继续对话后将自动补充' }}</p>
            </button>
          </div>
        </article>

        <article class="dashboard-panel capability-panel">
          <header><div><span class="section-kicker">能力分布</span><h2>当前掌握情况</h2><p>数据来自已完成练习的评估结果。</p></div><span class="data-source">实时画像</span></header>
          <div v-if="visibleRadarMetrics.length" class="capability-bars">
            <div v-for="metric in visibleRadarMetrics" :key="metric.dimension" class="capability-row"><div><span>{{ metric.dimension }}</span><b>{{ metric.score }}%</b></div><div class="capability-track"><i :style="{ width: `${metric.score}%` }"></i></div></div>
          </div>
          <div v-else class="panel-empty"><DataAnalysis /><strong>暂无能力数据</strong><span>完成练习后自动生成</span></div>
        </article>

        <article class="dashboard-panel activity-panel">
          <header><div><span class="section-kicker">近期活动</span><h2>学习进展</h2></div><button class="text-link" type="button" @click="router.push('/student/report')">查看报告<el-icon><ArrowRight /></el-icon></button></header>
          <div v-if="recentActivity.length" class="activity-list"><div v-for="activity in recentActivity" :key="activity.text" :data-tone="activity.tone"><i></i><div><strong>{{ activity.text }}</strong><p>{{ activity.time }}</p></div></div></div>
          <div v-else class="panel-empty compact"><TrendCharts /><strong>还没有学习活动</strong><span>练习与报告更新后会显示在这里</span></div>
        </article>

        <article class="dashboard-panel suggestion-panel">
          <header><div><span class="section-kicker">AI 建议</span><h2>下一步学什么</h2></div><span class="panel-badge">{{ suggestions.length }} 条</span></header>
          <ol v-if="suggestions.length"><li v-for="(suggestion, index) in suggestions" :key="suggestion"><span>{{ String(index + 1).padStart(2, '0') }}</span><p>{{ suggestion }}</p></li></ol>
          <div v-else class="panel-empty compact"><MagicStick /><strong>暂无个性化建议</strong><span>产生更多学习记录后系统会更新</span></div>
        </article>

        <article class="dashboard-panel mistakes-panel">
          <header><div><span class="section-kicker">错题进展</span><h2>巩固情况</h2></div><button class="text-link" type="button" @click="router.push('/student/mistakes')">打开错题本<el-icon><ArrowRight /></el-icon></button></header>
          <div v-if="mistakeStats" class="mistake-grid"><div v-for="item in mistakeItems" :key="item.label" :data-tone="item.tone"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div></div>
          <div v-else class="panel-empty compact"><Notebook /><strong>暂无错题统计</strong><span>提交练习后将同步更新</span></div>
        </article>

        <article class="dashboard-panel resources-panel">
          <header><div><span class="section-kicker">学习资源</span><h2>为你推荐</h2></div><button class="text-link" type="button" @click="router.push('/student/resources')">全部资源<el-icon><ArrowRight /></el-icon></button></header>
          <div v-if="resources.length" class="resource-list"><button v-for="resource in resources" :key="resource.id" type="button" @click="openRecommendedResource(resource)"><span><Collection /></span><div><strong>{{ resource.title }}</strong><p>{{ resource.recommendation_reason }} · {{ resource.view_count }} 次查看</p></div><ArrowRight /></button></div>
          <div v-else class="panel-empty compact"><Collection /><strong>推荐池正在积累</strong><span>保存或生成资源后会结合学习行为自动排序</span></div>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.student-dashboard { display:grid; gap:20px; }
.dashboard-hero { min-height:260px; display:grid; grid-template-columns:minmax(0,1.5fr) minmax(300px,.8fr); gap:28px; padding:30px; border:1px solid color-mix(in srgb,var(--accent) 16%,var(--line)); border-radius:20px; color:var(--text); background:linear-gradient(135deg,var(--panel) 0%,color-mix(in srgb,var(--accent) 7%,var(--panel)) 100%); box-shadow:var(--shadow-soft); overflow:hidden; position:relative; }
.dashboard-hero::after { content:''; width:280px; height:280px; border-radius:50%; position:absolute; right:-100px; top:-140px; background:color-mix(in srgb,var(--accent) 10%,transparent); }
.hero-copy { align-self:center; position:relative; z-index:1; }
.hero-kicker,.section-kicker { color:var(--accent); font-size:11px; font-weight:800; letter-spacing:.1em; }
.hero-copy h1 { margin:9px 0 10px; font-size:clamp(28px,3vw,40px); line-height:1.2; letter-spacing:-.035em; }
.hero-copy p { max-width:680px; margin:0; color:var(--muted); font-size:15px; line-height:1.8; }
.hero-actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:24px; }.dashboard-atmosphere { max-width:260px; margin-top:16px; opacity:.92; }
.hero-overview { display:flex; align-items:center; justify-content:center; gap:22px; padding:18px; border:1px solid var(--line); border-radius:16px; background:color-mix(in srgb,var(--panel-strong) 78%,transparent); position:relative; z-index:1; }
.progress-ring { --progress:0deg; width:132px; height:132px; min-width:132px; border-radius:50%; display:grid; place-items:center; background:conic-gradient(var(--accent) var(--progress),var(--surface-muted) 0); position:relative; }
.progress-ring::after { content:''; position:absolute; inset:10px; border-radius:50%; background:var(--panel-strong); }
.progress-ring div { display:grid; gap:2px; text-align:center; position:relative; z-index:1; }
.progress-ring strong { font-size:27px; font-variant-numeric:tabular-nums; }
.progress-ring span { color:var(--muted); font-size:11px; }
.service-stack { display:grid; gap:9px; min-width:150px; }
.service-stack > span { display:grid; grid-template-columns:8px 1fr auto; gap:7px; align-items:center; color:var(--muted); font-size:11px; }
.service-stack i { width:8px; height:8px; border-radius:50%; background:var(--red); }
.service-stack .online i { background:var(--green); }
.service-stack .checking i { background:var(--warning); }
.service-stack b { color:var(--text); font-size:10px; }
.dashboard-alert,.dashboard-skeleton { border-radius:14px; }
.metric-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }
.metric-card-new,.first-step-card { border:1px solid var(--line); border-radius:16px; background:var(--panel); box-shadow:var(--shadow-soft); }
.metric-card-new { display:grid; grid-template-columns:44px 1fr; gap:14px; align-items:start; padding:20px; position:relative; overflow:hidden; }
.metric-card-new::before { content:''; position:absolute; inset:0 auto 0 0; width:3px; background:var(--tone,var(--accent)); }
.metric-card-new[data-tone='violet'] { --tone:#8b5cf6; }.metric-card-new[data-tone='cyan'] { --tone:#0891b2; }.metric-card-new[data-tone='emerald'] { --tone:var(--green); }
.metric-icon-new { width:44px; height:44px; display:grid; place-items:center; border-radius:12px; color:var(--tone,var(--accent)); background:color-mix(in srgb,var(--tone,var(--accent)) 10%,transparent); }
.metric-icon-new :deep(svg) { width:21px; }
.metric-card-new div { display:grid; gap:3px; }.metric-card-new span { color:var(--muted); font-size:12px; }.metric-card-new strong { color:var(--text); font-size:24px; line-height:1.3; }.metric-card-new small { color:var(--muted); font-size:11px; line-height:1.5; }
.first-step-card { display:flex; align-items:center; gap:14px; padding:18px 20px; }.first-step-card > div { flex:1; }.first-step-card strong { font-size:15px; }.first-step-card p { margin:4px 0 0; color:var(--muted); }
.dashboard-grid { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(320px,.75fr); gap:18px; align-items:start; }
.dashboard-panel { min-width:0; padding:22px; border:1px solid var(--line); border-radius:16px; background:var(--panel); box-shadow:var(--shadow-soft); }
.dashboard-panel > header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:18px; }
.dashboard-panel h2 { margin:5px 0 0; color:var(--text); font-size:20px; letter-spacing:-.025em; }.dashboard-panel header p { max-width:620px; margin:6px 0 0; color:var(--muted); font-size:12px; line-height:1.65; }
.text-link { display:inline-flex; align-items:center; gap:5px; padding:6px 0; border:0; color:var(--accent); background:transparent; font-size:12px; font-weight:700; white-space:nowrap; cursor:pointer; }
.profile-completion { margin-bottom:16px; padding:12px 14px; border-radius:11px; background:var(--surface-soft); }.profile-completion > div:first-child { display:flex; justify-content:space-between; gap:10px; color:var(--muted); font-size:12px; }.profile-completion strong { color:var(--accent); }.thin-progress,.capability-track { height:6px; margin-top:9px; border-radius:10px; background:var(--surface-muted); overflow:hidden; }.thin-progress i,.capability-track i { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,var(--accent),color-mix(in srgb,var(--accent) 62%,var(--info))); }
.profile-dimension-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }.profile-dimension-grid button { min-height:98px; padding:13px; border:1px solid var(--line); border-radius:12px; color:var(--text); background:var(--panel); text-align:left; cursor:pointer; }.profile-dimension-grid button:hover { border-color:color-mix(in srgb,var(--accent) 34%,var(--line)); background:var(--accent-soft); }.profile-dimension-grid button > span { display:flex; align-items:center; justify-content:space-between; gap:8px; }.profile-dimension-grid b { font-size:13px; }.profile-dimension-grid em { color:var(--muted); font-size:10px; font-style:normal; }.profile-dimension-grid .filled em { color:var(--green); }.profile-dimension-grid p { margin:8px 0 0; color:var(--muted); font-size:12px; line-height:1.55; display:-webkit-box; overflow:hidden; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
.data-source,.panel-badge { padding:5px 8px; border-radius:7px; color:var(--accent); background:var(--accent-soft); font-size:10px; font-weight:700; }
.capability-bars { display:grid; gap:15px; }.capability-row > div:first-child { display:flex; justify-content:space-between; gap:10px; font-size:12px; }.capability-row span { color:var(--muted); }.capability-row b { color:var(--text); font-variant-numeric:tabular-nums; }
.activity-list { display:grid; }.activity-list > div { display:grid; grid-template-columns:10px 1fr; gap:12px; padding:13px 0; border-bottom:1px solid var(--line); }.activity-list > div:last-child { border-bottom:0; }.activity-list i { width:9px; height:9px; margin-top:5px; border-radius:50%; background:var(--accent); box-shadow:0 0 0 4px var(--accent-soft); }.activity-list [data-tone='success'] i { background:var(--green); box-shadow:0 0 0 4px color-mix(in srgb,var(--green) 10%,transparent); }.activity-list strong { font-size:13px; }.activity-list p { margin:3px 0 0; color:var(--muted); font-size:11px; line-height:1.5; }
.suggestion-panel ol { display:grid; gap:10px; margin:0; padding:0; list-style:none; }.suggestion-panel li { display:grid; grid-template-columns:28px 1fr; gap:10px; align-items:start; padding:11px; border-radius:11px; background:var(--surface-soft); }.suggestion-panel li span { color:var(--accent); font-size:11px; font-weight:800; }.suggestion-panel li p { margin:0; color:var(--text); font-size:12px; line-height:1.6; }
.mistake-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }.mistake-grid > div { padding:14px; border-radius:11px; background:var(--surface-soft); }.mistake-grid span { display:block; color:var(--muted); font-size:11px; }.mistake-grid strong { display:block; margin-top:5px; color:var(--text); font-size:25px; }.mistake-grid [data-tone='danger'] strong { color:var(--red); }.mistake-grid [data-tone='success'] strong { color:var(--green); }.mistake-grid [data-tone='warning'] strong { color:var(--warning); }
.resource-list { display:grid; gap:8px; }.resource-list button { display:grid; grid-template-columns:34px 1fr 15px; gap:10px; align-items:center; padding:10px; border:1px solid transparent; border-radius:11px; color:var(--text); background:var(--surface-soft); text-align:left; cursor:pointer; }.resource-list button:hover { border-color:var(--line); background:var(--accent-soft); }.resource-list button > span { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:var(--accent); background:var(--panel); }.resource-list strong { display:block; overflow:hidden; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }.resource-list p { margin:2px 0 0; color:var(--muted); font-size:10px; }
.panel-empty { min-height:210px; display:grid; place-items:center; align-content:center; gap:6px; color:var(--muted); text-align:center; }.panel-empty > svg { width:30px; color:var(--accent); }.panel-empty strong { color:var(--text); font-size:13px; }.panel-empty span { font-size:11px; }.panel-empty.compact { min-height:130px; }

@media (max-width:1100px) { .dashboard-hero { grid-template-columns:1fr; }.hero-overview { justify-content:flex-start; }.dashboard-grid { grid-template-columns:1fr; }.profile-dimension-grid { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media (max-width:720px) { .dashboard-hero { padding:22px; border-radius:16px; }.hero-overview { align-items:flex-start; flex-direction:column; }.service-stack { width:100%; }.profile-dimension-grid { grid-template-columns:1fr; }.first-step-card { align-items:flex-start; flex-wrap:wrap; }.first-step-card .el-button { width:100%; }.dashboard-panel { padding:17px; }.mistake-grid { grid-template-columns:1fr; }.dashboard-panel > header { align-items:flex-start; } }
</style>
