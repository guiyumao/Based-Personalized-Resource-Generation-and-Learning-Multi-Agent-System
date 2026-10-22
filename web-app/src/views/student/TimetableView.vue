<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { teacherApi, type ApiEnvelope, type StudentSchedule, type StudentScheduleEntry, type PersonalSchedule } from '../../api'

const router = useRouter()
const loading = ref(false)
const schedule = ref<StudentSchedule | null>(null)
const weekStart = ref('')
const loadError = ref('')
const dialog = ref(false)
const managing = ref(false)
const saving = ref(false)
const form = ref<PersonalSchedule>({} as PersonalSchedule)
let requestVersion = 0

function errorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail.map(item => item.msg || '').filter(Boolean).join('；') || fallback
  return typeof detail === 'string' ? detail : fallback
}

function openNew(classId: number | null = null) {
  form.value = {
    topic: schedule.value?.classrooms.find(c => c.class_id === classId)?.class_name || '',
    class_id: classId, source_session_id: null, source_date: null, hidden: false,
    weekday: 1, start_time: '09:00', end_time: '10:00',
    week_start: weekStart.value, week_end: schedule.value?.week_end || weekStart.value,
    location: '', mode: 'offline',
  }
  dialog.value = true
}

function editEntry(entry: StudentScheduleEntry) {
  if (entry.personal_id) {
    const own = schedule.value?.personal.find(p => p.id === entry.personal_id)
    if (!own) return
    form.value = { ...own }
  } else {
    form.value = {
      topic: entry.topic, class_id: entry.class_id, source_session_id: entry.session_id,
      source_date: entry.source_date || entry.date, hidden: false,
      weekday: entry.weekday, start_time: entry.start_time, end_time: entry.end_time,
      week_start: entry.date, week_end: entry.date, location: entry.location, mode: entry.mode,
    }
  }
  dialog.value = true
}

function alignOverrideDate(value: string) {
  if (form.value.source_session_id && value) {
    form.value.week_end = value
    form.value.weekday = ((new Date(`${value}T00:00:00`).getDay() + 6) % 7) + 1
  }
}

async function saveEntry() {
  if (!form.value.topic?.trim() || !form.value.week_start || !form.value.week_end || !form.value.start_time || !form.value.end_time) {
    ElMessage.warning('请填写课程名称、日期和起止时间')
    return
  }
  saving.value = true
  try {
    const { id, ...payload } = form.value
    if (id) await teacherApi.put(`/learning/schedule/me/personal/${id}`, payload)
    else await teacherApi.post('/learning/schedule/me/personal', payload)
    dialog.value = false
    ElMessage.success('已保存到我的课程表')
    await refresh()
  } catch (error: any) {
    ElMessage.error(errorMessage(error, '保存失败，请检查日期和时间'))
  } finally { saving.value = false }
}

async function removePersonal(id?: number) {
  if (!id) return
  try {
    await ElMessageBox.confirm('删除这条个人安排？课堂课程的个人调整删除后将恢复教师安排。', '确认删除')
  } catch { return }
  try {
    await teacherApi.delete(`/learning/schedule/me/personal/${id}`)
    ElMessage.success('已删除个人安排')
    await refresh()
  } catch (error: any) { ElMessage.error(error?.response?.data?.detail || '删除失败') }
}

async function hideEntry(entry: StudentScheduleEntry) {
  if (entry.personal_id) return removePersonal(entry.personal_id)
  try { await ElMessageBox.confirm('仅从你本人的课程表隐藏本次课程，可在“管理个人安排”恢复。', '隐藏本次课程') }
  catch { return }
  editEntry(entry)
  form.value.hidden = true
  dialog.value = false
  await saveEntry()
}

const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function isoDate(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function mondayOf(date: Date) {
  const copy = new Date(date)
  const offset = (copy.getDay() + 6) % 7
  copy.setDate(copy.getDate() - offset)
  return copy
}

function shiftWeek(days: number) {
  const base = weekStart.value ? new Date(`${weekStart.value}T00:00:00`) : mondayOf(new Date())
  base.setDate(base.getDate() + days)
  weekStart.value = isoDate(base)
  refresh()
}

function currentWeek() {
  weekStart.value = isoDate(mondayOf(new Date()))
  refresh()
}

const weekDays = computed(() => {
  const start = weekStart.value ? new Date(`${weekStart.value}T00:00:00`) : mondayOf(new Date())
  return Array.from({ length: 7 }, (_, index) => {
    const day = new Date(start)
    day.setDate(start.getDate() + index)
    const key = isoDate(day)
    return {
      key,
      label: weekdays[index],
      dayLabel: `${day.getMonth() + 1}/${day.getDate()}`,
      isToday: key === (schedule.value?.today || isoDate(new Date())),
      entries: (schedule.value?.entries || []).filter((item) => item.date === key),
    }
  })
})

const todayEntries = computed(() => {
  const today = schedule.value?.today || isoDate(new Date())
  return (schedule.value?.entries || []).filter((item) => item.date === today)
})

const weekLabel = computed(() => {
  if (!schedule.value) return ''
  return `${schedule.value.week_start} 至 ${schedule.value.week_end}`
})

function statusLabel(entry: StudentScheduleEntry) {
  if (entry.source === 'personal') return '个人安排'
  if (entry.status === 'rescheduled') return '已调课'
  if (entry.status === 'makeup') return '补课'
  return ''
}

function statusType(entry: StudentScheduleEntry) {
  if (entry.status === 'rescheduled') return 'warning'
  if (entry.status === 'makeup') return 'success'
  return 'info'
}

async function refresh() {
  const version = ++requestVersion
  loading.value = true
  loadError.value = ''
  try {
    const params = weekStart.value ? { week_start: weekStart.value } : undefined
    const { data } = await teacherApi.get<ApiEnvelope<StudentSchedule>>('/learning/schedule/me', { params })
    if (version !== requestVersion) return
    schedule.value = data.data
    if (!weekStart.value) weekStart.value = data.data.week_start
  } catch (error: any) {
    if (version !== requestVersion) return
    loadError.value = error?.response?.data?.detail || '课程表加载失败'
    ElMessage.error(loadError.value)
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

onMounted(() => {
  weekStart.value = isoDate(mondayOf(new Date()))
  refresh()
})
</script>

<template>
  <div class="timetable-page" v-loading="loading">
    <header class="timetable-hero">
      <div>
        <span class="eyebrow">MY TIMETABLE</span>
        <h1>我的课程表</h1>
        <p>已加入课堂自动导入，有上课时间的直接同步到周课表；尚未排课的可自行安排。你也可以新增个人课程，调整仅对自己生效。</p>
      </div>
      <div class="week-nav">
        <el-button type="primary" @click="openNew()">新增个人课程</el-button>
        <el-button @click="managing = true">管理个人安排</el-button>
        <el-button @click="refresh">同步课程</el-button>
        <el-button @click="shiftWeek(-7)">上一周</el-button>
        <el-button @click="currentWeek">本周</el-button>
        <el-button @click="shiftWeek(7)">下一周</el-button>
      </div>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false"><el-button @click="refresh">重试</el-button></el-alert>

    <article class="panel">
      <div class="panel-title"><h2>已自动导入的课堂（{{ schedule?.classrooms?.length || 0 }}）</h2><el-button link @click="router.push('/student/classroom')">我的课堂</el-button></div>
      <div v-for="room in schedule?.classrooms || []" :key="room.class_id" class="imported-class">
        <div><strong>{{ room.class_name }}</strong><p>{{ room.teacher_name }} · {{ room.scheduled ? '已有课程安排，可查看对应教学周' : '待安排：尚无上课时间，请补充或等待教师排课' }}</p></div>
        <el-button @click="openNew(room.class_id)">{{ room.scheduled ? '添加个人安排' : '安排上课时间' }}</el-button>
      </div>
      <el-empty v-if="schedule && !schedule.classrooms?.length" description="暂未加入课堂，也可以直接新增个人课程" />
    </article>

    <article class="panel">
      <div class="panel-title">
        <div><span class="eyebrow">WEEK</span><h2>{{ weekLabel }}</h2></div>
        <div class="legend"><span>共 {{ schedule?.entries.length || 0 }} 节课</span><el-button link @click="router.push('/student/classroom-plaza')">去课堂广场选课</el-button></div>
      </div>
      <div class="week-grid">
        <div v-for="day in weekDays" :key="day.key" class="day-column" :class="{ today: day.isToday }">
          <header><strong>{{ day.label }}</strong><small>{{ day.dayLabel }}</small></header>
          <div v-if="day.entries.length" class="day-entries">
            <div v-for="entry in day.entries" :key="`${entry.session_id}-${entry.date}-${entry.start_time}`" class="lesson" :class="{ moved: entry.status !== 'normal' }">
              <div class="lesson-head">
                <strong>{{ entry.start_time }} - {{ entry.end_time }}</strong>
                <el-tag v-if="statusLabel(entry)" :type="statusType(entry)" effect="light" size="small">{{ statusLabel(entry) }}</el-tag>
              </div>
              <p>{{ entry.topic }}</p>
              <small>{{ entry.class_name }} · {{ entry.teacher_name }}</small>
              <small>{{ entry.location || (entry.mode === 'online' ? '线上授课' : '地点待定') }}</small>
              <div class="lesson-actions"><el-button link type="primary" @click="editEntry(entry)">编辑</el-button><el-button link type="danger" @click="hideEntry(entry)">{{ entry.personal_id ? '删除' : '隐藏本次' }}</el-button></div>
            </div>
          </div>
          <p v-else class="no-lesson">无课</p>
        </div>
      </div>
    </article>

    <article class="panel">
      <div class="panel-title"><div><span class="eyebrow">TODAY</span><h2>今日课程</h2></div><el-button link @click="router.push('/student/classroom')">我的课堂</el-button></div>
      <div v-if="todayEntries.length" class="today-list">
        <div v-for="entry in todayEntries" :key="`${entry.session_id}-${entry.start_time}`" class="today-row">
          <strong>{{ entry.start_time }} - {{ entry.end_time }}</strong>
          <div><p>{{ entry.topic }}</p><small>{{ entry.class_name }} · {{ entry.teacher_name }} · {{ entry.location || '线上' }}</small></div>
          <el-tag :type="statusType(entry)" effect="light">{{ statusLabel(entry) || '正常' }}</el-tag>
        </div>
      </div>
      <el-empty v-else description="今天暂无课程，可在上方为待安排课堂补充上课时间" />
    </article>

    <el-dialog v-model="dialog" :title="form.source_session_id ? '调整我的本次课程' : (form.id ? '编辑个人课程' : '新增个人课程')" width="min(560px, 94vw)" append-to-body>
      <el-form label-position="top" @submit.prevent="saveEntry">
        <el-form-item label="课程名称" required><el-input v-model="form.topic" maxlength="160" /></el-form-item>
        <el-form-item v-if="!form.source_session_id" label="关联课堂（可选）"><el-select v-model="form.class_id" clearable placeholder="独立个人课程" @clear="form.class_id = null"><el-option v-for="room in schedule?.classrooms || []" :key="room.class_id" :label="room.class_name" :value="room.class_id" /></el-select></el-form-item>
        <el-alert v-if="form.source_session_id" title="仅调整你本人的本次课程，不修改教师或其他同学的课表。" type="info" :closable="false" />
        <div class="form-pair">
          <el-form-item :label="form.source_session_id ? '上课日期' : '开始日期'" required><el-date-picker v-model="form.week_start" type="date" value-format="YYYY-MM-DD" @change="alignOverrideDate" /></el-form-item>
          <el-form-item v-if="!form.source_session_id" label="结束日期" required><el-date-picker v-model="form.week_end" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        </div>
        <el-form-item v-if="!form.source_session_id" label="每周上课日"><el-select v-model="form.weekday"><el-option v-for="(name, index) in weekdays" :key="index" :label="name" :value="index + 1" /></el-select></el-form-item>
        <div class="form-pair"><el-form-item label="开始时间" required><el-time-select v-model="form.start_time" start="00:00" end="23:45" step="00:15" /></el-form-item><el-form-item label="结束时间" required><el-time-select v-model="form.end_time" start="00:00" end="23:45" step="00:15" /></el-form-item></div>
        <el-form-item label="地点"><el-input v-model="form.location" maxlength="160" /></el-form-item>
        <el-form-item label="上课方式"><el-radio-group v-model="form.mode"><el-radio value="offline">线下</el-radio><el-radio value="online">线上</el-radio></el-radio-group></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveEntry">保存课程</el-button></template>
    </el-dialog>
    <el-dialog v-model="managing" title="管理个人安排" width="min(700px, 94vw)" append-to-body>
      <p>删除课堂课程的个人调整或隐藏记录，即可恢复教师安排。</p>
      <div v-for="item in schedule?.personal || []" :key="item.id" class="imported-class"><div><strong>{{ item.topic }}</strong><p>{{ item.hidden ? '已隐藏本次课堂课程' : `${weekdays[item.weekday - 1]} ${item.start_time}–${item.end_time}` }} · {{ item.week_start }} 至 {{ item.week_end }}</p></div><el-button type="danger" link @click="removePersonal(item.id)">{{ item.source_session_id ? '恢复教师安排' : '删除' }}</el-button></div>
      <el-empty v-if="!schedule?.personal?.length" description="暂无个人安排" />
    </el-dialog>
  </div>
</template>

<style scoped>
.timetable-page{display:grid;gap:20px}
.imported-class{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px;border:1px solid var(--line);border-radius:12px;flex-wrap:wrap}.imported-class p{color:var(--muted);font-size:12px;margin-top:6px}.lesson-actions{display:flex;gap:10px}.form-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.form-pair :deep(.el-date-editor),.form-pair :deep(.el-select){width:100%}
.timetable-hero{display:flex;flex-wrap:wrap;justify-content:space-between;gap:18px;padding:28px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel)),var(--panel));box-shadow:var(--shadow-sm)}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}
h1,h2,p{margin:0}
h1{font-size:30px;margin:5px 0 8px}
.timetable-hero p{color:var(--muted);line-height:1.7;max-width:760px}
.week-nav{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.panel{padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--panel);box-shadow:var(--shadow-sm);display:grid;gap:16px}
.panel-title{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.panel-title h2{font-size:18px;margin-top:4px}
.legend{display:flex;align-items:center;gap:12px;font-size:12px;color:var(--muted)}
.week-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;align-items:start}
.day-column{border:1px solid var(--line);border-radius:14px;background:var(--surface-soft);padding:10px;min-height:180px;display:grid;align-content:start;gap:8px}
.day-column.today{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
.day-column header{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;color:var(--muted);padding-bottom:6px;border-bottom:1px solid var(--line)}
.day-column header strong{color:var(--text);font-size:13px}
.day-entries{display:grid;gap:8px}
.lesson{padding:8px;border-left:3px solid var(--accent);background:var(--panel);border-radius:8px;display:grid;gap:3px;min-width:0;overflow-wrap:anywhere}
.lesson-head{min-width:0}.lesson-actions{flex-wrap:wrap;gap:4px}.lesson-actions :deep(.el-button){padding:4px 6px;min-width:0;height:auto;margin:0}
.lesson.moved{border-left-color:#f59e0b}
.lesson-head{display:flex;justify-content:space-between;gap:4px;align-items:center;flex-wrap:wrap}
.lesson-head strong{font-size:12px}
.lesson p{font-size:13px;font-weight:600}
.lesson small{font-size:11px;color:var(--muted)}
.no-lesson{font-size:12px;color:var(--muted);text-align:center;padding:12px 0}
.today-list{display:grid;gap:10px}
.today-row{display:grid;grid-template-columns:150px 1fr auto;gap:12px;align-items:center;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface-soft)}
.today-row p{font-weight:600}
.today-row small{color:var(--muted)}
@media (max-width:1100px){.week-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.week-grid{grid-template-columns:1fr}.today-row{grid-template-columns:1fr}}
</style>
