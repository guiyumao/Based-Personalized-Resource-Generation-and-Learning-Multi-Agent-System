<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  teacherApi,
  type ApiEnvelope,
  type AttendanceSessionItem,
  type CheckinHome,
  type CheckinSubmissionItem,
  type CheckinTaskDetail,
  type CheckinTaskItem,
  type DailyCheckinItem,
  type PlatformCheckinCalendar,
  type PlatformCheckinStatus,
} from '../../api'

type TabKey = 'daily' | 'tasks' | 'attendance' | 'records'

const route = useRoute()
const loading = ref(false)
const activeTab = ref<TabKey>('daily')
const daily = ref<PlatformCheckinStatus | null>(null)
const calendar = ref<PlatformCheckinCalendar | null>(null)
const history = ref<DailyCheckinItem[]>([])
const home = ref<CheckinHome | null>(null)
const tasks = ref<CheckinTaskItem[]>([])
const submissions = ref<CheckinSubmissionItem[]>([])
const attendance = ref<AttendanceSessionItem[]>([])
const loadError = ref('')

const today = new Date()
const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
const month = ref(todayKey.slice(0, 7))

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

const checkinDialog = ref(false)
const saving = ref(false)
const checkinForm = reactive({ goal: '', reflection: '' })

const taskDialog = ref(false)
const taskDetail = ref<CheckinTaskDetail | null>(null)
const submitPeriod = ref('')
const submitContent = ref('')
const submitting = ref(false)
const detailLoading = ref(false)

const attendanceCode = ref('')
const checking = ref(false)

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
  if (value === 'approved' || value === 'present') return 'success'
  if (value === 'returned' || value === 'overdue' || value === 'absent') return 'danger'
  if (value === 'late' || value === 'pending_review' || value === 'leave') return 'warning'
  return 'info'
}

const checkedDates = computed(() => new Set((calendar.value?.days || []).map((item) => item.date)))

const weekStrip = computed(() => {
  const base = new Date(today)
  const offset = (base.getDay() + 6) % 7
  const monday = new Date(base.getFullYear(), base.getMonth(), base.getDate() - offset)
  return Array.from({ length: 7 }, (_, index) => {
    const day = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + index)
    const key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
    return { key, label: ['一', '二', '三', '四', '五', '六', '日'][index], checked: checkedDates.value.has(key), isToday: key === todayKey }
  })
})

const calendarCells = computed<Array<{ day: number; key: string; checked: boolean; data: PlatformCheckinCalendar['days'][number] | null } | null>>(() => {
  if (!calendar.value) return []
  const [year, monthNo] = calendar.value.month.split('-').map(Number)
  const first = new Date(year, monthNo - 1, 1)
  const offset = (first.getDay() + 6) % 7
  const total = new Date(year, monthNo, 0).getDate()
  const dayMap = new Map(calendar.value.days.map((item) => [item.date, item]))
  const cells: Array<{ day: number; key: string; checked: boolean; data: PlatformCheckinCalendar['days'][number] | null } | null> = []
  for (let index = 0; index < offset; index += 1) cells.push(null)
  for (let day = 1; day <= total; day += 1) {
    const key = `${year}-${String(monthNo).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    const data = dayMap.get(key) || null
    cells.push({ day, key, checked: Boolean(data?.checked_in), data })
  }
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
})

const availableAttendance = computed(() => attendance.value.filter((item) => item.status === 'open'))
const weekProgress = computed(() => {
  const done = daily.value?.week_days ?? 0
  const goal = daily.value?.week_goal || 7
  return Math.min(100, Math.round((done / goal) * 100))
})

async function loadDaily() {
  const [statusRes, historyRes] = await Promise.all([
    teacherApi.get<ApiEnvelope<PlatformCheckinStatus>>('/learning/checkin/daily'),
    teacherApi.get<ApiEnvelope<DailyCheckinItem[]>>('/learning/checkin/daily/history'),
  ])
  daily.value = statusRes.data.data
  history.value = historyRes.data.data
  await loadCalendar()
}

async function loadCalendar() {
  try {
    const { data } = await teacherApi.get<ApiEnvelope<PlatformCheckinCalendar>>(
      '/learning/checkin/daily/calendar',
      { params: { month: month.value } },
    )
    calendar.value = data.data
  } catch {
    calendar.value = null
  }
}

watch(month, loadCalendar)

async function refresh() {
  loadError.value = ''
  loading.value = true
  try {
    const [dailyRes, homeRes, taskRes, attendanceRes, submissionRes] = await Promise.all([
      teacherApi.get<ApiEnvelope<PlatformCheckinStatus>>('/learning/checkin/daily'),
      teacherApi.get<ApiEnvelope<CheckinHome>>('/learning/checkin/home'),
      teacherApi.get<ApiEnvelope<CheckinTaskItem[]>>('/learning/checkin/tasks'),
      teacherApi.get<ApiEnvelope<AttendanceSessionItem[]>>('/learning/checkin/attendance'),
      teacherApi.get<ApiEnvelope<CheckinSubmissionItem[]>>('/learning/checkin/submissions/me'),
    ])
    daily.value = dailyRes.data.data
    home.value = homeRes.data.data
    tasks.value = taskRes.data.data
    attendance.value = attendanceRes.data.data
    submissions.value = submissionRes.data.data
    await loadDaily()
  } catch (error: any) {
    loadError.value = errorText(error, '学习数据加载失败')
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

function openCheckin() {
  checkinForm.goal = daily.value?.today_checkin?.goal || ''
  checkinForm.reflection = daily.value?.today_checkin?.reflection || ''
  checkinDialog.value = true
}

async function submitCheckin() {
  saving.value = true
  try {
    const { data } = await teacherApi.post<ApiEnvelope<PlatformCheckinStatus>>('/learning/checkin/daily', {
      goal: checkinForm.goal.trim(),
      reflection: checkinForm.reflection.trim(),
    })
    daily.value = data.data
    checkinDialog.value = false
    ElMessage.success(data.data.today_checkin ? '今日平台学习打卡成功' : '打卡已更新')
    await loadDaily()
  } catch (error: any) {
    ElMessage.error(errorText(error, '打卡失败'))
  } finally {
    saving.value = false
  }
}

async function openTask(item: CheckinTaskItem) {
  taskDialog.value = true
  detailLoading.value = true
  taskDetail.value = null
  try {
    const { data } = await teacherApi.get<ApiEnvelope<CheckinTaskDetail>>(`/learning/checkin/tasks/${item.id}`)
    taskDetail.value = data.data
    const available = data.data.periods.filter((period) => period.state !== 'approved')
    submitPeriod.value = data.data.today_period || available[available.length - 1]?.period_key || ''
    submitContent.value = data.data.my_submission?.content || ''
  } catch (error: any) {
    ElMessage.error(errorText(error, '任务详情加载失败'))
    taskDialog.value = false
  } finally {
    detailLoading.value = false
  }
}

async function submitTask() {
  const detail = taskDetail.value
  if (!detail) return
  if (!submitContent.value.trim()) return ElMessage.warning('请填写学习成果或总结')
  if (!submitPeriod.value) return ElMessage.warning('请选择要完成的打卡周期')
  submitting.value = true
  try {
    await teacherApi.post(`/learning/checkin/tasks/${detail.id}/submit`, {
      content: submitContent.value.trim(),
      period_key: submitPeriod.value,
    })
    ElMessage.success(detail.review_mode === 'auto' ? '已提交并自动通过' : '已提交，等待教师审核')
    taskDialog.value = false
    await refresh()
  } catch (error: any) {
    ElMessage.error(errorText(error, '提交失败'))
  } finally {
    submitting.value = false
  }
}

async function checkinByCode() {
  const code = attendanceCode.value.trim()
  if (!code) return ElMessage.warning('请输入教师公布的签到码')
  checking.value = true
  try {
    const { data } = await teacherApi.post<ApiEnvelope<AttendanceSessionItem>>('/learning/checkin/attendance/checkin', { code })
    ElMessage.success(`签到成功：${label(data.data.my_record?.status)}`)
    attendanceCode.value = ''
    await refresh()
  } catch (error: any) {
    ElMessage.error(errorText(error, '签到失败'))
  } finally {
    checking.value = false
  }
}

async function focusFromQuery() {
  const taskId = Number(route.query.task)
  if (taskId) {
    const target = tasks.value.find((item) => item.id === taskId)
    if (target) {
      activeTab.value = 'tasks'
      await openTask(target)
    }
  }
  if (route.query.attendance) activeTab.value = 'attendance'
}

onMounted(async () => {
  await refresh()
  await focusFromQuery()
})
</script>

<template>
  <div class="checkin-page" v-loading="loading">
    <header class="checkin-hero">
      <div class="hero-copy">
        <span class="eyebrow">PLATFORM CHECK-IN</span>
        <h1>平台学习打卡</h1>
        <p>记录你每天在平台上的学习参与。平台打卡完全独立于课堂与考勤：不需要加入课堂，也不代表学习时长或知识掌握度。</p>
      </div>
      <div class="hero-stats">
        <article><strong>{{ daily?.current_streak ?? 0 }}</strong><span>连续打卡 / 天</span></article>
        <article><strong>{{ daily?.total_days ?? 0 }}</strong><span>累计打卡 / 天</span></article>
        <article><strong>{{ daily?.week_days ?? 0 }}/{{ daily?.week_goal ?? 7 }}</strong><span>本周目标</span></article>
      </div>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false">
      <el-button @click="refresh">重试加载</el-button>
    </el-alert>

    <el-tabs v-model="activeTab" class="checkin-tabs">
      <el-tab-pane label="平台打卡" name="daily">
        <section class="daily-card" :class="{ 'is-done': daily?.checked_in }">
          <div>
            <span class="eyebrow">{{ daily?.checked_in ? 'TODAY CHECKED IN' : 'READY TO CHECK IN' }}</span>
            <h2>{{ daily?.checked_in ? '今天已完成平台学习打卡' : '今天还没有打卡' }}</h2>
            <p>{{ daily?.today_checkin?.goal || '点击打卡，确认你今天参与了平台学习。可填写今日学习目标与感想。' }}</p>
            <p v-if="daily?.today_checkin?.reflection" class="muted">打卡感想：{{ daily.today_checkin.reflection }}</p>
          </div>
          <div class="daily-action">
            <el-button type="primary" size="large" @click="openCheckin">
              {{ daily?.checked_in ? '更新今日打卡' : '立即打卡' }}
            </el-button>
            <small>{{ daily?.today }} · 每个自然日仅记录一次</small>
          </div>
        </section>

        <section class="stat-grid">
          <article class="stat-card"><span>本周已打卡</span><strong>{{ daily?.week_days ?? 0 }}</strong><small>目标 {{ daily?.week_goal ?? 7 }} 天</small></article>
          <article class="stat-card"><span>本月打卡</span><strong>{{ daily?.month_days ?? 0 }}</strong><small>自然日</small></article>
          <article class="stat-card"><span>今日状态</span><strong>{{ daily?.checked_in ? '已打卡' : '未打卡' }}</strong><small>{{ daily?.today }}</small></article>
          <article class="stat-card"><span>本周进度</span><strong>{{ weekProgress }}%</strong><el-progress :percentage="weekProgress" :show-text="false" /></article>
        </section>

        <div class="overview-grid">
          <article class="panel">
            <div class="panel-title"><div><span class="eyebrow">THIS WEEK</span><h2>本周打卡</h2></div></div>
            <div class="week-strip">
              <div v-for="day in weekStrip" :key="day.key" class="week-day" :class="{ checked: day.checked, today: day.isToday }">
                <span>{{ day.label }}</span>
                <strong>{{ day.checked ? '✓' : '—' }}</strong>
                <small>{{ day.key.slice(5) }}</small>
              </div>
            </div>
            <p class="hint">平台打卡仅记录“当天是否参与平台学习”，不统计分钟数，也不等同于完成课堂任务。</p>
          </article>

          <article class="panel">
            <div class="panel-title">
              <div><span class="eyebrow">CALENDAR</span><h2>打卡日历</h2></div>
              <el-date-picker v-model="month" type="month" value-format="YYYY-MM" placeholder="选择月份" />
            </div>
            <div class="calendar-grid">
              <span v-for="name in ['一', '二', '三', '四', '五', '六', '日']" :key="name" class="weekday">{{ name }}</span>
              <div v-for="(cell, index) in calendarCells" :key="index" class="calendar-cell" :class="{ empty: !cell, checked: cell?.checked }">
                <template v-if="cell">
                  <span class="day-number">{{ cell.day }}</span>
                  <i v-if="cell.checked" class="dot"></i>
                  <small v-if="cell.data?.goal">{{ cell.data.goal }}</small>
                </template>
              </div>
            </div>
          </article>
        </div>

        <article class="panel">
          <div class="panel-title"><div><span class="eyebrow">HISTORY</span><h2>打卡历史</h2></div></div>
          <div class="history-list">
            <div v-for="item in history" :key="item.id" class="history-row">
              <strong>{{ item.checkin_date }}</strong>
              <span>{{ formatTime(item.checkin_at) }}</span>
              <p>{{ item.goal || '未填写学习目标' }}</p>
              <p v-if="item.reflection" class="muted">{{ item.reflection }}</p>
            </div>
          </div>
          <el-empty v-if="!history.length" description="还没有平台打卡记录，从今天开始吧" />
        </article>
      </el-tab-pane>

      <el-tab-pane label="课堂任务" name="tasks">
        <article class="panel">
          <div class="panel-title"><div><span class="eyebrow">CLASS TASKS</span><h2>教师布置的课堂任务</h2></div><el-button plain @click="refresh">刷新</el-button></div>
          <p class="hint">课堂任务来自你已加入的课堂，与平台打卡分别统计。</p>
          <div class="task-grid">
            <div v-for="item in tasks" :key="item.id" class="task-card">
              <div class="task-head">
                <div><span class="pill">{{ item.class_name }}</span><h3>{{ item.title }}</h3></div>
                <el-tag :type="tagType(item.my_state)" effect="light">{{ label(item.my_state) }}</el-tag>
              </div>
              <p class="muted">{{ item.goal || item.description || '教师未填写任务说明' }}</p>
              <small>截止 {{ formatTime(item.end_at) }} · {{ item.frequency === 'once' ? '单次' : item.frequency === 'daily' ? '每日' : '每周' }}</small>
              <div v-if="item.my_submission" class="submission-box">
                <small>我的提交（v{{ item.my_submission.version }}）· {{ formatTime(item.my_submission.submitted_at) }}</small>
                <p>{{ item.my_submission.content }}</p>
                <p v-if="item.my_submission.review_comment" class="muted">教师评语：{{ item.my_submission.review_comment }}</p>
              </div>
              <div class="task-actions">
                <span class="muted">完成率 {{ item.completion_rate === null ? '暂无数据' : `${item.completion_rate}%` }}</span>
                <el-button type="primary" :disabled="!item.can_submit && !item.my_submission" @click="openTask(item)">
                  {{ item.can_submit ? '提交任务' : '查看详情' }}
                </el-button>
              </div>
            </div>
          </div>
          <el-empty v-if="!tasks.length" description="你还没有加入课堂，或教师尚未发布课堂任务" />
        </article>
      </el-tab-pane>

      <el-tab-pane label="课堂签到" name="attendance">
        <article class="panel">
          <div class="panel-title"><div><span class="eyebrow">IN CLASS</span><h2>课堂签到</h2></div><el-button plain @click="refresh">刷新</el-button></div>
          <p class="hint">课堂签到是班级出勤记录，与平台学习打卡无关。</p>
          <div class="inline-form">
            <el-input v-model="attendanceCode" placeholder="输入教师公布的签到码" maxlength="64" @keyup.enter="checkinByCode" />
            <el-button type="primary" :loading="checking" @click="checkinByCode">签到</el-button>
          </div>
          <div class="card-list">
            <div v-for="item in attendance" :key="item.id" class="record-card">
              <div class="record-head">
                <strong>{{ item.title }}</strong>
                <el-tag :type="item.status === 'open' ? 'success' : 'info'" effect="light">{{ item.status === 'open' ? '签到中' : '已结束' }}</el-tag>
              </div>
              <small>{{ item.class_name }} · {{ formatTime(item.start_at) }} 至 {{ formatTime(item.end_at) }}</small>
              <div class="attendance-meta"><span>应到 {{ item.student_count }}</span><span>正常 {{ item.checked_in_count }}</span><span>迟到 {{ item.late_count }}</span><span>请假 {{ item.leave_count }}</span></div>
              <p v-if="item.my_record">我的出勤：<el-tag :type="tagType(item.my_record.status)" effect="light">{{ label(item.my_record.status) }}</el-tag></p>
            </div>
          </div>
          <el-empty v-if="!attendance.length" description="暂无课堂签到记录" />
        </article>
      </el-tab-pane>

      <el-tab-pane label="我的提交" name="records">
        <article class="panel">
          <div class="panel-title"><div><span class="eyebrow">SUBMISSIONS</span><h2>课堂任务提交记录</h2></div></div>
          <el-table :data="submissions" stripe empty-text="还没有提交过课堂任务">
            <el-table-column prop="task_title" label="任务" min-width="180" />
            <el-table-column prop="class_name" label="课堂" width="140" />
            <el-table-column prop="period_key" label="周期" width="110" />
            <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="tagType(row.status)" effect="light">{{ label(row.status) }}</el-tag></template></el-table-column>
            <el-table-column label="提交时间" width="150"><template #default="{ row }">{{ formatTime(row.submitted_at) }}</template></el-table-column>
            <el-table-column label="评分" width="90"><template #default="{ row }">{{ row.score ?? '暂无' }}</template></el-table-column>
            <el-table-column prop="review_comment" label="教师反馈" min-width="200" show-overflow-tooltip />
          </el-table>
        </article>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="checkinDialog" :title="daily?.checked_in ? '更新今日打卡' : '平台学习打卡'" width="480px">
      <el-form label-position="top">
        <el-form-item label="今日学习目标（可选）"><el-input v-model="checkinForm.goal" maxlength="500" placeholder="例如：完成数据结构第三章复习" /></el-form-item>
        <el-form-item label="打卡感想（可选）"><el-input v-model="checkinForm.reflection" type="textarea" :rows="3" maxlength="2000" placeholder="记录今天的学习状态" /></el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" title="每个自然日只记录一次打卡；重复提交不会增加天数。" />
      <template #footer>
        <el-button @click="checkinDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCheckin">{{ daily?.checked_in ? '保存' : '确认打卡' }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="taskDialog" :title="taskDetail?.title || '课堂任务'" width="720px" destroy-on-close>
      <div v-if="detailLoading" v-loading="true" class="dialog-loading" />
      <div v-else-if="taskDetail" class="task-detail">
        <div class="detail-meta"><span class="pill">{{ taskDetail.class_name }}</span><el-tag :type="tagType(taskDetail.my_state)" effect="light">{{ label(taskDetail.my_state) }}</el-tag><span class="muted">教师：{{ taskDetail.teacher_name }}</span></div>
        <p v-if="taskDetail.goal"><strong>学习目标：</strong>{{ taskDetail.goal }}</p>
        <p v-if="taskDetail.description"><strong>任务要求：</strong>{{ taskDetail.description }}</p>
        <p class="muted">截止 {{ formatTime(taskDetail.end_at) }} · {{ taskDetail.review_mode === 'auto' ? '自动验收' : '教师审核' }}</p>
        <el-table :data="taskDetail.periods" size="small" max-height="220" empty-text="暂无周期">
          <el-table-column prop="period_key" label="周期" width="120" />
          <el-table-column label="截止" width="160"><template #default="{ row }">{{ formatTime(row.due_at) }}</template></el-table-column>
          <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="tagType(row.state)" effect="light">{{ label(row.state) }}</el-tag></template></el-table-column>
        </el-table>
        <div v-if="taskDetail.my_submission" class="submission-box"><strong>最近提交（v{{ taskDetail.my_submission.version }}）</strong><p>{{ taskDetail.my_submission.content }}</p><p v-if="taskDetail.my_submission.review_comment" class="muted">教师评语：{{ taskDetail.my_submission.review_comment }}</p></div>
        <div v-if="taskDetail.can_submit" class="submit-area">
          <el-form label-position="top">
            <el-form-item label="选择打卡周期"><el-select v-model="submitPeriod"><el-option v-for="period in taskDetail.periods" :key="period.period_key" :label="`${period.period_key}（${label(period.state)}）`" :value="period.period_key" :disabled="period.state === 'approved'" /></el-select></el-form-item>
            <el-form-item label="学习成果 / 总结" required><el-input v-model="submitContent" type="textarea" :rows="5" placeholder="填写完成内容与总结" /></el-form-item>
          </el-form>
          <el-button type="primary" :loading="submitting" @click="submitTask">提交任务</el-button>
        </div>
        <el-alert v-else-if="taskDetail.my_state === 'approved'" type="success" :closable="false" title="该周期已通过审核，不能覆盖提交" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.checkin-page{display:grid;gap:20px}
.checkin-hero{display:flex;flex-wrap:wrap;gap:22px;padding:28px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel)),var(--panel));box-shadow:var(--shadow-sm)}
.hero-copy{flex:1;min-width:260px}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}
h1,h2,h3,p{margin:0}
h1{font-size:30px;margin:5px 0 8px}
.hero-copy p,.muted,.hint{color:var(--muted);line-height:1.7}
.hero-stats{display:flex;gap:12px;flex-wrap:wrap}
.hero-stats article{min-width:104px;padding:14px;border-radius:16px;background:var(--panel-strong);text-align:center}
.hero-stats strong{display:block;font-size:24px}
.hero-stats span{font-size:12px;color:var(--muted)}
.checkin-tabs{border:1px solid var(--line);border-radius:20px;background:var(--panel);padding:8px 20px 20px;box-shadow:var(--shadow-sm)}
.daily-card{display:flex;flex-wrap:wrap;justify-content:space-between;gap:20px;padding:24px;border:1px solid var(--line);border-radius:18px;background:var(--surface-soft);margin-bottom:16px}
.daily-card.is-done{background:linear-gradient(135deg,color-mix(in srgb,#22c55e 14%,var(--panel)),var(--panel))}
.daily-card h2{font-size:20px;margin:5px 0 8px}
.daily-action{display:grid;gap:8px;justify-items:end;align-content:center}
.daily-action small{color:var(--muted);font-size:12px}
.stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:16px}
.stat-card{padding:16px;border:1px solid var(--line);border-radius:16px;background:var(--surface-soft);display:grid;gap:6px}
.stat-card span{font-size:12px;color:var(--muted)}
.stat-card strong{font-size:22px}
.stat-card small{color:var(--muted)}
.overview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:16px}
.panel{padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--panel);display:grid;gap:14px;align-content:start}
.panel-title{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
.panel-title h2{font-size:18px;margin-top:4px}
.week-strip{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}
.week-day{display:grid;justify-items:center;gap:4px;padding:12px 6px;border:1px dashed var(--line);border-radius:12px;background:var(--surface-soft);color:var(--muted)}
.week-day strong{font-size:18px}
.week-day small{font-size:11px}
.week-day.checked{border-style:solid;border-color:#22c55e;background:color-mix(in srgb,#22c55e 12%,var(--panel));color:var(--text)}
.week-day.today{outline:2px solid var(--accent);outline-offset:1px}
.calendar-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}
.weekday{text-align:center;font-size:12px;font-weight:700;color:var(--muted);padding:6px 0}
.calendar-cell{min-height:70px;padding:8px;border:1px solid var(--line);border-radius:12px;background:var(--surface-soft);display:grid;align-content:start;gap:3px}
.calendar-cell.empty{border-style:dashed;background:transparent;opacity:.45}
.calendar-cell.checked{border-color:#22c55e;background:color-mix(in srgb,#22c55e 10%,var(--panel))}
.calendar-cell small{font-size:11px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.day-number{font-weight:700;font-size:13px}
.dot{width:9px;height:9px;border-radius:50%;background:#22c55e;display:inline-block}
.history-list{display:grid;gap:10px}
.history-row{display:grid;grid-template-columns:110px 130px 1fr;gap:10px;align-items:start;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface-soft)}
.history-row span{font-size:12px;color:var(--muted)}
.history-row p{grid-column:3;color:var(--muted);line-height:1.6}
.task-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.task-card{padding:16px;border:1px solid var(--line);border-radius:16px;background:var(--surface-soft);display:grid;gap:8px}
.task-head,.record-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.task-card h3{font-size:17px}
.task-card small,.record-card small{color:var(--muted)}
.pill{display:inline-block;font-size:11px;padding:4px 8px;border-radius:999px;color:var(--accent);background:var(--accent-soft);margin-bottom:6px}
.submission-box{padding:12px;border-left:3px solid var(--accent);background:var(--panel);border-radius:10px;display:grid;gap:6px}
.task-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.card-list{display:grid;gap:12px}
.record-card{padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--surface-soft);display:grid;gap:8px}
.inline-form{display:flex;gap:10px;flex-wrap:wrap}
.inline-form .el-input{flex:1;min-width:220px}
.attendance-meta{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
.dialog-loading{min-height:180px}
.task-detail{display:grid;gap:12px;max-height:60vh;overflow:auto;padding-right:6px}
.detail-meta{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.submit-area{display:grid;gap:10px;padding-top:8px;border-top:1px solid var(--line)}
.hint{font-size:12px}
@media (max-width:960px){.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.overview-grid{grid-template-columns:1fr}.daily-action{justify-items:start}.history-row{grid-template-columns:1fr}.history-row p{grid-column:auto}}
</style>
