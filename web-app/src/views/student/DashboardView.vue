<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import {
  agentApi,
  evaluationApi,
  serviceEndpoints,
  userApi,
  type ApiEnvelope,
  type LearnerProfileDashboard,
  type ReportDetail,
  type UserProfileRead,
} from '../../api'

type ServiceStatus = {
  label: string
  baseUrl: string
  online: boolean
  checking: boolean
}

type ActivityItem = {
  text: string
  time: string
  color: string
}

type DashboardCard = {
  label: string
  value: string
  icon: string
}

type ProfileDimensionItem = {
  key: string
  label: string
  value: string
}

const authStore = useAuthStore()
const router = useRouter()
const user = authStore.user!

const services = reactive<ServiceStatus[]>([
  { label: 'user-service', baseUrl: serviceEndpoints.user, online: false, checking: true },
  { label: 'agent-service', baseUrl: serviceEndpoints.agent, online: false, checking: true },
  { label: 'evaluation-service', baseUrl: serviceEndpoints.evaluation, online: false, checking: true },
])

const dashboard = ref<LearnerProfileDashboard | null>(null)
const learnerProfile = ref<UserProfileRead | null>(null)
const dashError = ref('')
const reportDetail = ref<ReportDetail | null>(null)
const recentActivity = ref<ActivityItem[]>([])
const suggestions = ref<string[]>([])
const mistakeStats = ref<Record<string, unknown> | null>(null)
const resources = ref<Record<string, unknown>[]>([])

const profileDimensionLabels: Record<string, string> = {
  knowledgeBase: '知识基础',
  cognitiveStyle: '认知风格',
  errorPreference: '易错偏好',
  learningSpeed: '学习节奏',
  interestDirection: '兴趣方向',
  goalOrientation: '目标导向',
}

const profileDimensionKeys = Object.keys(profileDimensionLabels)

const profileDimensionItems = computed<ProfileDimensionItem[]>(() =>
  profileDimensionKeys.map((key) => ({
    key,
    label: profileDimensionLabels[key],
    value: learnerProfile.value?.profile_dimensions?.[key]?.trim() || '',
  })),
)

const filledProfileDimensions = computed(() =>
  profileDimensionItems.value.filter((item) => Boolean(item.value)).length,
)

const profileCompletionPercent = computed(() =>
  Math.round((filledProfileDimensions.value / profileDimensionKeys.length) * 100),
)

const profileActionLabel = computed(() =>
  filledProfileDimensions.value > 0 ? '继续完善画像' : '去完善画像',
)

const masteryPct = computed(() => {
  const metrics = visibleRadarMetrics.value
  if (!metrics.length) {
    return null
  }
  const total = metrics.reduce((sum, item) => sum + item.score, 0)
  return Math.round(total / metrics.length)
})

const visibleRadarMetrics = computed(() => {
  return (dashboard.value?.radar_metrics ?? []).filter((metric) => metric.dimension && metric.score > 0)
})

const hasLearningActivity = computed(() => {
  return (reportDetail.value?.evidence?.total_answers ?? 0) > 0
})

function isRealLearningStyle(value: string | undefined) {
  return Boolean(value && value.trim() && value.trim().toUpperCase() !== 'VARK')
}

const dashboardCards = computed<DashboardCard[]>(() => {
  if (!dashboard.value) {
    return []
  }

  const cards: DashboardCard[] = []

  if (hasLearningActivity.value && isRealLearningStyle(dashboard.value.learning_style)) {
    cards.push({
      label: '学习风格',
      value: dashboard.value.learning_style,
      icon: '🧠',
    })
  }

  if (hasLearningActivity.value && masteryPct.value !== null) {
    cards.push({
      label: '掌握度',
      value: `${masteryPct.value}%`,
      icon: '🎯',
    })
  }

  if (hasLearningActivity.value && typeof dashboard.value.weekly_focus_minutes === 'number' && dashboard.value.weekly_focus_minutes > 0) {
    cards.push({
      label: '本周专注',
      value: `${dashboard.value.weekly_focus_minutes} 分钟`,
      icon: '⏱️',
    })
  }

  if (hasLearningActivity.value && typeof dashboard.value.mastery_overview === 'number' && dashboard.value.mastery_overview > 0) {
    cards.push({
      label: '综合评分',
      value: `${dashboard.value.mastery_overview}%`,
      icon: '📊',
    })
  }

  return cards
})

async function checkHealth(service: ServiceStatus) {
  try {
    const response = await fetch(new URL('/health', service.baseUrl))
    const data = await response.json()
    service.online = data.status === 'ok'
  } catch {
    service.online = false
  } finally {
    service.checking = false
  }
}

async function fetchDashboard() {
  dashError.value = ''
  try {
    const { data } = await userApi.get<LearnerProfileDashboard>(`/users/${user.userId}/profile/dashboard`)
    dashboard.value = data
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    dashError.value = `画像加载失败：${detail}`
  }
}

async function fetchLearnerProfile() {
  try {
    const { data } = await userApi.get<UserProfileRead>(`/users/${user.userId}/profile`)
    learnerProfile.value = data
  } catch {
    learnerProfile.value = null
  }
}

async function fetchRecentActivity() {
  try {
    const { data } = await evaluationApi.get<ApiEnvelope<ReportDetail>>(
      `/evaluation/reports/comprehensive/${user.userId}/detail`,
    )
    const report = (data as any).data ?? data
    reportDetail.value = report
    recentActivity.value = buildRecentActivity(report)
  } catch {
    reportDetail.value = null
    recentActivity.value = []
  }
}

function buildRecentActivity(report: ReportDetail | null): ActivityItem[] {
  if (!report?.evidence) {
    return []
  }

  const items: ActivityItem[] = []
  const { accuracy, total_answers: totalAnswers } = report.evidence

  if (typeof accuracy === 'number' && totalAnswers > 0) {
    items.push({
      text: `综合正确率：${accuracy}%`,
      time: report.title || '最新报告',
      color: 'var(--green)',
    })
  }

  if (typeof totalAnswers === 'number' && totalAnswers > 0) {
    items.push({
      text: `已完成 ${totalAnswers} 道练习`,
      time: report.summary || '累计统计',
      color: 'var(--accent-deep)',
    })
  }

  return items
}

async function fetchSuggestions() {
  try {
    const { data } = await evaluationApi.get(`/evaluation/reports/suggestions/${user.userId}`)
    suggestions.value = (data as any).data?.suggestions ?? (data as any).suggestions ?? []
  } catch {
    suggestions.value = []
  }
}

async function fetchMistakeStats() {
  try {
    const { data } = await evaluationApi.get(`/evaluation/mistakes/${user.userId}`)
    mistakeStats.value = (data as any).data ?? data
  } catch {
    mistakeStats.value = null
  }
}

async function fetchResources() {
  try {
    const { data } = await agentApi.get('/resources')
    resources.value = (data as any).data ?? (Array.isArray(data) ? data : [])
  } catch {
    resources.value = []
  }
}

onMounted(() => {
  services.forEach((service) => void checkHealth(service))
  void fetchLearnerProfile()
  void fetchDashboard()
  void fetchRecentActivity()
  void fetchSuggestions()
  void fetchMistakeStats()
  void fetchResources()
})

function goToProfileSetup() {
  void router.push('/profile-setup')
}
</script>

<template>
  <div>
    <div class="welcome-section" style="margin-bottom:20px">
      <h2 style="font-size:26px;font-weight:750">
        欢迎回来，
        <span style="background:linear-gradient(135deg,var(--text),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">
          {{ user.username }}
        </span>
      </h2>
      <p style="color:var(--muted)">以下是您的学习概览</p>
    </div>

    <router-link
      to="/student/profile-analysis"
      style="display:flex;align-items:center;gap:16px;padding:20px 24px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:20px;text-decoration:none;color:inherit;cursor:pointer;transition:box-shadow .2s"
      onmouseover="this.style.boxShadow='0 2px 16px color-mix(in srgb,var(--accent) 12%,transparent)'"
      onmouseout="this.style.boxShadow='none'"
    >
      <div style="width:48px;height:48px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:24px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 15%,transparent),color-mix(in srgb,var(--accent-deep) 15%,transparent))">
        🧠
      </div>
      <div style="flex:1">
        <div style="font-weight:700;font-size:16px">用户画像分析</div>
        <div style="font-size:13px;color:var(--muted);margin-top:2px">查看 AI 结合画像与练习行为生成的深度分析</div>
      </div>
      <div style="font-size:20px;color:var(--muted)">→</div>
    </router-link>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px">
      <span
        v-for="service in services"
        :key="service.label"
        style="display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:999px;font-size:13px;background:var(--panel);border:1px solid var(--line)"
      >
        <span
          style="width:8px;height:8px;border-radius:50%;display:inline-block"
          :style="{ background: service.checking ? 'var(--muted)' : service.online ? 'var(--green)' : 'var(--red)' }"
        ></span>
        {{ service.label }}
      </span>
    </div>

    <div
      v-if="dashError"
      style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:16px;font-size:14px"
    >
      {{ dashError }}
    </div>

    <div
      v-if="dashboardCards.length"
      style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px"
    >
      <div
        v-for="card in dashboardCards"
        :key="card.label"
        style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);position:relative;overflow:hidden"
      >
        <div style="position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--accent),var(--accent-deep))"></div>
        <div style="font-size:24px;margin-bottom:10px">{{ card.icon }}</div>
        <div style="font-size:12px;letter-spacing:.06em;color:var(--muted);text-transform:uppercase">{{ card.label }}</div>
        <div style="font-size:28px;font-weight:750;margin-top:6px">{{ card.value }}</div>
      </div>
    </div>
    <div
      v-else
      style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:24px;color:var(--muted)"
    >
      暂无练习概览数据，完成练习后将自动展示掌握度与学习统计。
    </div>

    <section
      style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:24px"
    >
      <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px">
        <div>
          <h3 style="margin:0 0 6px;font-size:20px">🧠 学习画像</h3>
          <p style="margin:0;color:var(--muted);font-size:13px">画像智能体从你的回答中沉淀出的个性化学习信息</p>
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:flex-end">
          <span style="font-size:12px;color:var(--muted);white-space:nowrap">
            {{ filledProfileDimensions }}/{{ profileDimensionKeys.length }} 维度
          </span>
          <div style="width:120px;height:6px;border-radius:999px;background:color-mix(in srgb,var(--muted) 16%,transparent);overflow:hidden">
            <div
              :style="{
                width: `${profileCompletionPercent}%`,
                height: '100%',
                background: 'linear-gradient(90deg,var(--accent),var(--accent-deep))',
              }"
            ></div>
          </div>
          <button
            type="button"
            style="padding:8px 14px;border-radius:999px;border:1px solid color-mix(in srgb,var(--accent) 28%,var(--line));background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent);font-size:12px;font-weight:700;cursor:pointer;font-family:inherit;white-space:nowrap"
            @click="goToProfileSetup"
          >
            {{ profileActionLabel }}
          </button>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px">
        <article
          v-for="item in profileDimensionItems"
          :key="item.key"
          style="min-height:92px;padding:14px;border-radius:12px;border:1px solid var(--line);cursor:pointer;transition:border-color .18s ease,transform .18s ease,background .18s ease"
          :style="item.value
            ? { background: 'color-mix(in srgb,var(--accent) 7%,transparent)' }
            : { background: 'color-mix(in srgb,var(--text) 3%,transparent)' }"
          @click="goToProfileSetup"
        >
          <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px">
            <strong style="font-size:13px">{{ item.label }}</strong>
            <span
              style="font-size:11px;font-weight:700"
              :style="{ color: item.value ? 'var(--accent)' : 'var(--muted)' }"
            >
              {{ item.value ? '已记录' : '待完善' }}
            </span>
          </div>
          <p style="margin:0;color:var(--muted);font-size:13px;line-height:1.6">
            {{ item.value || '画像构建页继续对话后会自动补充。' }}
          </p>
        </article>
      </div>
      <div
        v-if="filledProfileDimensions === 0"
        style="margin-top:14px;padding:12px 14px;border-radius:12px;border:1px dashed color-mix(in srgb,var(--accent) 24%,var(--line));background:color-mix(in srgb,var(--accent) 5%,transparent);color:var(--muted);font-size:13px;line-height:1.7"
      >
        当前还没有可用学习画像。点击上方按钮或任意维度卡片，就可以进入画像构建页继续完善。
      </div>
    </section>

    <div style="display:grid;grid-template-columns:1.3fr 1fr;gap:20px">
      <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
        <h3 style="margin-bottom:14px">📋 最近活动</h3>
        <div v-if="recentActivity.length">
          <div
            v-for="(activity, index) in recentActivity"
            :key="index"
            style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--line)"
          >
            <span
              style="width:8px;height:8px;border-radius:50%;flex-shrink:0"
              :style="{ background: activity.color }"
            ></span>
            <div style="flex:1">
              <div style="font-size:14px">{{ activity.text }}</div>
              <div style="font-size:11px;color:var(--muted)">{{ activity.time }}</div>
            </div>
          </div>
        </div>
        <div v-else style="text-align:center;padding:20px;color:var(--muted)">暂无活动数据</div>
      </div>

      <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
        <h3 style="margin-bottom:14px">📊 掌握度雷达</h3>
        <div v-if="hasLearningActivity && visibleRadarMetrics.length">
          <div
            v-for="metric in visibleRadarMetrics"
            :key="metric.dimension"
            style="display:flex;align-items:center;gap:12px;margin-bottom:10px"
          >
            <span style="width:80px;font-size:12px;color:var(--muted);text-align:right;flex-shrink:0">{{ metric.dimension }}</span>
            <div style="flex:1;height:8px;border-radius:4px;background:color-mix(in srgb,var(--muted) 15%,transparent);overflow:hidden">
              <div
                :style="{
                  width: `${metric.score}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg,var(--accent),var(--accent-deep))',
                  borderRadius: '4px',
                }"
              ></div>
            </div>
            <span style="width:36px;font-size:12px;font-weight:600;color:var(--accent);text-align:right">{{ metric.score }}%</span>
          </div>
        </div>
        <div v-else style="text-align:center;padding:20px;color:var(--muted)">暂无数据，完成练习后将自动生成</div>
      </div>
    </div>

    <div
      v-if="suggestions.length"
      style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-top:20px"
    >
      <h3 style="margin-bottom:14px">📑 AI 学习建议</h3>
      <ul style="padding-left:20px;color:var(--muted);line-height:1.8">
        <li v-for="(suggestion, index) in suggestions" :key="index" style="margin-top:4px">{{ suggestion }}</li>
      </ul>
    </div>

    <div
      v-if="mistakeStats"
      style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:20px"
    >
      <div style="padding:18px;text-align:center;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
        <div style="font-size:12px;color:var(--muted)">总错题数</div>
        <div style="font-size:28px;font-weight:700;color:var(--red);margin-top:6px">
          {{ mistakeStats.total ?? mistakeStats.count ?? '-' }}
        </div>
      </div>
      <div style="padding:18px;text-align:center;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
        <div style="font-size:12px;color:var(--muted)">已掌握</div>
        <div style="font-size:28px;font-weight:700;color:var(--green);margin-top:6px">
          {{ mistakeStats.mastered ?? mistakeStats.resolved ?? '-' }}
        </div>
      </div>
      <div style="padding:18px;text-align:center;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
        <div style="font-size:12px;color:var(--muted)">待重练</div>
        <div style="font-size:28px;font-weight:700;color:var(--accent);margin-top:6px">
          {{ mistakeStats.pending ?? mistakeStats.unresolved ?? '-' }}
        </div>
      </div>
    </div>

    <div
      v-if="resources.length"
      style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-top:20px"
    >
      <h3 style="margin-bottom:14px">📚 学习资源库</h3>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
        <div
          v-for="resource in resources.slice(0, 6)"
          :key="String(resource.id ?? resource.resource_id)"
          style="padding:14px;border-radius:12px;border:1px solid var(--line);background:color-mix(in srgb,var(--accent) 4%,transparent)"
        >
          <div style="font-size:13px;font-weight:600;margin-bottom:4px">
            {{ resource.title ?? resource.name ?? '未命名资源' }}
          </div>
          <div style="font-size:11px;color:var(--muted)">
            {{ resource.type ?? resource.resource_type ?? '' }}
            <span v-if="resource.status"> · {{ resource.status }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
