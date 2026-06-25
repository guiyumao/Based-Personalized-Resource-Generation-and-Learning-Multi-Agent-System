<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { marked } from 'marked'

// Configure marked to add IDs to headings for outline navigation
marked.use({
  renderer: {
    heading({ text, depth }: { text: string; depth: number }) {
      const id = 'section-' + text.replace(/<[^>]*>/g, '').replace(/[^\w一-鿿]+/g, '-').replace(/^-|-$/g, '').toLowerCase()
      return `<h${depth} id="${id}">${text}</h${depth}>`
    }
  }
})

import {
  agentApi,
  type LearningPathResponse,
  type ResourcePayload,
  type ResourceResult,
  type ResourceVariant,
} from '../api'
import { useAuthStore } from '../stores/auth'

type CoursewareBlock =
  | { type: 'paragraph'; lines: string[] }
  | { type: 'unordered'; lines: string[] }
  | { type: 'ordered'; lines: string[] }
  | { type: 'code'; lines: string[]; language: string }

type CoursewareSection = {
  heading: string
  anchor: string
  blocks: CoursewareBlock[]
}

type StoredCoursewareSnapshot = {
  subject: string
  topic: string
  goal: string
  selectedVariantId: string
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
const autoGenerating = ref(false)
const generationProgress = ref(0)
const progressStages = ref<ProgressStage[]>(createProgressStages())

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
const coursewarePersonalization = computed(() => snapshot.value?.resourceResult.personalization ?? null)
const readingProgress = computed(() => {
  if (!resourceSections.value.length) {
    return 0
  }
  return Math.round((resourceSections.value.filter((section) => section.blocks.length > 0).length / resourceSections.value.length) * 100)
})
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
    { key: 'profile', label: '装配学习画像', detail: '合并真实作答、掌握度、错题和空态画像，不使用演示假数据。', percent: 26, status: 'pending' },
    { key: 'rag', label: '检索知识材料', detail: '从知识库与 RAG 片段中提取可用于课件的概念、示例和易错点。', percent: 42, status: 'pending' },
    { key: 'plan', label: '制定生成规划', detail: '确定课件标题、章节大纲、难度、风格和目标字数。', percent: 58, status: 'pending' },
    { key: 'generate', label: '生成正式课件', detail: '调用资源生成智能体输出 Markdown；模型失败时自动生成兜底课件。', percent: 82, status: 'pending' },
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
    await generateFromLatestPath()
  }
})

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
    return parsed as StoredCoursewareSnapshot
  } catch {
    return null
  }
}

function reloadSnapshot() {
  snapshot.value = readStoredSnapshot()
  selectedVariantId.value = snapshot.value?.selectedVariantId ?? ''
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
  const target = document.getElementById(anchor)
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
  const references = currentSnapshot?.resourceResult.references ?? []
  const metadata = [
    '<!--',
    `主题: ${topic}`,
    `生成时间: ${generatedAt}`,
    `课件版本: ${variant?.title ?? '默认版本'}`,
    `文件名: ${downloadFileName.value}`,
    '-->',
    '',
  ]

  if (!references.length) {
    return `${metadata.join('\n')}${content}\n`
  }

  const referenceLines = references
    .map((reference, index) => {
      const title = reference.id || `参考材料 ${index + 1}`
      const source = String(reference.metadata?.source ?? 'RAG 检索')
      const body = reference.content?.trim() || '暂无摘要'
      return [`### ${title}`, '', `来源: ${source}`, '', body].join('\n')
    })
    .join('\n\n')

  return `${metadata.join('\n')}${content}\n\n---\n\n## 参考材料\n\n${referenceLines}\n`
}

function ensureMarkdownTitle(content: string, title: string) {
  if (/^#\s+/.test(content)) {
    return content
  }
  return `# ${title}\n\n${content}`
}

function renderMd(raw: string): string {
  if (!raw) return ''
  return marked.parse(raw, { breaks: true, gfm: true }) as string
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

async function generateFromLatestPath() {
  const user = authStore.user
  if (!user || autoGenerating.value) {
    return
  }

  autoGenerating.value = true
  generationProgress.value = 0
  progressStages.value = createProgressStages()
  try {
    setProgress('path', 12)
    const pathResponse = await agentApi.get<LearningPathResponse>(`/paths/${user.userId}`)
    const path = pathResponse.data
    if (!path?.knowledge_point) {
      return
    }

    setProgress('profile', 26)
    const payload: ResourcePayload = {
      user_id: user.userId,
      knowledge_point: path.knowledge_point,
      resource_style: 'interactive',
      resource_type: 'courseware',
      learner_profile: {},
      request_text: `围绕 ${path.subject || '当前学科'} 的 ${path.knowledge_point} 生成可独立阅读的正式课件`,
    }
    setProgress('rag', 42)
    setProgress('plan', 58)
    setProgress('generate', 82)
    const { data } = await agentApi.post<ResourceResult>('/resources/generate', payload)
    const resourceResult = (data as any).data ?? data
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
      resourceResult,
    }
    window.sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify(nextSnapshot))
    snapshot.value = nextSnapshot
    selectedVariantId.value = nextSelectedVariantId
    finishProgress()
    ElMessage.success('已根据最新学习路径生成课件')
  } catch (error: any) {
    ElMessage.error(`课件生成失败：${error?.response?.data?.detail ?? error?.message ?? '未知错误'}`)
  } finally {
    autoGenerating.value = false
  }
}

function buildCoursewareSections(content: string): CoursewareSection[] {
  const normalized = content.trim().replace(/\r\n/g, '\n')
  if (!normalized) {
    return []
  }

  const titleRemoved = normalized.replace(/^# .+\n?/, '').trim()
  const chunks = titleRemoved.split(/\n##\s+/).filter(Boolean)

  return chunks.map((chunk, index) => {
    const lines = chunk.trim().split('\n')
    const firstLine = lines.shift() ?? `章节 ${index + 1}`
    return {
      heading: firstLine.trim(),
      anchor: 'section-' + firstLine.trim().replace(/<[^>]*>/g, '').replace(/[^\w一-鿿]+/g, '-').replace(/^-|-$/g, '').toLowerCase(),
      blocks: parseMarkdownBlocks(lines.join('\n').trim()),
    }
  })
}

function parseMarkdownBlocks(body: string): CoursewareBlock[] {
  if (!body) {
    return []
  }

  const blocks: CoursewareBlock[] = []
  const lines = body.split('\n')
  let index = 0

  while (index < lines.length) {
    const line = lines[index].trimEnd()
    const trimmed = line.trim()

    if (!trimmed) {
      index += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const language = trimmed.slice(3).trim()
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) {
        index += 1
      }
      blocks.push({ type: 'code', lines: codeLines, language })
      continue
    }

    if (/^-\s+/.test(trimmed)) {
      const listLines: string[] = []
      while (index < lines.length && /^-\s+/.test(lines[index].trim())) {
        listLines.push(lines[index].trim().replace(/^-\s+/, ''))
        index += 1
      }
      blocks.push({ type: 'unordered', lines: listLines })
      continue
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const listLines: string[] = []
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        listLines.push(lines[index].trim().replace(/^\d+\.\s+/, ''))
        index += 1
      }
      blocks.push({ type: 'ordered', lines: listLines })
      continue
    }

    const paragraphLines: string[] = []
    while (index < lines.length) {
      const current = lines[index].trimEnd()
      const currentTrimmed = current.trim()
      if (!currentTrimmed || currentTrimmed.startsWith('```') || /^-\s+/.test(currentTrimmed) || /^\d+\.\s+/.test(currentTrimmed)) {
        break
      }
      paragraphLines.push(currentTrimmed)
      index += 1
    }
    blocks.push({ type: 'paragraph', lines: paragraphLines })
  }

  return blocks
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
          <el-button v-if="snapshot" type="primary" @click="reloadSnapshot">刷新当前课件</el-button>
          <el-button v-if="snapshot" :icon="Download" @click="downloadCurrentCourseware">
            下载课件
          </el-button>
        </div>
        <p v-if="snapshot" style="margin:10px 0 0;font-size:12px;color:var(--muted)">
          将当前选中的课件版本导出为 {{ downloadFileName }}，包含正文和参考材料。
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

      <div class="reader-layout">
        <aside class="reader-toc">
          <div class="courseware-reading-progress">
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
              <strong>阅读拆解进度</strong>
              <span>{{ readingProgress }}%</span>
            </div>
            <el-progress :percentage="readingProgress" :stroke-width="8" :show-text="false" />
            <p>已识别 {{ resourceSections.length }} 个章节，当前课件可按目录逐章学习。</p>
          </div>
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
                <strong>{{ coursewarePersonalization.mastery_score }}/100</strong>
              </div>
              <div class="report-evidence-card">
                <span>近期正确率</span>
                <strong>{{ coursewarePersonalization.correct_rate }}%</strong>
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

          <div
            class="markdown-body"
            v-html="renderMd(coursewareContent)"
          ></div>

          <article v-if="snapshot.resourceResult.references?.length" class="learning-section">
            <h3>参考材料</h3>
            <div class="reference-list">
              <article
                v-for="reference in snapshot.resourceResult.references"
                :key="reference.id ?? reference.content"
                class="reference-card"
              >
                <strong>{{ reference.id ?? '参考片段' }}</strong>
                <p>{{ reference.content }}</p>
                <span class="reference-meta">
                  来源：{{ String(reference.metadata?.source ?? 'RAG 检索') }}
                </span>
              </article>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section v-else class="workspace-panel wide">
      <div class="empty-state courseware-page-empty">
        <strong>当前没有可展示的正式课件。</strong>
        <p>先回到学生工作台生成课件，再进入这里查看独立页面。</p>
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
  max-height: calc(100vh - 110px);
  display: flex;
  flex-direction: column;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent) 7%, var(--panel));
}

.reader-toc .outline-list {
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  padding-right: 4px;
}

.reader-toc .outline-list::-webkit-scrollbar {
  width: 4px;
}

.reader-toc .outline-list::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--accent) 25%, transparent);
  border-radius: 2px;
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

<!-- Unscoped styles for v-html rendered markdown (scoped CSS doesn't apply to v-html content) -->
<style>
.markdown-body {
  line-height: 1.9;
  font-size: 15px;
  color: var(--text);
}
.markdown-body h1, .markdown-body h2, .markdown-body h3 {
  margin-top: 28px;
  margin-bottom: 12px;
}
.markdown-body p { margin-bottom: 14px; }
.markdown-body ul, .markdown-body ol { padding-left: 22px; margin-bottom: 14px; }
.markdown-body li { margin-top: 4px; }
.markdown-body code {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--accent);
}
.markdown-body pre {
  background: #0d1117;
  padding: 16px;
  border-radius: 12px;
  overflow: auto;
  margin-bottom: 14px;
  border: 1px solid var(--line);
}
.markdown-body pre code {
  background: none;
  padding: 0;
  font-size: 13px;
  color: #e6edf3;
  white-space: pre;
}
.markdown-body blockquote {
  border-left: 3px solid var(--accent);
  padding-left: 16px;
  margin: 14px 0;
  color: var(--muted);
}
.markdown-body table {
  width: 100%;
  border-collapse: collapse;
  margin: 14px 0;
}
.markdown-body th, .markdown-body td {
  padding: 10px 14px;
  border: 1px solid var(--line);
  text-align: left;
}
.markdown-body th { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.markdown-body a { color: var(--accent); }
.markdown-body img { max-width: 100%; border-radius: 10px; }
</style>
