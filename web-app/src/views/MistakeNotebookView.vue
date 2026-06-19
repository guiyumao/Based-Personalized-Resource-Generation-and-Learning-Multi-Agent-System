<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, Promotion } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

import {
  evaluationApi,
  type ApiEnvelope,
  type MistakeNotebook,
  type PracticeFeedback,
  type PracticeSubmissionPayload,
  type RemedialExerciseSet,
} from '../api'

type StoredMistakeSnapshot = {
  userId: number
  generatedAt: number
  mistakeNotebook: MistakeNotebook | null
  remedialExerciseSet: RemedialExerciseSet | null
}

type StoredPracticeSession = {
  userId: number
  savedAt: number
  mistakeNotebook: MistakeNotebook | null
}

type SubmittedRemedialState = {
  exerciseId: number
  userAnswer: string
  correctAnswer: string
  analysis: string
  feedback: PracticeFeedback
}

const MISTAKE_NOTEBOOK_STORAGE_KEY = 'student-workspace-mistakes'
const QA_MISTAKE_STORAGE_KEY = 'student-workspace-qa-mistakes'

const questionTypeLabelMap: Record<string, string> = {
  choice: '选择题',
  blank: '填空题',
  judge: '判断题',
  short_answer: '简答题',
  programming: '编程题',
}

const router = useRouter()
const authStore = useAuthStore()
const currentUserId = computed(() => authStore.user?.userId ?? 0)
const snapshot = ref<StoredMistakeSnapshot | null>(readStoredSnapshot())
const mistakeNotebook = ref<MistakeNotebook | null>(snapshot.value?.mistakeNotebook ?? null)
const remedialExerciseSet = ref<RemedialExerciseSet | null>(snapshot.value?.remedialExerciseSet ?? null)
const loadingMistakes = ref(false)
const loadingRemedial = ref(false)
const loadingSubmit = ref(false)
const loadingClearMistakes = ref(false)
const focusedKnowledgePoint = ref('')
const currentRemedialIndex = ref(0)
const answerStartAt = ref<number | null>(remedialExerciseSet.value?.exercises.length ? Date.now() : null)
const remedialDrafts = reactive<Record<number, string>>({})
const remedialSubmissions = reactive<Record<number, SubmittedRemedialState>>({})
let autoAdvanceTimer: ReturnType<typeof setTimeout> | null = null
const subjectiveTypes = new Set(['short_answer', 'programming'])

const userId = computed(() => snapshot.value?.userId ?? mistakeNotebook.value?.user_id ?? remedialExerciseSet.value?.user_id ?? currentUserId.value)
const hasMistakes = computed(() => Boolean(mistakeNotebook.value?.mistake_count))
const remedialCount = computed(() => remedialExerciseSet.value?.exercises.length ?? 0)
const mistakePreviewItems = computed(() => mistakeNotebook.value?.items.slice(0, 8) ?? [])
const remedialPreviewItems = computed(() => remedialExerciseSet.value?.exercises.slice(0, 6) ?? [])
const knowledgePointTags = computed(() =>
  Array.from(new Set((mistakeNotebook.value?.items ?? []).map((item) => item.knowledge_point))).slice(0, 6),
)
const generatedTimeLabel = computed(() => {
  if (!snapshot.value?.generatedAt) {
    return '刚刚更新'
  }
  return new Date(snapshot.value.generatedAt).toLocaleString('zh-CN', { hour12: false })
})
const currentRemedialExercise = computed(() => remedialExerciseSet.value?.exercises[currentRemedialIndex.value] ?? null)
const currentRemedialSubmission = computed(() => {
  const exerciseId = currentRemedialExercise.value?.exercise_id
  return exerciseId ? remedialSubmissions[exerciseId] ?? null : null
})
const currentRemedialAnswerDraft = computed({
  get() {
    const exerciseId = currentRemedialExercise.value?.exercise_id
    if (!exerciseId) {
      return ''
    }
    return currentRemedialSubmission.value?.userAnswer ?? remedialDrafts[exerciseId] ?? ''
  },
  set(value: string) {
    const exerciseId = currentRemedialExercise.value?.exercise_id
    if (!exerciseId || currentRemedialSubmission.value) {
      return
    }
    remedialDrafts[exerciseId] = value
  },
})

function readStoredSnapshot(): StoredMistakeSnapshot | null {
  if (typeof window === 'undefined') {
    return null
  }

  try {
    const raw = window.sessionStorage.getItem(MISTAKE_NOTEBOOK_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && 'userId' in parsed) {
        if (currentUserId.value && parsed.userId !== currentUserId.value) {
          return readPracticeMistakeSnapshot()
        }
        return parsed as StoredMistakeSnapshot
      }
    }
  } catch {
    // Ignore malformed session cache and try the practice progress fallback below.
  }

  return readPracticeMistakeSnapshot()
}

function readPracticeMistakeSnapshot(): StoredMistakeSnapshot | null {
  const targetUserId = currentUserId.value
  if (typeof window === 'undefined' || !targetUserId) {
    return null
  }

  try {
    const raw = window.localStorage.getItem(`student-practice-session-${targetUserId}`)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as StoredPracticeSession
    if (parsed.userId !== targetUserId || !parsed.mistakeNotebook) {
      return null
    }
    return {
      userId: targetUserId,
      generatedAt: parsed.savedAt ?? Date.now(),
      mistakeNotebook: parsed.mistakeNotebook,
      remedialExerciseSet: null,
    }
  } catch {
    return null
  }
}

function persistSnapshot() {
  if (typeof window === 'undefined' || !userId.value) {
    return
  }

  snapshot.value = {
    userId: userId.value,
    generatedAt: Date.now(),
    mistakeNotebook: mistakeNotebook.value,
    remedialExerciseSet: remedialExerciseSet.value,
  }
  window.sessionStorage.setItem(MISTAKE_NOTEBOOK_STORAGE_KEY, JSON.stringify(snapshot.value))
}

function buildEmptyMistakeNotebook(targetUserId: number): MistakeNotebook {
  return {
    user_id: targetUserId,
    mistake_count: 0,
    items: [],
  }
}

function clearStoredQaMistakes(targetUserId: number) {
  if (typeof window === 'undefined') {
    return
  }

  try {
    const raw = window.localStorage.getItem(QA_MISTAKE_STORAGE_KEY)
    if (!raw) {
      return
    }

    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return
    }

    const filtered = parsed.filter(
      (item) => !item || typeof item !== 'object' || (item as { user_id?: number }).user_id !== targetUserId,
    )

    if (filtered.length > 0) {
      window.localStorage.setItem(QA_MISTAKE_STORAGE_KEY, JSON.stringify(filtered))
      return
    }

    window.localStorage.removeItem(QA_MISTAKE_STORAGE_KEY)
  } catch {
    // Ignore malformed local QA notebook cache and proceed.
  }
}

function reloadSnapshot() {
  snapshot.value = readStoredSnapshot()
  mistakeNotebook.value = snapshot.value?.mistakeNotebook ?? null
  remedialExerciseSet.value = snapshot.value?.remedialExerciseSet ?? null
  focusedKnowledgePoint.value = ''
  resetRemedialSession()
  if (!snapshot.value) {
    ElMessage.warning('当前没有可展示的错题内容，请先回到工作台生成或刷新错题本。')
    return
  }
  ElMessage.success('已刷新当前错题页内容。')
}

function formatQuestionTypeLabel(value?: string) {
  if (!value) {
    return '未标注题型'
  }
  return questionTypeLabelMap[value] ?? value
}

function rememberRemedialSubmission(payload: PracticeSubmissionPayload, feedback: PracticeFeedback) {
  remedialSubmissions[payload.exercise_id] = {
    exerciseId: payload.exercise_id,
    userAnswer: payload.user_answer,
    correctAnswer: payload.correct_answer,
    analysis: feedback.analysis || payload.analysis,
    feedback,
  }
  remedialDrafts[payload.exercise_id] = payload.user_answer
}

function resetRemedialSession() {
  currentRemedialIndex.value = 0
  answerStartAt.value = remedialExerciseSet.value?.exercises.length ? Date.now() : null
  Object.keys(remedialDrafts).forEach((key) => delete remedialDrafts[Number(key)])
  Object.keys(remedialSubmissions).forEach((key) => delete remedialSubmissions[Number(key)])
  if (autoAdvanceTimer) {
    clearTimeout(autoAdvanceTimer)
    autoAdvanceTimer = null
  }
}

function goToNextRemedialExercise() {
  if (!remedialExerciseSet.value) {
    return
  }
  if (currentRemedialIndex.value < remedialExerciseSet.value.exercises.length - 1) {
    currentRemedialIndex.value += 1
    answerStartAt.value = Date.now()
    return
  }
  ElMessage.success('这一轮变式重练已完成。')
}

function goToPreviousRemedialExercise() {
  if (currentRemedialIndex.value <= 0) {
    return
  }
  currentRemedialIndex.value -= 1
  answerStartAt.value = Date.now()
}

function scheduleNextRemedialAutoAdvance() {
  if (!currentRemedialSubmission.value || !remedialExerciseSet.value) {
    return
  }
  if (autoAdvanceTimer) {
    clearTimeout(autoAdvanceTimer)
  }
  autoAdvanceTimer = setTimeout(() => {
    autoAdvanceTimer = null
    goToNextRemedialExercise()
  }, 1200)
}

async function refreshMistakeNotebook(options: { silent?: boolean } = {}) {
  if (!userId.value) {
    if (!options.silent) {
      ElMessage.warning('当前缺少学生信息，请先回到工作台。')
    }
    return
  }

  loadingMistakes.value = true
  try {
    const { data } = await evaluationApi.get<ApiEnvelope<MistakeNotebook>>(`/evaluation/mistakes/${userId.value}/detail`)
    mistakeNotebook.value = (data as any).data ?? data
    persistSnapshot()
    if (!options.silent) {
      ElMessage.success('错题本已刷新。')
    }
  } catch {
    if (mistakeNotebook.value) {
      if (!options.silent) {
        ElMessage.info('错题本服务暂不可用，当前先展示最近一次缓存内容。')
      }
    } else if (!options.silent) {
      ElMessage.warning('当前没有可展示的错题内容，请先回到工作台生成。')
    }
  } finally {
    loadingMistakes.value = false
  }
}

async function clearMistakeNotebook() {
  if (!userId.value) {
    ElMessage.warning('当前缺少学生信息，请先回到工作台。')
    return
  }
  if (!mistakeNotebook.value?.mistake_count && !remedialExerciseSet.value?.exercises.length) {
    ElMessage.info('当前错题页已经是空的。')
    return
  }

  try {
    await ElMessageBox.confirm(
      '清空后，这一页的错题列表和已生成的重练题会立即归零；历史答题记录和学习报告不会被删除。',
      '清空错题本',
      {
        confirmButtonText: '确认清空',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  loadingClearMistakes.value = true
  try {
    await evaluationApi.delete(`/evaluation/mistakes/${userId.value}`)
    mistakeNotebook.value = buildEmptyMistakeNotebook(userId.value)
    remedialExerciseSet.value = null
    focusedKnowledgePoint.value = ''
    clearStoredQaMistakes(userId.value)
    resetRemedialSession()
    persistSnapshot()
    ElMessage.success('错题本已清空。')
  } catch {
    ElMessage.error('清空错题本失败，请稍后重试。')
  } finally {
    loadingClearMistakes.value = false
  }
}

async function generateRemedialExercises(knowledgePoint?: string) {
  if (!userId.value) {
    ElMessage.warning('当前缺少学生信息，请先回到工作台。')
    return
  }

  loadingRemedial.value = true
  focusedKnowledgePoint.value = knowledgePoint ?? ''

  try {
    const { data } = await evaluationApi.get<ApiEnvelope<RemedialExerciseSet>>(`/evaluation/mistakes/${userId.value}/remedial`)
    remedialExerciseSet.value = {
      ...data.data,
      summary: knowledgePoint
        ? `${data.data.summary} 当前重点查看：${knowledgePoint}。`
        : data.data.summary,
    }
    resetRemedialSession()
    persistSnapshot()
    if (remedialExerciseSet.value.exercises.length > 0) {
      ElMessage.success(knowledgePoint ? '同类重练题已生成。' : '变式重练题已生成。')
    } else {
      ElMessage.info('当前还没有可生成的错题重练题。')
    }
  } catch {
    ElMessage.error('重练题生成服务暂不可用，请稍后重试。')
  } finally {
    loadingRemedial.value = false
  }
}

async function submitRemedialAnswer() {
  if (!currentRemedialExercise.value) {
    return
  }
  if (currentRemedialSubmission.value) {
    ElMessage.warning('这道变式题已经提交过了。')
    return
  }

  const answer = currentRemedialAnswerDraft.value.trim()
  if (!answer) {
    ElMessage.warning('请先填写答案。')
    return
  }

  loadingSubmit.value = true
  const payload: PracticeSubmissionPayload = {
    user_id: userId.value,
    exercise_id: currentRemedialExercise.value.exercise_id,
    knowledge_point: currentRemedialExercise.value.knowledge_point,
    question_type: currentRemedialExercise.value.question_type,
    user_answer: answer,
    correct_answer: currentRemedialExercise.value.answer,
    analysis: currentRemedialExercise.value.analysis,
    time_spent: answerStartAt.value ? Math.max(1, Math.round((Date.now() - answerStartAt.value) / 1000)) : 0,
    difficulty: 'intermediate',
    reference_answer: subjectiveTypes.has(currentRemedialExercise.value.question_type)
      ? currentRemedialExercise.value.answer
      : null,
    max_score: subjectiveTypes.has(currentRemedialExercise.value.question_type) ? 100 : null,
    exercise_content: currentRemedialExercise.value.prompt,
  }

  try {
    const { data } = await evaluationApi.post<ApiEnvelope<PracticeFeedback>>('/evaluation/practice/submit', payload)
    const feedback = (data as any).data ?? data
    rememberRemedialSubmission(payload, feedback)
    await refreshMistakeNotebook({ silent: true })
    ElMessage.success(feedback.is_correct ? '回答正确，已同步练习记录。' : '已加入错题本，并返回标准答案与解析。')
    scheduleNextRemedialAutoAdvance()
  } catch {
    ElMessage.error('答案提交失败，暂不使用本地判分，请稍后重试。')
  } finally {
    loadingSubmit.value = false
  }
}

function goBack() {
  void router.push({ name: 'student-dashboard' })
}

onMounted(() => {
  void refreshMistakeNotebook({ silent: true })
})

onUnmounted(() => {
  if (autoAdvanceTimer) {
    clearTimeout(autoAdvanceTimer)
    autoAdvanceTimer = null
  }
})
</script>

<template>
  <div class="mistake-page">

    <header class="hero-panel mistake-page-hero">
      <div class="hero-copy">
        <div class="eyebrow">独立错题页</div>
        <h1>复盘与重练</h1>
        <p v-if="snapshot">
          这里集中展示当前错题本、标准答案、解析建议和变式重练摘要，便于从“看懂错误”直接切到“针对性再练”。
        </p>
        <p v-else>
          当前还没有可展示的错题内容，请先回到学生工作台生成或刷新错题本。
        </p>

        <div class="action-row">
          <el-button @click="goBack">返回工作台</el-button>
          <el-button v-if="snapshot" @click="reloadSnapshot">刷新当前快照</el-button>
          <el-button v-if="snapshot" type="primary" :loading="loadingMistakes" @click="refreshMistakeNotebook()">刷新错题本</el-button>
          <el-button
            v-if="snapshot"
            plain
            type="danger"
            :loading="loadingClearMistakes"
            @click="clearMistakeNotebook"
          >
            清空错题本
          </el-button>
          <el-button
            v-if="snapshot"
            type="danger"
            :loading="loadingRemedial"
            @click="generateRemedialExercises()"
          >
            生成变式重练题
          </el-button>
        </div>
      </div>

      <div class="hero-aside">
        <div class="signal-card">
          <div class="signal-title">最近更新</div>
          <div class="signal-metric compact">{{ generatedTimeLabel }}</div>
          <div class="signal-caption">当前错题页快照最后一次同步到页面缓存的时间</div>
        </div>
        <div class="signal-card">
          <div class="signal-title">错题数量</div>
          <div class="signal-metric accent">{{ mistakeNotebook?.mistake_count ?? 0 }}</div>
          <div class="signal-caption">当前已收录到复盘页的错题条目</div>
        </div>
        <div class="signal-card">
          <div class="signal-title">重练题数量</div>
          <div class="signal-metric accent">{{ remedialCount }}</div>
          <div class="signal-caption">最近一轮变式重练生成结果</div>
        </div>
      </div>
    </header>

    <section v-if="snapshot" class="workspace-panel wide">
      <div class="panel-heading">
        <div>
          <div class="panel-kicker">错题复盘</div>
          <h2>集中查看与单独处理</h2>
        </div>
        <CircleCheck class="panel-icon" />
      </div>

      <div class="reader-layout mistake-page-layout">
        <aside class="reader-outline">
          <div class="insight-label">错题目录预览</div>
          <div class="outline-list">
            <button
              v-for="(item, index) in mistakePreviewItems"
              :key="`${item.exercise_id}-${index}`"
              type="button"
              class="outline-item static"
            >
              {{ item.knowledge_point }} / {{ formatQuestionTypeLabel(item.question_type) }}
            </button>
          </div>
        </aside>

        <div class="learning-content reader-content">
          <article class="learning-section courseware-entry-card">
            <h3>本页聚合内容</h3>
            <div class="tag-row">
              <span class="agent-tag">错题复盘</span>
              <span class="agent-tag">提交后看答案</span>
              <span class="agent-tag">变式重练</span>
              <span v-if="focusedKnowledgePoint" class="agent-tag">当前重点：{{ focusedKnowledgePoint }}</span>
            </div>
            <p class="learning-line">
              学生工作台现在只保留错题概览和进入入口，完整错题内容、逐题复盘以及重练结果已经集中放到这个独立页面里，阅读和操作会更连贯。
            </p>
            <div v-if="knowledgePointTags.length" class="tag-row">
              <span v-for="item in knowledgePointTags" :key="item" class="agent-tag">{{ item }}</span>
            </div>
          </article>

          <article v-if="hasMistakes" class="learning-section">
            <h3>错题列表</h3>
            <div class="reference-list">
              <article
                v-for="(item, index) in mistakeNotebook?.items"
                :key="`${item.exercise_id}-${index}`"
                class="reference-card"
              >
                <strong>{{ item.knowledge_point }} / {{ formatQuestionTypeLabel(item.question_type) }}</strong>
                <p>你的答案：{{ item.user_answer }}</p>
                <p>标准答案：{{ item.correct_answer }}</p>
                <p>解析：{{ item.analysis }}</p>
                <p>建议：{{ item.suggested_action }}</p>
                <div class="action-row">
                  <el-button
                    size="small"
                    type="warning"
                    :loading="loadingRemedial && focusedKnowledgePoint === item.knowledge_point"
                    @click="generateRemedialExercises(item.knowledge_point)"
                  >
                    生成同类重练题
                  </el-button>
                </div>
              </article>
            </div>
          </article>
          <div v-else class="empty-state mistake-page-empty">当前还没有错题记录，继续保持。</div>

          <article v-if="remedialExerciseSet" class="learning-section">
            <div class="panel-heading subtle">
              <div>
                <div class="panel-kicker">变式重练</div>
                <h3>直接在这里做题</h3>
              </div>
              <Promotion class="panel-icon" />
            </div>
            <div class="report-evidence-grid compact">
              <div class="report-evidence-card">
                <span>生成题目</span>
                <strong>{{ remedialCount }}</strong>
              </div>
              <div class="report-evidence-card">
                <span>来源错题</span>
                <strong>{{ remedialExerciseSet.generated_from_mistakes }}</strong>
              </div>
            </div>
            <p class="learning-line">{{ remedialExerciseSet.summary }}</p>
            <p class="learning-line">这一区现在就是独立错题页内的变式答题区，先作答，提交后才会显示标准答案与解析。</p>

            <div v-if="currentRemedialExercise" class="learning-section remedial-practice-card">
              <div class="tag-row">
                <span class="agent-tag">第 {{ currentRemedialIndex + 1 }} / {{ remedialCount }} 题</span>
                <span class="agent-tag">{{ currentRemedialExercise.knowledge_point }}</span>
                <span class="agent-tag">{{ formatQuestionTypeLabel(currentRemedialExercise.question_type) }}</span>
              </div>
              <h3>{{ currentRemedialExercise.prompt }}</h3>

              <div v-if="currentRemedialExercise.options.length" class="option-list">
                <label v-for="option in currentRemedialExercise.options" :key="option" class="option-item">
                  <input
                    v-model="currentRemedialAnswerDraft"
                    type="radio"
                    :value="option.charAt(0)"
                    :disabled="Boolean(currentRemedialSubmission)"
                  />
                  <span>{{ option }}</span>
                </label>
              </div>
              <el-input
                v-else
                v-model="currentRemedialAnswerDraft"
                type="textarea"
                :rows="5"
                :disabled="Boolean(currentRemedialSubmission)"
                placeholder="请输入你的答案"
              />

              <div class="action-row">
                <el-button
                  type="primary"
                  :loading="loadingSubmit"
                  :disabled="Boolean(currentRemedialSubmission)"
                  @click="submitRemedialAnswer"
                >
                  提交答案
                </el-button>
                <el-button
                  plain
                  :disabled="currentRemedialIndex === 0"
                  @click="goToPreviousRemedialExercise()"
                >
                  上一题
                </el-button>
                <el-button
                  plain
                  :disabled="currentRemedialIndex >= remedialCount - 1"
                  @click="goToNextRemedialExercise()"
                >
                  下一题
                </el-button>
              </div>

              <div
                v-if="currentRemedialSubmission"
                class="feedback-card"
                :class="{ correct: currentRemedialSubmission.feedback.is_correct, wrong: !currentRemedialSubmission.feedback.is_correct }"
              >
                <div class="insight-label">{{ currentRemedialSubmission.feedback.is_correct ? '作答结果' : '提交反馈' }}</div>
                <div class="insight-value">{{ currentRemedialSubmission.feedback.is_correct ? '回答正确' : '需要复盘' }}</div>
                <p class="panel-text"><strong>你的答案：</strong>{{ currentRemedialSubmission.userAnswer }}</p>
                <p class="panel-text"><strong>标准答案：</strong>{{ currentRemedialSubmission.correctAnswer }}</p>
                <p class="panel-text"><strong>解析：</strong>{{ currentRemedialSubmission.analysis }}</p>
              </div>
            </div>

            <div v-if="remedialPreviewItems.length" class="reference-list">
              <article
                v-for="(exercise, index) in remedialPreviewItems"
                :key="exercise.exercise_id"
                class="reference-card"
              >
                <strong>变式题 {{ index + 1 }} · {{ exercise.knowledge_point }} / {{ formatQuestionTypeLabel(exercise.question_type) }}</strong>
                <p>{{ exercise.prompt }}</p>
              </article>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section v-else class="workspace-panel wide">
      <div class="empty-state mistake-page-empty">
        <strong>当前没有可展示的错题内容。</strong>
        <p>先回到学生工作台刷新错题本，或者完成练习与问答后再进入这里查看独立页面。</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.mistake-page {
  max-width: 1120px;
  margin: 0 auto;
  color: var(--text);
  --mistake-surface: var(--panel);
  --mistake-surface-strong: var(--panel-strong);
  --mistake-surface-soft: rgba(10, 18, 32, 0.62);
  --mistake-ink: var(--text);
  --mistake-muted: var(--muted);
  --mistake-line: var(--line);
  --mistake-accent: var(--accent);
  --mistake-accent-dark: var(--accent-deep);
  --mistake-glow: color-mix(in srgb, var(--accent) 20%, transparent);
}

.hero-panel,
.workspace-panel {
  color: var(--mistake-ink);
  border: 1px solid var(--mistake-line);
  box-shadow: var(--shadow);
  backdrop-filter: blur(18px);
}

.hero-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 386px;
  gap: 32px;
  padding: 32px;
  border-radius: 28px;
  background:
    radial-gradient(circle at 16% 0%, var(--mistake-glow), transparent 36%),
    radial-gradient(circle at 84% 16%, color-mix(in srgb, var(--accent-deep) 16%, transparent), transparent 34%),
    linear-gradient(145deg, rgba(20, 32, 52, 0.96), rgba(8, 14, 26, 0.92));
}

.hero-copy {
  min-width: 0;
}

.eyebrow,
.panel-kicker,
.insight-label {
  color: var(--mistake-accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.hero-copy h1 {
  margin: 16px 0 12px;
  color: var(--mistake-ink);
  font-size: clamp(42px, 5vw, 58px);
  line-height: 1;
  background: linear-gradient(135deg, var(--text), var(--accent));
  background-clip: text;
  text-shadow: 0 0 34px var(--mistake-glow);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-copy p,
.learning-line,
.reference-card p,
.panel-text,
.signal-caption,
.empty-state p {
  color: var(--mistake-muted);
  line-height: 1.75;
}

.hero-aside {
  display: grid;
  gap: 16px;
}

.signal-card {
  padding: 24px;
  border-radius: 20px;
  color: var(--mistake-ink);
  background:
    linear-gradient(180deg, rgba(20, 32, 52, 0.9), rgba(10, 18, 32, 0.82)),
    radial-gradient(circle at 100% 0%, var(--mistake-glow), transparent 48%);
  border: 1px solid var(--mistake-line);
  box-shadow: inset 0 1px rgba(255, 255, 255, 0.06);
}

.signal-title,
.signal-caption {
  color: var(--mistake-muted);
}

.signal-metric {
  margin: 16px 0 8px;
  color: var(--mistake-ink);
  font-size: 30px;
  font-weight: 850;
}

.signal-metric.compact {
  font-size: 24px;
}

.signal-metric.accent {
  color: var(--mistake-accent);
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-top: 20px;
}

.workspace-panel {
  margin-top: 24px;
  padding: 24px;
  border-radius: 26px;
  background:
    radial-gradient(circle at 0% 0%, var(--mistake-glow), transparent 32%),
    var(--mistake-surface);
}

.workspace-panel.wide {
  width: 100%;
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.panel-heading.subtle {
  margin-bottom: 12px;
}

.panel-heading h2,
.panel-heading h3,
.learning-section h3 {
  margin: 6px 0 0;
  color: var(--mistake-ink);
}

.panel-icon {
  width: 32px;
  height: 32px;
  color: var(--mistake-accent);
}

.reader-layout {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  gap: 22px;
}

.reader-outline,
.learning-section,
.reference-card,
.empty-state,
.feedback-card,
.report-evidence-card {
  border: 1px solid var(--mistake-line);
  background: var(--mistake-surface-soft);
  color: var(--mistake-ink);
}

.reader-outline {
  align-self: start;
  position: sticky;
  top: 0;
  padding: 18px;
  border-radius: 20px;
}

.outline-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.outline-item {
  width: 100%;
  border: 1px solid color-mix(in srgb, var(--accent) 22%, transparent);
  border-radius: 12px;
  padding: 10px 12px;
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  color: var(--mistake-ink);
  text-align: left;
  cursor: default;
}

.learning-content {
  display: grid;
  gap: 18px;
  min-width: 0;
}

.learning-section {
  padding: 20px;
  border-radius: 20px;
}

.courseware-entry-card {
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, transparent), transparent 42%),
    var(--mistake-surface-soft);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}

.agent-tag {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 6px 10px;
  border: 1px solid color-mix(in srgb, var(--accent) 18%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--mistake-accent);
  font-size: 12px;
  font-weight: 750;
}

.reference-list {
  display: grid;
  gap: 14px;
}

.reference-card {
  padding: 16px;
  border-radius: 16px;
}

.reference-card strong {
  color: var(--mistake-ink);
}

.report-evidence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 12px 0;
}

.report-evidence-grid.compact {
  max-width: 420px;
}

.report-evidence-card {
  padding: 14px 16px;
  border-radius: 16px;
}

.report-evidence-card span {
  display: block;
  color: var(--mistake-muted);
  font-size: 12px;
}

.report-evidence-card strong {
  display: block;
  margin-top: 6px;
  color: var(--mistake-ink);
  font-size: 24px;
}

.remedial-practice-card {
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--accent) 8%, transparent), transparent 48%),
    var(--mistake-surface-strong);
}

.option-list {
  display: grid;
  gap: 10px;
  margin: 16px 0;
}

.option-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 12px 14px;
  border: 1px solid var(--mistake-line);
  border-radius: 14px;
  background: var(--mistake-surface-soft);
  color: var(--mistake-ink);
}

.feedback-card {
  margin-top: 16px;
  padding: 18px;
  border-radius: 18px;
}

.feedback-card.correct {
  border-color: color-mix(in srgb, var(--green) 38%, transparent);
  background: color-mix(in srgb, var(--green) 12%, transparent);
}

.feedback-card.wrong {
  border-color: color-mix(in srgb, var(--red) 34%, transparent);
  background: color-mix(in srgb, var(--red) 12%, transparent);
}

.insight-value {
  margin: 8px 0 12px;
  color: var(--mistake-ink);
  font-size: 22px;
  font-weight: 850;
}

.empty-state {
  padding: 22px;
  border-radius: 18px;
  color: var(--mistake-muted);
}

.empty-state strong {
  color: var(--mistake-ink);
}

:deep(.el-button) {
  --el-button-bg-color: rgba(16, 26, 44, 0.78);
  --el-button-border-color: var(--line);
  --el-button-hover-bg-color: color-mix(in srgb, var(--accent) 12%, var(--panel));
  --el-button-hover-border-color: color-mix(in srgb, var(--accent) 34%, var(--line));
  --el-button-text-color: var(--text);
  --el-button-hover-text-color: var(--text);
}

:deep(.el-button--primary) {
  --el-button-bg-color: var(--mistake-accent);
  --el-button-border-color: var(--mistake-accent);
  --el-button-hover-bg-color: var(--mistake-accent-dark);
  --el-button-hover-border-color: var(--mistake-accent-dark);
  --el-button-text-color: #ffffff;
}

:deep(.el-button--danger) {
  --el-button-bg-color: color-mix(in srgb, var(--red) 72%, #111827);
  --el-button-border-color: color-mix(in srgb, var(--red) 72%, #111827);
  --el-button-hover-bg-color: var(--red);
  --el-button-hover-border-color: var(--red);
  --el-button-text-color: #ffffff;
}

:deep(.el-button.is-plain) {
  background: rgba(16, 26, 44, 0.62);
}

:deep(.el-textarea__inner) {
  background: rgba(8, 14, 26, 0.72);
  color: var(--mistake-ink);
  border-color: var(--mistake-line);
  box-shadow: none;
}

:deep(.el-textarea__inner::placeholder) {
  color: var(--mistake-muted);
}

@media (max-width: 960px) {
  .hero-panel,
  .reader-layout {
    grid-template-columns: 1fr;
  }

  .reader-outline {
    position: static;
  }
}
</style>
