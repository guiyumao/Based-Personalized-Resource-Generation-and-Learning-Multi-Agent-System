<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { userApi } from '../../api'
import LearningContent from '../../components/LearningContent.vue'

const authStore = useAuthStore()
const userId = authStore.user!.userId

type AnalysisStatus = 'idle' | 'processing' | 'completed' | 'failed'
type AnalysisSection = {
  key: string
  label: string
  icon: string
  content: string
  summary: string
}
type ProfileDimInfo = { key: string; label: string; icon: string }

const DIM_META: Record<string, { label: string; icon: string }> = {
  knowledgeBase: { label: '知识基础', icon: '📚' },
  cognitiveStyle: { label: '认知风格', icon: '🧩' },
  errorPreference: { label: '易错偏好', icon: '⚠️' },
  learningSpeed: { label: '学习节奏', icon: '⏱️' },
  interestDirection: { label: '兴趣方向', icon: '🎯' },
  goalOrientation: { label: '目标导向', icon: '🚩' },
}

const STYLE_LABELS: Record<string, string> = {
  visual: '视觉型', reading: '文本型', auditory: '听觉型', kinesthetic: '动手实践型',
}

// ── Profile summary (always visible, from dashboard API) ──
const profileLearningStyle = ref('')
const profileHabitSummary = ref('')
const profileDimensions = ref<ProfileDimInfo[]>([])
const profileFilledCount = ref(0)
const studiedPoints = ref<Array<{ name: string; attempts: number; accuracy: number | null; weak: boolean }>>([])
const exploredPoints = ref<Array<{ name: string; interactions: number }>>([])
const answerCount = ref(0)
const idleReason = ref('完成练习后，系统会按实际学习的知识点生成分析。')

const status = ref<AnalysisStatus>('idle')
const progress = ref(0)
const currentStep = ref('')
const error = ref('')
const sections = ref<AnalysisSection[]>([])
const modelUsed = ref('')
const generatedAt = ref('')
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null)
const pageLoading = ref(true)
const initialRequestMade = ref(false)

const progressPct = computed(() => Math.min(100, Math.max(0, progress.value)))
const hasContent = computed(() => sections.value.length > 0)

// 学习正文（含公式）统一由 components/LearningContent.vue 渲染，此处不再维护本地 Markdown 实现。

async function startAnalysis() {
  sections.value = []
  status.value = 'processing'
  progress.value = 0
  error.value = ''
  currentStep.value = '正在连接分析服务…'

  try {
    // Request generation (returns immediately with status "processing" or "completed")
    const { data } = await userApi.get(`/users/${userId}/profile/analysis`)
    if (data.status === 'completed') {
      applyResult(data)
      return
    }
    if (data.status === 'idle') {
      status.value = 'idle'
      idleReason.value = data.reason || idleReason.value
      return
    }
    // Start polling
    startPolling()
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? '分析服务暂时不可用'
    status.value = 'failed'
  }
}

function startPolling() {
  stopPolling()
  pollingTimer.value = setInterval(pollStatus, 3000)
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

async function pollStatus() {
  try {
    const { data } = await userApi.get(`/users/${userId}/profile/analysis/status`)
    if (data.status === 'completed') {
      stopPolling()
      applyResult(data)
      return
    }
    if (data.status === 'failed') {
      stopPolling()
      error.value = (data.error as string) || '分析生成失败'
      status.value = 'failed'
      return
    }
    if (data.status === 'idle') {
      stopPolling()
      // Restart if we somehow lost the task
      if (!initialRequestMade.value) {
        initialRequestMade.value = true
        // Trigger auto-generation
        await startAnalysis()
      }
      return
    }
    // Still processing — update progress
    progress.value = (data.progress as number) || progress.value
    currentStep.value = (data.current as string) || currentStep.value
  } catch {
    // Keep polling
  }
}

function applyResult(data: any) {
  const analysis = data.analysis || data || {}
  const summaries = analysis.summaries || {}
  const items: AnalysisSection[] = []
  for (const [key, meta] of Object.entries(DIM_META)) {
    const text = (analysis[key] as string) || ''
    if (text) {
      items.push({
        key, label: meta.label, icon: meta.icon,
        content: text,
        summary: (summaries[key] as string) || '',
      })
    }
  }
  sections.value = items
  modelUsed.value = (analysis.model as string) || ''
  generatedAt.value = (analysis.generated_at as string) || ''
  status.value = 'completed'
  progress.value = 100
}

async function refreshAnalysis() {
  // Clear old content immediately so user doesn't see stale data
  sections.value = []
  status.value = 'processing'
  progress.value = 0
  error.value = ''
  currentStep.value = '正在请求重新分析…'
  try {
    const { data } = await userApi.post(`/users/${userId}/profile/analysis/refresh`, {})
    if (data.status === 'completed') {
      applyResult(data)
      return
    }
    if (data.status === 'idle') {
      status.value = 'idle'
      idleReason.value = data.reason || idleReason.value
      return
    }
    initialRequestMade.value = true
    startPolling()
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? '刷新失败'
    status.value = 'failed'
  }
}

function formatTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

async function fetchProfileSummary() {
  try {
    const { data } = await userApi.get(`/users/${userId}/profile/dashboard`)
    if (data.learning_style) {
      profileLearningStyle.value = STYLE_LABELS[data.learning_style] ?? data.learning_style
    }
    profileHabitSummary.value = (data.habit_summary as string) || ''
    studiedPoints.value = data.learning_content?.knowledge_points || []
    exploredPoints.value = data.learning_content?.explored_points || []
    answerCount.value = data.learning_content?.total_answers || 0
    const profile = (await userApi.get(`/users/${userId}/profile`)).data
    const dims: ProfileDimInfo[] = []
    for (const [key, meta] of Object.entries(DIM_META)) {
      if (profile.profile_dimensions?.[key]) {
        dims.push({ key, label: meta.label, icon: meta.icon })
      }
    }
    profileDimensions.value = dims
    profileFilledCount.value = dims.length
  } catch { /* dashboard unavailable — profile summary stays empty */ }
}

onMounted(async () => {
  await fetchProfileSummary()
  try {
    const { data } = await userApi.get(`/users/${userId}/profile/analysis`)
    if (data.status === 'completed') {
      applyResult(data)
    } else if (data.status === 'processing') {
      status.value = 'processing'
      initialRequestMade.value = true
      startPolling()
    } else {
      // 'idle' or missing — trigger first generation automatically
      await startAnalysis()
      initialRequestMade.value = true
    }
  } catch {
    // Will show idle state with launch button
  } finally {
    pageLoading.value = false
  }
})

onUnmounted(() => stopPolling())
</script>

<template>
  <div style="min-height:100vh;background:var(--bg)">
    <!-- Header -->
    <div style="max-width:1000px;margin:0 auto;padding:32px 24px 0">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <div>
          <h1 style="font-size:24px;font-weight:750;margin:0">
            🧠 用户画像分析
          </h1>
          <p style="color:var(--muted);margin:6px 0 0;font-size:14px">
            AI 基于您的学习数据和画像维度生成的深度分析报告
          </p>
        </div>
        <button
          v-if="hasContent"
          @click="refreshAnalysis"
          :disabled="status === 'processing'"
          style="padding:10px 22px;border-radius:12px;border:1px solid var(--line);
            background:var(--panel);color:var(--text);cursor:pointer;font-size:13px;
            font-family:inherit;white-space:nowrap"
          :style="status === 'processing' ? {opacity:0.5,cursor:'not-allowed'} : {}"
        >
          {{ status === 'processing' ? '分析中…' : '🔄 重新分析' }}
        </button>
      </div>
      <p v-if="generatedAt" style="color:var(--muted);font-size:12px;margin:0 0 24px">
        上次分析时间：{{ formatTime(generatedAt) }}<span v-if="modelUsed"> · 模型：{{ modelUsed }}</span>
      </p>
    </div>

    <!-- Content area -->
    <div style="max-width:1000px;margin:0 auto;padding:0 24px 48px">

      <!-- Profile dimension summary — always visible -->
      <div
        v-if="profileDimensions.length > 0"
        style="padding:22px 24px;border-radius:18px;background:var(--panel);
          border:1px solid var(--line);margin-bottom:24px"
      >
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
          <span style="font-size:20px">🧠</span>
          <span style="font-weight:700;font-size:15px">画像维度概览</span>
          <span style="font-size:12px;color:var(--muted)">
            · {{ profileFilledCount }} 项已记录
            <template v-if="profileLearningStyle"> · {{ profileLearningStyle }}</template>
          </span>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <span
            v-for="dim in profileDimensions"
            :key="dim.key"
            style="display:inline-flex;align-items:center;gap:6px;padding:6px 14px;
              border-radius:999px;font-size:13px;font-weight:550;
              background:color-mix(in srgb,var(--green) 10%,transparent);
              color:var(--green);border:1px solid color-mix(in srgb,var(--green) 18%,transparent)"
          >
            {{ dim.icon }} {{ dim.label }}
          </span>
        </div>
        <div
          v-if="profileHabitSummary"
          style="margin-top:12px;font-size:13px;color:var(--muted);line-height:1.6"
        >
          <LearningContent :content="profileHabitSummary" />
        </div>
      </div>

      <div v-if="studiedPoints.length" style="padding:22px 24px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:24px">
        <strong>真实学习内容 · {{ answerCount }} 次作答</strong>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
          <span v-for="point in studiedPoints" :key="point.name" style="padding:6px 10px;border-radius:8px;background:var(--surface-soft);font-size:13px">
            {{ point.name }} · {{ point.attempts }} 次<span v-if="point.accuracy != null"> · {{ point.accuracy }}% 正确</span><span v-if="point.weak"> · 待巩固</span>
          </span>
        </div>
      </div>
      <div v-if="exploredPoints.length" style="padding:18px 24px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:24px;font-size:13px">
        <strong>浏览过的知识点</strong>
        <p style="color:var(--muted);margin:8px 0 0">{{ exploredPoints.map(point => point.name).join('、') }}。浏览记录不代表已经掌握。</p>
      </div>

      <!-- Loading / progress state -->
      <div
        v-if="status === 'processing'"
        style="padding:48px 24px;border-radius:20px;background:var(--panel);
          border:1px solid var(--line);text-align:center"
      >
        <div style="font-size:48px;margin-bottom:16px">🧠</div>
        <h3 style="font-weight:700;margin:0 0 8px">AI 正在深度分析您的学习画像</h3>
        <p style="color:var(--muted);margin:0 0 20px;font-size:14px">{{ currentStep }}</p>
        <!-- Progress bar -->
        <div style="max-width:400px;margin:0 auto 16px">
          <div style="height:6px;border-radius:3px;background:color-mix(in srgb,var(--muted) 20%,transparent);overflow:hidden">
            <div
              style="height:100%;background:linear-gradient(90deg,var(--accent),var(--accent-deep));
                border-radius:3px;transition:width .6s"
              :style="{ width: progressPct + '%' }"
            ></div>
          </div>
          <div style="margin-top:8px;font-size:13px;color:var(--muted)">{{ progressPct }}%</div>
        </div>
        <p style="font-size:12px;color:var(--muted)">
          深度分析需要 1-2 分钟，完成后自动展示结果
        </p>
      </div>

      <!-- Error state -->
      <div
        v-if="status === 'failed'"
        style="padding:32px;border-radius:20px;background:color-mix(in srgb,var(--red) 6%,transparent);
          border:1px solid color-mix(in srgb,var(--red) 18%,transparent);text-align:center"
      >
        <div style="font-size:36px;margin-bottom:12px">⚠️</div>
        <p style="color:var(--red);margin:0 0 16px">{{ error }}</p>
        <button
          @click="startAnalysis()"
          style="padding:10px 24px;border-radius:12px;border:none;
            background:linear-gradient(135deg,var(--accent),var(--accent-deep));
            color:#fff;cursor:pointer;font-weight:600;font-size:14px;font-family:inherit"
        >
          重新尝试
        </button>
      </div>

      <!-- Idle state — no analysis yet -->
      <div
        v-if="status === 'idle' && !hasContent"
        style="padding:48px 24px;border-radius:20px;background:var(--panel);
          border:1px solid var(--line);text-align:center"
      >
        <div style="font-size:48px;margin-bottom:16px">🔍</div>
        <h3 style="font-weight:700;margin:0 0 8px">尚未生成分析报告</h3>
        <p style="color:var(--muted);margin:0 0 20px;font-size:14px">
          {{ idleReason }}
        </p>
        <button
          @click="startAnalysis()"
          style="padding:14px 36px;border-radius:14px;border:none;
            background:linear-gradient(135deg,var(--accent),var(--accent-deep));
            color:#fff;cursor:pointer;font-weight:700;font-size:15px;font-family:inherit;
            box-shadow:0 4px 18px color-mix(in srgb,var(--accent) 35%,transparent)"
        >
          🧠 开始分析
        </button>
      </div>

      <!-- Results — 6 dimension cards -->
      <div
        v-if="sections.length > 0"
        style="display:grid;gap:20px"
      >
        <div
          v-for="section in sections"
          :key="section.key"
          style="padding:24px;border-radius:18px;background:var(--panel);
            border:1px solid var(--line);transition:box-shadow .2s"
          @mouseenter="($el as HTMLElement).style.boxShadow = '0 2px 16px color-mix(in srgb,var(--accent) 12%,transparent)'"
          @mouseleave="($el as HTMLElement).style.boxShadow = 'none'"
        >
          <h3 style="display:flex;align-items:center;gap:10px;margin:0 0 14px;font-size:16px;font-weight:700">
            <span style="font-size:22px">{{ section.icon }}</span>
            {{ section.label }}
            <span
              v-if="section.summary"
              style="font-size:12px;font-weight:550;padding:3px 10px;border-radius:8px;
                background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,transparent),color-mix(in srgb,var(--accent-deep) 12%,transparent));
                color:var(--accent-deep);border:1px solid color-mix(in srgb,var(--accent) 20%,transparent);
                white-space:nowrap"
            >
              {{ section.summary }}
            </span>
          </h3>
          <div
            style="font-size:14px;line-height:1.85;color:var(--text)"
          >
            <LearningContent :content="section.content" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
