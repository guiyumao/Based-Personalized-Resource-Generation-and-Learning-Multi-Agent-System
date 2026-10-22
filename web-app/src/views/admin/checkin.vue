<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { teacherApi, type AdminCheckinOverview, type ApiEnvelope } from '../../api'

const loading = ref(false)
const overview = ref<AdminCheckinOverview | null>(null)
const audits = ref<Array<Record<string, any>>>([])
const loadError = ref('')

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function summarize(value: unknown) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    const [overviewRes, auditRes] = await Promise.all([
      teacherApi.get<ApiEnvelope<AdminCheckinOverview>>('/learning/checkin/admin/overview'),
      teacherApi.get<ApiEnvelope<Array<Record<string, any>>>>('/learning/checkin/admin/audits'),
    ])
    overview.value = overviewRes.data.data
    audits.value = auditRes.data.data
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || '打卡审计数据加载失败'
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="admin-checkin" v-loading="loading">
    <header class="admin-hero">
      <div>
        <span class="eyebrow">CHECK-IN GOVERNANCE</span>
        <h1>打卡与签到审计</h1>
        <p>查看全校打卡任务、提交与出勤汇总，并审计教师的人工出勤调整与任务状态变更。管理员只读，不直接干预正常师生流程。</p>
      </div>
      <el-button @click="refresh">刷新</el-button>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false">
      <el-button @click="refresh">重试</el-button>
    </el-alert>

    <section class="kpi-grid">
      <article><span>打卡任务</span><strong>{{ overview?.task_count ?? 0 }}</strong><small>进行中 {{ overview?.published_task_count ?? 0 }}</small></article>
      <article><span>学生提交</span><strong>{{ overview?.submission_count ?? 0 }}</strong><small>待审核 {{ overview?.pending_review_count ?? 0 }}</small></article>
      <article><span>课堂签到活动</span><strong>{{ overview?.attendance_session_count ?? 0 }}</strong><small>出勤记录 {{ overview?.attendance_record_count ?? 0 }}</small></article>
      <article><span>平台学习打卡</span><strong>{{ overview?.self_checkin_count ?? 0 }}</strong><small>学生每日平台打卡</small></article>
    </section>

    <article class="panel">
      <div class="panel-title"><div><span class="eyebrow">AUDIT</span><h2>最近操作审计</h2></div></div>
      <el-table :data="audits" stripe empty-text="暂无打卡相关审计记录">
        <el-table-column label="时间" width="170"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column prop="action" label="操作" width="180" />
        <el-table-column label="对象" width="170"><template #default="{ row }">{{ row.target_type }} #{{ row.target_id }}</template></el-table-column>
        <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
        <el-table-column label="执行账号" width="110"><template #default="{ row }">{{ row.actor_user_id ?? '系统' }}</template></el-table-column>
        <el-table-column label="变更前" min-width="160" show-overflow-tooltip><template #default="{ row }">{{ summarize(row.before) }}</template></el-table-column>
        <el-table-column label="变更后" min-width="160" show-overflow-tooltip><template #default="{ row }">{{ summarize(row.after) }}</template></el-table-column>
      </el-table>
    </article>
  </div>
</template>

<style scoped>
.admin-checkin{display:grid;gap:20px}
.admin-hero{display:flex;justify-content:space-between;flex-wrap:wrap;gap:18px;padding:28px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel)),var(--panel));box-shadow:var(--shadow-sm)}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}
h1,h2,p{margin:0}
h1{font-size:28px;margin:5px 0 8px}
.admin-hero p{color:var(--muted);line-height:1.7;max-width:820px}
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.kpi-grid article{padding:16px;border:1px solid var(--line);border-radius:16px;background:var(--panel);box-shadow:var(--shadow-sm);display:grid;gap:4px}
.kpi-grid span{font-size:12px;color:var(--muted)}
.kpi-grid strong{font-size:24px}
.kpi-grid small{color:var(--muted)}
.panel{padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--panel);display:grid;gap:14px}
.panel-title h2{font-size:18px;margin-top:4px}
@media (max-width: 900px){.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
