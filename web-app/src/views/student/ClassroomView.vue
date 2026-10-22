<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useNotifications } from '../../stores/notifications'
import { ElMessage, ElMessageBox } from 'element-plus'
import LearningContent from '../../components/LearningContent.vue'
import HomeworkAttachments from '../../components/HomeworkAttachments.vue'
import HomeworkPractice from '../../components/HomeworkPractice.vue'
import ReinforcementResult from '../../components/ReinforcementResult.vue'

import {
  teacherApi,
  type ApiEnvelope,
  type AssignmentItem,
  type HomeworkFileItem,
  type AssignmentSubmissionItem,
  type DiscussionItem,
  type TeacherClassItem,
  type TeachingScopeItem,
  type CourseResourceDelivery,
} from '../../api'

const noticeRoute = useRoute()
const assignments = ref<AssignmentItem[]>([])
const courseResources = ref<CourseResourceDelivery[]>([])
const practiceReady = reactive<Record<number, boolean>>({})
const practiceAnswers = reactive<Record<number, string[]>>({})
const openedAt = Date.now()
const discussions = ref<DiscussionItem[]>([])
const myClasses = ref<TeacherClassItem[]>([])
const teachingScopes = ref<TeachingScopeItem[]>([])
const inviteCode = ref(''), loadError = ref(''), joining = ref(false)
const previewClass = ref<TeacherClassItem | null>(null)
async function lookupClass() {
  previewClass.value = null
  try { previewClass.value = (await teacherApi.post<ApiEnvelope<TeacherClassItem>>('/teacher/students/me/classes/lookup', { invite_code: inviteCode.value.trim() })).data.data }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || '邀请码查询失败') }
}
async function joinClass() {
  if (!previewClass.value) return
  joining.value = true
  try { await teacherApi.post('/teacher/students/me/classes/join', { invite_code: inviteCode.value.trim() }); ElMessage.success('已加入班级'); previewClass.value = null; inviteCode.value = ''; await refresh() }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || '加入失败') }
  finally { joining.value = false }
}

async function leaveClass(item: TeacherClassItem) {
  try {
    await ElMessageBox.confirm(
      `退出后，该课堂的未来课程不再出现在你的课程表，但历史学习记录会保留。确定退出「${item.name}」吗？`,
      '退出课堂',
      { type: 'warning' },
    )
    await teacherApi.post(`/learning/classrooms/${item.id}/leave`)
    ElMessage.success('已退出课堂')
    await refresh()
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(error?.response?.data?.detail || '退出课堂失败')
  }
}
const notificationStore = useNotifications()
const loading = ref(false)
const submittingId = ref(0)
const selectedFiles = reactive<Record<number, HomeworkFileItem[]>>({})
const uploadingFiles = reactive<Record<number, boolean>>({})
const submissionText = reactive<Record<number, string>>({})
const replyText = reactive<Record<number, string>>({})
const discussionForm = reactive({ class_id: 0, title: '', content: '' })

const classOptions = computed(() => myClasses.value.map(c => ({label:c.name, value:c.id})))
const unreadCount = computed(() => notificationStore.unread)

function formatTime(value?: string | null) {
  if (!value) return '未设置'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

async function refresh() {
  loadError.value = ''
  loading.value = true
  try {
    const [homework, topics, classes, scopes, resources] = await Promise.all([
      teacherApi.get<ApiEnvelope<AssignmentItem[]>>('/teacher/students/me/homework'),
      teacherApi.get<ApiEnvelope<DiscussionItem[]>>('/learning/discussions'),
      teacherApi.get<ApiEnvelope<TeacherClassItem[]>>('/teacher/students/me/classes'),
      teacherApi.get<ApiEnvelope<TeachingScopeItem[]>>('/teacher/students/me/teaching-scopes'),
      teacherApi.get<ApiEnvelope<CourseResourceDelivery[]>>('/teacher/students/me/course-resources'),
    ])
    courseResources.value = resources.data.data
    teachingScopes.value = scopes.data.data
    myClasses.value = classes.data.data
    assignments.value = homework.data.data
    for (const item of assignments.value) {
      if (!selectedFiles[item.id]) selectedFiles[item.id] = [...(item.my_submission?.attachments || []), ...(item.pending_attachments || [])]
      if (submissionText[item.id] === undefined) submissionText[item.id] = item.my_submission?.content || ''
    }
    discussions.value = topics.data.data
    if (!discussionForm.class_id && classOptions.value.length) discussionForm.class_id = classOptions.value[0].value
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || '班级空间加载失败，请检查网络后重试'
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function submitHomework(item: AssignmentItem) {
  if (submittingId.value || uploadingFiles[item.id]) return
  if (item.practice_questions?.length && !practiceReady[item.id]) return ElMessage.warning('请完成每一道补强题后提交')
  const content = submissionText[item.id]?.trim()
  const attachment_ids = (selectedFiles[item.id] || []).map(file => file.id)
  if (!content && !attachment_ids.length) return ElMessage.warning('请填写作业内容或选择附件')
  submittingId.value = item.id
  try {
    await teacherApi.post<ApiEnvelope<AssignmentSubmissionItem>>(
      `/teacher/students/me/homework/${item.id}/submit`, { content: content || '', attachment_ids,
        answers: item.practice_questions?.length ? practiceAnswers[item.id] : undefined,
        time_spent: item.practice_questions?.length ? Math.min(86400, Math.floor((Date.now() - openedAt) / 1000)) : undefined },
    )
    ElMessage.success(item.practice_questions?.length ? '已提交，可立即查看参考答案；错题与模型分析将自动更新' : '作业已提交，等待教师批改')
    delete submissionText[item.id]
    delete selectedFiles[item.id]
    await refresh()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? '作业提交失败')
  } finally {
    submittingId.value = 0
  }
}

async function createDiscussion() {
  if (!discussionForm.class_id || !discussionForm.title.trim() || !discussionForm.content.trim()) {
    return ElMessage.warning('请选择班级并填写标题和正文')
  }
  try {
    await teacherApi.post('/learning/discussions', discussionForm)
    discussionForm.title = ''
    discussionForm.content = ''
    ElMessage.success('讨论已发布')
    await refresh()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? '讨论发布失败')
  }
}

async function replyDiscussion(item: DiscussionItem) {
  const content = replyText[item.id]?.trim()
  if (!content) return
  try {
    await teacherApi.post(`/learning/discussions/${item.id}/replies`, { content })
    replyText[item.id] = ''
    await refresh()
  } catch {
    ElMessage.error('回复失败')
  }
}

async function focusNotice(){await nextTick();const id=Number(noticeRoute.query.assignment);if(id)document.getElementById(`assignment-${id}`)?.scrollIntoView({block:'center'})}
watch(()=>noticeRoute.query.assignment,focusNotice)
onMounted(async()=>{await refresh();await focusNotice()})
let practicePoll: ReturnType<typeof setInterval> | undefined
onMounted(() => { practicePoll = setInterval(async () => {
  if (!assignments.value.some(a => ['pending', 'analyzing'].includes(a.my_submission?.practice_result?.status || ''))) return
  try { assignments.value = (await teacherApi.get<ApiEnvelope<AssignmentItem[]>>('/teacher/students/me/homework')).data.data }
  catch { /* Keep submitted answers visible; the normal refresh button retries. */ }
}, 4000) })
onUnmounted(() => clearInterval(practicePoll))
</script>

<template>
  <div class="classroom-page" v-loading="loading">
    <header class="classroom-hero">
      <div><span class="eyebrow">MY CLASSROOMS</span><h1>我的课堂</h1><p>查看已加入课堂的课程、作业与讨论。课堂是可选的学习方式，不加入课堂也可以正常使用平台学习与打卡。</p></div>
      <div class="hero-stat"><strong>{{ myClasses.length }}</strong><span>已加入课堂</span></div>
      <div class="hero-stat"><strong>{{ unreadCount }}</strong><span>条未读</span></div>
    </header>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false"><el-button @click="refresh">重试加载</el-button></el-alert>
    <article class="panel">
      <div class="panel-title"><h2>我的课堂</h2><div class="action-row"><el-button type="primary" plain @click="$router.push('/student/classroom-plaza')">去课堂广场选课</el-button><el-button @click="refresh">刷新课堂与作业</el-button></div></div>
      <div class="action-row"><el-input v-model="inviteCode" placeholder="输入教师提供的课堂邀请码（邀请制课堂）" @input="previewClass = null" /><el-button @click="lookupClass">查找课堂</el-button></div>
      <div v-if="previewClass" class="task-card"><strong>{{ previewClass.name }}</strong><p>{{ previewClass.subject }} · 教师 {{ previewClass.teacher_name }}</p><el-button type="primary" :loading="joining" @click="joinClass">确认加入课堂</el-button></div>
      <div v-for="item in myClasses" :key="item.id" class="task-card">
        <div class="task-head"><div><span class="pill">{{ item.subject }}</span><strong>{{ item.name }}</strong><p>{{ item.description || '教师尚未填写课堂简介' }}</p></div><el-tag effect="light">{{ item.semester || '未设置学期' }}</el-tag></div>
        <span class="muted">教师 {{ item.teacher_name }} · {{ item.student_count }} 名学生 · {{ item.join_mode === 'open' ? '公开选课' : '邀请制' }}<template v-if="item.capacity"> · 上限 {{ item.capacity }} 人</template></span>
        <div class="action-row"><el-button @click="$router.push('/student/classroom-plaza')">查看课堂详情</el-button><el-button type="danger" plain @click="leaveClass(item)">退出课堂</el-button></div>
      </div>
      <el-empty v-if="!loading && !loadError && !myClasses.length" description="尚未加入课堂，可前往课堂广场自主选择" />
    </article>
    <article v-if="courseResources.length" class="panel"><div class="panel-title"><h2>教师发送的课程资源</h2></div><div v-for="resource in courseResources" :key="resource.id" class="task-card"><h3>{{ resource.title }}</h3><small>{{ myClasses.find(c => c.id === resource.class_id)?.name }} · {{ resource.knowledge_points.join('、') }}</small><LearningContent :content="resource.content" /></div></article>
    <article v-if="teachingScopes.length" class="panel"><h2>本班教学范围与课件</h2><div v-for="scope in teachingScopes" :key="scope.id" class="task-card"><h3>{{ scope.courseware_title }}</h3><p>{{ scope.knowledge_points.join('、') }}</p><LearningContent :content="scope.learning_direction" /><LearningContent :content="scope.courseware_content" /></div></article>
    <section class="content-grid">
      <div class="main-column">
        <article class="panel">
          <div class="panel-title"><div><span class="eyebrow">ASSIGNMENTS</span><h2>课程作业</h2></div><el-button plain @click="refresh">刷新</el-button></div>
          <div v-if="assignments.length" class="card-list">
            <div v-for="item in assignments" :key="item.id" :id="`assignment-${item.id}`" class="task-card">
              <div class="task-head"><div><span class="pill">{{ item.class_name }}</span><h3>{{ item.title }}</h3></div><span class="status">{{ item.status === 'published' ? '进行中' : item.status === 'expired' ? '已截止' : item.status === 'inactive' ? '班级已停用' : '已关闭' }}</span></div>
              <ReinforcementResult v-if="item.my_submission?.practice_result" :result="item.my_submission.practice_result" />
              <HomeworkPractice v-else-if="item.practice_questions?.length" :questions="item.practice_questions" :readonly="item.status !== 'published'" @answer="value => { submissionText[item.id] = value.content; practiceReady[item.id] = value.complete; practiceAnswers[item.id] = value.answers }" />
              <LearningContent v-else class="task-description" :content="item.description" empty="(无描述)" /><small>截止：{{ formatTime(item.due_at) }} · 已有 {{ item.submission_count }} 次提交</small>
              <div v-if="item.my_submission" class="submission-result"><strong>{{ item.my_submission.practice_result ? '补强练习已完成，参考答案与逐题反馈见上方' : item.my_submission.status === 'reviewed' ? '已批改' : '已提交，等待批改' }}</strong><LearningContent :content="item.my_submission.content" /><HomeworkAttachments :files="item.my_submission.attachments" /><p v-if="item.my_submission.status === 'reviewed'">成绩：{{ item.my_submission.score }} 分</p><LearningContent v-if="item.my_submission.teacher_comment" :content="item.my_submission.teacher_comment" /><details v-if="item.my_submission.history?.length"><summary>提交与批改历史</summary><div v-for="(revision, index) in item.my_submission.history" :key="index"><small>{{ revision.recorded_at }} · {{ revision.status }}</small><LearningContent :content="revision.content" /><HomeworkAttachments :files="revision.attachments" /><p v-if="revision.score != null">{{ revision.score }} 分 · {{ revision.teacher_comment }}</p></div></details></div>
              <el-input v-if="!item.practice_questions?.length && item.my_submission?.status !== 'reviewed' && item.status === 'published'" v-model="submissionText[item.id]" type="textarea" :rows="3" placeholder="填写本次作业内容；再次提交会更新原记录" />
              <HomeworkAttachments v-if="!item.my_submission?.practice_result && item.my_submission?.status !== 'reviewed' && item.status === 'published'" :assignment-id="item.id" :files="selectedFiles[item.id] || []" editable @update:files="selectedFiles[item.id] = $event" @busy="uploadingFiles[item.id] = $event" />
              <el-button v-if="!item.my_submission?.practice_result && item.my_submission?.status !== 'reviewed' && item.status === 'published'" :disabled="uploadingFiles[item.id]" type="primary" :loading="submittingId === item.id" @click="submitHomework(item)">提交作业</el-button>
            </div>
          </div>
          <el-empty v-else-if="!loading && !loadError" description="尚未加入班级或教师还未布置作业" />
        </article>

        <article class="panel">
          <div class="panel-title"><div><span class="eyebrow">DISCUSSIONS</span><h2>课程讨论</h2></div></div>
          <div class="discussion-form">
            <el-select v-model="discussionForm.class_id" placeholder="选择班级"><el-option v-for="item in classOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
            <el-input v-model="discussionForm.title" placeholder="讨论标题" />
            <el-input v-model="discussionForm.content" type="textarea" :rows="3" placeholder="提出问题或分享学习思路" />
            <el-button type="primary" @click="createDiscussion">发布讨论</el-button>
          </div>
          <div class="card-list">
            <div v-for="item in discussions" :key="item.id" class="topic-card">
              <h3>{{ item.title }}</h3><small>{{ item.author_name }} · {{ formatTime(item.created_at) }}</small><LearningContent class="topic-content" :content="item.content" />
              <div v-for="reply in item.replies" :key="reply.id" class="reply"><strong>{{ reply.author_name }}</strong><LearningContent tag="span" :content="reply.content" inline /></div>
              <div class="reply-box"><el-input v-model="replyText[item.id]" placeholder="回复该讨论" @keyup.enter="replyDiscussion(item)" /><el-button @click="replyDiscussion(item)">回复</el-button></div>
            </div>
          </div>
        </article>
      </div>


    </section>
  </div>
</template>

<style scoped>
.classroom-page{display:grid;gap:20px}.classroom-hero,.panel{border:1px solid var(--line);background:var(--panel);border-radius:20px;box-shadow:var(--shadow-sm)}.classroom-hero{padding:28px;display:flex;align-items:center;gap:18px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel)),var(--panel))}.classroom-hero>div:first-child{flex:1}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}h1,h2,h3,p{margin:0}h1{font-size:30px;margin:5px 0 8px}.classroom-hero p,.task-card p,.topic-card p,.task-description,.topic-content{color:var(--muted);line-height:1.7}.hero-stat{min-width:92px;padding:15px;border-radius:15px;background:var(--panel-strong);text-align:center}.hero-stat strong{display:block;font-size:25px}.hero-stat span{font-size:12px;color:var(--muted)}.content-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:20px}.main-column{display:grid;gap:20px}.panel{padding:22px}.panel-title,.task-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.panel-title h2{margin-top:4px}.card-list{display:grid;gap:14px}.task-card,.topic-card{display:grid;gap:12px;padding:18px;border:1px solid var(--line);border-radius:16px;background:var(--surface-soft)}.pill,.status{font-size:11px;padding:5px 8px;border-radius:999px;color:var(--accent);background:var(--accent-soft)}.task-head h3{margin-top:8px}.task-card small,.topic-card small{color:var(--muted)}.discussion-form{display:grid;grid-template-columns:170px 1fr auto;gap:10px;margin-bottom:18px}.discussion-form .el-textarea{grid-column:1/3}.reply{display:flex;gap:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--panel);border-radius:8px}.reply strong{font-size:13px}.reply span,.reply .learning-content{color:var(--muted)}.reply-box{display:flex;gap:8px}.notice-panel{align-self:start;position:sticky;top:92px}.notice{width:100%;display:flex;gap:10px;padding:14px 8px;border:0;border-top:1px solid var(--line);background:transparent;text-align:left;cursor:pointer}.notice:hover{background:var(--surface-soft)}.notice-dot{width:8px;height:8px;margin-top:5px;border-radius:50%;background:var(--line)}.notice.unread .notice-dot{background:var(--accent);box-shadow:0 0 0 4px var(--accent-soft)}.notice span:last-child{display:grid;gap:4px}.notice small,.notice em{color:var(--muted);font-style:normal;line-height:1.5}.notice em{font-size:11px}@media(max-width:1000px){.content-grid{grid-template-columns:1fr}.notice-panel{position:static}}@media(max-width:700px){.classroom-hero{align-items:flex-start;flex-wrap:wrap}.discussion-form{grid-template-columns:1fr}.discussion-form .el-textarea{grid-column:auto}}
</style>
