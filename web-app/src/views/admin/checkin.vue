<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search, DocumentChecked, Tickets, Calendar, DataLine } from '@element-plus/icons-vue'

import { teacherApi, type AdminCheckinOverview, type ApiEnvelope } from '../../api'

const loading = ref(false)
const overview = ref<AdminCheckinOverview | null>(null)
const audits = ref<Array<Record<string, any>>>([])
const loadError = ref('')
const selectedAudit = ref<Record<string, any> | null>(null)
const detailOpen = ref(false)

const filters = reactive({
  action: '',
  target_type: '',
  target_id: undefined as number | undefined,
  actor_user_id: undefined as number | undefined,
  keyword: '',
  range: null as [Date, Date] | null,
  limit: 200,
})

const applied = reactive({ ...filters })

const actionOptions = computed(() => {
  const names = new Set<string>()
  audits.value.forEach((row) => row.action && names.add(row.action))
  return Array.from(names).sort()
})

const targetTypeOptions = computed(() => {
  const names = new Set<string>()
  audits.value.forEach((row) => row.target_type && names.add(row.target_type))
  return Array.from(names).sort()
})

const DEFAULT_ACTION_NAMES = [
  'attendance.adjust',
  'attendance.close',
  'attendance.create',
  'attendance.update',
  'schedule.create',
  'schedule.reschedule',
  'schedule.update',
  'task.create',
  'task.publish',
  'task.published',
  'task.status_change',
  'task.update',
]

const actionChoices = computed(() => {
  const names = new Set<string>([...DEFAULT_ACTION_NAMES, ...actionOptions.value, applied.action].filter(Boolean) as string[])
  return Array.from(names).sort()
})

const targetTypeChoices = computed(() => {
  const names = new Set<string>(['checkin_task', 'attendance_session', 'class_session', 'checkin_submission', ...targetTypeOptions.value, applied.target_type].filter(Boolean) as string[])
  return Array.from(names).sort()
})

// ---- client-side pagination ----
const page = ref(1)
const pageSize = ref(20)
const pagedAudits = computed(() => {
  const startIdx = (page.value - 1) * pageSize.value
  return audits.value.slice(startIdx, startIdx + pageSize.value)
})

function buildParams() {
  const params: Record<string, any> = { limit: filters.limit }
  if (filters.action) params.action = filters.action
  if (filters.target_type) params.target_type = filters.target_type
  if (filters.target_id != null) params.target_id = filters.target_id
  if (filters.actor_user_id != null) params.actor_user_id = filters.actor_user_id
  if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
  if (filters.range && filters.range.length === 2) {
    params.start = filters.range[0]
    params.end = filters.range[1]
  }
  return params
}

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
  if (value === null || value === undefined) return ''
  if (typeof value === 'object' && Object.keys(value).length === 0) return ''
  if (typeof value === 'object') {
    const text = JSON.stringify(value)
    return text.length > 80 ? `${text.slice(0, 80)}…` : text
  }
  const text = String(value)
  return text.length > 80 ? `${text.slice(0, 80)}…` : text
}

/** 变更摘要：仅在有实际内容时展示，避免「无变更内容」刷屏 */
function changeLines(row: Record<string, any>) {
  const before = summarize(row.before)
  const after = summarize(row.after)
  const lines: Array<{ label: string; text: string; empty: boolean }> = []
  if (before) lines.push({ label: '前', text: before, empty: false })
  if (after) lines.push({ label: '后', text: after, empty: false })
  if (!lines.length) lines.push({ label: '—', text: '无字段变更', empty: true })
  return lines
}

async function loadAudits() {
  const auditRes = await teacherApi.get<ApiEnvelope<Array<Record<string, any>>>>(
    '/learning/checkin/admin/audits',
    { params: buildParams() },
  )
  audits.value = auditRes.data.data
  page.value = 1
}

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    const [overviewRes] = await Promise.all([
      teacherApi.get<ApiEnvelope<AdminCheckinOverview>>('/learning/checkin/admin/overview'),
      loadAudits(),
    ])
    overview.value = overviewRes.data.data
    Object.assign(applied, filters, { range: filters.range })
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || '打卡审计数据加载失败'
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function search() {
  await refresh()
  if (!loadError.value) {
    const total = audits.value.length
    if (total === 0) ElMessage.info('没有符合条件的审计记录')
    else ElMessage.success(`查询到 ${total} 条审计记录`)
  }
}

function resetFilters() {
  filters.action = ''
  filters.target_type = ''
  filters.target_id = undefined
  filters.actor_user_id = undefined
  filters.keyword = ''
  filters.range = null
  filters.limit = 200
  search()
}

/** 点击表格中的操作/对象单元格，快速按该条件查询 */
async function filterByAction(action: string) {
  filters.action = action
  search()
}

async function filterByTarget(type: string, id: number | null) {
  filters.target_type = type
  filters.target_id = id ?? undefined
  search()
}

const ACTION_LABELS: Record<string, string> = {
  'attendance.adjust': '调整出勤', 'attendance.close': '结束签到',
  'attendance.create': '创建签到', 'attendance.update': '更新签到',
  'schedule.create': '创建课次', 'schedule.reschedule': '调整课次',
  'schedule.update': '更新课次',
  'task.create': '创建任务', 'task.publish': '发布任务',
  'task.published': '发布任务', 'task.status_change': '变更任务状态',
  'task.update': '更新任务',
}
const TARGET_LABELS: Record<string, string> = {
  checkin_task: '打卡任务', attendance_session: '课堂签到',
  class_session: '课堂课次', checkin_submission: '打卡提交',
}

function actionLabel(action: string) {
  return ACTION_LABELS[action] || action || '—'
}

/** 按动作语义分类着色：创建=绿 / 发布更新=蓝 / 调整=橙 / 关闭·状态变化=红 */
function actionTagType(action: string): 'success' | 'primary' | 'warning' | 'danger' | 'info' {
  if (/create/.test(action)) return 'success'
  if (/publish|update|reschedule/.test(action)) return 'primary'
  if (/adjust/.test(action)) return 'warning'
  if (/close|status_change|reject|withdraw/.test(action)) return 'danger'
  return 'info'
}

function targetLabel(type: string) { return TARGET_LABELS[type] || type || '—' }
function showDetail(row: Record<string, any>) {
  selectedAudit.value = row
  detailOpen.value = true
}
function formatJson(value: unknown) {
  return value == null || (typeof value === 'object' && Object.keys(value as object).length === 0)
    ? '无记录'
    : JSON.stringify(value, null, 2)
}
const hasAppliedFilters = computed(() => !!(applied.action || applied.target_type || applied.target_id != null || applied.actor_user_id != null || applied.keyword.trim() || applied.range))

const hasActiveFilters = computed(
  () =>
    !!filters.action ||
    !!filters.target_type ||
    filters.target_id != null ||
    filters.actor_user_id != null ||
    !!filters.keyword.trim() ||
    !!filters.range,
)

/** 已生效条件的快捷标签（可点 × 移除并重查） */
const appliedFilterChips = computed(() => {
  const chips: Array<{ key: string; label: string; clear: () => void }> = []
  if (applied.action) chips.push({ key: 'action', label: `操作：${actionLabel(applied.action)}`, clear: () => { filters.action = ''; search() } })
  if (applied.target_type) chips.push({ key: 'target_type', label: `对象：${targetLabel(applied.target_type)}`, clear: () => { filters.target_type = ''; search() } })
  if (applied.target_id != null) chips.push({ key: 'target_id', label: `对象 ID：${applied.target_id}`, clear: () => { filters.target_id = undefined; search() } })
  if (applied.actor_user_id != null) chips.push({ key: 'actor', label: `执行账号：${applied.actor_user_id}`, clear: () => { filters.actor_user_id = undefined; search() } })
  if (applied.keyword.trim()) chips.push({ key: 'keyword', label: `关键词：${applied.keyword.trim()}`, clear: () => { filters.keyword = ''; search() } })
  if (applied.range) chips.push({ key: 'range', label: '自定义时间范围', clear: () => { filters.range = null; search() } })
  return chips
})

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
      <div class="hero-actions"><el-tag type="info" effect="plain" round>只读审计</el-tag><el-button :icon="Refresh" :loading="loading" @click="refresh">刷新数据</el-button></div>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false">
      <el-button @click="refresh">重试</el-button>
    </el-alert>

    <section class="kpi-grid">
      <article>
        <div class="kpi-head"><el-icon class="kpi-icon tone-blue"><Tickets /></el-icon><span>打卡任务</span></div>
        <strong>{{ overview?.task_count ?? '—' }}</strong>
        <small>进行中 {{ overview?.published_task_count ?? '—' }}</small>
      </article>
      <article>
        <div class="kpi-head"><el-icon class="kpi-icon tone-green"><DocumentChecked /></el-icon><span>学生提交</span></div>
        <strong>{{ overview?.submission_count ?? '—' }}</strong>
        <small>待审核 {{ overview?.pending_review_count ?? '—' }}</small>
      </article>
      <article>
        <div class="kpi-head"><el-icon class="kpi-icon tone-purple"><Calendar /></el-icon><span>课堂签到活动</span></div>
        <strong>{{ overview?.attendance_session_count ?? '—' }}</strong>
        <small>出勤记录 {{ overview?.attendance_record_count ?? '—' }}</small>
      </article>
      <article>
        <div class="kpi-head"><el-icon class="kpi-icon tone-orange"><DataLine /></el-icon><span>平台学习打卡</span></div>
        <strong>{{ overview?.self_checkin_count ?? '—' }}</strong>
        <small>学生每日平台打卡</small>
      </article>
    </section>

    <article class="panel">
      <div class="panel-title">
        <div><span class="eyebrow">AUDIT TRAIL</span><h2>操作审计查询</h2><p class="muted">追溯操作原因与变更内容，点击操作或对象可快速筛选。</p></div>
        <el-tag effect="plain" type="info" round>{{ audits.length }} 条记录</el-tag>
      </div>

      <div class="filter-bar">
        <el-form label-position="top" class="filter-form" @submit.prevent="search">
          <el-form-item label="操作类型">
            <el-select v-model="filters.action" placeholder="全部操作" clearable filterable>
              <el-option v-for="name in actionChoices" :key="name" :label="actionLabel(name)" :value="name" />
            </el-select>
          </el-form-item>
          <el-form-item label="对象类型">
            <el-select v-model="filters.target_type" placeholder="全部对象" clearable filterable>
              <el-option v-for="name in targetTypeChoices" :key="name" :label="targetLabel(name)" :value="name" />
            </el-select>
          </el-form-item>
          <el-form-item label="对象 ID">
            <el-input-number v-model="filters.target_id" :min="1" :controls="false" placeholder="如 10" />
          </el-form-item>
          <el-form-item label="执行账号">
            <el-input-number v-model="filters.actor_user_id" :min="1" :controls="false" placeholder="如 101" />
          </el-form-item>
          <el-form-item label="关键词" class="span-2">
            <el-input v-model="filters.keyword" placeholder="搜索原因或操作" :prefix-icon="Search" clearable @keyup.enter="search" />
          </el-form-item>
          <el-form-item label="时间范围（北京时间）" class="span-3">
            <el-date-picker
              v-model="filters.range"
              type="datetimerange"
              start-placeholder="开始"
              end-placeholder="结束"
              range-separator="至"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
            />
          </el-form-item>
          <el-form-item label="最多加载">
            <el-select v-model="filters.limit">
              <el-option label="50 条" :value="50" />
              <el-option label="100 条" :value="100" />
              <el-option label="200 条" :value="200" />
              <el-option label="500 条" :value="500" />
            </el-select>
          </el-form-item>
          <div class="filter-actions">
            <el-button type="primary" :icon="Search" native-type="submit" :loading="loading">查询</el-button>
            <el-button :disabled="!hasActiveFilters && filters.limit === 200" @click="resetFilters">重置</el-button>
          </div>
        </el-form>

        <div v-if="appliedFilterChips.length" class="applied-chips">
          <span class="chips-label">已生效条件</span>
          <el-tag
            v-for="chip in appliedFilterChips"
            :key="chip.key"
            closable
            effect="plain"
            @close="chip.clear()"
          >{{ chip.label }}</el-tag>
          <el-button link type="primary" size="small" @click="resetFilters">清空全部</el-button>
        </div>
      </div>

      <div class="audit-table"><el-table :data="pagedAudits" stripe empty-text="暂无符合条件的审计记录" style="width: 100%">
        <el-table-column label="时间" width="150">
          <template #default="{ row }"><span class="time-cell">{{ formatTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-tag v-if="row.action" class="clickable-tag" :type="actionTagType(row.action)" effect="light" round :title="row.action" @click="filterByAction(row.action)">
              {{ actionLabel(row.action) }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="对象" width="170">
          <template #default="{ row }">
            <el-link v-if="row.target_type" type="primary" :underline="false" class="target-link" @click="filterByTarget(row.target_type, row.target_id)">
              {{ targetLabel(row.target_type) }} <b>#{{ row.target_id ?? '—' }}</b>
            </el-link>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip>
          <template #default="{ row }"><span :class="{ muted: !row.reason }">{{ row.reason || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="执行账号" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.actor_user_id" effect="plain" size="small" round>#{{ row.actor_user_id }}</el-tag>
            <span v-else class="muted">系统</span>
          </template>
        </el-table-column>
        <el-table-column label="变更摘要" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="change-summary">
              <div v-for="(line, idx) in changeLines(row)" :key="idx" class="change-line" :class="{ 'is-empty': line.empty }">
                <span class="change-label">{{ line.label }}</span>{{ line.text }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="详情" width="76" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="showDetail(row)">查看</el-button></template></el-table-column>
      </el-table></div>

      <div class="table-footer">
        <span class="muted">本次加载 {{ audits.length }} 条<span v-if="hasAppliedFilters">（已筛选）</span> · 上限 {{ applied.limit }} 条</span>
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="audits.length"
          :page-sizes="[10, 20, 50, 100]"
          :pager-count="5"
          layout="prev, pager, next, sizes"
          @size-change="page = 1"
          background
        />
      </div>
    </article>
    <el-drawer v-model="detailOpen" title="审计记录详情" size="min(620px, 100vw)" append-to-body>
      <div v-if="selectedAudit" class="audit-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="操作时间">{{ formatTime(selectedAudit.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="操作类型">{{ actionLabel(selectedAudit.action) }}<code>{{ selectedAudit.action }}</code></el-descriptions-item>
          <el-descriptions-item label="操作对象">{{ targetLabel(selectedAudit.target_type) }} #{{ selectedAudit.target_id ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="执行账号">{{ selectedAudit.actor_user_id ?? '系统' }}</el-descriptions-item>
          <el-descriptions-item label="操作原因">{{ selectedAudit.reason || '未填写原因' }}</el-descriptions-item>
        </el-descriptions>
        <section><h3>变更前</h3><pre>{{ formatJson(selectedAudit.before) }}</pre></section>
        <section><h3>变更后</h3><pre>{{ formatJson(selectedAudit.after) }}</pre></section>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.admin-checkin{display:grid;gap:20px}
.admin-hero{display:flex;justify-content:space-between;flex-wrap:wrap;gap:18px;padding:28px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel)),var(--panel));box-shadow:var(--shadow-sm)}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}
h1,h2,p{margin:0}
h1{font-size:28px;margin:5px 0 8px}
.admin-hero p{color:var(--muted);line-height:1.7;max-width:820px}
.hero-actions{display:flex;align-items:center;gap:10px}

/* ---- KPI 卡片 ---- */
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.kpi-grid article{padding:16px 18px;border:1px solid var(--line);border-radius:16px;background:var(--panel);box-shadow:var(--shadow-sm);display:grid;gap:4px;transition:transform .15s ease,box-shadow .15s ease}
.kpi-grid article:hover{transform:translateY(-2px);box-shadow:var(--shadow-md,0 6px 18px rgba(15,23,42,.08))}
.kpi-head{display:flex;align-items:center;gap:8px}
.kpi-head span{font-size:12px;color:var(--muted)}
.kpi-icon{font-size:18px;padding:6px;border-radius:8px}
.tone-blue{color:#2563eb;background:rgba(37,99,235,.1)}
.tone-green{color:#059669;background:rgba(5,150,105,.1)}
.tone-purple{color:#7c3aed;background:rgba(124,58,237,.1)}
.tone-orange{color:#d97706;background:rgba(217,119,6,.1)}
.kpi-grid strong{font-size:26px;line-height:1.2}
.kpi-grid small{color:var(--muted)}

.panel{padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--panel);display:grid;gap:14px}
.panel-title{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px}
.panel-title h2{font-size:18px;margin-top:4px}

/* ---- 筛选区：网格布局，紧凑两行 ---- */
.filter-bar{padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:color-mix(in srgb,var(--accent) 4%,var(--panel));display:grid;gap:10px}
.filter-form{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px 14px;align-items:end}
.filter-form :deep(.el-form-item){margin:0;min-width:0}
.filter-form :deep(.el-form-item .el-select),
.filter-form :deep(.el-form-item .el-input-number),
.filter-form :deep(.el-form-item .el-date-editor){width:100%}
.filter-form :deep(.el-input-number .el-input__inner){text-align:left}
.filter-form :deep(.el-form-item__label){padding-bottom:2px;line-height:1.5;font-size:12px;color:var(--muted)}
.filter-form .span-2{grid-column:span 2}
.filter-form .span-3{grid-column:span 3}
.filter-actions{display:flex;gap:8px;justify-content:flex-end;align-items:center;padding-bottom:1px}

/* 已生效条件快捷标签 */
.applied-chips{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding-top:10px;border-top:1px dashed var(--line)}
.chips-label{font-size:12px;color:var(--muted)}

/* ---- 表格 ---- */
.audit-table :deep(.el-table__row){cursor:default}
.clickable-tag{cursor:pointer;font-weight:600}
.clickable-tag:hover{opacity:.85}
.target-link{font-weight:600}
.target-link b{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:600}
.time-cell{font-variant-numeric:tabular-nums;color:var(--muted)}
.change-summary{display:grid;gap:2px;font-size:12px;line-height:1.55}
.change-line{display:flex;gap:6px;align-items:baseline;min-width:0}
.change-line .change-label{flex:none;font-weight:700;color:var(--accent);font-size:11px}
.change-line.is-empty{color:var(--muted)}
.change-line.is-empty .change-label{color:var(--muted)}
.muted{color:var(--muted);font-size:13px}

.table-footer{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}

@media (max-width: 1200px){
  .filter-form{grid-template-columns:repeat(4,minmax(0,1fr))}
  .filter-form .span-2{grid-column:span 2}
  .filter-form .span-3{grid-column:span 2}
}
@media (max-width: 900px){
  .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .filter-form{grid-template-columns:repeat(2,minmax(0,1fr))}
  .filter-form .span-2,.filter-form .span-3{grid-column:span 2}
  .filter-actions{justify-content:stretch}
  .filter-actions .el-button{flex:1}
}
</style>
