<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { agentApi, evaluationApi, type ApiEnvelope, type ExerciseGenerationPayload, type ExerciseGenerationResponse, type ExerciseItem, type LearningPathResponse, type PracticeFeedback, type PracticeSubmissionPayload } from '../../api'
import { postContentWithTimeout } from '../../utils/viewHelpers'

const authStore = useAuthStore()
const user = authStore.user!
const COURSEWARE_STORAGE_KEY = 'student-workspace-courseware'

type StoredCoursewareSnapshot = {
  subject?: string
  topic?: string
  resourceResult?: {
    content?: string
  }
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
const genError = ref('')
const submitError = ref('')
const knowledgeSource = ref('')

const currentExercise = computed<ExerciseItem | null>(() => exerciseSet.value?.exercises[currentIdx.value] ?? null)
const totalExercises = computed(() => exerciseSet.value?.exercises.length ?? 0)
const answeredCount = computed(() => Object.keys(submittedExercises).length)
const hasKnowledgePoint = computed(() => Boolean(exerciseForm.knowledge_point.trim()))

onMounted(() => {
  void loadExistingKnowledgePoint()
})

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
    time_spent: 30,
  }
  try {
    const { data } = await evaluationApi.post<ApiEnvelope<PracticeFeedback>>('/evaluation/practice/submit', payload)
    submittedExercises[ex.exercise_id] = (data as any).data ?? data
    ElMessage.success(submittedExercises[ex.exercise_id].is_correct ? '回答正确' : '已返回解析')
    // Auto-report wrong answer to mistake book
    if (!submittedExercises[ex.exercise_id].is_correct) {
      try { await evaluationApi.post('/evaluation/mistakes/qa', {
        student_id: String(user.userId), subject: exerciseForm.knowledge_point, grade: '大学',
        question: ex.prompt, student_answer: draft, correct_answer: ex.answer,
        current_knowledge_points: [ex.knowledge_point], learning_route: {}, error_book: {}, learning_history: {},
      }) } catch { /* best-effort */ }
    }
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
  currentIdx.value = 0
}
function nextQuestion() { if (currentIdx.value < totalExercises.value - 1) currentIdx.value++ }
function prevQuestion() { if (currentIdx.value > 0) currentIdx.value-- }
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
          <div v-for="opt in currentExercise.options" :key="opt" @click="answerDrafts[currentExercise.exercise_id] = opt.charAt(0)"
            style="display:flex;align-items:center;gap:12px;padding:14px 18px;border-radius:14px;border:1px solid var(--line);cursor:pointer"
            :style="answerDrafts[currentExercise.exercise_id]===opt.charAt(0)?{borderColor:'var(--accent)',background:'color-mix(in srgb,var(--accent) 10%,transparent)'}:{background:'var(--bg)'}">
            <span style="width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-weight:700;background:color-mix(in srgb,var(--accent) 8%,transparent)">{{ opt.charAt(0) }}</span>{{ opt.slice(3) }}
          </div>
        </div>
        <textarea v-else v-model="answerDrafts[currentExercise.exercise_id]" :disabled="!!submittedExercises[currentExercise.exercise_id]"
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
        <div v-if="currentExercise && submittedExercises[currentExercise.exercise_id]" style="padding:18px;border-radius:14px;border:1px solid"
          :style="submittedExercises[currentExercise.exercise_id].is_correct?{background:'color-mix(in srgb,var(--green) 10%,transparent)',borderColor:'var(--green)'}:{background:'color-mix(in srgb,var(--red) 10%,transparent)',borderColor:'var(--red)'}">
          <div style="font-weight:700;margin-bottom:8px" :style="{color:submittedExercises[currentExercise.exercise_id].is_correct?'var(--green)':'var(--red)'}">{{ submittedExercises[currentExercise.exercise_id].is_correct ? '✓ 正确' : '✗ 错误' }}</div>
          <div style="font-size:13px;color:var(--text)">{{ submittedExercises[currentExercise.exercise_id].analysis }}</div>
        </div>
      </div>
    </div>
    <div v-else-if="!genError" style="text-align:center;padding:60px;color:var(--muted);border-radius:18px;background:var(--panel);border:1px solid var(--line)">
      {{ hasKnowledgePoint ? '点击“生成练习题”开始自测' : '先生成学习路径或课件，系统会自动带入知识点' }}
    </div>
  </div>
</template>
