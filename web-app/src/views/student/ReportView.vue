<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  evaluationApi,
  type ApiEnvelope,
  type LearnerProfileSnapshot,
  type LearnerSuggestion,
  type MistakeItem,
  type MistakeNotebook,
  type ReportDashboard,
  type ReportDetail,
} from '../../api'

const authStore = useAuthStore()
const user = authStore.user!

const stageReport = ref<ReportDetail | null>(null)
const comprehensiveReport = ref<ReportDetail | null>(null)
const activeReport = ref<ReportDetail | null>(null)
const reportListPanel = ref<HTMLElement | null>(null)
const reportDetailPanel = ref<HTMLElement | null>(null)
const profileSnapshot = ref<LearnerProfileSnapshot | null>(null)
const learningSuggestions = ref<LearnerSuggestion | null>(null)
const mistakeNotebook = ref<MistakeNotebook | null>(null)
const loading = ref(false)
const reportError = ref('')
type ActivityDay = { date: string; answers: number; resource_events: number; questions_asked: number; card_reviews: number }
type KnowledgeAccuracy = { knowledge_point_id: number; name: string; answers: number; graded_answers: number; accuracy_percent: number | null }
type PathProgress = { path_id: number; total_tasks: number; completed_tasks: number; completion_percent: number | null }
type LearningAnalytics = {
  summary: { answers: number; graded_answers: number; accuracy_percent: number | null; active_days: number; question_seconds: number; resource_events: number; questions_asked: number; card_reviews: number; study_seconds?: number | null }
  week_comparison: { last_seven_answers: number; previous_seven_answers: number | null }
  daily: ActivityDay[]
  knowledge_accuracy: KnowledgeAccuracy[]
  path_progress: PathProgress | null
}
const analytics = ref<LearningAnalytics | null>(null)
const analyticsError = ref('')
const recentActivity = computed(() => analytics.value?.daily.slice(-14) ?? [])
const activityPeak = computed(() => Math.max(1, ...recentActivity.value.map(day => day.answers + day.resource_events + day.questions_asked + day.card_reviews)))

async function fetchAnalytics() {
  analyticsError.value = ''
  try {
    const response = await evaluationApi.get<ApiEnvelope<LearningAnalytics>>(`/evaluation/analytics/${user.userId}?days=30`)
    analytics.value = response.data.data
  } catch {
    analyticsError.value = '学习行为统计暂时不可用。'
  }
}

type PersonalInsightTone = 'good' | 'note' | 'bad'

type PersonalInsight = {
  title: string
  text: string
  tone: PersonalInsightTone
}

function openReportDetail(report: ReportDetail | null) {
  if (!report) {
    return
  }
  activeReport.value = report
  nextTick(() => {
    reportDetailPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function closeReportDetail() {
  activeReport.value = null
  nextTick(() => {
    reportListPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function reportKindLabel(reportType: ReportDetail['report_type']) {
  return reportType === 'stage' ? '阶段报告' : '综合报告'
}

const reportScopeText = computed(() => {
  const report = activeReport.value
  if (!report) {
    return ''
  }
  return report.report_type === 'stage'
    ? '聚焦最近章节或当前学习阶段，用来判断刚学内容是否过关。'
    : '汇总近 30 天整体表现，用来观察长期趋势、错题沉淀和下一阶段优先级。'
})

const detailMetricTitle = computed(() => {
  const report = activeReport.value
  if (!report) {
    return '报告指标'
  }
  return report.report_type === 'stage' ? '阶段掌握情况' : '近 30 天综合表现'
})

const diagnosisTitle = computed(() => {
  const report = activeReport.value
  if (!report) {
    return '具体诊断'
  }
  return report.report_type === 'stage' ? '本阶段诊断' : '本阶段全部错题'
})

const comprehensiveMistakes = computed<MistakeItem[]>(() => mistakeNotebook.value?.items ?? [])

const personalizedSectionTitle = computed(() => {
  const report = activeReport.value
  if (!report) {
    return '个性化分析'
  }
  return report.report_type === 'stage' ? '阶段个性化补救方案' : '综合个性化成长方案'
})

const personalizedSummaryTitle = computed(() => {
  const report = activeReport.value
  if (!report) {
    return '个性化结论'
  }
  return report.report_type === 'stage' ? '本阶段结论' : '近 30 天结论'
})

const personalizedInsights = computed<PersonalInsight[]>(() => {
  const report = activeReport.value
  if (!report) {
    return []
  }

  const insights: PersonalInsight[] = []
  const weakPoint = report.evidence.weakest_knowledge_point
  const weakTypes = report.evidence.weakest_question_types ?? []
  const snapshot = profileSnapshot.value
  const suggestions = learningSuggestions.value

  if (report.report_type === 'stage') {
    if (weakPoint) {
      insights.push({
        title: '本阶段突破口',
        text: `这一阶段先盯住 ${weakPoint}。它代表刚学内容里最容易失分的环节，适合用 10 到 15 分钟的小练习立刻补上。`,
        tone: 'bad',
      })
    }

    if (weakTypes.length) {
      insights.push({
        title: '本章题型修正',
        text: `当前章节失分集中在 ${weakTypes.slice(0, 2).join('、')}，建议先复盘这类题的审题步骤，再做同知识点变式题。`,
        tone: 'note',
      })
    }

    insights.push({
      title: '即时训练安排',
      text: `本阶段共完成 ${report.evidence.total_answers} 题，正确率 ${report.evidence.accuracy}%。下一次练习应优先保证这个章节的基础题稳定正确。`,
      tone: report.evidence.accuracy >= 70 ? 'good' : 'note',
    })

    if (snapshot?.learning_style) {
      insights.push({
        title: '阶段学习方式',
        text: `你的学习风格偏向“${snapshot.learning_style}”，本章复习更适合把概念、例题和错题解析放在同一轮里处理。`,
        tone: 'good',
      })
    }

    if (suggestions?.recommended_action) {
      insights.push({
        title: '本阶段动作',
        text: suggestions.recommended_action,
        tone: 'good',
      })
    }

    return insights.length
      ? insights
      : [{
          title: '阶段结论',
          text: '当前阶段数据还不够多，先完成本章练习，再回来查看更稳定的阶段诊断。',
          tone: 'note',
        }]
  }

  if (weakPoint) {
    insights.push({
      title: '长期薄弱趋势',
      text: `近 30 天持续薄弱的是 ${weakPoint}，它不是单次失误，更像需要放进下一阶段计划里的稳定补弱目标。`,
      tone: 'bad',
    })
  }

  if (weakTypes.length) {
    insights.push({
      title: '题型稳定性',
      text: `近 30 天失分更多出现在 ${weakTypes.slice(0, 2).join('、')}，说明这些题型需要持续训练，而不是只做一次章节补救。`,
      tone: 'note',
    })
  }

  if ((report.evidence.average_time_spent || 0) > 180) {
    insights.push({
      title: '长期用时节奏',
      text: `近 30 天平均用时约 ${Math.round(report.evidence.average_time_spent)} 秒，建议把限时训练纳入每周安排，减少长期犹豫成本。`,
      tone: 'note',
    })
  }

  if (snapshot?.learning_style) {
    insights.push({
      title: '综合学习偏好',
      text: `从整体画像看，你偏向“${snapshot.learning_style}”学习方式。后续计划可以把 ${weakPoint || '长期薄弱知识点'} 和错题回看、示例迁移结合起来。`,
      tone: 'good',
    })
  }

  if (snapshot?.habit_summary) {
    insights.push({
      title: '长期学习习惯',
      text: snapshot.habit_summary,
      tone: 'note',
    })
  }

  if (suggestions?.recommended_action) {
    insights.push({
      title: '下阶段策略',
      text: suggestions.recommended_action,
      tone: 'good',
    })
  }

  if (!insights.length) {
    insights.push({
      title: '个性化结论',
      text: '当前还没有足够的画像和作答记录来生成更细的个性化分析，建议继续完成练习后刷新报告。',
      tone: 'note',
    })
  }

  return insights
})

const personalizedSummary = computed(() => {
  const report = activeReport.value
  if (!report) {
    return ''
  }
  const parts: string[] = []
  if (report.evidence.weakest_knowledge_point) {
    const prefix = report.report_type === 'stage' ? '本阶段最该优先处理' : '近 30 天持续薄弱的是'
    parts.push(`${prefix} ${report.evidence.weakest_knowledge_point}`)
  }
  if (profileSnapshot.value?.learning_style) {
    const styleAction = report.report_type === 'stage' ? '用于本章即时复盘' : '用于长期复习计划'
    parts.push(`你的学习风格适合配合 ${profileSnapshot.value.learning_style} 方式${styleAction}`)
  }
  const suggestions = learningSuggestions.value
  if (suggestions?.suggestions?.length || suggestions?.focus_areas?.length || suggestions?.recommended_action) {
    parts.push(report.report_type === 'stage' ? '当前建议偏向短周期补救' : '当前建议偏向下一阶段规划')
  }
  if (parts.length) {
    return `${parts.join('，')}。`
  }
  return report.report_type === 'stage'
    ? '本阶段可以先从最近错题和本章高频薄弱点入手。'
    : '综合报告建议从近 30 天错题分布、用时节奏和长期薄弱点入手。'
})

async function fetchReports() {
  loading.value = true; reportError.value = ''
  try {
    const response = await evaluationApi.get<ApiEnvelope<ReportDashboard>>(
      `/evaluation/reports/dashboard/${user.userId}`,
    )
    const dashboard = (response.data as any).data ?? response.data
    stageReport.value = dashboard.stage_report
    comprehensiveReport.value = dashboard.comprehensive_report
    profileSnapshot.value = dashboard.profile_snapshot ?? null
    learningSuggestions.value = dashboard.learning_suggestions ?? null
    mistakeNotebook.value = dashboard.mistake_notebook ?? null
    ElMessage.success('学习报告已刷新')
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    reportError.value = `加载失败：${detail}`
    ElMessage.error(reportError.value)
  } finally {
    loading.value = false
  }
}

async function refreshPage() {
  await Promise.all([fetchReports(), fetchAnalytics()])
}

onMounted(() => { refreshPage() })
</script>

<template>
  <div>
    <div style="margin-bottom:24px;display:flex;justify-content:space-between;align-items:center">
      <div><h2 style="font-size:24px;font-weight:750">📈 学习报告</h2><p style="color:var(--muted);font-size:14px">阶段性学习分析与诊断</p></div>
      <button :disabled="loading" @click="refreshPage" style="padding:10px 20px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--text);cursor:pointer;font-weight:600;font-family:inherit">{{ loading ? '正在加载...' : '刷新学习分析与报告' }}</button>
    </div>

    <div v-if="activeReport" class="report-active-banner">
      <span>当前显示：<strong>{{ reportKindLabel(activeReport.report_type) }}</strong> - {{ activeReport.title }}</span>
      <button type="button" class="report-back compact" @click="closeReportDetail">返回报告列表</button>
    </div>

    <div v-if="reportError" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:16px;font-size:14px">{{ reportError }}</div>

    <section class="activity-panel" aria-label="近30天学习行为">
      <div class="activity-heading"><div><span class="panel-kicker">真实学习记录</span><h3>近 30 天学习行为</h3></div><small>统计来自作答、资源交互与问答记录</small></div>
      <p v-if="analyticsError" class="activity-note">{{ analyticsError }}</p>
      <template v-else-if="analytics">
        <div class="activity-metrics">
          <div><strong>{{ analytics.summary.answers }}</strong><span>作答题次</span></div>
          <div><strong>{{ analytics.summary.accuracy_percent === null ? '暂无' : `${analytics.summary.accuracy_percent}%` }}</strong><span>已判分正确率</span></div>
          <div><strong>{{ analytics.summary.active_days }}</strong><span>有记录天数</span></div>
          <div><strong>{{ analytics.summary.resource_events }}</strong><span>资源交互</span></div>
          <div><strong>{{ analytics.summary.questions_asked }}</strong><span>提问次数</span></div>
          <div><strong>{{ analytics.summary.card_reviews }}</strong><span>闪卡复习</span></div>
          <div><strong>{{ Math.round(analytics.summary.question_seconds / 60) }} 分钟</strong><span>有记录的做题用时</span></div>
          <div><strong>{{ analytics.summary.study_seconds == null ? '尚未启用采集' : `${Math.floor(analytics.summary.study_seconds / 60)} 分钟` }}</strong><span>有效学习活动（独立采集）</span></div>
        </div>
        <div class="activity-trend">
          <div class="activity-trend-label">近 14 天活动 <small>每根柱为作答、资源交互、提问和闪卡复习之和</small></div>
          <div class="activity-bars" role="img" :aria-label="`近14天共作答 ${recentActivity.reduce((sum, day) => sum + day.answers, 0)} 题次`">
            <div v-for="day in recentActivity" :key="day.date" class="activity-bar-cell" :title="`${day.date}：作答 ${day.answers}，资源 ${day.resource_events}，提问 ${day.questions_asked}，闪卡 ${day.card_reviews}`">
              <div class="activity-bar" :style="{ height: `${Math.max(5, (day.answers + day.resource_events + day.questions_asked + day.card_reviews) / activityPeak * 100)}%` }"></div>
              <span>{{ day.date.slice(5) }}</span>
            </div>
          </div>
          <p class="activity-note">最近 7 天作答 {{ analytics.week_comparison.last_seven_answers }} 题次；前 7 天 {{ analytics.week_comparison.previous_seven_answers ?? 0 }} 题次。资源浏览不计为掌握，做题用时不等于总学习时长。</p>
        </div>
        <div class="activity-breakdown">
          <div><h4>知识点作答表现</h4><p class="activity-note">近 30 天已判分练习的正确率，不代表全部知识掌握度。</p>
            <div v-for="point in analytics.knowledge_accuracy.slice(0, 6)" :key="point.knowledge_point_id" class="activity-point"><span>{{ point.name }}</span><strong>{{ point.accuracy_percent === null ? '未判分' : `${point.accuracy_percent}%` }}</strong><small>{{ point.graded_answers }} / {{ point.answers }} 题已判分</small></div>
            <p v-if="!analytics.knowledge_accuracy.length" class="activity-note">暂无关联知识点的练习记录。</p>
          </div>
          <div><h4>当前学习路径</h4><template v-if="analytics.path_progress"><strong>{{ analytics.path_progress.completion_percent === null ? '暂无任务' : `${analytics.path_progress.completion_percent}%` }}</strong><p class="activity-note">已完成 {{ analytics.path_progress.completed_tasks }} / {{ analytics.path_progress.total_tasks }} 个任务</p><router-link to="/student/learning-path">查看学习路径</router-link></template><p v-else class="activity-note">当前没有进行中的学习路径。</p></div>
        </div>
      </template>
      <p v-else class="activity-note">正在汇总学习记录…</p>
    </section>

    <div ref="reportListPanel" class="report-card-grid">
      <button
        type="button"
        class="report-card"
        :class="{ active: activeReport?.report_type === 'stage' }"
        :disabled="!stageReport"
        :aria-pressed="activeReport?.report_type === 'stage'"
        @click="openReportDetail(stageReport)"
      >
        <h3 style="margin-bottom:14px">📋 阶段报告</h3>
        <div v-if="stageReport">
          <div style="display:flex;gap:24px;margin-bottom:16px">
            <div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--accent)">{{ stageReport.evidence.accuracy }}%</div><div style="font-size:11px;color:var(--muted)">正确率</div></div>
            <div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--accent)">{{ stageReport.evidence.total_answers }}</div><div style="font-size:11px;color:var(--muted)">总题数</div></div>
          </div>
          <p style="font-size:14px;color:var(--muted);line-height:1.7;margin-bottom:12px">{{ stageReport.summary }}</p>
          <div v-if="stageReport.strengths?.length"><span v-for="s in stageReport.strengths" :key="s" style="display:inline-block;padding:4px 10px;margin:2px;border-radius:999px;font-size:11px;background:color-mix(in srgb,var(--green) 8%,transparent);color:var(--green)">{{ s }}</span></div>
          <div v-if="stageReport.weaknesses?.length" style="margin-top:8px"><span v-for="w in stageReport.weaknesses" :key="w" style="display:inline-block;padding:4px 10px;margin:2px;border-radius:999px;font-size:11px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red)">{{ w }}</span></div>
          <div style="margin-top:18px;font-size:12px;color:var(--accent);font-weight:700;text-align:left">点击查看阶段报告详情</div>
        </div>
        <div v-else style="text-align:center;padding:40px;color:var(--muted)">暂无数据，点击刷新加载</div>
      </button>
      <button
        type="button"
        class="report-card"
        :class="{ active: activeReport?.report_type === 'comprehensive' }"
        :disabled="!comprehensiveReport"
        :aria-pressed="activeReport?.report_type === 'comprehensive'"
        @click="openReportDetail(comprehensiveReport)"
      >
        <h3 style="margin-bottom:14px">📊 综合报告</h3>
        <div v-if="comprehensiveReport">
          <div style="display:flex;gap:24px;margin-bottom:16px">
            <div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--accent)">{{ comprehensiveReport.evidence.accuracy }}%</div><div style="font-size:11px;color:var(--muted)">综合正确率</div></div>
            <div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--red)">{{ comprehensiveReport.evidence.mistake_count }}</div><div style="font-size:11px;color:var(--muted)">错题数</div></div>
          </div>
          <p style="font-size:14px;color:var(--muted);line-height:1.7;margin-bottom:12px">{{ comprehensiveReport.summary }}</p>
          <div v-if="comprehensiveReport.next_actions?.length">
            <span v-for="a in comprehensiveReport.next_actions" :key="a" style="display:inline-block;padding:4px 10px;margin:2px;border-radius:999px;font-size:11px;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent)">{{ a }}</span>
          </div>
          <div style="margin-top:18px;font-size:12px;color:var(--accent);font-weight:700;text-align:left">点击查看综合报告详情</div>
        </div>
        <div v-else style="text-align:center;padding:40px;color:var(--muted)">暂无数据</div>
      </button>
    </div>

    <section v-if="activeReport" ref="reportDetailPanel" class="report-inline-panel">
      <div class="report-inline-head">
        <div>
          <div class="panel-kicker">{{ reportKindLabel(activeReport.report_type) }}详情</div>
          <h3>{{ activeReport.title }}</h3>
        </div>
        <div class="report-actions">
          <button type="button" class="report-back" @click="closeReportDetail">返回报告列表</button>
          <button type="button" class="report-close" aria-label="关闭报告详情" @click="closeReportDetail">×</button>
        </div>
      </div>

      <div class="report-scope-band" :data-kind="activeReport.report_type">
        <span>{{ activeReport.report_type === 'stage' ? '阶段诊断' : '综合诊断' }}</span>
        <p>{{ reportScopeText }}</p>
      </div>

      <div class="report-focus-grid">
        <div>
          <span>报告范围</span>
          <strong>{{ activeReport.report_type === 'stage' ? '最近章节 / 当前阶段' : '近 30 天学习记录' }}</strong>
        </div>
        <div>
          <span>判断重点</span>
          <strong>{{ activeReport.report_type === 'stage' ? '本章是否过关' : '整体趋势与稳定性' }}</strong>
        </div>
        <div>
          <span>建议口径</span>
          <strong>{{ activeReport.report_type === 'stage' ? '立即补救薄弱知识点' : '安排下一阶段学习优先级' }}</strong>
        </div>
      </div>

      <p class="report-modal-summary">{{ activeReport.summary }}</p>

      <h4 class="report-detail-title">{{ detailMetricTitle }}</h4>
      <section class="report-metrics">
        <div>
          <strong>{{ activeReport.evidence.accuracy }}%</strong>
          <span>{{ activeReport.report_type === 'stage' ? '阶段正确率' : '综合正确率' }}</span>
        </div>
        <div>
          <strong>{{ activeReport.evidence.total_answers }}</strong>
          <span>{{ activeReport.report_type === 'stage' ? '本阶段题数' : '近 30 天题数' }}</span>
        </div>
        <div>
          <strong>{{ activeReport.evidence.correct_answers }}</strong>
          <span>答对题数</span>
        </div>
        <div>
          <strong>{{ activeReport.evidence.mistake_count }}</strong>
          <span>{{ activeReport.report_type === 'stage' ? '阶段错题数' : '错题总量' }}</span>
        </div>
        <div>
          <strong>{{ Math.round(activeReport.evidence.average_time_spent) }}s</strong>
          <span>平均用时</span>
        </div>
        <div>
          <strong>{{ activeReport.evidence.average_score }}</strong>
          <span>平均得分</span>
        </div>
      </section>

      <div class="report-summary-grid">
        <section class="report-section">
          <h4>优势</h4>
          <div v-if="activeReport.strengths?.length" class="tag-row">
            <span v-for="item in activeReport.strengths" :key="`${activeReport.report_type}-strength-${item}`" class="tag tag-good">{{ item }}</span>
          </div>
          <p v-else class="empty-line">暂无优势标签。</p>
        </section>

        <section class="report-section">
          <h4>薄弱点</h4>
          <div v-if="activeReport.weaknesses?.length" class="tag-row">
            <span v-for="item in activeReport.weaknesses" :key="`${activeReport.report_type}-weakness-${item}`" class="tag tag-bad">{{ item }}</span>
          </div>
          <p v-else class="empty-line">暂无薄弱点标签。</p>
        </section>

        <section class="report-section">
          <h4>{{ activeReport.report_type === 'stage' ? '阶段补救动作' : '下一阶段学习策略' }}</h4>
          <div v-if="activeReport.next_actions?.length" class="tag-row">
            <span v-for="item in activeReport.next_actions" :key="`${activeReport.report_type}-next-${item}`" class="tag tag-note">{{ item }}</span>
          </div>
          <p v-else class="empty-line">暂无后续建议。</p>
        </section>
      </div>

      <div class="report-inline-grid">
        <section class="report-section">
          <h4>{{ personalizedSectionTitle }}</h4>
          <div class="detail-stack">
            <div class="insight-summary">
              <strong>{{ personalizedSummaryTitle }}</strong>
              <p>{{ personalizedSummary }}</p>
            </div>

            <div v-if="personalizedInsights.length" class="insight-grid">
              <article
                v-for="item in personalizedInsights"
                :key="`inline-${item.title}-${item.text}`"
                class="insight-card"
                :data-tone="item.tone"
              >
                <span class="insight-title">{{ item.title }}</span>
                <p>{{ item.text }}</p>
              </article>
            </div>
          </div>
        </section>

        <section class="report-section">
          <h4>{{ diagnosisTitle }}</h4>
          <div v-if="activeReport.report_type === 'comprehensive'" class="detail-stack">
            <div class="mistake-list-head">
              <span>共 {{ comprehensiveMistakes.length }} 道错题</span>
              <strong>{{ activeReport.evidence.mistake_count }} 次错题记录</strong>
            </div>

            <div v-if="comprehensiveMistakes.length" class="mistake-list">
              <article
                v-for="(item, index) in comprehensiveMistakes"
                :key="`${item.exercise_id}-${index}`"
                class="mistake-detail-card"
              >
                <div class="mistake-card-head">
                  <span>错题 {{ index + 1 }}</span>
                  <strong>{{ item.knowledge_point }}</strong>
                </div>
                <p class="mistake-prompt">{{ item.prompt || '题目内容暂无' }}</p>
                <div class="mistake-answer-grid">
                  <div>
                    <span>题型</span>
                    <strong>{{ item.question_type }}</strong>
                  </div>
                  <div>
                    <span>作答</span>
                    <strong>{{ item.user_answer || '未作答' }}</strong>
                  </div>
                  <div>
                    <span>正确答案</span>
                    <strong>{{ item.correct_answer }}</strong>
                  </div>
                </div>
                <p v-if="item.analysis" class="mistake-analysis">解析：{{ item.analysis }}</p>
                <p v-if="item.suggested_action" class="mistake-analysis">建议：{{ item.suggested_action }}</p>
              </article>
            </div>

            <p v-else class="empty-line">当前阶段暂无错题记录。</p>
          </div>

          <div v-else class="detail-stack">
            <div v-if="activeReport.evidence.weakest_knowledge_point" class="detail-row">
              <span>最薄弱知识点</span>
              <strong>{{ activeReport.evidence.weakest_knowledge_point }}</strong>
            </div>
            <div v-if="activeReport.evidence.weakest_knowledge_accuracy !== null" class="detail-row">
              <span>该知识点正确率</span>
              <strong>{{ activeReport.evidence.weakest_knowledge_accuracy }}%</strong>
            </div>
            <div v-if="activeReport.evidence.latest_mistake" class="mistake-box">
              <div><span>最近错题</span><strong>{{ activeReport.evidence.latest_mistake.knowledge_point }}</strong></div>
              <p>题型：{{ activeReport.evidence.latest_mistake.question_type }}</p>
              <p>作答：{{ activeReport.evidence.latest_mistake.user_answer }}</p>
              <p>正确：{{ activeReport.evidence.latest_mistake.correct_answer }}</p>
              <p>解析：{{ activeReport.evidence.latest_mistake.analysis }}</p>
            </div>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
.activity-panel { margin-bottom:20px; padding:22px; border:1px solid var(--line); border-radius:18px; background:var(--panel); box-shadow:var(--shadow-soft); }
.activity-heading { display:flex; align-items:end; justify-content:space-between; gap:12px; margin-bottom:17px; }
.activity-heading h3 { margin:4px 0 0; color:var(--text); font-size:19px; }
.activity-heading small,.activity-note { color:var(--muted); font-size:12px; }
.activity-metrics { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; }
.activity-metrics > div { padding:13px; border-radius:12px; background:var(--surface-soft); }
.activity-metrics strong,.activity-metrics span { display:block; }
.activity-metrics strong { color:var(--text); font-size:19px; }
.activity-metrics span { margin-top:4px; color:var(--muted); font-size:11px; }
.activity-trend { margin-top:19px; }
.activity-trend-label { color:var(--text); font-weight:700; font-size:13px; }
.activity-trend-label small { margin-left:9px; color:var(--muted); font-weight:400; }
.activity-bars { display:grid; grid-template-columns:repeat(14,minmax(0,1fr)); gap:7px; height:116px; margin-top:12px; }
.activity-bar-cell { display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:5px; min-width:0; }
.activity-bar { width:100%; min-height:4px; max-width:26px; border-radius:5px 5px 2px 2px; background:var(--accent); }
.activity-bar-cell span { color:var(--muted); font-size:9px; white-space:nowrap; }
.activity-breakdown { display:grid; grid-template-columns:2fr 1fr; gap:16px; margin-top:20px; }.activity-breakdown > div { padding:16px; background:var(--surface-soft); border-radius:12px; }.activity-breakdown h4 { margin:0 0 5px; font-size:14px; }.activity-breakdown strong { color:var(--text); }.activity-point { display:flex; align-items:center; gap:12px; padding:8px 0; border-top:1px solid var(--line); font-size:12px; }.activity-point span { flex:1; }.activity-point small { color:var(--muted); }
@media (max-width:1100px) { .activity-metrics { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media (max-width:680px) { .activity-heading { align-items:start; flex-direction:column; }.activity-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }.activity-bars { gap:3px; }.activity-bar-cell span { font-size:8px; transform:rotate(-40deg); }.activity-breakdown { grid-template-columns:1fr; } }
.report-card {
  padding: 22px;
  border-radius: 18px;
  background: var(--panel);
  border: 1px solid var(--line);
  text-align: left;
  cursor: pointer;
  color: inherit;
  font: inherit;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.report-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.report-card:disabled {
  cursor: default;
  opacity: 0.7;
}

.report-card h3 {
  margin-bottom: 14px;
}

.report-card:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent) 24%, var(--line));
  transform: translateY(-1px);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.16);
}

.report-card.active {
  border-color: color-mix(in srgb, var(--accent) 72%, var(--line));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 34%, transparent), 0 14px 34px rgba(0, 0, 0, 0.18);
}

.report-active-banner {
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--panel);
  color: var(--text);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.report-inline-panel {
  margin-top: 20px;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
}

.report-inline-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.report-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.report-back {
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid color-mix(in srgb, var(--accent) 36%, var(--line));
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent) 10%, var(--panel));
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
}

.report-back.compact {
  flex: 0 0 auto;
}

.report-inline-head h3 {
  margin: 10px 0 0;
  font-size: 22px;
  font-weight: 750;
}

.report-inline-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 18px;
  margin-top: 18px;
}

.report-scope-band {
  margin-top: 18px;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--line));
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent) 7%, var(--bg));
  display: grid;
  gap: 6px;
}

.report-scope-band[data-kind='comprehensive'] {
  border-color: color-mix(in srgb, var(--green) 24%, var(--line));
  background: color-mix(in srgb, var(--green) 6%, var(--bg));
}

.report-scope-band span {
  color: var(--accent);
  font-size: 13px;
  font-weight: 750;
}

.report-scope-band[data-kind='comprehensive'] span {
  color: var(--green);
}

.report-scope-band p {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.report-focus-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.report-focus-grid div {
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--bg) 78%, var(--panel));
  display: grid;
  gap: 4px;
}

.report-focus-grid span {
  color: var(--muted);
  font-size: 12px;
}

.report-focus-grid strong {
  color: var(--text);
  font-size: 14px;
}

.report-detail-title {
  margin: 16px 0 10px;
  font-size: 16px;
}

.report-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.report-close {
  width: 34px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--bg);
  color: var(--muted);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
}

.report-modal-summary {
  margin: 16px 0 18px;
  color: var(--muted);
  line-height: 1.8;
}

.report-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.report-metrics div,
.detail-row,
.mistake-box {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--bg) 76%, var(--panel));
}

.report-metrics div {
  padding: 14px;
  display: grid;
  gap: 4px;
}

.report-metrics strong {
  color: var(--accent);
  font-size: 20px;
}

.report-metrics span,
.detail-row span,
.empty-line,
.mistake-box p {
  color: var(--muted);
}

.report-section {
  margin-top: 18px;
}

.report-section h4 {
  margin-bottom: 10px;
  font-size: 16px;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
}

.tag-good {
  background: color-mix(in srgb, var(--green) 10%, transparent);
  color: var(--green);
}

.tag-bad {
  background: color-mix(in srgb, var(--red) 10%, transparent);
  color: var(--red);
}

.tag-note {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
}

.detail-stack {
  display: grid;
  gap: 10px;
}

.detail-row,
.mistake-box {
  padding: 14px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.detail-row strong,
.mistake-box strong {
  color: var(--text);
}

.mistake-box {
  display: grid;
  gap: 8px;
}

.mistake-list-head {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent) 6%, var(--bg));
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.mistake-list-head span {
  color: var(--muted);
}

.mistake-list-head strong {
  color: var(--accent);
}

.mistake-list {
  display: grid;
  gap: 12px;
  max-height: 620px;
  overflow: auto;
  padding-right: 4px;
}

.mistake-detail-card {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--bg) 76%, var(--panel));
  display: grid;
  gap: 12px;
}

.mistake-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.mistake-card-head span,
.mistake-answer-grid span {
  color: var(--muted);
}

.mistake-card-head strong {
  color: var(--text);
  text-align: right;
}

.mistake-prompt,
.mistake-analysis {
  margin: 0;
  color: var(--muted);
  line-height: 1.75;
  white-space: pre-wrap;
}

.mistake-answer-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.mistake-answer-grid div {
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--panel) 76%, var(--bg));
  display: grid;
  gap: 4px;
}

.mistake-answer-grid strong {
  color: var(--text);
  word-break: break-word;
}

.insight-summary {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent) 6%, var(--bg));
  display: grid;
  gap: 8px;
}

.insight-summary strong {
  color: var(--text);
  font-size: 14px;
}

.insight-summary p {
  margin: 0;
  color: var(--muted);
  line-height: 1.8;
}

.insight-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.insight-card {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--bg) 72%, var(--panel));
  display: grid;
  gap: 8px;
}

.insight-card[data-tone='good'] {
  border-color: color-mix(in srgb, var(--green) 25%, var(--line));
}

.insight-card[data-tone='note'] {
  border-color: color-mix(in srgb, var(--accent) 22%, var(--line));
}

.insight-card[data-tone='bad'] {
  border-color: color-mix(in srgb, var(--red) 24%, var(--line));
}

.insight-title {
  color: var(--text);
  font-size: 13px;
  font-weight: 700;
}

.insight-card p {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
  font-size: 13px;
}

.mistake-box > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.mistake-box span {
  color: var(--muted);
}

@media (max-width: 900px) {
  .report-card-grid,
  .report-focus-grid,
  .report-summary-grid,
  .report-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .report-active-banner,
  .report-inline-head,
  .report-actions {
    flex-direction: column;
    align-items: flex-start;
  }

  .report-card,
  .report-inline-panel {
    padding: 18px;
  }

  .report-inline-grid {
    grid-template-columns: 1fr;
  }

  .report-card-grid,
  .report-focus-grid,
  .report-summary-grid,
  .report-metrics {
    grid-template-columns: 1fr;
  }

  .detail-row,
  .mistake-card-head,
  .mistake-list-head,
  .mistake-box > div {
    flex-direction: column;
    align-items: flex-start;
  }

  .mistake-answer-grid {
    grid-template-columns: 1fr;
  }
}
</style>
