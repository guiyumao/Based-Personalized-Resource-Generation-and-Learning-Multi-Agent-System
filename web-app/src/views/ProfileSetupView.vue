<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { userApi } from '../api'

const router = useRouter()
const authStore = useAuthStore()
const user = authStore.user!

interface ChatMessage { role: 'ai' | 'user'; text: string }
interface ProfileStatus { completed: boolean; skipped: boolean; dimensions_filled: number; total_dimensions: number; dimensions: Record<string, boolean> }
interface UserProfileRead { profile_dimensions: Record<string, string> }
interface QuickChoiceGroup {
  key: string
  label: string
  hint: string
  accent: string
  options: string[]
}

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const deletingDimension = ref('')
const status = ref<ProfileStatus | null>(null)
const profileRecords = ref<Record<string, string>>({})
const selectedQuickChoices = ref<Record<string, string[]>>({})
const activeDimensionIndex = ref(0)
const totalRounds = ref(0)
const maxRounds = ref(6)
const minRequiredDimensions = 3

// Profile dimension labels
const DIM_LABELS: Record<string, string> = {
  knowledgeBase: '知识基础',
  cognitiveStyle: '认知风格',
  errorPreference: '易错偏好',
  learningSpeed: '学习节奏',
  interestDirection: '兴趣方向',
  goalOrientation: '目标导向',
}

const dimensionKeys = Object.keys(DIM_LABELS)
const totalDimensions = computed(() => dimensionKeys.length)
const filledCount = computed(() =>
  status.value ? dimensionKeys.filter((key) => Boolean(status.value?.dimensions[key])).length : 0)
const recordedCount = computed(() => dimensionKeys.filter((key) => Boolean(profileRecords.value[key]?.trim())).length)
const recordedItems = computed(() =>
  dimensionKeys.map((key) => ({
    key,
    label: DIM_LABELS[key],
    value: profileRecords.value[key]?.trim() || '',
    filled: Boolean(profileRecords.value[key]?.trim() || status.value?.dimensions[key]),
  })),
)
const progressPercent = computed(() =>
  totalDimensions.value > 0 ? Math.round((filledCount.value / totalDimensions.value) * 100) : 0)
const canFinish = computed(() => Boolean(status.value?.completed) || filledCount.value >= minRequiredDimensions)
const remainingRequired = computed(() => Math.max(0, minRequiredDimensions - filledCount.value))
const quickChoiceGroups: QuickChoiceGroup[] = [
  {
    key: 'knowledgeBase',
    label: '知识基础',
    hint: '已经接触过的内容',
    accent: '#22d3ee',
    options: [
      '零基础刚开始',
      '学过基础概念',
      '能看懂示例',
      '做过小项目',
      '有系统学习经历',
      '能独立完成作业',
      '学过相关课程',
      '有真实项目经验',
      '基础断断续续',
      '需要先补前置知识',
    ],
  },
  {
    key: 'cognitiveStyle',
    label: '认知风格',
    hint: '更舒服的理解方式',
    accent: '#a78bfa',
    options: [
      '视觉型',
      '文本型',
      '听觉型',
      '动手实践型',
      '先看例子再总结',
      '先理解原理再练习',
      '喜欢类比解释',
      '喜欢步骤清单',
      '需要即时反馈',
      '适合图文结合',
    ],
  },
  {
    key: 'errorPreference',
    label: '易错偏好',
    hint: '常见卡点或薄弱点',
    accent: '#fb7185',
    options: [
      '概念理解容易混淆',
      '步骤推导容易断',
      '代码调试容易卡',
      '公式迁移不熟',
      '题意审读不准',
      '综合应用题容易错',
      '细节边界常漏',
      '知识点之间串不起来',
      '遇到新题型没思路',
      '复盘错题不充分',
    ],
  },
  {
    key: 'learningSpeed',
    label: '学习节奏',
    hint: '希望系统怎样安排速度',
    accent: '#f59e0b',
    options: [
      '较快推进',
      '适中节奏',
      '慢一点分步讲',
      '先复习再进阶',
      '短时高频练习',
      '周末集中学习',
      '每天少量推进',
      '先易后难',
      '需要阶段复盘',
      '希望有明确 deadline',
    ],
  },
  {
    key: 'interestDirection',
    label: '兴趣方向',
    hint: '更想看到的主题或场景',
    accent: '#34d399',
    options: [
      '前端可视化',
      '后端开发',
      '算法思维',
      '数据分析',
      'AI 应用',
      '自动化工具',
      '游戏/交互项目',
      '移动应用',
      '数据库设计',
      '工程实践',
      '竞赛题目',
      '真实业务案例',
    ],
  },
  {
    key: 'goalOrientation',
    label: '目标导向',
    hint: '当前学习目标',
    accent: '#60a5fa',
    options: [
      '通过考试',
      '完成项目',
      '求职实习',
      '补齐薄弱点',
      '长期兴趣探索',
      '提升课堂成绩',
      '准备面试',
      '做作品集',
      '通过认证',
      '跟上课程进度',
      '提升解决问题能力',
      '形成学习习惯',
    ],
  },
]
const selectedQuickChoiceCount = computed(() =>
  Object.values(selectedQuickChoices.value).reduce((sum, items) => sum + items.length, 0),
)
const selectedQuickDimensionCount = computed(() =>
  quickChoiceGroups.filter((group) => (selectedQuickChoices.value[group.key] || []).length > 0).length,
)
const selectedQuickSummary = computed(() =>
  quickChoiceGroups
    .map((group) => ({
      key: group.key,
      label: group.label,
      values: selectedQuickChoices.value[group.key] || [],
    }))
    .filter((item) => item.values.length > 0),
)
const activeDimension = computed(() => quickChoiceGroups[activeDimensionIndex.value])
const activeDimensionSelections = computed(() =>
  activeDimension.value ? selectedQuickChoices.value[activeDimension.value.key] || [] : [],
)
const activeDimensionHasSelection = computed(() => activeDimensionSelections.value.length > 0)
const isLastDimension = computed(() => activeDimensionIndex.value >= quickChoiceGroups.length - 1)
const wizardProgressPercent = computed(() =>
  quickChoiceGroups.length > 0 ? Math.round(((activeDimensionIndex.value + 1) / quickChoiceGroups.length) * 100) : 0,
)
const connectedAgents = [
  { name: '学习路径智能体', detail: '按画像里的基础、目标和节奏规划学习路线' },
  { name: '资源生成智能体', detail: '按认知风格和兴趣方向生成课件与资料' },
  { name: '练习生成智能体', detail: '根据薄弱点和节奏调整题型与难度' },
  { name: '问答智能体', detail: '答疑时带入画像、知识图谱和错题上下文' },
]

function normalizeStatus(data: Partial<ProfileStatus> = {}): ProfileStatus {
  const dims: Record<string, boolean> = {}
  for (const key of dimensionKeys) {
    dims[key] = Boolean(data.dimensions?.[key])
  }
  const nextFilledCount = dimensionKeys.filter((key) => dims[key]).length
  return {
    completed: nextFilledCount >= 3,
    skipped: Boolean(data.skipped),
    dimensions_filled: nextFilledCount,
    total_dimensions: totalDimensions.value,
    dimensions: dims,
  }
}

// ── Init: load profile status ──
onMounted(async () => {
  try {
    const { data } = await userApi.get<ProfileStatus>(`/users/${user.userId}/profile/status`)
    status.value = normalizeStatus(data)
    await loadProfileRecords()
    if (data.skipped || data.completed) {
      // User already completed or skipped — ask first question anyway
      await startConversation()
    } else {
      await startConversation()
    }
  } catch {
    await loadProfileRecords()
    await startConversation()
  }
})

async function loadProfileRecords() {
  try {
    const { data } = await userApi.get<UserProfileRead>(`/users/${user.userId}/profile`)
    mergeProfileRecords(data.profile_dimensions)
  } catch {
    // Keep setup usable when the profile read endpoint is temporarily unavailable.
  }
}

function mergeProfileRecords(updates?: Record<string, string>) {
  if (!updates) return
  const next = { ...profileRecords.value }
  for (const key of dimensionKeys) {
    const value = updates[key]
    if (typeof value === 'string' && value.trim()) {
      next[key] = value.trim()
    }
  }
  profileRecords.value = next
}

function replaceProfileRecords(updates?: Record<string, string>) {
  const next: Record<string, string> = {}
  if (updates) {
    for (const key of dimensionKeys) {
      const value = updates[key]
      if (typeof value === 'string' && value.trim()) {
        next[key] = value.trim()
      }
    }
  }
  profileRecords.value = next
}

async function startConversation() {
  loading.value = true
  try {
    // Send empty message to get the first question
    const { data } = await userApi.post(`/users/${user.userId}/profile/chat`, { message: '' })
    messages.value.push({ role: 'ai', text: data.reply })
    updateStatus(data)
    mergeProfileRecords(data.profile_updates)
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
    for (const key of dimensionKeys) {
      dims[key] = data.profile_completeness[key] === '已获取'
    }
    const nextFilledCount = dimensionKeys.filter((key) => dims[key]).length
    status.value = normalizeStatus({
      completed: nextFilledCount >= 3,
      skipped: false,
      dimensions_filled: nextFilledCount,
      total_dimensions: totalDimensions.value,
      dimensions: dims,
    })
  }
}

function updateStatusFromProfileRecords() {
  const dims: Record<string, boolean> = {}
  for (const key of dimensionKeys) {
    dims[key] = Boolean(profileRecords.value[key]?.trim())
  }
  status.value = normalizeStatus({
    skipped: status.value?.skipped ?? false,
    dimensions: dims,
  })
}

async function refreshProfileStatus() {
  try {
    const { data } = await userApi.get<ProfileStatus>(`/users/${user.userId}/profile/status`)
    status.value = normalizeStatus(data)
  } catch {
    updateStatusFromProfileRecords()
  }
}

async function deleteRecord(key: string, label: string) {
  if (!profileRecords.value[key]?.trim() || deletingDimension.value) return

  try {
    await ElMessageBox.confirm(
      `删除后，${label} 会从画像记录和后续智能体协作上下文中移除。`,
      '删除了解记录',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  deletingDimension.value = key
  try {
    const { data } = await deleteProfileDimension(key)
    replaceProfileRecords(data.profile_dimensions)
    updateStatusFromProfileRecords()
    await refreshProfileStatus()
    ElMessage.success(`已删除${label}记录`)
  } catch {
    ElMessage.error('删除记录失败，请稍后重试。')
  } finally {
    deletingDimension.value = ''
  }
}

async function deleteProfileDimension(key: string) {
  try {
    return await userApi.delete<UserProfileRead>(`/users/${user.userId}/profile/dimensions/${key}`)
  } catch (error) {
    return userApi.put<UserProfileRead>(`/users/${user.userId}/profile`, {
      learning_style: null,
      profile_dimensions: { [key]: '' },
    })
  }
}

async function sendProfileMessage(text: string) {
  if (!text || loading.value) return

  messages.value.push({ role: 'user', text })
  loading.value = true
  totalRounds.value++

  try {
    const { data } = await userApi.post(`/users/${user.userId}/profile/chat`, { message: text })
    messages.value.push({ role: 'ai', text: data.reply })
    updateStatus(data)
    mergeProfileRecords(data.profile_updates)
    await nextTick()
    scrollToBottom()
  } catch {
    messages.value.push({ role: 'ai', text: '抱歉，画像服务暂时不可用。您可以跳过此步骤，稍后在个人中心继续完善画像。' })
  } finally {
    loading.value = false
  }
}

async function submitQuickChoices() {
  if (!selectedQuickChoiceCount.value || loading.value) return

  const lines = quickChoiceGroups
    .map((group) => {
      const values = selectedQuickChoices.value[group.key] || []
      return values.length ? `${group.label}：${values.join('、')}` : ''
    })
    .filter(Boolean)

  const text = `我想一次补充画像多维度：\n${lines.join('\n')}`
  await sendProfileMessage(text)
  selectedQuickChoices.value = {}
}

function clearQuickChoices() {
  selectedQuickChoices.value = {}
  activeDimensionIndex.value = 0
}

function isQuickChoiceSelected(key: string, option: string) {
  return (selectedQuickChoices.value[key] || []).includes(option)
}

function selectedQuickCountFor(key: string) {
  return (selectedQuickChoices.value[key] || []).length
}

function toggleQuickChoice(key: string, option: string) {
  if (loading.value) return
  const current = selectedQuickChoices.value[key] || []
  const next = current.includes(option)
    ? current.filter((item) => item !== option)
    : [...current, option]
  selectedQuickChoices.value = {
    ...selectedQuickChoices.value,
    [key]: next,
  }
}

function goToDimension(index: number) {
  if (index < 0 || index >= quickChoiceGroups.length || loading.value) return
  activeDimensionIndex.value = index
}

function previousDimension() {
  goToDimension(activeDimensionIndex.value - 1)
}

async function continueDimensionFlow() {
  if (!activeDimensionHasSelection.value || loading.value) return
  if (!isLastDimension.value) {
    activeDimensionIndex.value += 1
    return
  }
  await submitQuickChoices()
}

// ── Send message ──
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return
  inputText.value = ''
  await sendProfileMessage(text)
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
async function finishSetup() {
  loading.value = true
  try {
    const { data } = await userApi.get<ProfileStatus>(`/users/${user.userId}/profile/status`)
    status.value = normalizeStatus(data)
    if (!status.value.completed) {
      ElMessage.warning(`还需要至少补充 ${remainingRequired.value} 个维度，画像才能被学习路径、资源、练习和问答智能体稳定使用。`)
      return
    }
    ElMessage.success('画像已接入学习路径、资源、练习和问答智能体')
    goToWorkspace()
  } catch {
    if (!canFinish.value) {
      ElMessage.warning(`还需要至少补充 ${remainingRequired.value} 个维度，画像才能接入系统功能。`)
      return
    }
    ElMessage.success('画像构建完成，进入工作台后将用于个性化智能体协作')
    goToWorkspace()
  } finally {
    loading.value = false
  }
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
          已填充 {{ filledCount }}/{{ totalDimensions }} 维度
        </span>
        <button @click="skipSetup"
          style="padding:8px 18px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--text);cursor:pointer;font-size:13px;font-family:inherit">
          跳过
        </button>
        <button v-if="filledCount > 0" @click="finishSetup" :disabled="!canFinish || loading"
          style="padding:8px 20px;border-radius:999px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;cursor:pointer;font-weight:600;font-size:13px;font-family:inherit"
          :style="!canFinish || loading ? {opacity:.55,cursor:'not-allowed'} : {}">
          {{ canFinish ? '完成，进入工作台' : `还需 ${remainingRequired} 项` }}
        </button>
      </div>
    </header>

    <!-- Progress bar -->
    <div v-if="status" style="padding:8px 20px;border-bottom:1px solid var(--line);background:var(--panel)">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-size:12px;color:var(--muted)">画像完成度</span>
        <span style="font-size:12px;font-weight:600;color:var(--accent)">
          {{ filledCount }}/{{ totalDimensions }}
          <span v-if="totalRounds > 0" style="color:var(--muted);font-weight:400">
            · 已对话 {{ totalRounds }} 轮 · 预计还需 {{ Math.max(0, maxRounds - totalRounds) }} 轮
          </span>
        </span>
      </div>
      <div style="height:4px;border-radius:2px;background:color-mix(in srgb,var(--muted) 15%,transparent);overflow:hidden">
        <div :style="{width:progressPercent+'%',height:'100%',background:'linear-gradient(90deg,var(--accent),var(--accent-deep))',borderRadius:'2px',transition:'width .5s'}"></div>
      </div>
    </div>

    <main class="profile-setup-main">
      <section v-if="status" class="profile-capture-panel">
        <div class="panel-heading-line">
          <div>
            <div class="panel-kicker-text">画像向导 · 第 {{ activeDimensionIndex + 1 }} / {{ quickChoiceGroups.length }} 维</div>
            <h1>{{ activeDimension.label }}</h1>
            <p>{{ activeDimension.hint }}。选择完成后会自动进入下一个维度，最后统一生成学习画像。</p>
          </div>
          <div class="selection-pill">
            本维已选 {{ activeDimensionSelections.length }} 项
          </div>
        </div>

        <div class="wizard-progress">
          <div class="wizard-progress-line">
            <span :style="{ width: wizardProgressPercent + '%' }"></span>
          </div>
          <div class="wizard-step-row">
            <button
              v-for="(group, index) in quickChoiceGroups"
              :key="group.key"
              type="button"
              class="wizard-step"
              :class="{ active: index === activeDimensionIndex, done: selectedQuickCountFor(group.key) > 0 }"
              :style="{ '--group-accent': group.accent }"
              :disabled="loading"
              @click="goToDimension(index)">
              <span>{{ index + 1 }}</span>
              <strong>{{ group.label }}</strong>
            </button>
          </div>
        </div>

        <article class="single-dimension-card" :style="{ '--group-accent': activeDimension.accent }">
          <div class="single-dimension-head">
            <div class="dimension-mark">{{ activeDimensionIndex + 1 }}</div>
            <div>
              <strong>{{ activeDimension.label }}</strong>
              <span>{{ activeDimension.hint }}</span>
            </div>
            <em>{{ activeDimensionSelections.length ? `已选 ${activeDimensionSelections.length}` : '待选择' }}</em>
          </div>

          <div class="quick-option-list single">
            <button
              v-for="option in activeDimension.options"
              :key="option"
              type="button"
              class="quick-option-chip"
              :class="{ active: isQuickChoiceSelected(activeDimension.key, option) }"
              :disabled="loading"
              @click="toggleQuickChoice(activeDimension.key, option)">
              {{ option }}
            </button>
          </div>
        </article>

        <div class="capture-actions">
          <button
            class="ghost-action"
            @click="previousDimension"
            :disabled="loading || activeDimensionIndex === 0">
            上一维度
          </button>
          <button
            class="ghost-action"
            @click="clearQuickChoices"
            :disabled="loading || !selectedQuickChoiceCount">
            重选
          </button>
          <button
            class="primary-action"
            @click="continueDimensionFlow"
            :disabled="loading || !activeDimensionHasSelection">
            {{ loading ? '生成中...' : isLastDimension ? '生成学习画像' : '下一维度' }}
          </button>
        </div>
      </section>

      <aside class="profile-side-panel">
        <section v-if="status" class="side-section handoff-strip">
          <div class="side-title-row">
            <div>
              <div class="panel-kicker-text">画像智能体联动</div>
              <strong>{{ canFinish ? '已达到系统接入条件' : `完成 ${minRequiredDimensions} 个维度后接入系统功能` }}</strong>
            </div>
          </div>
          <div class="handoff-agent-list">
            <span v-for="agent in connectedAgents" :key="agent.name">{{ agent.name }}</span>
          </div>
        </section>

        <section class="side-section">
          <div class="side-title-row">
            <div>
              <div class="panel-kicker-text">画像生成进度</div>
              <strong>完成 6 个维度后生成学习画像</strong>
            </div>
            <span>{{ selectedQuickDimensionCount }}/{{ quickChoiceGroups.length }}</span>
          </div>

          <div class="wizard-summary-list">
            <button
              v-for="(group, index) in quickChoiceGroups"
              :key="group.key"
              type="button"
              class="wizard-summary-row"
              :class="{ active: index === activeDimensionIndex, filled: selectedQuickCountFor(group.key) > 0 || Boolean(profileRecords[group.key]) }"
              :style="{ '--group-accent': group.accent }"
              :disabled="loading"
              @click="goToDimension(index)">
              <div>
                <strong>{{ group.label }}</strong>
                <p>{{ (selectedQuickChoices[group.key] || []).join('、') || profileRecords[group.key] || '等待填写该维度' }}</p>
              </div>
              <span>{{ selectedQuickCountFor(group.key) || (profileRecords[group.key] ? 1 : 0) }}</span>
            </button>
          </div>
        </section>

        <section v-if="recordedCount > 0" class="side-section compact-record-section">
          <div class="side-title-row">
            <div>
              <div class="panel-kicker-text">已生成记录</div>
              <strong>已提交到系统画像中的信息</strong>
            </div>
            <span>{{ recordedCount }}/{{ totalDimensions }}</span>
          </div>
          <div class="record-list compact">
            <article v-for="item in recordedItems.filter((record) => record.value)" :key="item.key" class="record-row filled">
              <div>
                <strong>{{ item.label }}</strong>
                <p>{{ item.value }}</p>
              </div>
              <button @click="deleteRecord(item.key, item.label)"
                :disabled="Boolean(deletingDimension)"
                :title="`删除${item.label}记录`"
                aria-label="删除画像记录"
                class="delete-record-button">
                <el-icon :size="13"><Delete /></el-icon>
              </button>
            </article>
          </div>
        </section>

        <section class="side-section assistant-section">
          <div class="side-title-row">
            <div>
              <div class="panel-kicker-text">AI 助手</div>
              <strong>只用于补充说明和追问缺口</strong>
            </div>
          </div>

          <div id="chat-messages" class="assistant-thread">
            <div v-if="messages.length === 0 && loading" class="assistant-muted">正在准备补充问题...</div>
            <div v-for="(msg, i) in messages" :key="i" class="assistant-message" :class="msg.role">
              <span>{{ msg.role === 'user' ? '你补充' : 'AI 补充' }}</span>
              <p>{{ msg.text }}</p>
            </div>
            <div v-if="loading && messages.length > 0" class="assistant-muted">AI 正在分析补充内容...</div>
          </div>

          <div class="assistant-input-row">
            <input v-model="inputText" @keydown.enter="sendMessage" :disabled="loading"
              placeholder="有选项没覆盖的内容，再写在这里"
              class="assistant-input" />
            <button @click="sendMessage" :disabled="loading || !inputText.trim()" class="assistant-send">
              {{ loading ? '...' : '发送' }}
            </button>
          </div>
        </section>
      </aside>
    </main>
  </div>
</template>

<style scoped>
.profile-setup-main {
  flex: 1;
  width: min(1380px, calc(100% - 40px));
  margin: 14px auto 22px;
  display: grid;
  grid-template-columns: minmax(640px, 1fr) minmax(330px, 0.46fr);
  gap: 18px;
  align-items: stretch;
  min-height: 0;
}

.profile-capture-panel,
.side-section,
.handoff-strip {
  border: 1px solid color-mix(in srgb, var(--accent) 18%, var(--line));
  border-radius: 8px;
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 9%, transparent), transparent 34%),
    linear-gradient(180deg, color-mix(in srgb, var(--panel-strong) 94%, transparent), color-mix(in srgb, var(--panel) 88%, transparent));
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.22);
}

.profile-capture-panel {
  grid-column: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 18px;
}

.handoff-strip {
  padding-bottom: 15px;
}

.handoff-agent-list {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.handoff-agent-list span {
  padding: 7px 9px;
  border: 1px solid color-mix(in srgb, var(--accent) 14%, var(--line));
  border-radius: 8px;
  background: color-mix(in srgb, var(--text) 3%, transparent);
  color: color-mix(in srgb, var(--text) 82%, var(--muted));
  font-size: 11px;
  line-height: 1.35;
}

.panel-heading-line,
.side-title-row,
.capture-actions,
.assistant-input-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-kicker-text {
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.3;
}

.panel-heading-line h1 {
  margin: 0;
  color: var(--text);
  font-size: 22px;
  line-height: 1.25;
  letter-spacing: 0;
}

.panel-heading-line p {
  max-width: 680px;
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.65;
}

.selection-pill {
  flex: 0 0 auto;
  padding: 9px 13px;
  border: 1px solid color-mix(in srgb, var(--accent) 38%, var(--line));
  border-radius: 999px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 11%, transparent);
  font-size: 12px;
  font-weight: 750;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 10%, transparent);
}

.single-dimension-card {
  --group-accent: var(--accent);
  position: relative;
  overflow: hidden;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  margin-top: 16px;
  padding: 20px;
  border: 1px solid color-mix(in srgb, var(--group-accent) 18%, var(--line));
  border-radius: 8px;
  background:
    radial-gradient(circle at 84% 18%, color-mix(in srgb, var(--group-accent) 16%, transparent), transparent 30%),
    linear-gradient(180deg, color-mix(in srgb, var(--text) 4%, transparent), color-mix(in srgb, var(--text) 2%, transparent)),
    color-mix(in srgb, var(--group-accent) 4%, transparent);
}

.single-dimension-card::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: linear-gradient(180deg, var(--group-accent), transparent);
  opacity: 0.95;
}

.single-dimension-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.dimension-mark {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: #f8fbff;
  background: color-mix(in srgb, var(--group-accent) 74%, #111827);
  font-size: 12px;
  font-weight: 850;
  box-shadow: 0 8px 18px color-mix(in srgb, var(--group-accent) 18%, transparent);
}

.single-dimension-head strong {
  display: block;
  color: var(--text);
  font-size: 18px;
  line-height: 1.35;
}

.single-dimension-head span {
  display: block;
  margin-top: 5px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}

.single-dimension-head em {
  flex: 0 0 auto;
  padding: 6px 10px;
  border-radius: 999px;
  color: color-mix(in srgb, var(--group-accent) 76%, #e5eef8);
  background: color-mix(in srgb, var(--group-accent) 10%, transparent);
  font-size: 12px;
  font-style: normal;
  font-weight: 750;
}

.wizard-progress {
  margin-top: 14px;
  display: grid;
  gap: 10px;
}

.wizard-progress-line {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 14%, transparent);
}

.wizard-progress-line span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--accent), var(--accent-deep));
  transition: width 0.24s ease;
}

.wizard-step-row {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}

.wizard-step {
  --group-accent: var(--accent);
  min-width: 0;
  display: grid;
  gap: 6px;
  justify-items: center;
  padding: 8px 6px;
  border: 1px solid color-mix(in srgb, var(--muted) 16%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--text) 3%, transparent);
  color: var(--muted);
  cursor: pointer;
  font-family: inherit;
}

.wizard-step span {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg) 70%, transparent);
  color: inherit;
  font-size: 12px;
  font-weight: 850;
}

.wizard-step strong {
  max-width: 100%;
  overflow: hidden;
  color: inherit;
  font-size: 11px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wizard-step.active {
  border-color: color-mix(in srgb, var(--group-accent) 54%, var(--line));
  color: #f8fbff;
  background: color-mix(in srgb, var(--group-accent) 14%, transparent);
}

.wizard-step.done span,
.wizard-step.active span {
  color: #f8fbff;
  background: color-mix(in srgb, var(--group-accent) 76%, #111827);
}

.quick-option-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.quick-option-list.single {
  flex: 1;
  align-content: start;
  margin-top: 4px;
}

.quick-option-chip {
  min-height: 42px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--muted) 20%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg) 66%, transparent);
  color: color-mix(in srgb, var(--text) 74%, var(--muted));
  cursor: pointer;
  font-size: 13px;
  line-height: 1.35;
  text-align: left;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
  transition:
    border-color 0.16s ease,
    background 0.16s ease,
    color 0.16s ease,
    transform 0.16s ease;
}

.quick-option-chip:hover {
  border-color: color-mix(in srgb, var(--group-accent) 50%, var(--line));
  color: var(--text);
  transform: translateY(-1px);
}

.quick-option-chip.active {
  border-color: color-mix(in srgb, var(--group-accent) 76%, var(--line));
  background: color-mix(in srgb, var(--group-accent) 20%, transparent);
  color: #eafffb;
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--group-accent) 20%, transparent),
    0 8px 18px color-mix(in srgb, var(--group-accent) 10%, transparent);
}

.quick-option-chip:disabled,
.ghost-action:disabled,
.primary-action:disabled,
.assistant-send:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.capture-actions {
  justify-content: flex-end;
  margin-top: 14px;
}

.ghost-action,
.primary-action,
.assistant-send {
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  font-weight: 750;
}

.ghost-action {
  padding: 10px 14px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text);
}

.primary-action {
  padding: 10px 18px;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  color: #fff;
}

.profile-side-panel {
  grid-column: 2;
  position: sticky;
  top: 14px;
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  gap: 12px;
  align-self: stretch;
  height: 100%;
  min-height: 0;
}

.side-section {
  padding: 15px;
}

.side-title-row {
  align-items: flex-start;
  margin-bottom: 12px;
}

.side-title-row strong {
  color: var(--text);
  font-size: 14px;
  line-height: 1.45;
}

.side-title-row span {
  flex: 0 0 auto;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
}

.record-list {
  display: grid;
  gap: 8px;
}

.record-list.compact {
  max-height: 190px;
  overflow-y: auto;
  padding-right: 4px;
}

.compact-record-section {
  max-height: 290px;
  overflow: hidden;
}

.wizard-summary-list {
  display: grid;
  gap: 8px;
}

.wizard-summary-row {
  --group-accent: var(--accent);
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid color-mix(in srgb, var(--muted) 12%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--text) 2.5%, transparent);
  color: inherit;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
}

.wizard-summary-row.active {
  border-color: color-mix(in srgb, var(--group-accent) 46%, var(--line));
  background: color-mix(in srgb, var(--group-accent) 9%, transparent);
}

.wizard-summary-row.filled {
  border-color: color-mix(in srgb, var(--group-accent) 30%, var(--line));
}

.wizard-summary-row strong {
  display: block;
  color: var(--text);
  font-size: 12px;
}

.wizard-summary-row p {
  margin: 5px 0 0;
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wizard-summary-row span {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  color: color-mix(in srgb, var(--group-accent) 76%, #e5eef8);
  background: color-mix(in srgb, var(--group-accent) 10%, transparent);
  font-size: 12px;
  font-weight: 850;
}

.record-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 52px;
  padding: 10px 11px;
  border: 1px solid color-mix(in srgb, var(--muted) 12%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--text) 2.5%, transparent);
}

.record-row.filled {
  background: color-mix(in srgb, var(--accent) 7%, transparent);
  border-color: color-mix(in srgb, var(--accent) 22%, var(--line));
}

.record-row strong {
  display: block;
  color: var(--text);
  font-size: 12px;
  line-height: 1.35;
}

.record-row p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
}

.delete-record-button {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: color-mix(in srgb, var(--text) 4%, transparent);
  color: var(--muted);
  cursor: pointer;
}

.assistant-section {
  grid-row: -2 / -1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.assistant-thread {
  flex: 1;
  min-height: 190px;
  max-height: none;
  overflow-y: auto;
  display: grid;
  align-content: start;
  gap: 10px;
  padding-right: 4px;
}

.assistant-message {
  padding: 10px 12px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--text) 3%, transparent);
  border: 1px solid color-mix(in srgb, var(--muted) 12%, transparent);
}

.assistant-message.user {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border-color: color-mix(in srgb, var(--accent) 24%, var(--line));
}

.assistant-message span,
.assistant-muted {
  color: var(--muted);
  font-size: 11px;
  font-weight: 750;
}

.assistant-message p {
  margin: 5px 0 0;
  color: var(--text);
  font-size: 12px;
  line-height: 1.65;
}

.assistant-input-row {
  align-items: stretch;
}

.assistant-input {
  min-width: 0;
  flex: 1;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  outline: none;
  background: color-mix(in srgb, var(--bg) 84%, transparent);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}

.assistant-send {
  width: 64px;
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
}

@media (max-width: 1180px) {
  .profile-setup-main {
    grid-template-columns: minmax(560px, 1fr) minmax(300px, 0.5fr);
  }

  .profile-capture-panel {
    grid-column: 1;
  }

  .profile-side-panel {
    grid-column: 2;
  }
}

@media (max-width: 860px) {
  .profile-setup-main {
    width: calc(100% - 28px);
    grid-template-columns: 1fr;
  }

  .profile-capture-panel,
  .profile-side-panel {
    grid-column: auto;
  }

  .profile-side-panel {
    position: static;
    height: auto;
  }
}

@media (max-width: 640px) {
  .profile-setup-main {
    margin-top: 14px;
  }

  .quick-option-list,
  .wizard-step-row {
    grid-template-columns: 1fr;
  }

  .panel-heading-line,
  .capture-actions,
  .assistant-input-row {
    align-items: stretch;
    flex-direction: column;
  }

  .selection-pill,
  .primary-action,
  .ghost-action,
  .assistant-send {
    width: 100%;
  }
}
</style>
