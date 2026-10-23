<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import CoursewareReader from '../components/CoursewareReader.vue'
import { Download } from '@element-plus/icons-vue'
import { renderLearningMarkdown } from '../utils/renderLearningMarkdown'

import {
  agentApi, resourceApi,
  type LearningPathResponse,
  type ResourceResult,
  type ResourceVariant,
} from '../api'
import { useAuthStore } from '../stores/auth'
import { isPathGenerationBusy, onPathGenerationSettled, resumePathGeneration } from '../stores/pathGeneration'

type CoursewareSection = {
  heading: string
  anchor: string
  html: string
}

type StoredCoursewareSnapshot = {
  subject: string
  topic: string
  goal: string
  selectedVariantId: string
  version?: string
  teaching_json?: string
  generatedAt: number
  resourceResult: ResourceResult
}

type ProgressStage = {
  key: string
  label: string
  detail: string
  percent: number
  status: 'pending' | 'active' | 'done'
}

const COURSEWARE_STORAGE_KEY = 'student-workspace-courseware'

const router = useRouter()
const authStore = useAuthStore()
const snapshot = ref<StoredCoursewareSnapshot | null>(readStoredSnapshot())
const selectedVariantId = ref(snapshot.value?.selectedVariantId ?? '')
const reader = ref<InstanceType<typeof CoursewareReader>>()
const availableUpgrade = ref<any>(null)
const checkingStored = ref(false)
const storedLoadError = ref('')
const legacySnapshot = computed(() => {
  try { return JSON.parse(snapshot.value?.teaching_json || '{}').schema !== 'teaching-v2' } catch { return true }
})
let mounted = true
onUnmounted(() => { mounted = false })
const autoGenerating = ref(false)
const generationProgress = ref(0)
const progressStages = ref<ProgressStage[]>(createProgressStages())
const pathMissing = ref(false)

const coursewareVariants = computed<ResourceVariant[]>(() => snapshot.value?.resourceResult.variants ?? [])
const activeCoursewareVariant = computed<ResourceVariant | null>(() => {
  const variants = coursewareVariants.value
  if (!variants.length) {
    return null
  }
  return (
    variants.find((item) => item.variant_id === selectedVariantId.value)
    ?? variants.find((item) => item.is_recommended)
    ?? variants[0]
  )
})

const coursewareTitle = computed(() => {
  const raw = activeCoursewareVariant.value?.content?.trim() ?? snapshot.value?.resourceResult.content?.trim() ?? ''
  const firstLine = raw.split(/\r?\n/)[0] ?? ''
  return firstLine.startsWith('# ') ? firstLine.replace(/^#\s+/, '') : '个性化学习课件'
})

const coursewareContent = computed(() => activeCoursewareVariant.value?.content ?? snapshot.value?.resourceResult.content ?? '')
const resourceSections = computed<CoursewareSection[]>(() => buildCoursewareSections(coursewareContent.value))
const _coursewareOutline = computed(() => resourceSections.value.map((section) => section.heading))
const coursewarePersonalization = computed(() => { const value = snapshot.value?.resourceResult.personalization; return value?.evidence?.version === "point-evidence-v4" ? value : null })
const generatedTimeLabel = computed(() => {
  if (!snapshot.value?.generatedAt) {
    return '刚刚生成'
  }
  return new Date(snapshot.value.generatedAt).toLocaleString('zh-CN', { hour12: false })
})
const downloadFileName = computed(() => `${buildSafeFileName(coursewareTitle.value)}.md`)

function createProgressStages(): ProgressStage[] {
  return [
    { key: 'path', label: '读取学习路径', detail: '拉取当前学生的最新学习主题、路径目标和章节任务。', percent: 12, status: 'pending' },
    { key: 'generate', label: '持久任务生成课件', detail: '由独立Worker检索、规划并逐章生成，执行进度来自服务端。', percent: 82, status: 'pending' },
    { key: 'persist', label: '保存课件快照', detail: '写入浏览器会话缓存，课件中心可直接展开阅读。', percent: 100, status: 'pending' },
  ]
}

function setProgress(activeKey: string, percent?: number) {
  progressStages.value = progressStages.value.map((stage) => {
    if (stage.key === activeKey) {
      return { ...stage, status: 'active' }
    }
    if (stage.percent < (percent ?? 0)) {
      return { ...stage, status: 'done' }
    }
    return { ...stage, status: 'pending' }
  })
  generationProgress.value = percent ?? progressStages.value.find((stage) => stage.key === activeKey)?.percent ?? generationProgress.value
}

function finishProgress() {
  generationProgress.value = 100
  progressStages.value = progressStages.value.map((stage) => ({ ...stage, status: 'done' }))
}

onMounted(async () => {
  if (!snapshot.value) {
    // A learning-path generation queued on the other page (or before a reload)
    // may still be writing this topic's courseware; adopt it instead of paying
    // for a second task.
    const userId = authStore.user?.userId ?? 0
    if (userId) {
      void resumePathGeneration(userId)
    }
    if (isPathGenerationBusy() && await adoptBackgroundCourseware()) {
      return
    }
    await generateFromLatestPath()
  } else {
    await refreshSavedCourseware()
  }
})

const BACKGROUND_COURSEWARE_WAIT_MS = 12 * 60 * 1000

/**
 * Wait for the background learning-path task to settle, then load the courseware
 * snapshot it persisted. Returns false when no courseware became available (the
 * caller then falls back to requesting one).
 */
async function adoptBackgroundCourseware(): Promise<boolean> {
  autoGenerating.value = true
  setProgress('path', 12)
  setProgress('generate', 20)
  progressStages.value = progressStages.value.map(stage =>
    stage.key === 'generate'
      ? { ...stage, detail: '学习路径页发起的后台任务仍在生成课件，完成后会自动展开。' }
      : stage,
  )
  try {
    await waitForBackgroundGeneration()
  } finally {
    autoGenerating.value = false
  }
  const stored = readStoredSnapshot()
  if (!mounted || !stored) {
    return false
  }
  snapshot.value = stored
  selectedVariantId.value = stored.selectedVariantId || ''
  finishProgress()
  ElMessage.success('课件已由后台生成任务完成')
  void refreshSavedCourseware()
  return true
}

function waitForBackgroundGeneration(): Promise<void> {
  return new Promise((resolve) => {
    let settled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    const finish = () => {
      if (settled) return
      settled = true
      off()
      if (timer) clearTimeout(timer)
      resolve()
    }
    const off = onPathGenerationSettled(() => finish())
    timer = setTimeout(finish, BACKGROUND_COURSEWARE_WAIT_MS)
    if (!isPathGenerationBusy()) finish()
  })
}

function readStoredSnapshot(): StoredCoursewareSnapshot | null {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    const raw = window.sessionStorage.getItem(COURSEWARE_STORAGE_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || !('resourceResult' in parsed)) {
      return null
    }
    if (parsed.resourceResult?.user_id !== authStore.user?.userId) return null
    return parsed as StoredCoursewareSnapshot
  } catch {
    return null
  }
}

async function reloadSnapshot() {
  snapshot.value = readStoredSnapshot()
  selectedVariantId.value = snapshot.value?.selectedVariantId ?? ''
  if (snapshot.value) await refreshSavedCourseware()
  if (!snapshot.value) {
    ElMessage.warning('当前没有可展示的课件内容，请先回到工作台生成课件。')
  }
}

function selectCoursewareVariant(variantId: string) {
  selectedVariantId.value = variantId
  if (!snapshot.value || typeof window === 'undefined') {
    return
  }
  snapshot.value = {
    ...snapshot.value,
    selectedVariantId: variantId,
  }
  window.sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify(snapshot.value))
}

function scrollToCoursewareSection(anchor: string) {
  const section = resourceSections.value.find(item => item.anchor === anchor)
  if (section) reader.value?.openHeading(section.heading)
}

async function adoptSavedCourseware(detail: any) {
  if (!snapshot.value) return
  const teaching = JSON.parse(detail.teaching_json || '{}')
  snapshot.value = { ...snapshot.value, version: detail.version, teaching_json: detail.teaching_json,
    selectedVariantId: '', resourceResult: { ...snapshot.value.resourceResult, id: detail.id,
      content: detail.content, variants: [], personalization: teaching.personalization || null,
      generation_plan: teaching.generation_plan, references: teaching.sources || [],
    } }
  selectedVariantId.value = ''
  sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify(snapshot.value))
}
async function refreshSavedCourseware() {
  if (!snapshot.value || checkingStored.value) return
  const id = snapshot.value.resourceResult.id
  const userId = authStore.user?.userId
  checkingStored.value = true
  storedLoadError.value = ''
  availableUpgrade.value = null
  try {
    let current: any
    if (id) {
      current = (await resourceApi.get(`/resources/${id}`)).data.data
      if (!mounted || authStore.user?.userId !== userId || snapshot.value?.resourceResult.id !== id) return
      await adoptSavedCourseware(current)
    }
    if (!legacySnapshot.value || !current) return
    const visible = (await resourceApi.get('/resources')).data.data || []
    const candidates = visible.filter((item: any) => item.id > id && item.type === 'courseware'
      && item.owner_user_id === userId && current.knowledge_point_id != null
      && item.knowledge_point_id === current.knowledge_point_id
      && item.generation_status === 'generated').sort((a: any, b: any) => b.id - a.id)
    for (const item of candidates) {
      const detail = (await resourceApi.get(`/resources/${item.id}`)).data.data
      const teaching = JSON.parse(detail.teaching_json || '{}')
      if (!mounted || authStore.user?.userId !== userId || snapshot.value?.resourceResult.id !== id) return
      // Match the saved subject as well; equal topic names across subjects are not enough.
      if (teaching.schema === 'teaching-v2' && teaching.subject === snapshot.value.subject) {
        availableUpgrade.value = detail
        break
      }
    }
  } catch (error: any) {
    storedLoadError.value = `未能核验已保存课件：${error?.response?.data?.detail || error?.message || '请稍后刷新'}`
  } finally { checkingStored.value = false }
}
async function openUpgrade() {
  if (!availableUpgrade.value) return
  await adoptSavedCourseware(availableUpgrade.value)
  availableUpgrade.value = null
}

function goBack() {
  void router.push({ name: 'student-dashboard' })
}

function downloadCurrentCourseware() {
  if (!snapshot.value || !coursewareContent.value.trim()) {
    ElMessage.warning('当前没有可下载的课件内容')
    return
  }

  const blob = new Blob(['\ufeff', buildDownloadMarkdown()], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = downloadFileName.value
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  ElMessage.success('课件已下载为 Markdown 文件')
}

function buildDownloadMarkdown() {
  const currentSnapshot = snapshot.value
  const variant = activeCoursewareVariant.value
  const generatedAt = currentSnapshot?.generatedAt
    ? new Date(currentSnapshot.generatedAt).toLocaleString('zh-CN', { hour12: false })
    : '刚刚生成'
  const topic = currentSnapshot?.topic || currentSnapshot?.resourceResult.knowledge_point || '当前学习主题'
  const content = ensureMarkdownTitle(coursewareContent.value.trim(), coursewareTitle.value)
  const metadata = [
    '<!--',
    `主题: ${topic}`,
    `生成时间: ${generatedAt}`,
    `课件版本: ${variant?.title ?? '默认版本'}`,
    `文件名: ${downloadFileName.value}`,
    '-->',
    '',
  ]

  return `${metadata.join('\n')}${content}\n`
}

function ensureMarkdownTitle(content: string, title: string) {
  if (/^#\s+/.test(content)) {
    return content
  }
  return `# ${title}\n\n${content}`
}

function buildSafeFileName(rawTitle: string) {
  const stem = rawTitle
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80)
  const datePart = new Date().toISOString().slice(0, 10)
  return `${stem || 'courseware'}-${datePart}`
}

async function generateFromLatestPath(useCurrentTopic = false) {
  const user = authStore.user
  if (!user || autoGenerating.value) {
    return
  }

  autoGenerating.value = true
  pathMissing.value = false
  generationProgress.value = 0
  progressStages.value = createProgressStages()
  try {
    setProgress('path', 12)
    const path = useCurrentTopic && snapshot.value
      ? { knowledge_point: snapshot.value.topic || snapshot.value.resourceResult.knowledge_point, subject: snapshot.value.subject, overview: snapshot.value.goal }
      : (await agentApi.get<LearningPathResponse>(`/paths/${user.userId}`)).data
    if (!path?.knowledge_point) {
      pathMissing.value = true
      return
    }

    const pendingKey = `courseware-task:v2:${user.userId}:${path.subject}:${path.knowledge_point}`
    let pending = JSON.parse(sessionStorage.getItem(pendingKey) || 'null')
    if (!pending) {
      pending = { client_request_id: crypto.randomUUID(), task_id: null }
      sessionStorage.setItem(pendingKey, JSON.stringify(pending))
    }
    setProgress('generate', 20)
    if (!pending.task_id) {
      const { data: submitted } = await agentApi.post('/assistant/chat', {
        message: `${useCurrentTopic ? '重新生成' : '生成'}${path.knowledge_point}完整标准课件`, action: 'courseware',
        knowledge_point: path.knowledge_point, course_key: path.subject,
        client_request_id: pending.client_request_id, use_learning_context: false,
      })
      pending.task_id = submitted.task.id
      sessionStorage.setItem(pendingKey, JSON.stringify(pending))
    }
    let task: any
    while (mounted && authStore.user?.userId === user.userId) {
      task = (await agentApi.get(`/assistant/tasks/${pending.task_id}`)).data
      const completed = String(task.current_step || '').match(/课件章节 (\d+)\/9/)
      if (completed) generationProgress.value = Math.min(96, 20 + Number(completed[1]) * 8)
      progressStages.value = progressStages.value.map(stage => stage.key === 'generate' ? { ...stage, detail: task.current_step || '等待Worker执行' } : stage)
      if (task.status === 'SUCCEEDED') break
      if (['FAILED', 'TIMED_OUT', 'CANCELLED'].includes(task.status)) throw new Error(`任务 #${task.id} ${task.current_step}；已完成章节保留，可在学习助手中重试。`)
      await new Promise(resolve => setTimeout(resolve, 1500))
    }
    if (!mounted || authStore.user?.userId !== user.userId) return
    const card = task.result?.cards?.find((item: any) => item.type === 'courseware')
    if (!card?.resource_id) throw new Error('任务没有返回可用课件，请查看任务详情')
    const detail = (await resourceApi.get(`/resources/${card.resource_id}`)).data.data
    const teaching = JSON.parse(detail.teaching_json || '{}')
    const resourceResult = { id: detail.id, user_id: user.userId, knowledge_point: path.knowledge_point,
      resource_type: 'courseware', resource_style: 'interactive', content: detail.content, variants: [],
      generation_plan: teaching.generation_plan, references: teaching.sources || [],
      personalization: teaching.personalization || { mastery_score: null, correct_rate: null, answered_count: 0,
        weak_question_types: [], basis: teaching.personalization_basis || [], recent_mistakes: [] },
      generation_status: detail.generation_status, audit_status: detail.audit_status, publish_status: detail.publish_status,
    } as ResourceResult
    if (!mounted || authStore.user?.userId !== user.userId) return
    const nextSelectedVariantId =
      resourceResult.variants?.find((item: any) => item.is_recommended)?.variant_id
      ?? resourceResult.variants?.[0]?.variant_id
      ?? ''
    setProgress('persist', 96)
    const nextSnapshot: StoredCoursewareSnapshot = {
      subject: path.subject,
      topic: path.knowledge_point,
      goal: path.overview,
      selectedVariantId: nextSelectedVariantId,
      generatedAt: Date.now(),
      resourceResult, version: detail.version, teaching_json: detail.teaching_json,
    }
    window.sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify(nextSnapshot))
    snapshot.value = nextSnapshot
    selectedVariantId.value = nextSelectedVariantId
    sessionStorage.removeItem(pendingKey)
    finishProgress()
    availableUpgrade.value = null
    ElMessage.success('已根据最新学习路径生成课件')
  } catch (error: any) {
    if (error?.response?.status === 404) {
      pathMissing.value = true
      return
    }
    ElMessage.error(`课件生成失败：${error?.response?.data?.detail ?? error?.message ?? '未知错误'}`)
  } finally {
    autoGenerating.value = false
  }
}

function buildCoursewareSections(content: string): CoursewareSection[] {
  const normalized = content.trim().replace(/\r\n/g, '\n')
  if (!normalized) return []

  const sections: Array<{ heading: string; lines: string[] }> = []
  let current: { heading: string; lines: string[] } | null = null
  let inCodeFence = false
  for (const line of normalized.split('\n')) {
    if (/^\s*```/.test(line)) inCodeFence = !inCodeFence
    if (!inCodeFence && /^#\s+/.test(line) && !current && sections.length === 0) continue
    const heading = !inCodeFence ? line.match(/^##\s+(.+?)\s*$/) : null
    if (heading) {
      current = { heading: heading[1].replace(/\*\*|`/g, '').trim(), lines: [] }
      sections.push(current)
      continue
    }
    if (!current) {
      current = { heading: '课件内容', lines: [] }
      sections.push(current)
    }
    current.lines.push(line)
  }

  return sections.filter((section) => section.lines.some((line) => line.trim())).map((section, index) => ({
    heading: section.heading,
    anchor: `courseware-page-section-${index + 1}`,
    html: renderLearningMarkdown(section.lines.join('\n').trim()),
  }))
}
</script>

<template>
  <div class="courseware-page">
    <header class="courseware-hero">
      <div>
        <div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin-bottom:8px">独立课件页</div>
        <h1>{{ coursewareTitle }}</h1>
        <p v-if="snapshot">
          围绕 {{ snapshot.topic || '当前学习主题' }} 生成的正式课件内容已经单独展开，适合直接专注阅读和按章节学习。
        </p>
        <p v-else>
          当前还没有可展示的课件内容，请先回到工作台生成正式课件。
        </p>

        <div class="action-row">
          <el-button @click="goBack">返回工作台</el-button>
          <el-button v-if="snapshot" type="primary" :loading="checkingStored" @click="reloadSnapshot">刷新当前课件</el-button>
          <el-button v-if="snapshot" :loading="autoGenerating" @click="generateFromLatestPath(true)">重新生成完整课件</el-button>
          <el-button v-if="snapshot" :icon="Download" @click="downloadCurrentCourseware">
            下载课件
          </el-button>
        </div>
        <p v-if="snapshot" style="margin:10px 0 0;font-size:12px;color:var(--muted)">
          将当前选中的课件版本导出为 {{ downloadFileName }}。
        </p>
      </div>

      <div class="hero-stats">
        <div class="hero-stat-card">
          <div style="font-size:12px;letter-spacing:.06em;color:var(--muted)">生成时间</div>
          <div style="font-size:22px;font-weight:700;margin-top:6px">{{ generatedTimeLabel }}</div>
          <div style="font-size:12px;color:var(--muted);margin-top:4px">课件快照保存时间</div>
        </div>
        <div class="hero-stat-card">
          <div style="font-size:12px;letter-spacing:.06em;color:var(--muted)">章节数量</div>
          <div style="font-size:28px;font-weight:700;color:var(--accent);margin-top:6px">{{ resourceSections.length }}</div>
          <div style="font-size:12px;color:var(--muted);margin-top:4px">已拆分为独立章节</div>
        </div>
      </div>
    </header>

    <section v-if="autoGenerating || generationProgress > 0" class="workspace-panel courseware-progress-panel">
      <div class="courseware-progress-header">
        <div>
          <div class="eyebrow">课件生成进度</div>
          <h3>智能体正在整理正式课件</h3>
          <p class="courseware-progress-meta">
            {{ autoGenerating ? '请稍等，系统会依次完成路径读取、画像装配、材料检索、规划生成和快照保存。' : '课件生成流程已完成，可继续按章节阅读。' }}
          </p>
        </div>
        <div class="courseware-progress-percentage">{{ generationProgress }}%</div>
      </div>
      <el-progress
        :percentage="generationProgress"
        :stroke-width="12"
        :show-text="false"
        status="success"
      />
      <div class="courseware-progress-steps">
        <article
          v-for="stage in progressStages"
          :key="stage.key"
          class="courseware-progress-step"
          :class="stage.status"
        >
          <span class="generation-hint-dot"></span>
          <div>
            <strong>{{ stage.label }}</strong>
            <p>{{ stage.detail }}</p>
          </div>
          <em>{{ stage.percent }}%</em>
        </article>
      </div>
    </section>

    <section v-if="snapshot" class="courseware-reader-shell">
      <div class="reader-head">
        <div>
          <div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)">正式课件</div>
          <h2 style="margin:6px 0 0;font-size:22px">专注阅读模式</h2>
        </div>
      </div>

      <el-alert v-if="storedLoadError" :title="storedLoadError" type="warning" :closable="false" />
      <el-alert v-if="legacySnapshot" title="正在阅读历史课件：旧正文不会自动变详细，旧学情段落已停止展示。" type="warning" :closable="false" />
      <el-button v-if="availableUpgrade" type="primary" @click="openUpgrade">打开已生成的九章新版（{{ availableUpgrade.content.length }} 字符）</el-button>
      <div class="reader-layout">
        <aside class="reader-toc">
          <div style="font-size:12px;color:var(--muted);margin-bottom:10px">课件目录</div>
          <div class="outline-list">
            <button
              v-for="section in resourceSections"
              :key="section.anchor"
              type="button"
              class="outline-item"
              @click="scrollToCoursewareSection(section.anchor)"
            >
              {{ section.heading }}
            </button>
          </div>
        </aside>

        <div class="learning-content reader-content">
          <article v-if="coursewareVariants.length > 1" class="learning-section">
            <h3>可选课件版本</h3>
            <div class="reference-list">
              <article
                v-for="variant in coursewareVariants"
                :key="variant.variant_id"
                class="reference-card clickable-card"
                :class="{ active: activeCoursewareVariant?.variant_id === variant.variant_id }"
                @click="selectCoursewareVariant(variant.variant_id)"
              >
                <strong>{{ variant.title }}</strong>
                <p>{{ variant.summary }}</p>
                <span class="reference-meta">
                  风格：{{ variant.resource_style }}
                  <template v-if="variant.is_recommended"> · 推荐</template>
                </span>
              </article>
            </div>
          </article>

          <article class="learning-section">
            <h3>阅读建议</h3>
            <div class="tag-row">
              <span class="agent-tag">先看目录</span>
              <span class="agent-tag">逐章学习</span>
              <span class="agent-tag">再去做题</span>
            </div>
            <p class="learning-line">
              这份课件已经拆成独立章节。建议先顺着目录学习，再返回工作台生成练习题，提交后再结合标准答案做复盘。
            </p>
          </article>

          <article v-if="coursewarePersonalization" class="learning-section">
            <h3>本次个性化依据</h3>
            <div class="report-evidence-grid">
              <div class="report-evidence-card">
                <span>当前掌握度</span>
                <strong>{{ coursewarePersonalization.mastery_score == null ? '暂无可靠评估' : `${coursewarePersonalization.mastery_score}/100` }}</strong>
              </div>
              <div class="report-evidence-card">
                <span>近期正确率</span>
                <strong>{{ coursewarePersonalization.correct_rate == null ? '暂无有效作答' : `${coursewarePersonalization.correct_rate}%` }}</strong>
              </div>
              <div class="report-evidence-card">
                <span>真实作答次数</span>
                <strong>{{ coursewarePersonalization.answered_count }}</strong>
              </div>
              <div class="report-evidence-card">
                <span>近期弱项题型</span>
                <strong>{{ coursewarePersonalization.weak_question_types.length || 0 }}</strong>
              </div>
            </div>
            <ul class="markdown-list">
              <li v-for="item in coursewarePersonalization.basis" :key="item">{{ item }}</li>
            </ul>
          </article>

          <CoursewareReader ref="reader" hide-navigation :content="coursewareContent" :resource-id="snapshot.resourceResult.id" :version="snapshot.version" :structured="snapshot.teaching_json" />

        </div>
      </div>
    </section>

    <section v-else class="workspace-panel wide">
      <div class="empty-state courseware-page-empty">
        <strong>{{ pathMissing ? '当前还没有学习路径，暂时无法生成课件。' : '当前没有可展示的正式课件。' }}</strong>
        <p>{{ pathMissing ? '先生成学习路径，系统会根据路径主题继续生成正式课件。' : '先回到学生工作台生成课件，再进入这里查看独立页面。' }}</p>
        <el-button v-if="pathMissing" type="primary" @click="router.push('/student/learning-path')">去生成学习路径</el-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.courseware-page {
  max-width: 1100px;
  color: var(--text);
}

.courseware-hero,
.courseware-reader-shell {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel);
}

.courseware-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 28px 32px;
  margin-bottom: 20px;
}

.courseware-hero h1,
.courseware-reader-shell h2,
.learning-section h3 {
  color: var(--text);
}

.courseware-hero p,
.learning-line,
.markdown-list,
.reference-card p,
.courseware-reading-progress p {
  color: var(--muted);
}

.hero-stats {
  display: grid;
  gap: 12px;
}

.hero-stat-card {
  min-width: 140px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--panel-strong);
}

.courseware-reader-shell {
  padding: 22px;
}

.reader-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}

.reader-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.reader-toc {
  position: sticky;
  top: 80px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent) 7%, var(--panel));
}

.courseware-reading-progress {
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--line));
  border-radius: 12px;
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.courseware-reading-progress strong,
.courseware-reading-progress span {
  color: var(--accent);
}

.outline-list {
  display: grid;
  gap: 10px;
}

.outline-item {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel-strong);
  color: var(--text);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.outline-item:hover {
  border-color: color-mix(in srgb, var(--accent) 55%, var(--line));
  color: var(--accent);
}

.reader-content {
  display: grid;
  gap: 14px;
}

.learning-section {
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--panel-strong);
}

.learning-section h3 {
  margin: 0 0 12px;
}

.learning-line {
  line-height: 1.8;
}

.learning-markdown {
  color: var(--muted);
  line-height: 1.85;
  overflow-wrap: anywhere;
}

.learning-markdown :deep(p),
.learning-markdown :deep(ul),
.learning-markdown :deep(ol),
.learning-markdown :deep(pre),
.learning-markdown :deep(.learning-math-block) {
  margin: 0 0 14px;
}

.learning-markdown :deep(:last-child) { margin-bottom: 0; }
.learning-markdown :deep(ul),
.learning-markdown :deep(ol) { padding-left: 24px; }
.learning-markdown :deep(li) { margin: 4px 0; }
.learning-markdown :deep(strong),
.learning-markdown :deep(h4) { color: var(--text); }
.learning-markdown :deep(h4) { margin: 18px 0 8px; }
.learning-markdown :deep(code) { background: var(--bg); border-radius: 4px; padding: 2px 5px; }
.learning-markdown :deep(pre) { padding: 14px; overflow: auto; border-radius: 10px; background: var(--bg); }
.learning-markdown :deep(pre code) { padding: 0; }
.learning-markdown :deep(.learning-math-block) { overflow-x: auto; }

.tag-row,
.reference-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.agent-tag {
  padding: 5px 12px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}

.report-evidence-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.report-evidence-card,
.reference-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: color-mix(in srgb, var(--text) 3%, transparent);
}

.report-evidence-card {
  padding: 14px;
}

.report-evidence-card span,
.reference-meta {
  color: var(--muted);
  font-size: 12px;
}

.report-evidence-card strong {
  display: block;
  margin-top: 8px;
  color: var(--accent);
  font-size: 20px;
}

.reference-card {
  flex: 1 1 220px;
  padding: 14px;
}

.reference-card strong {
  color: var(--text);
}

.clickable-card {
  cursor: pointer;
}

.reference-card.active,
.clickable-card:hover {
  border-color: color-mix(in srgb, var(--accent) 55%, var(--line));
  background: color-mix(in srgb, var(--accent) 8%, var(--panel-strong));
}

.markdown-list {
  line-height: 1.8;
  padding-left: 20px;
}

.code-block {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
}

.code-block-label {
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}

.code-block pre {
  margin: 0;
  padding: 14px;
  overflow: auto;
  color: var(--text);
}

@media (max-width: 900px) {
  .reader-layout,
  .report-evidence-grid {
    grid-template-columns: 1fr;
  }

  .reader-toc {
    position: static;
  }
}
</style>
