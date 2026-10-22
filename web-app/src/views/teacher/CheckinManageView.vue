<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  teacherApi,
  type ApiEnvelope,
  type AttendanceLive,
  type AttendanceSessionItem,
  type CheckinReviewPayload,
  type CheckinTaskCompletion,
  type CheckinTaskCompletionRow,
  type CheckinTaskCreatePayload,
  type CheckinTaskItem,
  type ClassCheckinStat,
  type TeacherCheckinOverview,
  type TeacherClassItem,
} from '../../api'

type TabKey = 'tasks' | 'review' | 'attendance' | 'dashboard'

const loading = ref(false)
const activeTab = ref<TabKey>('tasks')
const overview = ref<TeacherCheckinOverview | null>(null)
const classes = ref<TeacherClassItem[]>([])
const tasks = ref<CheckinTaskItem[]>([])
const sessions = ref<AttendanceSessionItem[]>([])
const selectedClassId = ref(0)
const loadError = ref('')

const stateLabels: Record<string, string> = {
  draft: '草稿',
  published: '进行中',
  closed: '已结束',
  cancelled: '已取消',
  not_started: '未开始',
  pending: '待完成',
  pending_review: '待审核',
  approved: '已通过',
  returned: '被退回',
  overdue: '已逾期',
  missing: '未签到',
  present: '正常',
  late: '迟到',
  leave: '请假',
  absent: '缺勤',
  submitted: '待审核',
}

const freqLabels: Record<string, string> = { once: '单次任务', daily: '每日重复', weekly: '每周重复' }

const taskForm = reactive({
  class_id: 0,
  title: '',
  goal: '',
  description: '',
  frequency: 'once' as 'once' | 'daily' | 'weekly',
  weekly_days: [] as number[],
  start_at: '',
  end_at: '',
  due_time: '23:59',
  allow_late: false,
  review_mode: 'manual' as 'auto' | 'manual',
  require_attachment: false,
  knowledge_text: '',
})
const taskDialog = ref(false)
const savingTask = ref(false)
const editingTaskId = ref(0)

const attendanceForm = reactive({
  class_id: 0,
  title: '',
  start_at: '',
  end_at: '',
  late_after_at: '',
})
const attendanceDialog = ref(false)
const savingAttendance = ref(false)

const completion = ref<CheckinTaskCompletion | null>(null)
const completionTaskId = ref(0)
const completionPeriod = ref('')
const completionLoading = ref(false)
const selectedRows = ref<CheckinTaskCompletionRow[]>([])

const reviewDialog = ref(false)
const reviewForm = reactive<CheckinReviewPayload>({ verdict: 'approve', comment: '', score: null })
const reviewBatch = ref(false)
const reviewTargets = ref<number[]>([])
const reviewSubmitting = ref(false)

const liveDialog = ref(false)
const live = ref<AttendanceLive | null>(null)
const liveSessionId = ref(0)

const manualDialog = ref(false)
const manualForm = reactive({
  student_user_id: 0,
  student_name: '',
  status: 'present' as 'present' | 'late' | 'leave' | 'absent' | 'pending',
  reason: '',
  note: '',
})

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function localInput(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function toIso(value: string) {
  if (!value) return ''
  return `${value.replace(' ', 'T')}:00+08:00`
}

function tomorrowInput() {
  const date = new Date(Date.now() + 24 * 3600 * 1000)
  date.setHours(23, 59, 0, 0)
  return localInput(date)
}

function errorText(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) return detail[0]?.msg || fallback
  return `${fallback}${error?.response?.status ? `（HTTP ${error.response.status}）` : '，请检查网络后重试'}`
}

function formatTime(value?: string | null) {
  if (!value) return '未设置'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function label(value?: string | null) {
  if (!value) return '未开始'
  return stateLabels[value] || value
}

function tagType(value?: string | null) {
  if (value === 'approved' || value === 'present' || value === 'published') return 'success'
  if (value === 'returned' || value === 'absent' || value === 'overdue' || value === 'cancelled') return 'danger'
  if (value === 'late' || value === 'pending_review' || value === 'leave' || value === 'submitted') return 'warning'
  return 'info'
}

function rate(value: number | null | undefined) {
  return value === null || value === undefined ? '暂无数据' : `${value}%`
}

const classOptions = computed(() => classes.value.map((item) => ({ label: item.name, value: item.id })))

const filteredTasks = computed(() =>
  selectedClassId.value ? tasks.value.filter((item) => item.class_id === selectedClassId.value) : tasks.value,
)
const filteredSessions = computed(() =>
  selectedClassId.value ? sessions.value.filter((item) => item.class_id === selectedClassId.value) : sessions.value,
)

const reviewableSubmissions = computed(() => (completion.value?.rows || []).filter((row) => row.submission_id))

async function refresh() {
  loadError.value = ''
  loading.value = true
  try {
    const params = selectedClassId.value ? { class_id: selectedClassId.value } : undefined
    const [overviewRes, classRes, taskRes, sessionRes] = await Promise.all([
      teacherApi.get<ApiEnvelope<TeacherCheckinOverview>>('/learning/checkin/overview'),
      teacherApi.get<ApiEnvelope<TeacherClassItem[]>>('/teacher/classes'),
      teacherApi.get<ApiEnvelope<CheckinTaskItem[]>>('/learning/checkin/manage/tasks', { params }),
      teacherApi.get<ApiEnvelope<AttendanceSessionItem[]>>('/learning/checkin/manage/attendance', { params }),
    ])
    overview.value = overviewRes.data.data
    classes.value = classRes.data.data
    tasks.value = taskRes.data.data
    sessions.value = sessionRes.data.data
    if (!taskForm.class_id && classOptions.value.length) taskForm.class_id = classOptions.value[0].value
    if (!attendanceForm.class_id && classOptions.value.length) attendanceForm.class_id = classOptions.value[0].value
    if (!completionTaskId.value && tasks.value.length) await loadCompletion(tasks.value[0].id)
  } catch (error: any) {
    loadError.value = errorText(error, '打卡管理数据加载失败')
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function loadCompletion(taskId: number, period?: string) {
  completionLoading.value = true
  completionTaskId.value = taskId
  completionPeriod.value = period || ''
  try {
    const params = completionPeriod.value ? { period: completionPeriod.value } : undefined
    const { data } = await teacherApi.get<ApiEnvelope<CheckinTaskCompletion>>(
      `/learning/checkin/manage/tasks/${taskId}/completion`,
      { params },
    )
    completion.value = data.data
    completionPeriod.value = data.data.period_key
  } catch (error: any) {
    completion.value = null
    ElMessage.error(errorText(error, '完成情况加载失败'))
  } finally {
    completionLoading.value = false
  }
}

function openTaskDialog(item?: CheckinTaskItem) {
  editingTaskId.value = item?.id || 0
  taskForm.class_id = item?.class_id || selectedClassId.value || classOptions.value[0]?.value || 0
  taskForm.title = item?.title || ''
  taskForm.goal = item?.goal || ''
  taskForm.description = item?.description || ''
  taskForm.frequency = item?.frequency || 'once'
  taskForm.weekly_days = [...(item?.weekly_days || [])]
  taskForm.start_at = item ? localInput(new Date(item.start_at)) : localInput(new Date())
  taskForm.end_at = item ? localInput(new Date(item.end_at)) : tomorrowInput()
  taskForm.due_time = item?.due_time || '23:59'
  taskForm.allow_late = item?.allow_late || false
  taskForm.review_mode = item?.review_mode || 'manual'
  taskForm.require_attachment = item?.require_attachment || false
  taskForm.knowledge_text = (item?.knowledge_points || []).join('、')
  taskDialog.value = true
}

function buildTaskPayload(): CheckinTaskCreatePayload {
  return {
    class_id: taskForm.class_id,
    title: taskForm.title.trim(),
    goal: taskForm.goal.trim(),
    description: taskForm.description.trim(),
    frequency: taskForm.frequency,
    weekly_days: taskForm.weekly_days,
    start_at: toIso(taskForm.start_at),
    end_at: toIso(taskForm.end_at),
    due_time: taskForm.due_time || '23:59',
    allow_late: taskForm.allow_late,
    review_mode: taskForm.review_mode,
    require_attachment: taskForm.require_attachment,
    knowledge_points: taskForm.knowledge_text
      .split(/[，,、\s]+/)
      .map((item) => item.trim())
      .filter(Boolean),
  }
}

async function createTask(publish: boolean) {
  if (!taskForm.class_id) return ElMessage.warning('请选择发布班级')
  if (!taskForm.title.trim()) return ElMessage.warning('请填写任务名称')
  if (!taskForm.start_at || !taskForm.end_at) return ElMessage.warning('请设置开始与截止时间')
  savingTask.value = true
  try {
    let taskId = editingTaskId.value
    if (taskId) {
      await teacherApi.put(`/learning/checkin/manage/tasks/${taskId}`, buildTaskPayload())
      ElMessage.success('打卡任务已更新')
    } else {
      const { data } = await teacherApi.post<ApiEnvelope<CheckinTaskItem>>(
        '/learning/checkin/manage/tasks',
        buildTaskPayload(),
      )
      taskId = data.data.id
      ElMessage.success(publish ? '打卡任务已发布，学生端将同步显示' : '打卡任务已保存为草稿')
    }
    if (publish) {
      await teacherApi.post(`/learning/checkin/manage/tasks/${taskId}/publish`)
      ElMessage.success('打卡任务已发布，学生端将同步显示')
    }
    taskDialog.value = false
    editingTaskId.value = 0
    await refresh()
  } catch (error: any) {
    ElMessage.error(errorText(error, '任务保存失败'))
  } finally {
    savingTask.value = false
  }
}

async function taskAction(item: CheckinTaskItem, action: 'publish' | 'close' | 'cancel') {
  const labels = { publish: '发布', close: '结束', cancel: '取消' }
  try {
    if (action !== 'publish') {
      await ElMessageBox.confirm(`确定要${labels[action]}任务「${item.title}」吗？`, '确认操作', {
        type: 'warning',
      })
    }
    await teacherApi.post(`/learning/checkin/manage/tasks/${item.id}/${action}`)
    ElMessage.success(`任务已${labels[action]}`)
    await refresh()
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorText(error, '操作失败'))
  }
}

async function remind(item: CheckinTaskItem) {
  try {
    const { data } = await teacherApi.post<ApiEnvelope<{ reminded: number; period_key: string }>>(
      `/learning/checkin/manage/tasks/${item.id}/remind`,
      {},
    )
    ElMessage.success(`已向 ${data.data.reminded} 名未完成学生发送 ${data.data.period_key} 的提醒`)
  } catch (error: any) {
    ElMessage.error(errorText(error, '提醒发送失败'))
  }
}

function openReview(row: CheckinTaskCompletionRow, batch = false) {
  if (batch) {
    const ids = selectedRows.value.map((item) => item.submission_id).filter((id): id is number => Boolean(id))
    if (!ids.length) return ElMessage.warning('请先勾选待审核的提交')
    reviewTargets.value = ids
  } else {
    if (!row.submission_id) return
    reviewTargets.value = [row.submission_id]
  }
  reviewBatch.value = batch
  reviewForm.verdict = 'approve'
  reviewForm.comment = ''
  reviewForm.score = null
  reviewDialog.value = true
}

async function submitReview() {
  if (!reviewTargets.value.length) return
  if (reviewForm.verdict === 'return' && !reviewForm.comment.trim()) {
    return ElMessage.warning('退回补交必须填写原因')
  }
  reviewSubmitting.value = true
  try {
    if (reviewBatch.value) {
      await teacherApi.post('/learning/checkin/manage/submissions/review-batch', {
        submission_ids: reviewTargets.value,
        ...reviewForm,
      })
    } else {
      await teacherApi.post(`/learning/checkin/manage/submissions/${reviewTargets.value[0]}/review`, {
        ...reviewForm,
      })
    }
    ElMessage.success(reviewForm.verdict === 'approve' ? '审核已通过' : '已退回并通知学生')
    reviewDialog.value = false
    await loadCompletion(completionTaskId.value, completionPeriod.value)
    await refresh()
  } catch (error: any) {
    ElMessage.error(errorText(error, '审核失败'))
  } finally {
    reviewSubmitting.value = false
  }
}

function onSelectionChange(rows: CheckinTaskCompletionRow[]) {
  selectedRows.value = rows
}

function openAttendanceDialog() {
  attendanceForm.class_id = selectedClassId.value || classOptions.value[0]?.value || 0
  attendanceForm.title = ''
  attendanceForm.start_at = localInput(new Date())
  const end = new Date(Date.now() + 2 * 3600 * 1000)
  attendanceForm.end_at = localInput(end)
  attendanceForm.late_after_at = ''
  attendanceDialog.value = true
}

async function createAttendance() {
  if (!attendanceForm.class_id) return ElMessage.warning('请选择班级')
  if (!attendanceForm.title.trim()) return ElMessage.warning('请填写签到名称')
  if (!attendanceForm.start_at || !attendanceForm.end_at) return ElMessage.warning('请设置签到时段')
  savingAttendance.value = true
  try {
    await teacherApi.post('/learning/checkin/manage/attendance', {
      class_id: attendanceForm.class_id,
      title: attendanceForm.title.trim(),
      start_at: toIso(attendanceForm.start_at),
      end_at: toIso(attendanceForm.end_at),
      late_after_at: attendanceForm.late_after_at ? toIso(attendanceForm.late_after_at) : null,
    })
    ElMessage.success('签到已开启，签到码已生成')
    attendanceDialog.value = false
    await refresh()
  } catch (error: any) {
    ElMessage.error(errorText(error, '发起签到失败'))
  } finally {
    savingAttendance.value = false
  }
}

async function openLive(sessionId: number) {
  liveSessionId.value = sessionId
  liveDialog.value = true
  await loadLive()
}

async function loadLive() {
  if (!liveSessionId.value) return
  try {
    const { data } = await teacherApi.get<ApiEnvelope<AttendanceLive>>(
      `/learning/checkin/manage/attendance/${liveSessionId.value}/live`,
    )
    live.value = data.data
  } catch (error: any) {
    ElMessage.error(errorText(error, '实时出勤加载失败'))
    liveDialog.value = false
  }
}

async function closeAttendance(session: AttendanceSessionItem) {
  try {
    await ElMessageBox.confirm(
      `结束后未签到的学生将记为缺勤，且签到码立即失效。确定结束「${session.title}」吗？`,
      '结束签到',
      { type: 'warning' },
    )
    await teacherApi.post(`/learning/checkin/manage/attendance/${session.id}/close`)
    ElMessage.success('签到已结束')
    await refresh()
    if (liveDialog.value) await loadLive()
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorText(error, '结束签到失败'))
  }
}

function openManual(row: { student_user_id: number; student_name: string; status: string }) {
  manualForm.student_user_id = row.student_user_id
  manualForm.student_name = row.student_name
  manualForm.status = row.status === 'missing' ? 'present' : (row.status as typeof manualForm.status)
  manualForm.reason = ''
  manualForm.note = ''
  manualDialog.value = true
}

async function submitManual() {
  if (!manualForm.reason.trim()) return ElMessage.warning('人工调整必须填写原因')
  try {
    await teacherApi.post(
      `/learning/checkin/manage/attendance/${liveSessionId.value}/students/${manualForm.student_user_id}`,
      { status: manualForm.status, reason: manualForm.reason.trim(), note: manualForm.note.trim() },
    )
    ElMessage.success('出勤结果已更新并记录审计日志')
    manualDialog.value = false
    await loadLive()
    await refresh()
  } catch (error: any) {
    ElMessage.error(errorText(error, '人工登记失败'))
  }
}

async function copyToken(session: AttendanceSessionItem) {
  if (!session.token) return
  try {
    await navigator.clipboard.writeText(session.token)
    ElMessage.success('签到令牌已复制，可用于扫码/链接签到')
  } catch {
    ElMessage.warning('复制失败，请手动选择令牌文本')
  }
}

function classStatRows(): ClassCheckinStat[] {
  return overview.value?.classes || []
}

onMounted(refresh)
</script>

<template>
  <div class="manage-page" v-loading="loading">
    <header class="manage-hero">
      <div>
        <span class="eyebrow">TEACHING CHECK-IN</span>
        <h1>学习打卡与课堂签到管理</h1>
        <p>发布打卡任务、查看真实完成情况、审核学习成果并发起课堂签到；所有操作仅作用于本人班级。</p>
      </div>
      <div class="hero-actions">
        <el-select v-model="selectedClassId" placeholder="全部班级" clearable style="width:180px" @change="refresh">
          <el-option label="全部班级" :value="0" />
          <el-option v-for="item in classOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-button @click="refresh">刷新</el-button>
      </div>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false">
      <el-button @click="refresh">重试</el-button>
    </el-alert>

    <section class="kpi-grid">
      <article><span>我的班级</span><strong>{{ overview?.class_count ?? 0 }}</strong></article>
      <article><span>进行中任务</span><strong>{{ overview?.active_task_count ?? 0 }}</strong></article>
      <article><span>待审核提交</span><strong>{{ overview?.pending_review_count ?? 0 }}</strong></article>
      <article><span>今日签到</span><strong>{{ overview?.today_attendance_count ?? 0 }}</strong></article>
      <article><span>未完成学生</span><strong>{{ overview?.overdue_student_count ?? 0 }}</strong></article>
    </section>

    <el-tabs v-model="activeTab" class="manage-tabs">
      <el-tab-pane label="打卡任务" name="tasks">
        <article class="panel">
          <div class="panel-title">
            <div><span class="eyebrow">TASKS</span><h2>打卡任务</h2></div>
            <el-button type="primary" @click="openTaskDialog()">新建打卡任务</el-button>
          </div>
          <el-table :data="filteredTasks" stripe empty-text="还没有打卡任务">
            <el-table-column prop="title" label="任务" min-width="180" />
            <el-table-column prop="class_name" label="班级" width="140" />
            <el-table-column label="频率" width="110"><template #default="{ row }">{{ freqLabels[row.frequency] }}</template></el-table-column>
            <el-table-column label="时间" min-width="190">
              <template #default="{ row }">{{ formatTime(row.start_at) }} 至 {{ formatTime(row.end_at) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><el-tag :type="tagType(row.status)" effect="light">{{ label(row.status) }}</el-tag></template>
            </el-table-column>
            <el-table-column label="完成率" width="110">
              <template #default="{ row }">{{ row.completion_rate === null ? '暂无数据' : `${row.completion_rate}%` }}</template>
            </el-table-column>
            <el-table-column label="待审核" width="90"><template #default="{ row }">{{ row.pending_review_count }}</template></el-table-column>
            <el-table-column label="操作" min-width="260" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.status === 'draft' || row.status === 'published'" link type="primary" @click="openTaskDialog(row)">编辑</el-button>
                <el-button v-if="row.status === 'draft'" link type="primary" @click="taskAction(row, 'publish')">发布</el-button>
                <el-button v-if="row.status === 'published'" link type="warning" @click="taskAction(row, 'close')">结束</el-button>
                <el-button v-if="row.status === 'published' || row.status === 'draft'" link type="danger" @click="taskAction(row, 'cancel')">取消</el-button>
                <el-button link @click="activeTab = 'review'; loadCompletion(row.id)">完成情况</el-button>
                <el-button v-if="row.status === 'published'" link @click="remind(row)">提醒</el-button>
              </template>
            </el-table-column>
          </el-table>
        </article>
      </el-tab-pane>

      <el-tab-pane label="完成与审核" name="review">
        <article class="panel">
          <div class="panel-title">
            <div><span class="eyebrow">REVIEW</span><h2>学生完成情况</h2></div>
            <div class="inline">
              <el-select v-model="completionTaskId" placeholder="选择任务" style="width:240px" @change="(id) => loadCompletion(id)">
                <el-option v-for="item in filteredTasks" :key="item.id" :label="`${item.title}（${item.class_name}）`" :value="item.id" />
              </el-select>
              <el-select v-if="completion" v-model="completionPeriod" style="width:150px" @change="(value) => loadCompletion(completionTaskId, value)">
                <el-option v-for="period in completion.periods" :key="period.period_key" :label="period.period_key" :value="period.period_key" />
              </el-select>
            </div>
          </div>
          <div v-if="completion" class="completion-head">
            <div><strong>{{ completion.task.title }}</strong><small>{{ completion.task.class_name }} · {{ completion.period_key }} · 应完成 {{ completion.task.expected_count }} 人次 · 完成率 {{ rate(completion.task.completion_rate) }}</small></div>
            <div class="inline">
              <el-button :disabled="!selectedRows.length" type="success" plain @click="openReview(selectedRows[0], true)">批量通过</el-button>
              <el-button :disabled="!selectedRows.length" type="warning" plain @click="openReview(selectedRows[0], true)">批量退回</el-button>
            </div>
          </div>
          <el-table
            v-loading="completionLoading"
            :data="reviewableSubmissions"
            stripe
            empty-text="该周期暂无学生提交"
            @selection-change="onSelectionChange"
          >
            <el-table-column type="selection" width="46" />
            <el-table-column prop="student_name" label="学生" width="140" />
            <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="tagType(row.state)" effect="light">{{ label(row.state) }}</el-tag></template></el-table-column>
            <el-table-column label="提交时间" width="150"><template #default="{ row }">{{ formatTime(row.submitted_at) }}</template></el-table-column>
            <el-table-column prop="content" label="学习成果" min-width="220" show-overflow-tooltip />
            <el-table-column label="评分" width="80"><template #default="{ row }">{{ row.score ?? '暂无' }}</template></el-table-column>
            <el-table-column prop="review_comment" label="教师评语" min-width="160" show-overflow-tooltip />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }"><el-button link type="primary" @click="openReview(row)">审核 / 评价</el-button></template>
            </el-table-column>
          </el-table>
          <el-empty v-if="completion && !reviewableSubmissions.length" description="该周期还没有学生提交，可发送提醒" />
        </article>
      </el-tab-pane>

      <el-tab-pane label="课堂签到" name="attendance">
        <article class="panel">
          <div class="panel-title">
            <div><span class="eyebrow">ATTENDANCE</span><h2>课堂签到</h2></div>
            <el-button type="primary" @click="openAttendanceDialog">发起签到</el-button>
          </div>
          <el-table :data="filteredSessions" stripe empty-text="还没有发起过课堂签到">
            <el-table-column prop="title" label="签到" min-width="160" />
            <el-table-column prop="class_name" label="班级" width="130" />
            <el-table-column label="签到码" width="110"><template #default="{ row }"><strong>{{ row.code || '—' }}</strong></template></el-table-column>
            <el-table-column label="时段" min-width="180"><template #default="{ row }">{{ formatTime(row.start_at) }} 至 {{ formatTime(row.end_at) }}</template></el-table-column>
            <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status === 'open' ? 'success' : 'info'" effect="light">{{ row.status === 'open' ? '签到中' : '已结束' }}</el-tag></template></el-table-column>
            <el-table-column label="出勤" width="150"><template #default="{ row }">正常 {{ row.checked_in_count }} / 迟到 {{ row.late_count }}</template></el-table-column>
            <el-table-column label="缺勤" width="90"><template #default="{ row }">{{ row.absent_count }}</template></el-table-column>
            <el-table-column label="操作" min-width="240" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openLive(row.id)">实时出勤</el-button>
                <el-button link @click="copyToken(row)">复制令牌</el-button>
                <el-button v-if="row.status === 'open'" link type="warning" @click="closeAttendance(row)">结束签到</el-button>
              </template>
            </el-table-column>
          </el-table>
        </article>
      </el-tab-pane>

      <el-tab-pane label="数据概览" name="dashboard">
        <div class="dashboard-grid">
          <article class="panel">
            <div class="panel-title"><div><span class="eyebrow">BY CLASS</span><h2>班级完成与出勤</h2></div></div>
            <el-table :data="classStatRows()" stripe empty-text="暂无班级数据">
              <el-table-column prop="class_name" label="班级" min-width="140" />
              <el-table-column prop="student_count" label="学生" width="80" />
              <el-table-column label="任务完成率" width="130"><template #default="{ row }">{{ rate(row.task_completion_rate) }}</template></el-table-column>
              <el-table-column label="课堂出勤率" width="130"><template #default="{ row }">{{ rate(row.attendance_rate) }}</template></el-table-column>
              <el-table-column prop="pending_review" label="待审核" width="90" />
              <el-table-column prop="low_participation" label="零完成学生" width="110" />
            </el-table>
          </article>
          <article class="panel">
            <div class="panel-title"><div><span class="eyebrow">TREND</span><h2>近 7 天参与趋势</h2></div></div>
            <div class="trend">
              <div v-for="point in overview?.trend || []" :key="point.date" class="trend-row">
                <span>{{ point.date.slice(5) }}</span>
                <div class="bars">
                  <i class="bar approved" :style="{ width: `${Math.min(100, point.approved * 12)}%` }" :title="`已通过 ${point.approved}`"></i>
                  <i class="bar submitted" :style="{ width: `${Math.min(100, point.submitted * 12)}%` }" :title="`待审核 ${point.submitted}`"></i>
                  <i class="bar attendance" :style="{ width: `${Math.min(100, point.attendance * 12)}%` }" :title="`出勤 ${point.attendance}`"></i>
                </div>
                <small>{{ point.approved }} / {{ point.submitted }} / {{ point.attendance }}</small>
              </div>
            </div>
            <div class="legend"><span><i class="bar approved"></i>已通过</span><span><i class="bar submitted"></i>待审核</span><span><i class="bar attendance"></i>出勤</span></div>
          </article>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="taskDialog" :title="editingTaskId ? '编辑打卡任务' : '新建打卡任务'" width="680px" destroy-on-close>
      <el-form :model="taskForm" label-position="top" class="task-form">
        <el-form-item label="发布班级" required>
          <el-select v-model="taskForm.class_id" placeholder="选择班级">
            <el-option v-for="item in classOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务名称" required><el-input v-model="taskForm.title" maxlength="160" placeholder="例如：二叉树遍历每日练习" /></el-form-item>
        <el-form-item label="学习目标"><el-input v-model="taskForm.goal" placeholder="例如：掌握前序、中序、后序遍历" /></el-form-item>
        <el-form-item label="任务说明"><el-input v-model="taskForm.description" type="textarea" :rows="3" placeholder="具体要求、提交内容与验收标准" /></el-form-item>
        <el-form-item label="重复频率">
          <el-radio-group v-model="taskForm.frequency">
            <el-radio value="once">单次</el-radio>
            <el-radio value="daily">每日</el-radio>
            <el-radio value="weekly">每周</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="taskForm.frequency === 'weekly'" label="每周重复日">
          <el-checkbox-group v-model="taskForm.weekly_days">
            <el-checkbox v-for="(name, index) in ['周一', '周二', '周三', '周四', '周五', '周六', '周日']" :key="name" :value="index + 1">{{ name }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="开始时间" required><el-date-picker v-model="taskForm.start_at" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="开始时间" /></el-form-item>
        <el-form-item label="结束时间" required><el-date-picker v-model="taskForm.end_at" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="结束时间" /></el-form-item>
        <el-form-item label="每日截止时刻"><el-time-picker v-model="taskForm.due_time" value-format="HH:mm" format="HH:mm" placeholder="23:59" /></el-form-item>
        <el-form-item label="审核方式">
          <el-radio-group v-model="taskForm.review_mode">
            <el-radio value="manual">教师人工审核</el-radio>
            <el-radio value="auto">自动验收</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="其他要求">
          <el-checkbox v-model="taskForm.allow_late">允许逾期补交</el-checkbox>
          <el-checkbox v-model="taskForm.require_attachment">必须上传附件</el-checkbox>
        </el-form-item>
        <el-form-item label="关联知识点（逗号分隔）"><el-input v-model="taskForm.knowledge_text" placeholder="二叉树、遍历、递归" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialog = false">取消</el-button>
        <el-button :loading="savingTask" @click="createTask(false)">{{ editingTaskId ? '保存修改' : '保存草稿' }}</el-button>
        <el-button type="primary" :loading="savingTask" @click="createTask(true)">{{ editingTaskId ? '保存并发布' : '创建并发布' }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="reviewDialog" :title="reviewBatch ? '批量审核打卡提交' : '审核打卡提交'" width="520px">
      <el-form :model="reviewForm" label-position="top">
        <el-form-item label="审核结果">
          <el-radio-group v-model="reviewForm.verdict">
            <el-radio value="approve">通过</el-radio>
            <el-radio value="return">退回补交</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="评分（可选）"><el-input-number v-model="reviewForm.score" :min="0" :max="100" /></el-form-item>
        <el-form-item :label="reviewForm.verdict === 'return' ? '退回原因（必填）' : '教师评语'">
          <el-input v-model="reviewForm.comment" type="textarea" :rows="4" placeholder="填写具体反馈，学生端会收到通知" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialog = false">取消</el-button>
        <el-button type="primary" :loading="reviewSubmitting" @click="submitReview">提交审核</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="attendanceDialog" title="发起课堂签到" width="520px">
      <el-form :model="attendanceForm" label-position="top">
        <el-form-item label="班级" required>
          <el-select v-model="attendanceForm.class_id" placeholder="选择班级">
            <el-option v-for="item in classOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="签到名称" required><el-input v-model="attendanceForm.title" placeholder="例如：第 5 次课签到" /></el-form-item>
        <el-form-item label="开始时间" required><el-date-picker v-model="attendanceForm.start_at" type="datetime" value-format="YYYY-MM-DD HH:mm" /></el-form-item>
        <el-form-item label="结束时间" required><el-date-picker v-model="attendanceForm.end_at" type="datetime" value-format="YYYY-MM-DD HH:mm" /></el-form-item>
        <el-form-item label="迟到判定时间（可选）"><el-date-picker v-model="attendanceForm.late_after_at" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="不填则按签到时段中点判定" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="attendanceDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingAttendance" @click="createAttendance">开启签到</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="liveDialog" title="实时出勤" width="820px" destroy-on-close>
      <div v-if="live" class="live-body">
        <div class="live-head">
          <div>
            <strong>{{ live.session.title }}</strong>
            <small>{{ live.session.class_name }} · {{ formatTime(live.session.start_at) }} 至 {{ formatTime(live.session.end_at) }}</small>
          </div>
          <div class="code-box">
            <span>签到码</span>
            <strong>{{ live.session.code }}</strong>
            <el-button link type="primary" @click="copyToken(live.session)">复制令牌</el-button>
          </div>
        </div>
        <div class="attendance-summary">
          <span>应到 {{ live.session.student_count }}</span>
          <span>正常 {{ live.session.checked_in_count }}</span>
          <span>迟到 {{ live.session.late_count }}</span>
          <span>请假 {{ live.session.leave_count }}</span>
          <span>缺勤 {{ live.session.absent_count }}</span>
          <span>未签到 {{ live.session.missing_count }}</span>
        </div>
        <el-table :data="live.rows" stripe max-height="420">
          <el-table-column prop="student_name" label="学生" width="140" />
          <el-table-column label="出勤" width="110"><template #default="{ row }"><el-tag :type="tagType(row.status)" effect="light">{{ label(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="签到时间" width="160"><template #default="{ row }">{{ formatTime(row.checked_in_at) }}</template></el-table-column>
          <el-table-column prop="source" label="来源" width="110" />
          <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip />
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }"><el-button link type="primary" @click="openManual(row)">人工登记</el-button></template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="liveDialog = false">关闭</el-button>
        <el-button v-if="live?.session.status === 'open'" type="warning" @click="closeAttendance(live.session)">结束签到</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="manualDialog" :title="`人工登记：${manualForm.student_name}`" width="460px">
      <el-form :model="manualForm" label-position="top">
        <el-form-item label="出勤结果">
          <el-select v-model="manualForm.status">
            <el-option label="正常" value="present" />
            <el-option label="迟到" value="late" />
            <el-option label="请假" value="leave" />
            <el-option label="缺勤" value="absent" />
            <el-option label="待确认" value="pending" />
          </el-select>
        </el-form-item>
        <el-form-item label="调整原因（必填）"><el-input v-model="manualForm.reason" type="textarea" :rows="2" placeholder="例如：学生出示病假条" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="manualForm.note" placeholder="可选" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="manualDialog = false">取消</el-button>
        <el-button type="primary" @click="submitManual">保存并记录审计</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.manage-page{display:grid;gap:20px}
.manage-hero{display:flex;flex-wrap:wrap;justify-content:space-between;gap:18px;padding:28px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel)),var(--panel));box-shadow:var(--shadow-sm)}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}
h1,h2,p{margin:0}
h1{font-size:28px;margin:5px 0 8px}
.manage-hero p{color:var(--muted);line-height:1.7;max-width:760px}
.hero-actions,.inline{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}
.kpi-grid article{padding:16px;border:1px solid var(--line);border-radius:16px;background:var(--panel);box-shadow:var(--shadow-sm);display:grid;gap:4px}
.kpi-grid span{font-size:12px;color:var(--muted)}
.kpi-grid strong{font-size:24px}
.manage-tabs{border:1px solid var(--line);border-radius:20px;background:var(--panel);padding:8px 20px 20px;box-shadow:var(--shadow-sm)}
.panel{padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--panel);display:grid;gap:14px}
.panel-title{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
.panel-title h2{font-size:18px;margin-top:4px}
.completion-head{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--surface-soft)}
.completion-head strong{display:block}
.completion-head small{color:var(--muted)}
.task-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}
.task-form .el-form-item:nth-child(2),.task-form .el-form-item:nth-child(3),.task-form .el-form-item:nth-child(4){grid-column:span 2}
.dashboard-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:16px}
.trend{display:grid;gap:8px}
.trend-row{display:grid;grid-template-columns:56px 1fr 88px;align-items:center;gap:10px;font-size:12px}
.trend-row small{color:var(--muted);text-align:right}
.bars{display:grid;gap:3px}
.bar{display:block;height:7px;border-radius:999px;min-width:2px;background:var(--line)}
.bar.approved{background:#22c55e}
.bar.submitted{background:#f59e0b}
.bar.attendance{background:#3b82f6}
.legend{display:flex;gap:14px;font-size:12px;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend .bar{width:14px;height:7px}
.live-body{display:grid;gap:14px}
.live-head{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;align-items:center}
.live-head small{display:block;color:var(--muted)}
.code-box{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:12px;background:var(--accent-soft)}
.code-box span{font-size:12px;color:var(--muted)}
.code-box strong{font-size:22px;letter-spacing:.14em}
.attendance-summary{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted)}
@media (max-width: 1100px){
  .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .dashboard-grid{grid-template-columns:1fr}
}
@media (max-width: 760px){
  .task-form{grid-template-columns:1fr}
  .task-form .el-form-item:nth-child(n){grid-column:auto}
}
</style>
