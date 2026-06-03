<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CircleCheck, Promotion } from '@element-plus/icons-vue'

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

type SubmittedRemedialState = {
  exerciseId: number
  userAnswer: string
  correctAnswer: string
  analysis: string
  feedback: PracticeFeedback
}

const MISTAKE_NOTEBOOK_STORAGE_KEY = 'student-workspace-mistakes'

const questionTypeLabelMap: Record<string, string> = {
  choice: '选择题',
  blank: '填空题',
  judge: '判断题',
  short_answer: '简答题',
  programming: '编程题',
}

const router = useRouter()
const snapshot = ref<StoredMistakeSnapshot | null>(readStoredSnapshot())
const mistakeNotebook = ref<MistakeNotebook | null>(snapshot.value?.mistakeNotebook ?? null)
const remedialExerciseSet = ref<RemedialExerciseSet | null>(snapshot.value?.remedialExerciseSet ?? null)
const loadingMistakes = ref(false)
const loadingRemedial = ref(false)
const loadingSubmit = ref(false)
const focusedKnowledgePoint = ref('')
const currentRemedialIndex = ref(0)
const answerStartAt = ref<number | null>(remedialExerciseSet.value?.exercises.length ? Date.now() : null)
const remedialDrafts = reactive<Record<number, string>>({})
const remedialSubmissions = reactive<Record<number, SubmittedRemedialState>>({})
let autoAdvanceTimer: ReturnType<typeof setTimeout> | null = null

const userId = computed(() => snapshot.value?.userId ?? mistakeNotebook.value?.user_id ?? remedialExerciseSet.value?.user_id ?? 0)
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
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || !('userId' in parsed)) {
      return null
    }
    return parsed as StoredMistakeSnapshot
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

function buildFallbackPracticeFeedback(payload: PracticeSubmissionPayload): PracticeFeedback {
  const normalizedUserAnswer = payload.user_answer.trim().toLowerCase()
  const normalizedCorrectAnswer = payload.correct_answer.trim().toLowerCase()
  const isCorrect = normalizedCorrectAnswer === normalizedUserAnswer
    || normalizedCorrectAnswer.includes(normalizedUserAnswer)
    || normalizedUserAnswer.includes(normalizedCorrectAnswer)
  const score = isCorrect ? 100 : payload.user_answer.trim() ? (payload.question_type === 'choice' ? 0 : 60) : 0
  return {
    user_id: payload.user_id,
    exercise_id: payload.exercise_id,
    is_correct: isCorrect,
    score,
    feedback: isCorrect ? '回答正确，当前知识点掌握较稳定。' : '这道题还有提升空间，请先阅读解析。',
    suggested_action: isCorrect ? '保持节奏，继续下一题。' : '先看解析，再继续同类重练。',
    analysis: payload.analysis,
  }
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

function buildLocalRemedialSet(notebook: MistakeNotebook, knowledgePoint?: string): RemedialExerciseSet {
  const sourceItems = knowledgePoint
    ? notebook.items.filter((item) => item.knowledge_point === knowledgePoint)
    : notebook.items

  const exercises = sourceItems.map((item, index) => ({
    exercise_id: 9500 + index,
    knowledge_point: item.knowledge_point,
    question_type: item.question_type,
    prompt: `变式题 ${index + 1}：围绕 ${item.knowledge_point} 重新完成一道题，重点避免上次错误。`,
    options: item.question_type === 'choice'
      ? ['A. 关注边界条件', 'B. 按步骤拆解逻辑', 'C. 检查循环或判断条件', 'D. 对照示例验证结果']
      : [],
    answer: item.correct_answer,
    analysis: `本题用于针对性复练 ${item.knowledge_point}，帮助你修正同类错误。`,
    source_exercise_id: item.exercise_id,
  }))

  return {
    user_id: notebook.user_id,
    generated_from_mistakes: sourceItems.length,
    summary: knowledgePoint
      ? `已根据 ${knowledgePoint} 的错题记录生成同类变式重练题。`
      : '已根据本地错题记录生成变式重练题。',
    exercises,
  }
}

async function refreshMistakeNotebook() {
  if (!userId.value) {
    ElMessage.warning('当前缺少学生信息，请先回到工作台。')
    return
  }

  loadingMistakes.value = true
  try {
    const { data } = await evaluationApi.get<ApiEnvelope<MistakeNotebook>>(`/evaluation/mistakes/${userId.value}/detail`)
    mistakeNotebook.value = data.data
    persistSnapshot()
    ElMessage.success('错题本已刷新。')
  } catch {
    if (mistakeNotebook.value) {
      ElMessage.info('错题本服务暂不可用，当前先展示最近一次缓存内容。')
    } else {
      ElMessage.warning('当前没有可展示的错题内容，请先回到工作台生成。')
    }
  } finally {
    loadingMistakes.value = false
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
    if (!mistakeNotebook.value) {
      ElMessage.warning('当前没有错题记录，暂时无法生成重练题。')
      return
    }
    remedialExerciseSet.value = buildLocalRemedialSet(mistakeNotebook.value, knowledgePoint)
    resetRemedialSession()
    persistSnapshot()
    if (remedialExerciseSet.value.exercises.length > 0) {
      ElMessage.success('已根据本地错题记录生成变式重练题。')
    } else {
      ElMessage.info('当前知识点还没有可用错题，暂时无法生成重练题。')
    }
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
  }

  try {
    const { data } = await evaluationApi.post<ApiEnvelope<PracticeFeedback>>('/evaluation/practice/submit', payload)
    rememberRemedialSubmission(payload, data.data)
    ElMessage.success(data.data.is_correct ? '回答正确。' : '已返回标准答案与解析。')
    scheduleNextRemedialAutoAdvance()
  } catch {
    const fallback = buildFallbackPracticeFeedback(payload)
    rememberRemedialSubmission(payload, fallback)
    ElMessage.success(fallback.is_correct ? '回答正确。' : '已返回标准答案与解析。')
    scheduleNextRemedialAutoAdvance()
  } finally {
    loadingSubmit.value = false
  }
}

function goBack() {
  void router.push({ name: 'student' })
}

onUnmounted(() => {
  if (autoAdvanceTimer) {
    clearTimeout(autoAdvanceTimer)
    autoAdvanceTimer = null
  }
})
</script>

<template>
  <div style="max-width:1100px">

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
          <el-button v-if="snapshot" type="primary" :loading="loadingMistakes" @click="refreshMistakeNotebook">刷新错题本</el-button>
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
