<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { evaluationApi } from '../api/http'

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
const maxSeconds = computed(() => Math.max(60, ...days.value.map(day => day.study_seconds ?? 0)))
const minutes = (seconds: number | null | undefined) => seconds == null ? '尚未启用采集' : `${Math.floor(seconds / 60)} 分钟`
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
          <h3>近期生成资源</h3>
          <div v-if="!overview.recent_resources.length" class="overview-empty">暂无生成资源</div>
          <button v-for="resource in overview.recent_resources" :key="resource.id" type="button" class="overview-resource" @click="router.push({ path: '/student/resources', query: { resource: String(resource.id) } })">{{ resource.title || '未命名资源' }} <small>{{ resource.type }} · {{ resource.generation_status }}</small></button>
        </article>
        <article>
          <h3>近七日有效活动</h3>
          <div v-for="day in days" :key="day.date" class="study-day"><time>{{ day.date.slice(5) }}</time><meter min="0" :max="maxSeconds" :value="day.study_seconds ?? 0" :aria-label="`${day.date}有效活动秒数`" /><span>{{ minutes(day.study_seconds) }}</span></div>
          <p class="evidence-note">仅统计学习页面可见、获得焦点且近期有操作的活动；空闲和重复标签页不累计，不回填历史时长。</p>
          <h3>需要加强的知识点</h3>
          <div v-if="!overview.weak_points.length" class="overview-empty">暂无薄弱项证据，完成练习后更新。</div>
          <div v-for="point in overview.weak_points" :key="point.knowledge_point_id" class="overview-weak"><strong>{{ point.name }}</strong><span>{{ point.accuracy_percent }}% · {{ point.graded_answers }} 次判分{{ point.confidence === 'low' ? ' · 样本不足' : '' }}</span><el-button size="small" @click="router.push({ path: '/student/exercise', query: { topic: point.name } })">补强练习</el-button></div>
          <ul class="overview-suggestions"><li v-for="suggestion in overview.suggestions" :key="suggestion">{{ suggestion }}</li></ul>
          <nav aria-label="学习快捷入口"><el-button @click="router.push('/student/report')">学情报告</el-button><el-button @click="router.push('/student/mistakes')">错题本</el-button><el-button @click="router.push('/student/knowledge-graph')">知识图谱</el-button></nav>
        </article>
      </div>
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
.overview-columns { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:28px; }.overview-columns article { min-width:0; }
.overview-plan { padding:16px; border:1px solid var(--line); border-radius:12px; margin-bottom:12px; }.overview-plan ul,.overview-suggestions { padding-left:20px; line-height:1.8; }
.overview-resource { display:block; width:100%; background:none; border:0; border-bottom:1px solid var(--line); padding:12px 0; color:var(--text); text-align:left; font:inherit; overflow-wrap:anywhere; cursor:pointer; }.overview-resource small { display:block; }
.study-day { display:flex; gap:12px; align-items:center; margin:9px 0; font-size:12px; }.study-day meter { flex:1; min-width:20px; }.study-day span { min-width:64px; }.evidence-note { font-size:12px; }
.overview-weak { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:12px 0; }.overview-weak span { color:var(--muted); font-size:12px; } nav { display:flex; flex-wrap:wrap; gap:8px; }
button:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
@media(max-width:1000px) { .overview-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:650px) { .overview-columns { grid-template-columns:minmax(0,1fr); }.learning-overview { padding:16px; } }
</style>
