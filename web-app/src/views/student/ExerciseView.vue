<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { agentApi, evaluationApi, type ApiEnvelope, type ExerciseGenerationPayload, type ExerciseGenerationResponse, type ExerciseItem, type LearningPathResponse, type MistakeNotebook, type PracticeFeedback, type PracticeSubmissionPayload } from '../../api'
import { postContentWithTimeout } from '../../utils/viewHelpers'

const authStore = useAuthStore()
const user = authStore.user!
const COURSEWARE_STORAGE_KEY = 'student-workspace-courseware'
const EXERCISE_STORAGE_KEY = 'student-workspace-exercise-set'
const MISTAKE_NOTEBOOK_STORAGE_KEY = 'student-workspace-mistakes'
const PRACTICE_SESSION_STORAGE_KEY = `student-practice-session-${user.userId}`

type StoredCoursewareSnapshot = {
  subject?: string
  topic?: string
  resourceResult?: {
    content?: string
  }
}

type StoredExerciseSnapshot = {
  generatedAt?: number
  exerciseSet?: ExerciseGenerationResponse
}

type SubmissionHistoryItem = {
  exercise_id: number
  index: number
  prompt: string
  question_type: ExerciseItem['question_type']
  user_answer: string
  correct_answer: string
  feedback: PracticeFeedback
}

type StoredPracticeSession = {
  userId: number
  savedAt: number
  exerciseSet: ExerciseGenerationResponse
  currentIdx: number
  answerDrafts: Record<number, string>
  submittedExercises: Record<number, PracticeFeedback>
  submissionHistory: SubmissionHistoryItem[]
  mistakeNotebook: MistakeNotebook | null
  knowledgeSource: string
}

type StoredMistakeSnapshot = {
  userId: number
  generatedAt: number
  mistakeNotebook: MistakeNotebook | null
  remedialExerciseSet: unknown | null
}

const exerciseForm = reactive<ExerciseGenerationPayload>({
  user_id: user.userId, knowledge_point: '', resource_style: 'interactive',
  learner_profile: {}, exercise_count: 5,
  generation_mode: 'self_test', courseware_content: '',
})

const exerciseSet = ref<ExerciseGenerationResponse | null>(null)
const currentIdx = ref(0)
const loading = ref({ exercises: false, submit: false })
const answerDrafts = reactive<Record<number, string>>({})
const submittedExercises = reactive<Record<number, PracticeFeedback>>({})
const submissionHistory = ref<SubmissionHistoryItem[]>([])
const mistakeNotebook = ref<MistakeNotebook | null>(null)
const genError = ref('')
const submitError = ref('')
const knowledgeSource = ref('')

const currentExercise = computed<ExerciseItem | null>(() => exerciseSet.value?.exercises[currentIdx.value] ?? null)
const totalExercises = computed(() => exerciseSet.value?.exercises.length ?? 0)
const answeredCount = computed(() => Object.keys(submittedExercises).length)
const mistakeCount = computed(() => mistakeNotebook.value?.mistake_count ?? 0)
const hasKnowledgePoint = computed(() => Boolean(exerciseForm.knowledge_point.trim()))
const subjectiveTypes = new Set(['short_answer', 'programming'])

onMounted(() => {
  if (!loadStoredPracticeSession()) {
    loadStoredExerciseSet()
  }
  void loadExistingKnowledgePoint()
  void refreshMistakeNotebook()
})

function loadStoredPracticeSession() {
  if (typeof window === 'undefined') {
    return false
  }
  try {
    const raw = window.localStorage.getItem(PRACTICE_SESSION_STORAGE_KEY)
    if (!raw) {
      return false
    }
    const stored = JSON.parse(raw) as StoredPracticeSession
    if (stored.userId !== user.userId || !stored.exerciseSet?.exercises?.length) {
      return false
    }

    exerciseSet.value = stored.exerciseSet
    exerciseForm.knowledge_point = stored.exerciseSet.knowledge_point
    currentIdx.value = Math.min(Math.max(stored.currentIdx ?? 0, 0), stored.exerciseSet.exercises.length - 1)
    Object.assign(answerDrafts, stored.answerDrafts ?? {})
    Object.assign(submittedExercises, stored.submittedExercises ?? {})
    submissionHistory.value = stored.submissionHistory ?? []
    mistakeNotebook.value = stored.mistakeNotebook ?? null
    knowledgeSource.value = stored.knowledgeSource || '已恢复练习进度'
    ElMessage.success('已恢复上次练习进度')
    return true
  } catch {
    return false
  }
}

function loadStoredExerciseSet() {
  if (typeof window === 'undefined') {
    return
  }
  try {
    const raw = window.sessionStorage.getItem(EXERCISE_STORAGE_KEY)
    if (!raw) {
      return
    }
    const stored = JSON.parse(raw) as StoredExerciseSnapshot
    if (stored.exerciseSet?.exercises?.length) {
      exerciseSet.value = stored.exerciseSet
      exerciseForm.knowledge_point = stored.exerciseSet.knowledge_point
      ElMessage.success('已载入协同智能体生成的练习题')
    }
  } catch {
    // Ignore malformed session snapshots.
  }
}

async function loadExistingKnowledgePoint() {
  const stored = readCoursewareSnapshot()
  if (stored?.topic?.trim()) {
    applyKnowledgePoint(stored.topic, '来自已生成课件')
    exerciseForm.courseware_content = stored.resourceResult?.content ?? ''
    return
  }

  try {
    const { data } = await agentApi.get<LearningPathResponse>(`/paths/${user.userId}`)
    if (data?.knowledge_point?.trim()) {
      applyKnowledgePoint(data.knowledge_point, '来自当前学习路径')
    }
  } catch {
    knowledgeSource.value = ''
  }
}

function readCoursewareSnapshot(): StoredCoursewareSnapshot | null {
  if (typeof window === 'undefined') {
    return null
  }
  try {
    const raw = window.sessionStorage.getItem(COURSEWARE_STORAGE_KEY)
    return raw ? JSON.parse(raw) as StoredCoursewareSnapshot : null
  } catch {
    return null
  }
}

function applyKnowledgePoint(knowledgePoint: string, source: string) {
  exerciseForm.knowledge_point = knowledgePoint.trim()
  knowledgeSource.value = source
}

async function generateExercises() {
  if (!exerciseForm.knowledge_point.trim()) {
    await loadExistingKnowledgePoint()
  }
  if (!exerciseForm.knowledge_point.trim()) { ElMessage.warning('请先在学习路径生成知识点'); return }
  loading.value.exercises = true; genError.value = ''; exerciseSet.value = null
  try {
    exerciseForm.user_id = user.userId
    const { data } = await postContentWithTimeout<ExerciseGenerationResponse>('/exercises/generate', exerciseForm, 30000)
    exerciseSet.value = data
    resetSession()
    persistPracticeSession()
    ElMessage.success('课后自测已生成')
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    genError.value = `生成失败：${detail}`
    ElMessage.error(genError.value)
  } finally {
    loading.value.exercises = false
  }
}

async function submitAnswer() {
  const ex = currentExercise.value
  const draft = (answerDrafts[ex?.exercise_id ?? 0] ?? '').trim()
  if (!ex) return
  if (submittedExercises[ex.exercise_id]) { ElMessage.warning('这道题已经提交过'); return }
  if (!draft) { ElMessage.warning('请先填写答案'); return }
  loading.value.submit = true; submitError.value = ''

  const payload: PracticeSubmissionPayload = {
    user_id: exerciseForm.user_id, exercise_id: ex.exercise_id,
    knowledge_point: ex.knowledge_point, question_type: ex.question_type,
    user_answer: draft, correct_answer: ex.answer, analysis: ex.analysis,
    difficulty: normalizePracticeDifficulty(ex.difficulty),
    reference_answer: subjectiveTypes.has(ex.question_type) ? ex.answer : null,
    max_score: subjectiveTypes.has(ex.question_type) ? 100 : null,
    exercise_content: ex.prompt,
    time_spent: 30,
  }
  try {
    const { data } = await evaluationApi.post<ApiEnvelope<PracticeFeedback>>('/evaluation/practice/submit', payload)
    const feedback = (data as any).data ?? data
    submittedExercises[ex.exercise_id] = feedback
    rememberSubmission(ex, draft, feedback)
    await refreshMistakeNotebook()
    persistPracticeSession()
    ElMessage.success(feedback.is_correct ? '回答正确，已记录本题' : '已记录错题并返回解析')
    scheduleNextQuestion()
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    submitError.value = `提交失败：${detail}`
    ElMessage.error(submitError.value)
  } finally {
    loading.value.submit = false
  }
}

function resetSession() {
  for (const k of Object.keys(answerDrafts)) delete answerDrafts[Number(k)]
  for (const k of Object.keys(submittedExercises)) delete submittedExercises[Number(k)]
  submissionHistory.value = []
  currentIdx.value = 0
}
function persistPracticeSession() {
  if (typeof window === 'undefined' || !exerciseSet.value) {
    return
  }
  const snapshot: StoredPracticeSession = {
    userId: user.userId,
    savedAt: Date.now(),
    exerciseSet: exerciseSet.value,
    currentIdx: currentIdx.value,
    answerDrafts: { ...answerDrafts },
    submittedExercises: { ...submittedExercises },
    submissionHistory: submissionHistory.value,
    mistakeNotebook: mistakeNotebook.value,
    knowledgeSource: knowledgeSource.value,
  }
  window.localStorage.setItem(PRACTICE_SESSION_STORAGE_KEY, JSON.stringify(snapshot))
}
function persistMistakeNotebookSnapshot() {
  if (typeof window === 'undefined' || !mistakeNotebook.value) {
    return
  }

  let existing: StoredMistakeSnapshot | null = null
  try {
    const raw = window.sessionStorage.getItem(MISTAKE_NOTEBOOK_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) as StoredMistakeSnapshot : null
    existing = parsed?.userId === user.userId ? parsed : null
  } catch {
    existing = null
  }

  const snapshot: StoredMistakeSnapshot = {
    userId: user.userId,
    generatedAt: Date.now(),
    mistakeNotebook: mistakeNotebook.value,
    remedialExerciseSet: existing?.remedialExerciseSet ?? null,
  }
  window.sessionStorage.setItem(MISTAKE_NOTEBOOK_STORAGE_KEY, JSON.stringify(snapshot))
}
function setAnswer(exerciseId: number, answer: string) {
  answerDrafts[exerciseId] = answer
  persistPracticeSession()
}
function rememberSubmission(exercise: ExerciseItem, userAnswer: string, feedback: PracticeFeedback) {
  submissionHistory.value = [
    {
      exercise_id: exercise.exercise_id,
      index: currentIdx.value + 1,
      prompt: exercise.prompt,
      question_type: exercise.question_type,
      user_answer: userAnswer,
      correct_answer: exercise.answer,
      feedback,
    },
    ...submissionHistory.value.filter((item) => item.exercise_id !== exercise.exercise_id),
  ]
}
async function refreshMistakeNotebook() {
  try {
    const { data } = await evaluationApi.get<ApiEnvelope<MistakeNotebook>>(`/evaluation/mistakes/${user.userId}/detail`)
    mistakeNotebook.value = (data as any).data ?? data
    persistMistakeNotebookSnapshot()
    persistPracticeSession()
  } catch {
    // Keep practice flow usable even if the notebook endpoint is temporarily unavailable.
  }
}
function normalizePracticeDifficulty(difficulty: ExerciseItem['difficulty']): PracticeSubmissionPayload['difficulty'] {
  return difficulty === 'foundation' ? 'basic' : difficulty
}
function scheduleNextQuestion() {
  if (currentIdx.value >= totalExercises.value - 1) {
    ElMessage.success('本组练习已完成')
    return
  }
  window.setTimeout(() => {
    nextQuestion()
  }, 800)
}
function nextQuestion() {
  if (currentIdx.value < totalExercises.value - 1) {
    currentIdx.value++
    persistPracticeSession()
  }
}
function prevQuestion() {
  if (currentIdx.value > 0) {
    currentIdx.value--
    persistPracticeSession()
  }
}
</script>

<template>
  <div>
    <div style="margin-bottom:24px"><h2 style="font-size:24px;font-weight:750">✏️ 练习测评</h2><p style="color:var(--muted);font-size:14px">课后自测，即时反馈，巩固知识点</p></div>

    <div style="display:flex;gap:10px;align-items:center;margin-bottom:20px;flex-wrap:wrap">
      <div style="flex:1;min-width:260px;padding:12px 16px;border-radius:14px;border:1px solid var(--line);background:var(--panel);display:flex;align-items:center;justify-content:space-between;gap:12px">
        <div>
          <div style="font-size:12px;color:var(--muted);margin-bottom:4px">当前练习知识点</div>
          <strong v-if="hasKnowledgePoint" style="font-size:16px;color:var(--text)">{{ exerciseForm.knowledge_point }}</strong>
          <span v-else style="font-size:14px;color:var(--muted)">请先在学习路径生成知识点</span>
        </div>
        <span v-if="knowledgeSource" class="agent-tag">{{ knowledgeSource }}</span>
      </div>
      <button :disabled="loading.exercises" @click="generateExercises"
        style="padding:10px 20px;border-radius:12px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;cursor:pointer;font-weight:600;font-family:inherit;white-space:nowrap">
        {{ loading.exercises ? '生成中...' : '生成练习题' }}
      </button>
    </div>

    <div v-if="genError" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:16px;font-size:14px">{{ genError }}</div>
    <div v-if="submitError" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:16px;font-size:14px">{{ submitError }}</div>

    <div v-if="currentExercise" style="display:grid;grid-template-columns:1fr 280px;gap:20px">
      <div style="padding:28px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
        <div style="font-size:12px;letter-spacing:.08em;color:var(--accent);margin-bottom:12px">第 {{ currentIdx + 1 }} 题 / 共 {{ totalExercises }} 题 · {{ currentExercise.question_type }} · {{ currentExercise.difficulty }}</div>
        <h3 style="font-size:18px;line-height:1.6;margin-bottom:20px">{{ currentExercise.prompt }}</h3>
        <div v-if="currentExercise.question_type === 'choice' && currentExercise.options?.length" style="display:grid;gap:10px">
          <div v-for="opt in currentExercise.options" :key="opt" @click="setAnswer(currentExercise.exercise_id, opt.charAt(0))"
            style="display:flex;align-items:center;gap:12px;padding:14px 18px;border-radius:14px;border:1px solid var(--line);cursor:pointer"
            :style="answerDrafts[currentExercise.exercise_id]===opt.charAt(0)?{borderColor:'var(--accent)',background:'color-mix(in srgb,var(--accent) 10%,transparent)'}:{background:'var(--bg)'}">
            <span style="width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:700;background:color-mix(in srgb,var(--accent) 8%,transparent)">{{ opt.charAt(0) }}</span>{{ opt.slice(3) }}
          </div>
        </div>
        <textarea v-else v-model="answerDrafts[currentExercise.exercise_id]" :disabled="!!submittedExercises[currentExercise.exercise_id]"
          @input="persistPracticeSession"
          placeholder="输入你的答案..." style="width:100%;padding:12px 16px;border-radius:14px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:14px;resize:vertical;min-height:100px;outline:none;font-family:inherit"></textarea>
        <div style="display:flex;gap:12px;margin-top:24px">
          <button @click="submitAnswer" :disabled="loading.submit || !!submittedExercises[currentExercise.exercise_id]"
            style="padding:11px 28px;border-radius:12px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;cursor:pointer;font-weight:700;font-family:inherit">提交答案</button>
          <button @click="prevQuestion" :disabled="currentIdx===0" style="padding:11px 20px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--text);cursor:pointer;font-family:inherit">上一题</button>
          <button @click="nextQuestion" :disabled="currentIdx>=totalExercises-1" style="padding:11px 20px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--text);cursor:pointer;font-family:inherit">下一题</button>
        </div>
      </div>
      <div style="display:grid;gap:12px;align-content:start">
        <div style="padding:18px;text-align:center;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
          <div style="font-size:36px;font-weight:750;background:linear-gradient(135deg,var(--accent),var(--accent-deep));-webkit-background-clip:text;-webkit-text-fill-color:transparent">{{ answeredCount }}/{{ totalExercises }}</div>
          <div style="font-size:12px;color:var(--muted);margin-top:6px">已提交</div>
        </div>
        <div style="padding:18px;text-align:center;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
          <div style="font-size:30px;font-weight:750;color:var(--red)">{{ mistakeCount }}</div>
          <div style="font-size:12px;color:var(--muted);margin-top:6px">错题本</div>
        </div>
        <div v-if="currentExercise && submittedExercises[currentExercise.exercise_id]" style="padding:18px;border-radius:14px;border:1px solid"
          :style="submittedExercises[currentExercise.exercise_id].is_correct?{background:'color-mix(in srgb,var(--green) 10%,transparent)',borderColor:'var(--green)'}:{background:'color-mix(in srgb,var(--red) 10%,transparent)',borderColor:'var(--red)'}">
          <div style="font-weight:700;margin-bottom:8px" :style="{color:submittedExercises[currentExercise.exercise_id].is_correct?'var(--green)':'var(--red)'}">{{ submittedExercises[currentExercise.exercise_id].is_correct ? '✓ 正确' : '✗ 错误' }}</div>
          <div style="font-size:13px;color:var(--text)">{{ submittedExercises[currentExercise.exercise_id].analysis }}</div>
        </div>
        <div v-if="submissionHistory.length" style="padding:18px;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
          <h3 style="margin:0 0 12px;font-size:16px">本次提交记录</h3>
          <div style="display:grid;gap:10px;max-height:280px;overflow:auto;padding-right:4px">
            <article v-for="item in submissionHistory" :key="item.exercise_id" style="padding:12px;border-radius:12px;border:1px solid var(--line);background:var(--bg)">
              <div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:6px">
                <strong style="font-size:13px">第 {{ item.index }} 题</strong>
                <span :style="{ color: item.feedback.is_correct ? 'var(--green)' : 'var(--red)', fontSize: '12px', fontWeight: 700 }">
                  {{ item.feedback.is_correct ? '正确' : '已入错题' }}
                </span>
              </div>
              <div style="font-size:12px;color:var(--muted);line-height:1.6;margin-bottom:6px">
                {{ item.prompt }}
              </div>
              <div style="font-size:12px;line-height:1.6">
                <div>你的答案：{{ item.user_answer }}</div>
                <div v-if="!item.feedback.is_correct">正确答案：{{ item.correct_answer }}</div>
              </div>
            </article>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="!genError" style="text-align:center;padding:60px;color:var(--muted);border-radius:18px;background:var(--panel);border:1px solid var(--line)">
      {{ hasKnowledgePoint ? '点击“生成练习题”开始自测' : '先生成学习路径或课件，系统会自动带入知识点' }}
    </div>
  </div>
</template>
