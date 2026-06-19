<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { userApi } from '../api'

const router = useRouter()
const authStore = useAuthStore()
const user = authStore.user!

interface ChatMessage { role: 'ai' | 'user'; text: string }
interface ProfileStatus { completed: boolean; skipped: boolean; dimensions_filled: number; total_dimensions: number; dimensions: Record<string, boolean> }

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const status = ref<ProfileStatus | null>(null)
const totalRounds = ref(0)
const maxRounds = ref(6)

// Profile dimension labels
const DIM_LABELS: Record<string, string> = {
  knowledgeBase: '知识基础',
  cognitiveStyle: '认知风格',
  errorPreference: '易错偏好',
  learningSpeed: '学习节奏',
  interestDirection: '兴趣方向',
  goalOrientation: '目标导向',
}

const filledCount = computed(() =>
  status.value ? Object.values(status.value.dimensions).filter(Boolean).length : 0)

// Show inline completion button once 4+ of 6 dimensions are known
const showCompletionButton = computed(() => filledCount.value >= 4)

// ── Init: load profile status ──
onMounted(async () => {
  try {
    const { data } = await userApi.get<ProfileStatus>(`/users/${user.userId}/profile/status`)
    status.value = data
    if (data.skipped || data.completed) {
      // User already completed or skipped — ask first question anyway
      await startConversation()
    } else {
      await startConversation()
    }
  } catch {
    await startConversation()
  }
})

async function startConversation() {
  loading.value = true
  try {
    // Send empty message to get the first question
    const { data } = await userApi.post(`/users/${user.userId}/profile/chat`, { message: '' })
    messages.value.push({ role: 'ai', text: data.reply })
    updateStatus(data)
  } catch {
    messages.value.push({
      role: 'ai',
      text: '为了更方便地了解您的需求，提供个性化服务，请您简单地描述一下您现在的情况——比如您的学习基础、目标、感兴趣的领域以及平时的学习习惯。',
    })
  } finally {
    loading.value = false
  }
}

function updateStatus(data: any) {
  if (data.estimated_remaining_rounds !== undefined) {
    maxRounds.value = totalRounds.value + data.estimated_remaining_rounds
  }
  if (data.profile_completeness) {
    const dims: Record<string, boolean> = {}
    for (const [k, v] of Object.entries(data.profile_completeness)) {
      dims[k] = v === '已获取'
    }
    status.value = {
      completed: Object.values(dims).filter(Boolean).length >= 3,
      skipped: false,
      dimensions_filled: Object.values(dims).filter(Boolean).length,
      total_dimensions: Object.keys(dims).length || 6,
      dimensions: dims,
    }
  }
}

// ── Send message ──
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', text })
  inputText.value = ''
  loading.value = true
  totalRounds.value++

  try {
    const { data } = await userApi.post(`/users/${user.userId}/profile/chat`, { message: text })
    messages.value.push({ role: 'ai', text: data.reply })
    updateStatus(data)
    await nextTick()
    scrollToBottom()
  } catch {
    messages.value.push({ role: 'ai', text: '抱歉，画像服务暂时不可用。您可以跳过此步骤，稍后在个人中心继续完善画像。' })
  } finally {
    loading.value = false
  }
}

// ── Skip ──
async function skipSetup() {
  try {
    await userApi.post(`/users/${user.userId}/profile/skip`, {})
  } catch { /* ok */ }
  ElMessage.info('已跳过画像设置，您可以稍后在个人中心继续完善')
  goToWorkspace()
}

// ── Finish ──
function finishSetup() {
  ElMessage.success('画像构建完成！')
  goToWorkspace()
}

function goToWorkspace() {
  router.replace(authStore.homeRoute)
}

function scrollToBottom() {
  const el = document.getElementById('chat-messages')
  if (el) el.scrollTop = el.scrollHeight
}
</script>

<template>
  <div style="min-height:100vh;display:flex;flex-direction:column;background:var(--bg)">
    <!-- Top bar -->
    <header style="display:flex;align-items:center;justify-content:space-between;padding:14px 28px;border-bottom:1px solid var(--line);background:var(--panel-strong)">
      <div style="display:flex;align-items:center;gap:12px">
        <div style="width:32px;height:32px;border-radius:10px;background:linear-gradient(135deg,var(--accent),var(--accent-deep))"></div>
        <span style="font-weight:700;font-size:16px">智学平台 · 画像构建</span>
      </div>
      <div style="display:flex;align-items:center;gap:12px">
        <span v-if="status" style="font-size:13px;color:var(--muted)">
          已填充 {{ filledCount }}/{{ status.total_dimensions }} 维度
        </span>
        <button @click="skipSetup"
          style="padding:8px 18px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--text);cursor:pointer;font-size:13px;font-family:inherit">
          跳过
        </button>
        <button v-if="filledCount >= 2" @click="finishSetup"
          style="padding:8px 20px;border-radius:999px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;cursor:pointer;font-weight:600;font-size:13px;font-family:inherit">
          完成，进入工作台
        </button>
      </div>
    </header>

    <!-- Progress bar -->
    <div v-if="status" style="padding:12px 28px;border-bottom:1px solid var(--line);background:var(--panel)">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-size:12px;color:var(--muted)">画像完成度</span>
        <span style="font-size:12px;font-weight:600;color:var(--accent)">
          {{ filledCount }}/{{ status.total_dimensions }}
          <span v-if="totalRounds > 0" style="color:var(--muted);font-weight:400">
            · 已对话 {{ totalRounds }} 轮 · 预计还需 {{ Math.max(0, maxRounds - totalRounds) }} 轮
          </span>
        </span>
      </div>
      <div style="height:4px;border-radius:2px;background:color-mix(in srgb,var(--muted) 15%,transparent);overflow:hidden">
        <div :style="{width:(filledCount/status.total_dimensions*100)+'%',height:'100%',background:'linear-gradient(90deg,var(--accent),var(--accent-deep))',borderRadius:'2px',transition:'width .5s'}"></div>
      </div>
    </div>

    <!-- Dimension tags -->
    <div v-if="status" style="padding:10px 28px;display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--line);background:var(--panel)">
      <span v-for="(label, key) in DIM_LABELS" :key="key"
        style="padding:4px 12px;border-radius:999px;font-size:11px;font-weight:550"
        :style="status.dimensions[key]
          ? {background:'color-mix(in srgb,var(--green) 14%,transparent)',color:'var(--green)'}
          : {background:'color-mix(in srgb,var(--muted) 10%,transparent)',color:'var(--muted)'}">
        {{ status.dimensions[key] ? '✓' : '○' }} {{ label }}
      </span>
    </div>

    <!-- Chat area -->
    <div id="chat-messages"
      style="flex:1;overflow-y:auto;padding:28px;max-width:720px;margin:0 auto;width:100%;display:grid;gap:16px;align-content:start">

      <div v-if="messages.length === 0 && loading" style="text-align:center;padding:60px 20px;color:var(--muted)">
        <div style="font-size:48px;margin-bottom:16px">🧠</div>
        <p>正在准备对话...</p>
      </div>

      <div v-for="(msg, i) in messages" :key="i"
        style="padding:16px 20px;border-radius:16px;font-size:14px;line-height:1.75;max-width:90%"
        :style="msg.role === 'user'
          ? { background:'linear-gradient(135deg,var(--accent),var(--accent-deep))',color:'#fff',marginLeft:'auto',borderBottomRightRadius:'6px' }
          : { background:'var(--panel)',border:'1px solid var(--line)',marginRight:'auto',borderBottomLeftRadius:'6px' }">
        <div style="font-size:11px;letter-spacing:.06em;margin-bottom:6px;opacity:.6">
          {{ msg.role === 'user' ? '你' : '🤖 AI 助手' }}
        </div>
        {{ msg.text }}
      </div>

      <!-- Inline completion button — appears when profile is sufficiently complete -->
      <div v-if="showCompletionButton && !loading"
        style="display:flex;justify-content:center;padding:8px 0 4px">
        <button @click="finishSetup"
          style="display:flex;align-items:center;gap:8px;padding:14px 36px;
            border-radius:14px;border:none;
            background:linear-gradient(135deg,var(--accent),var(--accent-deep));
            color:#fff;font-weight:700;font-size:15px;cursor:pointer;
            font-family:inherit;box-shadow:0 4px 18px color-mix(in srgb,var(--accent) 35%,transparent);
            transition:transform .15s,box-shadow .15s"
          onmouseover="this.style.transform='translateY(-1px)';this.style.boxShadow='0 6px 24px color-mix(in srgb,var(--accent) 50%,transparent)'"
          onmouseout="this.style.transform='translateY(0)';this.style.boxShadow='0 4px 18px color-mix(in srgb,var(--accent) 35%,transparent)'">
          <span style="font-size:18px">🎯</span>
          完成，进入学习
        </button>
      </div>

      <!-- Loading indicator -->
      <div v-if="loading && messages.length > 0" style="padding:12px 20px;color:var(--muted);font-size:13px">
        🤖 AI 正在分析您的回答...
      </div>
    </div>

    <!-- Input area -->
    <div style="padding:16px 28px 24px;border-top:1px solid var(--line);background:var(--panel-strong)">
      <div style="max-width:720px;margin:0 auto;display:flex;gap:12px">
        <input v-model="inputText" @keydown.enter="sendMessage" :disabled="loading"
          placeholder="输入您的回答..."
          style="flex:1;padding:12px 18px;border-radius:14px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:14px;outline:none;font-family:inherit" />
        <button @click="sendMessage" :disabled="loading || !inputText.trim()"
          style="padding:12px 28px;border-radius:14px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;font-weight:700;font-size:14px;cursor:pointer;font-family:inherit;white-space:nowrap">
          {{ loading ? '发送中...' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>
