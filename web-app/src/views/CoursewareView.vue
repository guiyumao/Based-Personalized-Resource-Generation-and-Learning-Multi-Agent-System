<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document } from '@element-plus/icons-vue'

import type { ResourceResult, ResourceVariant } from '../api'

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

const COURSEWARE_STORAGE_KEY = 'student-workspace-courseware'

const router = useRouter()
const snapshot = ref<StoredCoursewareSnapshot | null>(readStoredSnapshot())
const selectedVariantId = ref(snapshot.value?.selectedVariantId ?? '')

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
const coursewareOutline = computed(() => resourceSections.value.map((section) => section.heading))
const coursewarePersonalization = computed(() => snapshot.value?.resourceResult.personalization ?? null)
const generatedTimeLabel = computed(() => {
  if (!snapshot.value?.generatedAt) {
    return '刚刚生成'
  }
  return new Date(snapshot.value.generatedAt).toLocaleString('zh-CN', { hour12: false })
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
  void router.push({ name: 'student' })
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
      anchor: `courseware-page-section-${index + 1}`,
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
  <div class="dashboard-shell student-workspace-shell courseware-page-shell">
    <div class="aurora aurora-a" />
    <div class="aurora aurora-b" />

    <header class="hero-panel courseware-page-hero">
      <div class="hero-copy">
        <div class="eyebrow">独立课件页</div>
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
        </div>
      </div>

      <div class="hero-aside">
        <div class="signal-card">
          <div class="signal-title">生成时间</div>
          <div class="signal-metric compact">{{ generatedTimeLabel }}</div>
          <div class="signal-caption">当前课件快照最后一次保存到页面缓存的时间</div>
        </div>
        <div class="signal-card">
          <div class="signal-title">章节数量</div>
          <div class="signal-metric accent">{{ resourceSections.length }}</div>
          <div class="signal-caption">已拆分为独立可阅读章节</div>
        </div>
      </div>
    </header>

    <section v-if="snapshot" class="workspace-panel wide">
      <div class="panel-heading">
        <div>
          <div class="panel-kicker">正式课件</div>
          <h2>专注阅读模式</h2>
        </div>
        <Document class="panel-icon" />
      </div>

      <div class="reader-layout courseware-page-layout">
        <aside class="reader-outline">
          <div class="insight-label">课件目录</div>
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

          <section
            v-for="section in resourceSections"
            :id="section.anchor"
            :key="section.anchor"
            class="learning-section"
          >
            <h3>{{ section.heading }}</h3>
            <template v-for="block in section.blocks" :key="`${section.anchor}-${block.type}-${block.lines.join('-')}`">
              <p v-if="block.type === 'paragraph'" class="learning-line">
                {{ block.lines.join(' ') }}
              </p>
              <ul v-else-if="block.type === 'unordered'" class="markdown-list">
                <li v-for="line in block.lines" :key="line">{{ line }}</li>
              </ul>
              <ol v-else-if="block.type === 'ordered'" class="markdown-list markdown-list-ordered">
                <li v-for="line in block.lines" :key="line">{{ line }}</li>
              </ol>
              <div v-else class="code-block">
                <div v-if="block.language" class="code-block-label">{{ block.language }}</div>
                <pre><code>{{ block.lines.join('\n') }}</code></pre>
              </div>
            </template>
          </section>

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
