<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  teacherApi,
  type ApiEnvelope,
  type ClassSessionItem,
  type ClassSessionPayload,
  type ScheduleExceptionItem,
  type TeacherClassItem,
  type TeacherSchedule,
} from '../../api'

const loading = ref(false)
const classes = ref<TeacherClassItem[]>([])
const selectedClassId = ref(0)
const schedule = ref<TeacherSchedule | null>(null)
const loadError = ref('')

const sessionDialog = ref(false)
const editingSessionId = ref(0)
const savingSession = ref(false)
const sessionForm = reactive({
  topic: '',
  weekday: 1,
  start_time: '09:00',
  end_time: '10:00',
  week_start: '',
  week_end: '',
  location: '',
  mode: 'offline' as 'offline' | 'online',
})

const exceptionDialog = ref(false)
const currentSession = ref<ClassSessionItem | null>(null)
const savingException = ref(false)
const exceptionForm = reactive({
  date: '',
  kind: 'cancel' as 'cancel' | 'reschedule' | 'makeup',
  new_date: '',
  new_start_time: '',
  new_end_time: '',
  location: '',
  reason: '',
})

const weekdayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function isoDate(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function mondayOf(date: Date) {
  const copy = new Date(date)
  copy.setDate(copy.getDate() - ((copy.getDay() + 6) % 7))
  return copy
}

const sessions = computed(() => schedule.value?.sessions || [])
const exceptions = computed(() => schedule.value?.exceptions || [])

function errorText(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  return `${fallback}${error?.response?.status ? `（HTTP ${error.response.status}）` : '，请检查网络后重试'}`
}

async function refresh() {
  loadError.value = ''
  loading.value = true
  try {
    const { data } = await teacherApi.get<ApiEnvelope<TeacherClassItem[]>>('/teacher/classes')
    classes.value = data.data
    if (!selectedClassId.value && classes.value.length) selectedClassId.value = classes.value[0].id
    if (selectedClassId.value) await loadSchedule()
  } catch (error: any) {
    loadError.value = errorText(error, '课堂与课程表加载失败')
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function loadSchedule() {
  if (!selectedClassId.value) return
  try {
    const { data } = await teacherApi.get<ApiEnvelope<TeacherSchedule>>(
      `/learning/classes/${selectedClassId.value}/schedule`,
    )
    schedule.value = data.data
  } catch (error: any) {
    schedule.value = null
    ElMessage.error(errorText(error, '课程表加载失败'))
  }
}

function openSessionDialog(item?: ClassSessionItem) {
  editingSessionId.value = item?.id || 0
  const monday = mondayOf(new Date())
  sessionForm.topic = item?.topic || ''
  sessionForm.weekday = item?.weekday || 1
  sessionForm.start_time = item?.start_time || '09:00'
  sessionForm.end_time = item?.end_time || '10:00'
  sessionForm.week_start = item?.week_start || isoDate(monday)
  sessionForm.week_end = item?.week_end || isoDate(new Date(monday.getTime() + 27 * 86400000))
  sessionForm.location = item?.location || ''
  sessionForm.mode = item?.mode || 'offline'
  sessionDialog.value = true
}

async function saveSession() {
  if (!selectedClassId.value) return
  if (!sessionForm.topic.trim()) return ElMessage.warning('请填写课程主题')
  if (!sessionForm.week_start || !sessionForm.week_end) return ElMessage.warning('请选择教学周范围')
  if (sessionForm.week_start > sessionForm.week_end) return ElMessage.warning('教学周开始日期不能晚于结束日期')
  const payload: ClassSessionPayload = {
    topic: sessionForm.topic.trim(),
    weekday: sessionForm.weekday,
    start_time: sessionForm.start_time,
    end_time: sessionForm.end_time,
    week_start: sessionForm.week_start,
    week_end: sessionForm.week_end,
    location: sessionForm.location.trim(),
    mode: sessionForm.mode,
  }
  savingSession.value = true
  try {
    if (editingSessionId.value) {
      await teacherApi.put(
        `/learning/classes/${selectedClassId.value}/schedule/${editingSessionId.value}`,
        payload,
      )
      ElMessage.success('课程安排已更新，学生课程表同步')
    } else {
      await teacherApi.post(`/learning/classes/${selectedClassId.value}/schedule`, payload)
      ElMessage.success('课程安排已创建，学生课程表同步')
    }
    sessionDialog.value = false
    await loadSchedule()
  } catch (error: any) {
    ElMessage.error(errorText(error, '保存课程失败'))
  } finally {
    savingSession.value = false
  }
}

async function removeSession(item: ClassSessionItem) {
  try {
    await ElMessageBox.confirm(`删除后该课程的未来安排将不再显示，确定删除「${item.topic}」吗？`, '删除课程', { type: 'warning' })
    await teacherApi.delete(`/learning/classes/${selectedClassId.value}/schedule/${item.id}`)
    ElMessage.success('课程安排已删除')
    await loadSchedule()
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorText(error, '删除失败'))
  }
}

function openExceptionDialog(item: ClassSessionItem, kind: 'cancel' | 'reschedule' | 'makeup' = 'cancel') {
  currentSession.value = item
  const next = new Date()
  next.setDate(next.getDate() + ((item.weekday - next.getDay() + 7) % 7 || 7))
  exceptionForm.date = isoDate(next)
  exceptionForm.kind = kind
  exceptionForm.new_date = ''
  exceptionForm.new_start_time = ''
  exceptionForm.new_end_time = ''
  exceptionForm.location = ''
  exceptionForm.reason = ''
  exceptionDialog.value = true
}

async function saveException() {
  const session = currentSession.value
  if (!session) return
  if (!exceptionForm.reason.trim()) return ElMessage.warning('请填写调整原因')
  if (exceptionForm.kind === 'makeup' && !(exceptionForm.new_date && exceptionForm.new_start_time && exceptionForm.new_end_time)) {
    return ElMessage.warning('补课必须填写新日期和起止时间')
  }
  savingException.value = true
  try {
    await teacherApi.post(
      `/learning/classes/${selectedClassId.value}/schedule/${session.id}/exceptions`,
      {
        date: exceptionForm.date,
        kind: exceptionForm.kind,
        new_date: exceptionForm.new_date || null,
        new_start_time: exceptionForm.new_start_time || null,
        new_end_time: exceptionForm.new_end_time || null,
        location: exceptionForm.location || null,
        reason: exceptionForm.reason.trim(),
      },
    )
    ElMessage.success('调整已保存，学生课程表与通知同步更新')
    exceptionDialog.value = false
    await loadSchedule()
  } catch (error: any) {
    ElMessage.error(errorText(error, '保存调整失败'))
  } finally {
    savingException.value = false
  }
}

async function removeException(item: ScheduleExceptionItem) {
  try {
    await ElMessageBox.confirm('撤销后学生课程表恢复原安排，确定继续吗？', '撤销调整', { type: 'warning' })
    await teacherApi.delete(`/learning/classes/${selectedClassId.value}/schedule/exceptions/${item.id}`)
    ElMessage.success('调整已撤销')
    await loadSchedule()
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorText(error, '撤销失败'))
  }
}

function kindLabel(kind: string) {
  return kind === 'cancel' ? '停课' : kind === 'reschedule' ? '调课' : '补课'
}

onMounted(refresh)
</script>

<template>
  <div class="schedule-page" v-loading="loading">
    <header class="schedule-hero">
      <div>
        <span class="eyebrow">TEACHING SCHEDULE</span>
        <h1>课程安排与教学日历</h1>
        <p>为本人课堂安排每周课程。时间冲突由后端确定性校验；调课、停课、补课会同步学生课程表并发送通知。</p>
      </div>
      <div class="hero-actions">
        <el-select v-model="selectedClassId" placeholder="选择课堂" style="width:220px" @change="loadSchedule">
          <el-option v-for="item in classes" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-button type="primary" :disabled="!selectedClassId" @click="openSessionDialog()">新增课程</el-button>
        <el-button @click="refresh">刷新</el-button>
      </div>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false"><el-button @click="refresh">重试</el-button></el-alert>
    <el-empty v-if="!loading && !classes.length" description="还没有课堂，请先在班级管理中创建课堂" />

    <article v-if="schedule" class="panel">
      <div class="panel-title"><div><span class="eyebrow">WEEKLY</span><h2>{{ schedule.class_name }} · 每周课程</h2></div><small>{{ sessions.length }} 条安排</small></div>
      <el-table :data="sessions" stripe empty-text="还没有课程安排">
        <el-table-column label="星期" width="90"><template #default="{ row }">{{ weekdayNames[row.weekday - 1] }}</template></el-table-column>
        <el-table-column label="时间" width="140"><template #default="{ row }">{{ row.start_time }} - {{ row.end_time }}</template></el-table-column>
        <el-table-column prop="topic" label="课程主题" min-width="160" />
        <el-table-column prop="location" label="地点" min-width="120" />
        <el-table-column label="方式" width="90"><template #default="{ row }">{{ row.mode === 'online' ? '线上' : '线下' }}</template></el-table-column>
        <el-table-column label="教学周" min-width="190"><template #default="{ row }">{{ row.week_start }} 至 {{ row.week_end }}</template></el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openSessionDialog(row)">编辑</el-button>
            <el-button link @click="openExceptionDialog(row, 'cancel')">停课</el-button>
            <el-button link @click="openExceptionDialog(row, 'reschedule')">调课</el-button>
            <el-button link @click="openExceptionDialog(row, 'makeup')">补课</el-button>
            <el-button link type="danger" @click="removeSession(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </article>

    <article v-if="schedule" class="panel">
      <div class="panel-title"><div><span class="eyebrow">EXCEPTIONS</span><h2>调课 / 停课 / 补课记录</h2></div></div>
      <el-table :data="exceptions" stripe empty-text="暂无单次调整">
        <el-table-column label="类型" width="90"><template #default="{ row }">{{ kindLabel(row.kind) }}</template></el-table-column>
        <el-table-column prop="date" label="原日期" width="120" />
        <el-table-column label="调整后" min-width="180"><template #default="{ row }"><span v-if="row.new_date">{{ row.new_date }} {{ row.new_start_time }}-{{ row.new_end_time }}</span><span v-else>—</span></template></el-table-column>
        <el-table-column prop="reason" label="原因" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="danger" @click="removeException(row)">撤销</el-button></template></el-table-column>
      </el-table>
    </article>

    <el-dialog v-model="sessionDialog" :title="editingSessionId ? '编辑课程安排' : '新增课程安排'" width="560px">
      <el-form :model="sessionForm" label-position="top" class="session-form">
        <el-form-item label="课程主题" required><el-input v-model="sessionForm.topic" maxlength="160" placeholder="例如：图的最短路径" /></el-form-item>
        <el-form-item label="星期" required>
          <el-select v-model="sessionForm.weekday">
            <el-option v-for="(name, index) in weekdayNames" :key="name" :label="name" :value="index + 1" />
          </el-select>
        </el-form-item>
        <el-form-item label="开始时间" required><el-time-picker v-model="sessionForm.start_time" value-format="HH:mm" format="HH:mm" /></el-form-item>
        <el-form-item label="结束时间" required><el-time-picker v-model="sessionForm.end_time" value-format="HH:mm" format="HH:mm" /></el-form-item>
        <el-form-item label="教学周开始" required><el-date-picker v-model="sessionForm.week_start" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="教学周结束" required><el-date-picker v-model="sessionForm.week_end" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="授课地点"><el-input v-model="sessionForm.location" placeholder="教室或线上会议说明" /></el-form-item>
        <el-form-item label="授课方式">
          <el-radio-group v-model="sessionForm.mode"><el-radio value="offline">线下</el-radio><el-radio value="online">线上</el-radio></el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sessionDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingSession" @click="saveSession">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="exceptionDialog" :title="`${kindLabel(exceptionForm.kind)}：${currentSession?.topic || ''}`" width="520px">
      <el-form :model="exceptionForm" label-position="top">
        <el-form-item label="原课程日期" required><el-date-picker v-model="exceptionForm.date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item v-if="exceptionForm.kind !== 'cancel'" label="调整后日期"><el-date-picker v-model="exceptionForm.new_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item v-if="exceptionForm.kind !== 'cancel'" label="调整后开始时间"><el-time-picker v-model="exceptionForm.new_start_time" value-format="HH:mm" format="HH:mm" /></el-form-item>
        <el-form-item v-if="exceptionForm.kind !== 'cancel'" label="调整后结束时间"><el-time-picker v-model="exceptionForm.new_end_time" value-format="HH:mm" format="HH:mm" /></el-form-item>
        <el-form-item v-if="exceptionForm.kind !== 'cancel'" label="调整后地点"><el-input v-model="exceptionForm.location" placeholder="可选" /></el-form-item>
        <el-form-item label="原因" required><el-input v-model="exceptionForm.reason" type="textarea" :rows="3" placeholder="填写停课/调课/补课原因，学生将收到通知" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="exceptionDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingException" @click="saveException">保存并通知学生</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.schedule-page{display:grid;gap:20px}
.schedule-hero{display:flex;flex-wrap:wrap;justify-content:space-between;gap:18px;padding:28px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel)),var(--panel));box-shadow:var(--shadow-sm)}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}
h1,h2,p{margin:0}
h1{font-size:28px;margin:5px 0 8px}
.schedule-hero p{color:var(--muted);line-height:1.7;max-width:760px}
.hero-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.panel{padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--panel);box-shadow:var(--shadow-sm);display:grid;gap:14px}
.panel-title{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.panel-title h2{font-size:18px;margin-top:4px}
.panel-title small{color:var(--muted)}
.session-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}
.session-form .el-form-item:nth-child(1){grid-column:span 2}
@media (max-width:640px){.session-form{grid-template-columns:1fr}.session-form .el-form-item:nth-child(1){grid-column:auto}}
</style>
