<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  teacherApi,
  type ApiEnvelope,
  type AssignmentItem,
  type AssignmentSubmissionItem,
  type DiscussionItem,
  type LearningNotificationItem,
} from '../../api'

const assignments = ref<AssignmentItem[]>([])
const discussions = ref<DiscussionItem[]>([])
const notifications = ref<LearningNotificationItem[]>([])
const loading = ref(false)
const submittingId = ref(0)
const submissionText = reactive<Record<number, string>>({})
const replyText = reactive<Record<number, string>>({})
const discussionForm = reactive({ class_id: 0, title: '', content: '' })

const classOptions = computed(() => {
  const ids = Array.from(new Set(assignments.value.map((item) => item.class_id)))
  return ids.map((id) => ({ label: `班级 #${id}`, value: id }))
})
const unreadCount = computed(() => notifications.value.filter((item) => !item.is_read).length)

function formatTime(value?: string | null) {
  if (!value) return '未设置'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value))
}

async function refresh() {
  loading.value = true
  try {
    const [homework, topics, notices] = await Promise.all([
      teacherApi.get<ApiEnvelope<AssignmentItem[]>>('/teacher/students/me/homework'),
      teacherApi.get<ApiEnvelope<DiscussionItem[]>>('/learning/discussions'),
      teacherApi.get<ApiEnvelope<LearningNotificationItem[]>>('/learning/notifications'),
    ])
    assignments.value = homework.data.data
    discussions.value = topics.data.data
    notifications.value = notices.data.data
    if (!discussionForm.class_id && classOptions.value.length) discussionForm.class_id = classOptions.value[0].value
  } catch {
    ElMessage.error('班级空间加载失败，请确认教师服务已启动')
  } finally {
    loading.value = false
  }
}

async function submitHomework(item: AssignmentItem) {
  const content = submissionText[item.id]?.trim()
  if (!content) return ElMessage.warning('请先填写作业内容')
  submittingId.value = item.id
  try {
    const { data } = await teacherApi.post<ApiEnvelope<AssignmentSubmissionItem>>(
      `/teacher/students/me/homework/${item.id}/submit`, { content },
    )
    ElMessage.success(`作业已提交，提交记录 #${data.data.id}`)
    submissionText[item.id] = ''
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

async function markRead(item: LearningNotificationItem) {
  if (item.is_read) return
  await teacherApi.patch(`/learning/notifications/${item.id}/read`)
  item.is_read = true
}

onMounted(refresh)
</script>

<template>
  <div class="classroom-page" v-loading="loading">
    <header class="classroom-hero">
      <div><span class="eyebrow">LEARNING COMMUNITY</span><h1>班级与课程空间</h1><p>查看真实作业、提交学习成果、参与课程讨论，并集中处理教学通知。</p></div>
      <div class="hero-stat"><strong>{{ assignments.length }}</strong><span>项作业</span></div>
      <div class="hero-stat"><strong>{{ unreadCount }}</strong><span>条未读</span></div>
    </header>

    <section class="content-grid">
      <div class="main-column">
        <article class="panel">
          <div class="panel-title"><div><span class="eyebrow">ASSIGNMENTS</span><h2>课程作业</h2></div><el-button plain @click="refresh">刷新</el-button></div>
          <div v-if="assignments.length" class="card-list">
            <div v-for="item in assignments" :key="item.id" class="task-card">
              <div class="task-head"><div><span class="pill">班级 #{{ item.class_id }}</span><h3>{{ item.title }}</h3></div><span class="status">{{ item.status === 'published' ? '进行中' : item.status }}</span></div>
              <p>{{ item.description }}</p><small>截止：{{ formatTime(item.due_at) }} · 已有 {{ item.submission_count }} 次提交</small>
              <el-input v-model="submissionText[item.id]" type="textarea" :rows="3" placeholder="填写本次作业内容；再次提交会更新原记录" />
              <el-button type="primary" :loading="submittingId === item.id" @click="submitHomework(item)">提交作业</el-button>
            </div>
          </div>
          <el-empty v-else description="尚未加入班级或教师还未布置作业" />
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
              <h3>{{ item.title }}</h3><small>{{ item.author_name }} · {{ formatTime(item.created_at) }}</small><p>{{ item.content }}</p>
              <div v-for="reply in item.replies" :key="reply.id" class="reply"><strong>{{ reply.author_name }}</strong><span>{{ reply.content }}</span></div>
              <div class="reply-box"><el-input v-model="replyText[item.id]" placeholder="回复该讨论" @keyup.enter="replyDiscussion(item)" /><el-button @click="replyDiscussion(item)">回复</el-button></div>
            </div>
          </div>
        </article>
      </div>

      <aside class="panel notice-panel">
        <div class="panel-title"><div><span class="eyebrow">NOTIFICATIONS</span><h2>教学通知</h2></div></div>
        <button v-for="item in notifications" :key="item.id" class="notice" :class="{ unread: !item.is_read }" type="button" @click="markRead(item)">
          <span class="notice-dot"></span><span><strong>{{ item.title }}</strong><small>{{ item.content }}</small><em>{{ formatTime(item.created_at) }}</em></span>
        </button>
        <el-empty v-if="!notifications.length" description="暂无通知" />
      </aside>
    </section>
  </div>
</template>

<style scoped>
.classroom-page{display:grid;gap:20px}.classroom-hero,.panel{border:1px solid var(--line);background:var(--panel);border-radius:20px;box-shadow:var(--shadow-sm)}.classroom-hero{padding:28px;display:flex;align-items:center;gap:18px;background:linear-gradient(135deg,color-mix(in srgb,var(--accent) 12%,var(--panel)),var(--panel))}.classroom-hero>div:first-child{flex:1}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent)}h1,h2,h3,p{margin:0}h1{font-size:30px;margin:5px 0 8px}.classroom-hero p,.task-card p,.topic-card p{color:var(--muted);line-height:1.7}.hero-stat{min-width:92px;padding:15px;border-radius:15px;background:var(--panel-strong);text-align:center}.hero-stat strong{display:block;font-size:25px}.hero-stat span{font-size:12px;color:var(--muted)}.content-grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px}.main-column{display:grid;gap:20px}.panel{padding:22px}.panel-title,.task-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.panel-title h2{margin-top:4px}.card-list{display:grid;gap:14px}.task-card,.topic-card{display:grid;gap:12px;padding:18px;border:1px solid var(--line);border-radius:16px;background:var(--surface-soft)}.pill,.status{font-size:11px;padding:5px 8px;border-radius:999px;color:var(--accent);background:var(--accent-soft)}.task-head h3{margin-top:8px}.task-card small,.topic-card small{color:var(--muted)}.discussion-form{display:grid;grid-template-columns:170px 1fr auto;gap:10px;margin-bottom:18px}.discussion-form .el-textarea{grid-column:1/3}.reply{display:flex;gap:10px;padding:10px 12px;border-left:3px solid var(--accent);background:var(--panel);border-radius:8px}.reply strong{font-size:13px}.reply span{color:var(--muted)}.reply-box{display:flex;gap:8px}.notice-panel{align-self:start;position:sticky;top:92px}.notice{width:100%;display:flex;gap:10px;padding:14px 8px;border:0;border-top:1px solid var(--line);background:transparent;text-align:left;cursor:pointer}.notice:hover{background:var(--surface-soft)}.notice-dot{width:8px;height:8px;margin-top:5px;border-radius:50%;background:var(--line)}.notice.unread .notice-dot{background:var(--accent);box-shadow:0 0 0 4px var(--accent-soft)}.notice span:last-child{display:grid;gap:4px}.notice small,.notice em{color:var(--muted);font-style:normal;line-height:1.5}.notice em{font-size:11px}@media(max-width:1000px){.content-grid{grid-template-columns:1fr}.notice-panel{position:static}}@media(max-width:700px){.classroom-hero{align-items:flex-start;flex-wrap:wrap}.discussion-form{grid-template-columns:1fr}.discussion-form .el-textarea{grid-column:auto}}
</style>
