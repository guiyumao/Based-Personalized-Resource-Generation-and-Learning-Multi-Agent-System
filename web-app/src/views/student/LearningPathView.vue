<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  agentApi,
  type LearningPathPayload,
  type LearningPathResponse,
  type ResourcePayload,
  type ResourceResult,
} from '../../api'

const authStore = useAuthStore()
const user = authStore.user!

const pathForm = reactive<LearningPathPayload>({
  user_id: user.userId, subject: '', knowledge_point: '', daily_minutes: 45,
  learner_profile: {},
})

const learningPath = ref<LearningPathResponse | null>(null)
const activeTaskId = ref('')
const loading = ref(false)
const pathError = ref('')
const coordination = ref<{ agents: string[]; plan_summary?: string } | null>(null)

const COURSEWARE_STORAGE_KEY = 'student-workspace-courseware'

// ── Load existing path on mount ──
onMounted(async () => {
  try {
    const { data } = await agentApi.get<LearningPathResponse>(`/paths/${user.userId}`)
    if (data && data.stages?.length) {
      learningPath.value = data
      activeTaskId.value = data.stages[0]?.tasks[0]?.task_id ?? ''
    }
  } catch { /* no existing path */ }
})

// ── Generate path (with coordination) ──
async function generateLearningPath() {
  if (!pathForm.knowledge_point.trim()) { ElMessage.warning('请先输入学习主题'); return }
  loading.value = true; pathError.value = ''; coordination.value = null
  try {
    pathForm.user_id = user.userId
    // Step 1: Coordinate with agents
    try {
      const coordRes = await agentApi.post('/agents/coordinate', {
        user_id: user.userId,
        intent: `围绕 ${pathForm.subject} 中的"${pathForm.knowledge_point}"生成个性化学习路径`,
        knowledge_point: pathForm.knowledge_point,
      })
      coordination.value = (coordRes.data as any).data ?? coordRes.data
    } catch { /* coordination is optional */ }

    // Step 2: Generate path
    const { data } = await agentApi.post<LearningPathResponse>('/paths/generate', pathForm)
    learningPath.value = data
    activeTaskId.value = data.stages[0]?.tasks[0]?.task_id ?? ''
    await generateCoursewareSnapshot()
    ElMessage.success('学习路径和课件已生成')
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    pathError.value = `请求失败：${detail}`
    ElMessage.error(pathError.value)
  } finally {
    loading.value = false
  }
}

async function generateCoursewareSnapshot() {
  const payload: ResourcePayload = {
    user_id: user.userId,
    knowledge_point: pathForm.knowledge_point,
    resource_style: 'interactive',
    resource_type: 'courseware',
    learner_profile: pathForm.learner_profile,
    request_text: `围绕 ${pathForm.subject || '当前学科'} 的 ${pathForm.knowledge_point} 生成可独立阅读的正式课件`,
  }
  const { data } = await agentApi.post<ResourceResult>('/resources/generate', payload)
  const resourceResult = (data as any).data ?? data
  const selectedVariantId =
    resourceResult.variants?.find((item: any) => item.is_recommended)?.variant_id
    ?? resourceResult.variants?.[0]?.variant_id
    ?? ''

  window.sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify({
    subject: pathForm.subject,
    topic: pathForm.knowledge_point,
    goal: learningPath.value?.overview ?? '',
    selectedVariantId,
    generatedAt: Date.now(),
    resourceResult,
  }))
}

// ── Adjust task state ──
async function adjustTask(taskId: string, action: 'complete' | 'skip') {
  try {
    await agentApi.post('/paths/adjust', { user_id: user.userId, task_id: taskId, action })
    // Optimistic update
    if (learningPath.value) {
      for (const stage of learningPath.value.stages) {
        for (const task of stage.tasks) {
          if (task.task_id === taskId) {
            task.completed = action === 'complete'
            break
          }
        }
      }
    }
    ElMessage.success(action === 'complete' ? '任务已标记完成' : '任务已跳过')
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? ''
    ElMessage.error(`操作失败：${detail}`)
  }
}

const completedStages = computed(() => learningPath.value?.stages.filter(s => s.tasks.every(t => t.completed)).length ?? 0)
const totalStages = computed(() => learningPath.value?.stages.length ?? 0)
const progressPct = computed(() => totalStages.value > 0 ? Math.round((completedStages.value / totalStages.value) * 100) : 0)
</script>

<template>
  <div>
    <div style="margin-bottom:24px"><h2 style="font-size:24px;font-weight:750">🗺️ 学习路径</h2><p style="color:var(--muted);font-size:14px">AI 为您生成的个性化学习路径</p></div>

    <div style="display:grid;grid-template-columns:1.3fr 1fr;gap:20px">
      <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
          <input v-model="pathForm.subject" placeholder="学科" style="width:120px;padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:14px;outline:none;font-family:inherit" />
          <input v-model="pathForm.knowledge_point" placeholder="知识点/主题" style="flex:1;min-width:160px;padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:14px;outline:none;font-family:inherit" />
          <button :disabled="loading" @click="generateLearningPath"
            style="padding:10px 20px;border-radius:12px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;cursor:pointer;font-weight:600;font-family:inherit;white-space:nowrap">
            {{ loading ? '生成中...' : '生成路径' }}
          </button>
        </div>

        <div v-if="pathError" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:12px;font-size:14px">{{ pathError }}</div>

        <div v-if="learningPath" style="position:relative;padding-left:24px">
          <div style="position:absolute;left:7px;top:8px;bottom:8px;width:2px;background:linear-gradient(180deg,var(--accent),var(--accent-deep),transparent);border-radius:1px"></div>
          <div v-for="stage in learningPath.stages" :key="stage.stage_id" style="position:relative;padding:6px 0 6px 24px">
            <div :style="{position:'absolute',left:'-21px',top:'16px',width:'14px',height:'14px',borderRadius:'50%',border:'3px solid var(--accent)',background:stage.tasks.every(t=>t.completed)?'var(--accent)':'var(--bg)'}"></div>
            <div style="padding:16px;border-radius:14px;background:color-mix(in srgb,var(--accent) 4%,transparent);border:1px solid var(--line)">
              <h4 style="margin:0 0 4px">{{ stage.title }}</h4>
              <p style="margin:0;font-size:13px;color:var(--muted)">{{ stage.description }}</p>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center">
                <span v-for="t in stage.tasks" :key="t.task_id" style="padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600"
                  :style="t.completed?{background:'color-mix(in srgb,var(--green) 14%,transparent)',color:'var(--green)'}:{background:'color-mix(in srgb,var(--accent) 10%,transparent)',color:'var(--accent)'}">
                  {{ t.completed ? '✓' : '○' }} {{ t.title }}
                </span>
                <!-- Task action buttons -->
                <span v-for="t in stage.tasks" :key="'btn-'+t.task_id" style="display:inline-flex;gap:4px;margin-left:4px">
                  <button v-if="!t.completed" @click="adjustTask(t.task_id, 'complete')"
                    style="width:20px;height:20px;border-radius:50%;border:1px solid var(--green);background:transparent;color:var(--green);cursor:pointer;font-size:11px;line-height:1;padding:0" title="标记完成">✓</button>
                  <button v-if="t.completed" @click="adjustTask(t.task_id, 'skip')"
                    style="width:20px;height:20px;border-radius:50%;border:1px solid var(--muted);background:transparent;color:var(--muted);cursor:pointer;font-size:11px;line-height:1;padding:0" title="取消完成">↩</button>
                </span>
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="!pathError && !learningPath" style="text-align:center;padding:40px;color:var(--muted)">输入学科和知识点，点击"生成路径"开始</div>
      </div>

      <div style="display:grid;gap:16px;align-content:start">
        <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
          <h3 style="margin:0 0 14px">📊 路径统计</h3>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px"><span style="color:var(--muted)">总体进度</span><span style="font-weight:700;color:var(--accent)">{{ progressPct }}%</span></div>
          <div style="height:6px;border-radius:3px;background:color-mix(in srgb,var(--muted) 15%,transparent);overflow:hidden"><div :style="{width:progressPct+'%',height:'100%',background:'linear-gradient(90deg,var(--accent),var(--accent-deep))',borderRadius:'3px'}"></div></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px">
            <div style="text-align:center;padding:16px;border-radius:14px;background:color-mix(in srgb,var(--accent) 5%,transparent);border:1px solid var(--line)"><div style="font-size:28px;font-weight:700;color:var(--accent)">{{ completedStages }}</div><div style="font-size:11px;color:var(--muted)">已完成阶段</div></div>
            <div style="text-align:center;padding:16px;border-radius:14px;background:color-mix(in srgb,var(--accent) 5%,transparent);border:1px solid var(--line)"><div style="font-size:28px;font-weight:700;color:var(--accent-deep)">{{ totalStages - completedStages }}</div><div style="font-size:11px;color:var(--muted)">剩余阶段</div></div>
          </div>
        </div>

        <!-- Coordination result -->
        <div v-if="coordination" style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
          <h3 style="margin:0 0 10px">🤖 Agent 协调结果</h3>
          <div v-if="coordination.agents?.length" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
            <span v-for="a in coordination.agents" :key="a" style="padding:4px 10px;border-radius:999px;font-size:11px;font-weight:600;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent)">{{ a }}</span>
          </div>
          <p v-if="coordination.plan_summary" style="font-size:13px;color:var(--muted);line-height:1.6">{{ coordination.plan_summary }}</p>
        </div>
      </div>
    </div>
  </div>
</template>
