<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { evaluationApi } from '../api/http'
import { formatDuration } from '../utils/duration'
import LearningContent from './LearningContent.vue'
import WeeklyActivityChart from './WeeklyActivityChart.vue'

type Task = { task_id: string; title: string; knowledge_point: string; task_type: string }
type Plan = { path_id: number; subject: string; knowledge_point: string; completed_tasks: number; total_tasks: number; completion_percent: number | null; pending_tasks: Task[] }
type Overview = {
  active_plans: Plan[]; due_cards: number; suggestions: string[]
  recent_resources: { id: number; title: string; type: string; generation_status: string }[]
  weak_points: { knowledge_point_id: number; name: string; graded_answers: number; accuracy_percent: number; confidence: string }[]
  analytics: {
    daily: { date: string; study_seconds: number | null; answers: number }[]
    summary: { study_seconds: number | null; current_streak_days: number }
    week_comparison: { this_week_study_seconds: number | null; previous_week_study_seconds: number | null }
  }
}
const router = useRouter()
const overview = ref<Overview | null>(null)
const loading = ref(false)
const error = ref('')
const days = computed(() => overview.value?.analytics.daily.slice(-7) ?? [])
const minutes = (seconds: number | null | undefined) => seconds == null ? '尚未启用采集' : formatDuration(seconds)
async function refresh() {
  loading.value = true
  error.value = ''
  try { overview.value = (await evaluationApi.get('/evaluation/overview/me')).data.data }
  catch (reason: any) {
    overview.value = null
    error.value = reason?.response?.status === 404 ? '学习概览接口尚未部署，请更新评估服务后重试。' : `学习概览暂不可用：${reason?.response?.data?.detail ?? reason?.message ?? '连接失败'}`
  } finally { loading.value = false }
}
function openPlan() { void router.push('/student/learning-path') }
onMounted(refresh)
</script>

<template>
  <section class="learning-overview" aria-label="学习计划与有效活动">
    <header><div><h2>我的学习进程</h2><p>计划、练习和复习记录同步汇总</p></div><el-button :loading="loading" @click="refresh">刷新概览</el-button></header>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-skeleton v-else-if="loading" :rows="4" animated />
    <template v-else-if="overview">
      <div class="overview-metrics">
        <div><span>本周有效活动</span><strong>{{ minutes(overview.analytics.week_comparison.this_week_study_seconds) }}</strong></div>
        <div><span>上周有效活动</span><strong>{{ minutes(overview.analytics.week_comparison.previous_week_study_seconds) }}</strong></div>
        <div><span>连续活跃（近30天内）</span><strong>{{ overview.analytics.summary.current_streak_days }} 天</strong></div>
        <button type="button" @click="router.push('/student/study-tools')"><span>到期闪卡</span><strong>{{ overview.due_cards }} 张 →</strong></button>
      </div>
      <div class="overview-columns">
        <article>
          <header><h3>当前计划</h3><el-button size="small" @click="openPlan">创建 / 继续计划</el-button></header>
          <div v-if="!overview.active_plans.length" class="overview-empty">暂无学习计划，选择学科和目标后开始。</div>
          <div v-for="plan in overview.active_plans" :key="plan.path_id" class="overview-plan">
            <h4>{{ plan.subject }} · {{ plan.knowledge_point }}</h4>
            <p>已完成 {{ plan.completed_tasks }} / {{ plan.total_tasks }} 项任务</p>
            <el-progress v-if="plan.completion_percent != null" :percentage="plan.completion_percent" />
            <ul v-if="plan.pending_tasks.length"><li v-for="task in plan.pending_tasks.slice(0, 3)" :key="task.task_id">{{ task.title || task.knowledge_point || '待学习任务' }}</li></ul>
            <el-button size="small" @click="openPlan">打开学习目录</el-button>
          </div>
        </article>
        <article class="overview-activity" aria-label="近七日有效活动">
          <h3>近七日有效活动</h3>
          <WeeklyActivityChart :days="days" />
          <p class="evidence-note">仅统计学习页面可见、获得焦点且近期有操作的活动；空闲和重复标签页不累计，不回填历史时长。</p>
        </article>
        <article>
          <h3>需要加强的知识点</h3>
          <div v-if="!overview.weak_points.length" class="overview-empty">暂无薄弱项证据，完成练习后更新。</div>
          <div v-for="point in overview.weak_points" :key="point.knowledge_point_id" class="overview-weak"><strong>{{ point.name }}</strong><span>{{ point.accuracy_percent }}% · {{ point.graded_answers }} 次判分{{ point.confidence === 'low' ? ' · 样本不足' : '' }}</span><el-button size="small" @click="router.push({ path: '/student/exercise', query: { topic: point.name } })">补强练习</el-button></div>
        </article>
        <article>
          <h3>AI 学习建议</h3>
          <ul v-if="overview.suggestions.length" class="overview-suggestions"><li v-for="suggestion in overview.suggestions" :key="suggestion"><LearningContent :content="suggestion" /></li></ul>
          <div v-else class="overview-empty">产生更多学习记录后，这里会给出个性化建议。</div>
          <nav aria-label="学习快捷入口"><el-button @click="router.push('/student/report')">学情报告</el-button><el-button @click="router.push('/student/mistakes')">错题本</el-button><el-button @click="router.push('/student/knowledge-graph')">知识图谱</el-button></nav>
        </article>
      </div>
      <section class="overview-resources" aria-label="近期生成资源">
        <header><h3>近期生成资源</h3><el-button v-if="overview.recent_resources.length" size="small" text type="primary" @click="router.push('/student/resources')">查看全部 →</el-button></header>
        <div v-if="!overview.recent_resources.length" class="overview-empty">暂无生成资源</div>
        <div v-else class="resource-grid">
          <button v-for="resource in overview.recent_resources.slice(0, 8)" :key="resource.id" type="button" class="resource-card" @click="router.push({ path: '/student/resources', query: { resource: String(resource.id) } })">
            <strong>{{ resource.title || '未命名资源' }}</strong>
            <small><span class="resource-tag">{{ resource.type }}</span>{{ resource.generation_status }}</small>
          </button>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.learning-overview { padding:24px; border:1px solid var(--line); background:var(--panel); border-radius:18px; min-width:0; }
header { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-bottom:16px; }
h2,h3,h4,p { margin:0 0 10px; } h2 { font-size:20px; } h3 { margin-top:16px; font-size:16px; } h4 { overflow-wrap:anywhere; }
p,small,.overview-empty,.evidence-note { color:var(--muted); line-height:1.7; }
.overview-metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
.overview-metrics>div,.overview-metrics>button { display:grid; gap:10px; padding:16px; border:1px solid var(--line); border-radius:12px; background:var(--surface-muted); text-align:left; color:var(--text); font:inherit; }
.overview-metrics span { color:var(--muted); font-size:13px; }.overview-metrics strong { font-size:20px; }
.overview-columns { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:20px 28px; align-items:start; margin-top:20px; }.overview-columns article { min-width:0; }
.overview-columns article > h3:first-child,.overview-columns article > header h3 { margin-top:0; }
.overview-activity { padding:18px; border:1px solid var(--line); border-radius:12px; background:var(--surface-muted); }
.overview-activity .evidence-note { margin:8px 0 0; }
.overview-plan { padding:16px; border:1px solid var(--line); border-radius:12px; margin-bottom:12px; }.overview-plan ul,.overview-suggestions { padding-left:20px; line-height:1.8; }
.overview-resources { margin-top:24px; padding-top:18px; border-top:1px solid var(--line); }
.overview-resources > header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.overview-resources h3 { margin:0; }
.resource-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:10px; }
.resource-card { display:grid; gap:8px; align-content:start; padding:14px; border:1px solid var(--line); border-radius:12px; background:var(--surface-muted); color:var(--text); text-align:left; font:inherit; cursor:pointer; transition:border-color .15s ease, background .15s ease, transform .15s ease; }
.resource-card:hover { border-color:color-mix(in srgb,var(--accent) 40%,var(--line)); background:var(--accent-soft); transform:translateY(-1px); }
.resource-card strong { font-size:13px; line-height:1.5; overflow-wrap:anywhere; display:-webkit-box; overflow:hidden; -webkit-line-clamp:2; -webkit-box-orient:vertical; min-height:2.9em; }
.resource-card small { color:var(--muted); font-size:11px; display:flex; align-items:center; gap:6px; }
.resource-tag { padding:2px 7px; border-radius:6px; background:var(--accent-soft); color:var(--accent); font-weight:700; }
.evidence-note { font-size:12px; }
.overview-weak { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:12px 0; }.overview-weak span { color:var(--muted); font-size:12px; } nav { display:flex; flex-wrap:wrap; gap:8px; }
button:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
@media(max-width:1000px) { .overview-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:650px) { .overview-columns { grid-template-columns:minmax(0,1fr); }.learning-overview { padding:16px; } }
</style>
