<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { teacherApi, type ApiEnvelope, type PlazaClassItem } from '../../api'

const router = useRouter()
const loading = ref(false)
const joining = ref(0)
const query = ref('')
const subject = ref('')
const items = ref<PlazaClassItem[]>([])
const loadError = ref('')
const resultQuery = ref('')
let searchVersion = 0

const subjects = computed(() => Array.from(new Set(items.value.map((item) => item.subject))).sort())

function errorText(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  return `${fallback}${error?.response?.status ? `（HTTP ${error.response.status}）` : '，请检查网络后重试'}`
}

async function refresh() {
  const version = ++searchVersion
  const submittedQuery = query.value.trim()
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await teacherApi.get<ApiEnvelope<PlazaClassItem[]>>('/learning/classrooms/plaza', {
      params: { query: submittedQuery, subject: subject.value },
    })
    if (version !== searchVersion) return
    items.value = data.data
    resultQuery.value = submittedQuery
  } catch (error: any) {
    if (version !== searchVersion) return
    loadError.value = errorText(error, '课堂广场加载失败')
    ElMessage.error(loadError.value)
  } finally {
    if (version === searchVersion) loading.value = false
  }
}

async function join(item: PlazaClassItem) {
  if ((!item.invite_matched && item.join_mode !== 'open') || item.joined || joining.value) return
  joining.value = item.id
  try {
    if (item.invite_matched) {
      await teacherApi.post('/teacher/students/me/classes/join', { invite_code: resultQuery.value })
    } else {
      await teacherApi.post(`/learning/classrooms/${item.id}/join`)
    }
    ElMessage.success(`已加入「${item.name}」，可在我的课堂和课程表中查看`)
    await refresh()
  } catch (error: any) {
    ElMessage.error(errorText(error, '加入课堂失败'))
  } finally {
    joining.value = 0
  }
}

const inviteDialog = ref(false)
const inviteCode = ref('')
const inviteBusy = ref(false)
const inviteError = ref('')

function openInviteDialog(prefill = '') {
  inviteCode.value = (prefill || query.value).trim()
  inviteError.value = ''
  inviteDialog.value = true
}

async function submitInvite() {
  const code = inviteCode.value.trim()
  if (!code) { inviteError.value = '请输入教师提供的邀请码'; return }
  inviteBusy.value = true
  inviteError.value = ''
  try {
    // The invite code is submitted to the backend join endpoint; the backend
    // resolves it to a classroom and checks capacity/status there.
    const { data } = await teacherApi.post<ApiEnvelope<{ name: string }>>(
      '/teacher/students/me/classes/join',
      { invite_code: code },
    )
    ElMessage.success(`已加入「${data.data.name}」，可在我的课堂和课程表中查看`)
    inviteDialog.value = false
    inviteCode.value = ''
    await refresh()
  } catch (error: any) {
    inviteError.value = errorText(error, '邀请码加入失败')
  } finally {
    inviteBusy.value = false
  }
}

function goClassroom() {
  router.push('/student/classroom')
}

onMounted(refresh)
</script>

<template>
  <div class="plaza-page" v-loading="loading">
    <header class="plaza-hero">
      <div>
        <span class="eyebrow">CLASSROOM PLAZA</span>
        <h1>课堂广场</h1>
        <p>搜索课程名称、学科、教师或完整邀请码。输入教师提供的邀请码，可以找到对应课堂并直接加入。</p>
      </div>
      <div class="plaza-stats">
        <article><strong>{{ items.length }}</strong><span>可选课堂</span></article>
        <article><strong>{{ items.filter((item) => item.joined).length }}</strong><span>我已加入</span></article>
      </div>
    </header>

    <article class="panel">
      <div class="filter-bar">
        <el-input v-model="query" placeholder="搜索课堂、学科、教师或完整邀请码" clearable @keyup.enter="refresh" @clear="refresh" />
        <el-select v-model="subject" placeholder="全部学科" clearable @change="refresh">
          <el-option label="全部学科" value="" />
          <el-option v-for="name in subjects" :key="name" :label="name" :value="name" />
        </el-select>
        <el-button type="primary" @click="refresh">搜索</el-button>
        <el-button @click="openInviteDialog()">邀请码加入</el-button>
        <el-button @click="goClassroom">我的课堂</el-button>
      </div>
      <el-alert v-if="loadError" :title="loadError" type="error" :closable="false">
        <el-button @click="refresh">重试</el-button>
      </el-alert>

      <div v-if="items.length" class="plaza-grid">
        <article v-for="item in items" :key="item.id" class="plaza-card">
          <div class="card-head">
            <div>
              <span class="subject-pill">{{ item.subject }}</span>
              <h2>{{ item.name }}</h2>
            </div>
            <el-tag :type="item.join_mode === 'open' ? 'success' : 'info'" effect="light">
              {{ item.join_mode === 'open' ? '公开选课' : '邀请码加入' }}
            </el-tag>
          </div>
          <p class="teacher">授课教师：{{ item.teacher_name }} · {{ item.student_count }}<template v-if="item.capacity"> / {{ item.capacity }}</template> 名学生<template v-if="item.semester"> · {{ item.semester }}</template></p>
          <div class="course-block">
            <small>课程安排</small>
            <strong>{{ item.course_title || item.name }}</strong>
            <p>{{ item.description || item.course_description || '教师尚未填写课程简介' }}</p>
            <p v-if="item.objective"><b>教学目标：</b>{{ item.objective }}</p>
            <p v-if="item.syllabus"><b>教学大纲：</b>{{ item.syllabus }}</p>
            <p v-if="item.latest_scope_title" class="scope">最近教学范围：{{ item.latest_scope_title }}</p>
            <p v-if="item.open_task_count" class="scope">进行中的课堂任务：{{ item.open_task_count }} 项</p>
          </div>
          <div class="card-actions">
            <el-button v-if="item.joined" type="success" plain @click="goClassroom">已加入 · 进入我的课堂</el-button>
            <el-button v-else-if="item.invite_matched && (!item.capacity || item.student_count < item.capacity)" type="primary" :loading="joining === item.id" @click="join(item)">使用邀请码加入</el-button>
            <el-button v-else-if="item.join_mode === 'open' && (!item.capacity || item.student_count < item.capacity)" type="primary" :loading="joining === item.id" @click="join(item)">加入课堂</el-button>
            <el-button v-else-if="item.capacity && item.student_count >= item.capacity" disabled>人数已满</el-button>
            <el-button v-else @click="openInviteDialog()">输入邀请码加入</el-button>
          </div>
        </article>
      </div>
      <el-empty v-else-if="!loading && !loadError" :description="resultQuery ? '未找到对应课堂，请检查课程名称或完整邀请码；停用、已更换的邀请码无法使用' : '暂无可选课堂，可向教师获取邀请码后搜索加入'" />
      <p class="hint">邀请码需完整匹配，支持大小写；非公开课堂仅在持有正确邀请码时出现在搜索结果中。加入后自动同步到我的课堂和课程表。</p>
    </article>

    <el-dialog v-model="inviteDialog" title="使用邀请码加入课堂" width="min(440px, 92vw)">
      <p class="hint invite-hint">向任课教师获取完整邀请码，输入后由系统校验班级状态与容量。</p>
      <el-input
        v-model="inviteCode"
        placeholder="请输入课堂邀请码"
        clearable
        @keyup.enter="submitInvite"
      />
      <p v-if="inviteError" class="invite-error">{{ inviteError }}</p>
      <template #footer>
        <el-button @click="inviteDialog = false">取消</el-button>
        <el-button type="primary" :loading="inviteBusy" @click="submitInvite">加入课堂</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.plaza-page{display:grid;gap:20px}
.plaza-hero{display:flex;flex-wrap:wrap;justify-content:space-between;gap:20px;padding:28px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 14%,var(--panel)),var(--panel));box-shadow:var(--shadow-sm)}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}
h1,h2,p{margin:0}
h1{font-size:30px;margin:5px 0 8px}
.plaza-hero p{color:var(--muted);line-height:1.7;max-width:720px}
.plaza-stats{display:flex;gap:12px}
.plaza-stats article{min-width:100px;padding:14px;border-radius:16px;background:var(--panel-strong);text-align:center}
.plaza-stats strong{display:block;font-size:24px}
.plaza-stats span{font-size:12px;color:var(--muted)}
.panel{padding:22px;border:1px solid var(--line);border-radius:20px;background:var(--panel);box-shadow:var(--shadow-sm);display:grid;gap:18px}
.filter-bar{display:flex;gap:10px;flex-wrap:wrap}
.filter-bar .el-input{flex:1;min-width:220px}
.plaza-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}
.plaza-card{display:grid;gap:12px;padding:18px;border:1px solid var(--line);border-radius:18px;background:var(--surface-soft)}
.card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.subject-pill{display:inline-block;font-size:11px;padding:4px 8px;border-radius:999px;color:var(--accent);background:var(--accent-soft);margin-bottom:6px}
.plaza-card h2{font-size:18px}
.teacher{font-size:12px;color:var(--muted)}
.course-block{display:grid;gap:5px;padding:12px;border-radius:12px;background:var(--panel);border-left:3px solid var(--accent)}
.course-block small{font-size:11px;color:var(--muted);letter-spacing:.08em}
.course-block p{font-size:13px;color:var(--muted);line-height:1.6}
.course-block .scope{color:var(--accent)}
.card-actions{display:flex;justify-content:flex-end}
.hint{font-size:12px;color:var(--muted);line-height:1.7}
@media (max-width:640px){.plaza-stats{width:100%}.plaza-stats article{flex:1}.plaza-grid{grid-template-columns:minmax(0,1fr)}.plaza-card{min-width:0;overflow-wrap:anywhere}.card-head{flex-wrap:wrap}}
.invite-hint{margin:0 0 12px}
.invite-error{margin:8px 0 0;color:var(--red);font-size:12px}
</style>
