<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { evaluationApi, type ApiEnvelope, type ReportDetail } from '../../api'

const authStore = useAuthStore()
const user = authStore.user!

const stageReport = ref<ReportDetail | null>(null)
const comprehensiveReport = ref<ReportDetail | null>(null)
const loading = ref(false)
const reportError = ref('')

async function fetchReports() {
  loading.value = true; reportError.value = ''
  try {
    const [stageRes, compRes] = await Promise.all([
      evaluationApi.get<ApiEnvelope<ReportDetail>>(`/evaluation/reports/stage/${user.userId}/detail`),
      evaluationApi.get<ApiEnvelope<ReportDetail>>(`/evaluation/reports/comprehensive/${user.userId}/detail`),
    ])
    stageReport.value = (stageRes.data as any).data ?? stageRes.data
    comprehensiveReport.value = (compRes.data as any).data ?? compRes.data
    ElMessage.success('学习报告已刷新')
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    reportError.value = `加载失败：${detail}`
    ElMessage.error(reportError.value)
  } finally {
    loading.value = false
  }
}

onMounted(() => { fetchReports() })
</script>

<template>
  <div>
    <div style="margin-bottom:24px;display:flex;justify-content:space-between;align-items:center">
      <div><h2 style="font-size:24px;font-weight:750">📈 学习报告</h2><p style="color:var(--muted);font-size:14px">阶段性学习分析与诊断</p></div>
      <button :disabled="loading" @click="fetchReports" style="padding:10px 20px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--text);cursor:pointer;font-weight:600;font-family:inherit">{{ loading ? '刷新中...' : '刷新报告' }}</button>
    </div>

    <div v-if="reportError" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:16px;font-size:14px">{{ reportError }}</div>

    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:20px">
      <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
        <h3 style="margin-bottom:14px">📋 阶段报告</h3>
        <div v-if="stageReport">
          <div style="display:flex;gap:24px;margin-bottom:16px">
            <div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--accent)">{{ stageReport.evidence.accuracy }}%</div><div style="font-size:11px;color:var(--muted)">正确率</div></div>
            <div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--accent)">{{ stageReport.evidence.total_answers }}</div><div style="font-size:11px;color:var(--muted)">总题数</div></div>
          </div>
          <p style="font-size:14px;color:var(--muted);line-height:1.7;margin-bottom:12px">{{ stageReport.summary }}</p>
          <div v-if="stageReport.strengths?.length"><span v-for="s in stageReport.strengths" :key="s" style="display:inline-block;padding:4px 10px;margin:2px;border-radius:999px;font-size:11px;background:color-mix(in srgb,var(--green) 8%,transparent);color:var(--green)">{{ s }}</span></div>
          <div v-if="stageReport.weaknesses?.length" style="margin-top:8px"><span v-for="w in stageReport.weaknesses" :key="w" style="display:inline-block;padding:4px 10px;margin:2px;border-radius:999px;font-size:11px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red)">{{ w }}</span></div>
        </div>
        <div v-else style="text-align:center;padding:40px;color:var(--muted)">暂无数据，点击刷新加载</div>
      </div>
      <div style="padding:22px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
        <h3 style="margin-bottom:14px">📊 综合报告</h3>
        <div v-if="comprehensiveReport">
          <div style="display:flex;gap:24px;margin-bottom:16px">
            <div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--accent)">{{ comprehensiveReport.evidence.accuracy }}%</div><div style="font-size:11px;color:var(--muted)">综合正确率</div></div>
            <div style="text-align:center"><div style="font-size:28px;font-weight:700;color:var(--red)">{{ comprehensiveReport.evidence.mistake_count }}</div><div style="font-size:11px;color:var(--muted)">错题数</div></div>
          </div>
          <p style="font-size:14px;color:var(--muted);line-height:1.7;margin-bottom:12px">{{ comprehensiveReport.summary }}</p>
          <div v-if="comprehensiveReport.next_actions?.length">
            <span v-for="a in comprehensiveReport.next_actions" :key="a" style="display:inline-block;padding:4px 10px;margin:2px;border-radius:999px;font-size:11px;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent)">{{ a }}</span>
          </div>
        </div>
        <div v-else style="text-align:center;padding:40px;color:var(--muted)">暂无数据</div>
      </div>
    </div>
  </div>
</template>
