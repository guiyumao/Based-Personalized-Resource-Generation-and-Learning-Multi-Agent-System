<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { evaluationApi, userApi, type ApiEnvelope, type LearnerProfileDashboard, type ReportDetail } from '../../api'

const authStore = useAuthStore()
const user = authStore.user!

const services = reactive({
  user: { online: false, checking: true },
  agent: { online: false, checking: true },
  evaluation: { online: false, checking: true },
})

async function checkHealth(port: number, key: keyof typeof services) {
  try { const resp = await fetch(`http://127.0.0.1:${port}/health`); const data = await resp.json(); services[key] = { online: data.status === 'ok', checking: false } }
  catch { services[key] = { online: false, checking: false } }
}

const dashboard = ref<LearnerProfileDashboard | null>(null)
const dashError = ref('')

async function fetchDashboard() {
  dashError.value = ''
  try { const { data } = await userApi.get<LearnerProfileDashboard>(`/users/${user.userId}/profile/dashboard`); dashboard.value = data }
  catch (error: any) { const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'; dashError.value = `画像加载失败：${detail}` }
}

const masteryPct = computed(() => {
  const m = dashboard.value?.radar_metrics?.reduce((s, r) => s + r.score, 0) ?? 0
  const c = dashboard.value?.radar_metrics?.length ?? 1
  return Math.round((m / (c * 100)) * 100)
})

const recentActivity = ref<{ text: string; time: string; color: string }[]>([])

async function fetchRecentActivity() {
  try {
    const { data } = await evaluationApi.get<ApiEnvelope<ReportDetail>>(`/evaluation/reports/comprehensive/${user.userId}/detail`)
    const report = (data as any).data ?? data
    recentActivity.value = report ? [
      { text: `综合正确率：${report.evidence?.accuracy ?? '?'}%`, time: '最新报告', color: 'var(--green)' },
      { text: `已完成 ${report.evidence?.total_answers ?? 0} 道练习`, time: '累计统计', color: 'var(--accent-deep)' },
    ] : []
  } catch { recentActivity.value = [] }
}

onMounted(() => {
  checkHealth(8001, 'user'); checkHealth(8002, 'agent'); checkHealth(8004, 'evaluation')
  fetchDashboard(); fetchRecentActivity()
})
</script>

<template>
  <div>
    <div class="welcome-section" style="margin-bottom:20px">
      <h2 style="font-size:26px;font-weight:750">欢迎回来，<span style="background:linear-gradient(135deg,var(--text),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">{{ user.username }}</span></h2>
      <p style="color:var(--muted)">以下是您的学习概览</p>
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px">
      <span v-for="(s,key) in services" :key="key" style="display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:999px;font-size:13px;background:var(--panel);border:1px solid var(--line)">
        <span style="width:8px;height:8px;border-radius:50%;display:inline-block" :style="{background:s.checking?'var(--muted)':s.online?'var(--green)':'var(--red)'}"></span>{{ key }}-service
      </span>
    </div>

    <div v-if="dashError" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:16px;font-size:14px">{{ dashError }}</div>

    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px">
      <div v-for="card in [{label:'学习风格',value:dashboard?.learning_style??'...',icon:'🧠'},{label:'掌握度',value:masteryPct+'%',icon:'🎯'},{label:'本周专注',value:(dashboard?.weekly_focus_minutes??0)+'分钟',icon:'⏱️'},{label:'综合评分',value:(dashboard?.mastery_overview??'?')+'%',icon:'📊'}]" :key="card.label"
        style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line);position:relative;overflow:hidden">
        <div style="position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--accent),var(--accent-deep))"></div>
        <div style="font-size:24px;margin-bottom:10px">{{ card.icon }}</div>
        <div style="font-size:12px;letter-spacing:.06em;color:var(--muted);text-transform:uppercase">{{ card.label }}</div>
        <div style="font-size:28px;font-weight:750;margin-top:6px">{{ card.value }}</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1.3fr 1fr;gap:20px">
      <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
        <h3 style="margin-bottom:14px">📋 最近活动</h3>
        <div v-if="recentActivity.length">
          <div v-for="(act,i) in recentActivity" :key="i" style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--line)">
            <span style="width:8px;height:8px;border-radius:50%;flex-shrink:0" :style="{background:act.color}"></span>
            <div style="flex:1"><div style="font-size:14px">{{ act.text }}</div><div style="font-size:11px;color:var(--muted)">{{ act.time }}</div></div>
          </div>
        </div>
        <div v-else style="text-align:center;padding:20px;color:var(--muted)">暂无活动数据</div>
      </div>
      <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
        <h3 style="margin-bottom:14px">📊 掌握度雷达</h3>
        <div v-if="dashboard?.radar_metrics?.length">
          <div v-for="m in dashboard.radar_metrics" :key="m.dimension" style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
            <span style="width:80px;font-size:12px;color:var(--muted);text-align:right;flex-shrink:0">{{ m.dimension }}</span>
            <div style="flex:1;height:8px;border-radius:4px;background:color-mix(in srgb,var(--muted) 15%,transparent);overflow:hidden"><div :style="{width:m.score+'%',height:'100%',background:'linear-gradient(90deg,var(--accent),var(--accent-deep))',borderRadius:'4px'}"></div></div>
            <span style="width:36px;font-size:12px;font-weight:600;color:var(--accent);text-align:right">{{ m.score }}%</span>
          </div>
        </div>
        <div v-else style="text-align:center;padding:20px;color:var(--muted)">暂无数据，完成练习后将自动生成</div>
      </div>
    </div>
  </div>
</template>
