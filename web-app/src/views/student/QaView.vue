<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  evaluationApi,
  qaApi,
  type QAConversationMessage,
  type QAResponsePayload,
  type QARequestPayload,
} from '../../api'

const authStore = useAuthStore()
const user = authStore.user!

const qaForm = reactive<QARequestPayload>({
  student_id: String(user.userId),
  subject: '',
  grade: '大学',
  question: '',
  session_id: null,
  session_title: '',
  student_answer: '',
  wrong_answer: '',
  current_knowledge_points: [],
  learning_route: {},
  error_book: {},
  learning_history: {},
})

const loading = ref(false)
const qaResult = ref<QAResponsePayload | null>(null)
const qaError = ref('')
const qaElapsed = ref(0)
const qaConversation = ref<QAConversationMessage[]>([])
let qaTimer: ReturnType<typeof setInterval> | null = null

const qaKnowledgeGaps = computed(() => qaResult.value?.structured_analysis?.identified_knowledge_gaps ?? [])
const qaMisconceptions = computed(() => qaResult.value?.structured_analysis?.misconceptions ?? [])
const qaRouteUpdates = computed(() => qaResult.value?.structured_analysis?.learning_route_updates ?? [])
const qaRecommendations = computed(() => qaResult.value?.structured_analysis?.resource_recommendations ?? [])
const qaStudySuggestions = computed(() => qaResult.value?.structured_analysis?.study_suggestions ?? [])
const hasAnalysis = computed(() => qaKnowledgeGaps.value.length || qaMisconceptions.value.length || qaRouteUpdates.value.length || qaRecommendations.value.length)
const hasConversation = computed(() => qaConversation.value.length > 0)

function normalizeConversation(messages: QAConversationMessage[]) {
  return messages.filter((item) => item.role === 'user' || item.role === 'assistant')
}

function resetConversation() {
  qaForm.session_id = null
  qaForm.session_title = ''
  qaConversation.value = []
  qaResult.value = null
  qaError.value = ''
}

async function askQaAgent() {
  if (loading.value) return
  if (!qaForm.question.trim()) {
    qaError.value = '请先输入你的问题'
    return
  }

  const currentQuestion = qaForm.question.trim()
  loading.value = true
  qaError.value = ''
  qaElapsed.value = 0
  qaTimer = setInterval(() => { qaElapsed.value++ }, 1000)

  try {
    qaForm.student_id = String(user.userId)
    if (!qaForm.session_title?.trim()) {
      qaForm.session_title = currentQuestion.slice(0, 20)
    }

    const { data } = await qaApi.post<QAResponsePayload>('/qa/analyze', {
      ...qaForm,
      question: currentQuestion,
    })

    qaResult.value = data
    qaForm.session_id = data.session_id ?? qaForm.session_id ?? null
    qaForm.session_title = data.session_title || qaForm.session_title || ''
    qaConversation.value = normalizeConversation(data.message_history ?? [])
    qaForm.question = ''
    qaForm.student_answer = ''
    qaForm.wrong_answer = ''

    ElMessage.success(qaForm.session_id ? '已加入当前问答会话' : '智能回答已生成')

    if (data.structured_analysis?.mistake_book_update?.should_add) {
      try {
        await evaluationApi.post('/evaluation/mistakes/qa', {
          student_id: String(user.userId),
          subject: qaForm.subject,
          grade: qaForm.grade,
          question: currentQuestion,
          student_answer: qaForm.student_answer,
          wrong_answer: qaForm.wrong_answer,
          current_knowledge_points: qaForm.current_knowledge_points,
          learning_route: qaForm.learning_route,
          error_book: qaForm.error_book,
          learning_history: qaForm.learning_history,
        })
      } catch {
        // best-effort
      }
    }
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    qaError.value = `请求失败：${detail}`
    ElMessage.error(qaError.value)
  } finally {
    loading.value = false
    if (qaTimer) {
      clearInterval(qaTimer)
      qaTimer = null
    }
  }
}
</script>

<template>
  <div>
    <div style="margin-bottom:24px">
      <h2 style="font-size:24px;font-weight:750">智能问答</h2>
      <p style="color:var(--muted);font-size:14px">支持连续追问，学习类问题仍会附带结构化分析。</p>
    </div>

    <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:20px">
      <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:14px;gap:12px;flex-wrap:wrap">
        <div>
          <div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)">智能问答</div>
          <h2 style="margin:6px 0 0;font-size:20px">提问、追问与按需分析</h2>
          <p v-if="qaForm.session_id" style="margin:8px 0 0;color:var(--muted);font-size:13px">
            当前会话：#{{ qaForm.session_id }} {{ qaForm.session_title ? `· ${qaForm.session_title}` : '' }}
          </p>
        </div>
        <button
          v-if="hasConversation"
          @click="resetConversation"
          style="padding:10px 16px;border-radius:12px;border:1px solid var(--line);background:transparent;color:var(--text);font-weight:600;font-size:13px;cursor:pointer;font-family:inherit"
        >
          开启新会话
        </button>
      </div>

      <textarea
        v-model="qaForm.question"
        :rows="4"
        style="width:100%;padding:12px 16px;border-radius:14px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:14px;resize:vertical;min-height:80px;outline:none;font-family:inherit"
        :placeholder="hasConversation ? '继续追问，系统会结合上文回答' : '输入问题，例如：如何理解不定积分中的换元法？'"
      ></textarea>

      <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap">
        <input
          v-model="qaForm.student_answer"
          placeholder="可选：你的答案或思路"
          style="flex:1;padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:13px;outline:none;min-width:160px;font-family:inherit"
        />
        <input
          v-model="qaForm.wrong_answer"
          placeholder="可选：你的错误答案"
          style="flex:1;padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:13px;outline:none;min-width:160px;font-family:inherit"
        />
      </div>

      <div style="margin-top:12px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <button
          :disabled="loading"
          @click="askQaAgent"
          style="padding:11px 28px;border-radius:12px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;font-weight:700;font-size:14px;cursor:pointer;font-family:inherit"
        >
          {{ loading ? `分析中 (${qaElapsed}s)...` : (hasConversation ? '继续追问' : '开始智能问答') }}
        </button>
        <span style="color:var(--muted);font-size:13px">同一会话内会自动带上历史上下文。</span>
      </div>
    </div>

    <div v-if="loading" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:20px">
      <h3>问答处理中</h3>
      <p style="color:var(--muted);margin-top:8px">已等待 {{ qaElapsed }} 秒，AI 正在结合历史上下文分析...</p>
    </div>

    <div v-if="qaError" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:20px">
      <h3>错误</h3>
      <p style="color:var(--red);margin-top:8px">{{ qaError }}</p>
    </div>

    <div v-if="hasConversation" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:20px">
      <h3>对话记录</h3>
      <div style="display:flex;flex-direction:column;gap:14px;margin-top:14px">
        <div
          v-for="(message, index) in qaConversation"
          :key="message.id ?? `${message.role}-${index}-${message.created_at}`"
          :style="{
            alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '86%',
            padding: '14px 16px',
            borderRadius: '16px',
            border: '1px solid var(--line)',
            background: message.role === 'user'
              ? 'color-mix(in srgb,var(--accent) 14%,transparent)'
              : 'color-mix(in srgb,var(--text) 4%,transparent)',
          }"
        >
          <div style="font-size:12px;color:var(--muted);margin-bottom:6px">
            {{ message.role === 'user' ? '我' : 'AI 助手' }}
            <span v-if="message.model_used">· {{ message.model_used }}</span>
          </div>
          <div style="white-space:pre-wrap;line-height:1.8;font-size:14px">{{ message.content }}</div>
        </div>
      </div>
    </div>

    <div v-if="qaResult" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:20px">
      <h3>本轮分析</h3>
      <div style="margin-top:10px;display:flex;gap:12px;flex-wrap:wrap;color:var(--muted);font-size:13px">
        <span v-if="qaResult.confidence !== null">置信度：{{ Math.round(qaResult.confidence * 100) }}%</span>
        <span v-if="qaResult.context_snippets.length">参考片段：{{ qaResult.context_snippets.length }} 条</span>
      </div>
      <div style="white-space:pre-wrap;line-height:1.8;font-size:14px;padding:16px 18px;border-radius:14px;background:color-mix(in srgb,var(--accent) 6%,transparent);border:1px solid var(--line);margin-top:10px">{{ qaResult.student_response }}</div>
    </div>

    <template v-if="qaResult && hasAnalysis">
      <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:16px">
        <h3 style="color:var(--accent);margin-bottom:10px">知识漏洞</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <span v-for="g in qaKnowledgeGaps" :key="g" style="padding:6px 14px;border-radius:999px;font-size:12px;font-weight:600;background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent)">{{ g }}</span>
        </div>
        <p style="margin-top:10px;color:var(--muted);font-size:14px">{{ qaResult.structured_analysis.learning_state }}</p>
      </div>

      <div v-if="qaMisconceptions.length" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:16px">
        <h3 style="color:var(--accent);margin-bottom:10px">思维误区</h3>
        <ul style="padding-left:20px;color:var(--muted);line-height:1.8">
          <li v-for="m in qaMisconceptions" :key="m" style="margin-top:4px">{{ m }}</li>
        </ul>
      </div>

      <div v-if="qaRouteUpdates.length" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:16px">
        <h3 style="color:var(--accent);margin-bottom:10px">路线更新建议</h3>
        <div v-for="u in qaRouteUpdates" :key="`${u.knowledge_point}-${u.priority}`" style="padding:14px 16px;border-radius:12px;background:color-mix(in srgb,var(--accent) 4%,transparent);border:1px solid var(--line);margin-bottom:8px">
          <strong>{{ u.knowledge_point }} / {{ u.priority }}</strong>
          <p style="font-size:13px;color:var(--muted);margin:4px 0">{{ u.action }}</p>
          <p style="font-size:13px;color:var(--muted)">{{ u.reason }}</p>
        </div>
      </div>

      <div v-if="qaRecommendations.length" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:16px">
        <h3 style="color:var(--accent);margin-bottom:10px">推荐资源</h3>
        <div v-for="r in qaRecommendations" :key="r.title" style="padding:14px 16px;border-radius:12px;background:color-mix(in srgb,var(--accent) 4%,transparent);border:1px solid var(--line);margin-bottom:8px">
          <strong>{{ r.title }}</strong>
          <p style="font-size:13px;color:var(--muted);margin-top:4px">{{ r.reason }}</p>
        </div>
      </div>

      <div v-if="qaStudySuggestions.length" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);margin-bottom:16px">
        <h3 style="color:var(--accent);margin-bottom:10px">学习建议</h3>
        <ul style="padding-left:20px;color:var(--muted);line-height:1.8">
          <li v-for="s in qaStudySuggestions" :key="s" style="margin-top:4px">{{ s }}</li>
        </ul>
        <div
          v-if="qaResult.structured_analysis.mistake_book_update.should_add"
          style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--accent) 8%,transparent);border:1px solid var(--line);margin-top:12px"
        >
          <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent-deep);margin-bottom:6px">错题本更新建议</div>
          <p style="font-size:14px;margin:6px 0">题目摘要：{{ qaResult.structured_analysis.mistake_book_update.question_summary }}</p>
          <p style="font-size:13px;color:var(--muted)">错误原因：{{ qaResult.structured_analysis.mistake_book_update.wrong_reason }}</p>
          <p style="font-size:13px;color:var(--muted)">正确思路：{{ qaResult.structured_analysis.mistake_book_update.correct_approach }}</p>
        </div>
      </div>
    </template>
  </div>
</template>

