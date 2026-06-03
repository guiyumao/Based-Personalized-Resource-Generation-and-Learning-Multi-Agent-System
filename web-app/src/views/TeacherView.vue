<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  teacherApi,
  type ApiEnvelope,
  type HomeworkAssignPayload,
  type HomeworkReviewPayload,
  type StudentInsight,
  type StudentLearningDetail,
  type TeacherClassCreatePayload,
  type TeacherClassItem,
} from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const classes = ref<TeacherClassItem[]>([])
const progress = ref<Record<string, unknown> | null>(null)
const insights = ref<StudentInsight[]>([])
const selectedClassId = ref(1)
const detailVisible = ref(false)
const selectedStudentDetail = ref<StudentLearningDetail | null>(null)

const classForm = reactive<TeacherClassCreatePayload>({
  name: '算法提高班',
  subject: '数据结构',
  teacher_name: authStore.user?.username ?? '教师用户',
})

const homeworkForm = reactive<HomeworkAssignPayload>({
  class_id: 1,
  title: '链表与栈练习',
  description: '完成链表插入、删除和栈模拟题。',
})

const reviewForm = reactive<HomeworkReviewPayload>({
  score: 92,
  comment: '逻辑清晰，建议补充边界处理。',
})

const loading = reactive({
  classes: false,
  create: false,
  progress: false,
  insights: false,
  detail: false,
  assign: false,
  review: false,
})

const assignResult = ref<Record<string, unknown> | null>(null)
const reviewResult = ref<Record<string, unknown> | null>(null)

const classProgressCards = computed(() => {
  if (!progress.value) {
    return []
  }

  return [
    { label: '班级人数', value: String(progress.value.student_count ?? '-') },
    { label: '已完成任务', value: String(progress.value.completed_tasks ?? '-') },
    { label: '平均掌握度', value: `${String(progress.value.average_mastery ?? '-')}%` },
  ]
})

async function fetchClasses() {
  loading.classes = true
  try {
    const { data } = await teacherApi.get<ApiEnvelope<TeacherClassItem[]>>('/teacher/classes')
    classes.value = data.data
    if (classes.value.length > 0) {
      selectedClassId.value = classes.value[0].id
      homeworkForm.class_id = classes.value[0].id
    }
  } catch {
    ElMessage.error('获取班级列表失败')
  } finally {
    loading.classes = false
  }
}

async function createClass() {
  loading.create = true
  try {
    const { data } = await teacherApi.post<ApiEnvelope<TeacherClassItem>>('/teacher/classes', classForm)
    classes.value.unshift(data.data)
    selectedClassId.value = data.data.id
    homeworkForm.class_id = data.data.id
    ElMessage.success('班级创建成功')
  } catch {
    ElMessage.error('班级创建失败')
  } finally {
    loading.create = false
  }
}

async function fetchProgress(classId: number) {
  loading.progress = true
  try {
    const { data } = await teacherApi.get<ApiEnvelope<Record<string, unknown>>>(`/teacher/classes/${classId}/progress`)
    progress.value = data.data
  } catch {
    ElMessage.error('获取班级进度失败')
  } finally {
    loading.progress = false
  }
}

async function fetchInsights(classId: number) {
  loading.insights = true
  try {
    const { data } = await teacherApi.get<ApiEnvelope<StudentInsight[]>>(`/teacher/classes/${classId}/insights`)
    insights.value = data.data
  } catch {
    ElMessage.error('获取学生洞察失败')
  } finally {
    loading.insights = false
  }
}

async function openStudentDetail(student: StudentInsight) {
  loading.detail = true
  detailVisible.value = true
  try {
    const { data } = await teacherApi.get<ApiEnvelope<StudentLearningDetail>>(
      `/teacher/classes/${selectedClassId.value}/students/${student.user_id}`,
    )
    selectedStudentDetail.value = data.data
  } catch {
    selectedStudentDetail.value = null
    ElMessage.error('获取学生详情失败')
  } finally {
    loading.detail = false
  }
}

function openClassWorkspace(classId: number) {
  selectedClassId.value = classId
  homeworkForm.class_id = classId
  void fetchProgress(classId)
  void fetchInsights(classId)
}

async function assignHomework() {
  loading.assign = true
  try {
    const { data } = await teacherApi.post<ApiEnvelope<Record<string, unknown>>>('/teacher/homework/assign', homeworkForm)
    assignResult.value = data.data
    ElMessage.success('作业布置成功')
  } catch {
    ElMessage.error('作业布置失败')
  } finally {
    loading.assign = false
  }
}

async function reviewHomework() {
  loading.review = true
  try {
    const { data } = await teacherApi.post<ApiEnvelope<Record<string, unknown>>>('/teacher/homework/1001/review', reviewForm)
    reviewResult.value = data.data
    ElMessage.success('作业批改成功')
  } catch {
    ElMessage.error('作业批改失败')
  } finally {
    loading.review = false
  }
}

async function logout() {
  authStore.clear()
  ElMessage.success('已退出登录')
  await router.push({ name: 'login' })
}

onMounted(() => {
  void fetchClasses().then(() => {
    void fetchProgress(selectedClassId.value)
    void fetchInsights(selectedClassId.value)
  })
})
</script>

<template>
  <div class="role-shell">
    <div class="role-card large">
      <div class="login-kicker">Teacher Console</div>
      <h1>教师管理系统</h1>
      <p>教师端已经从概览面板升级为可操作工作台，可以查看班级进度、学生洞察，以及每位学生的错题本与学习报告详情。</p>

      <div class="role-meta">
        <span>用户：{{ authStore.user?.username }}</span>
        <span>角色：{{ authStore.user?.role }}</span>
      </div>

      <div class="workspace-grid teacher-grid">
        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">班级管理</div>
              <h2>创建与查看班级</h2>
            </div>
          </div>
          <el-form :model="classForm" label-position="top">
            <el-form-item label="班级名称">
              <el-input v-model="classForm.name" />
            </el-form-item>
            <el-form-item label="学科">
              <el-input v-model="classForm.subject" />
            </el-form-item>
            <el-form-item label="教师姓名">
              <el-input v-model="classForm.teacher_name" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="primary" :loading="loading.create" @click="createClass">创建班级</el-button>
            <el-button :loading="loading.classes" @click="fetchClasses">刷新列表</el-button>
          </div>
          <div class="list-stack">
            <button
              v-for="item in classes"
              :key="item.id"
              class="list-card"
              type="button"
              @click="openClassWorkspace(item.id)"
            >
              <strong>{{ item.name }}</strong>
              <span>{{ item.subject }} / {{ item.teacher_name }}</span>
            </button>
          </div>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">班级进度</div>
              <h2>学习概览卡片</h2>
            </div>
          </div>
          <div class="action-row">
            <el-button :loading="loading.progress" @click="fetchProgress(selectedClassId)">刷新班级进度</el-button>
          </div>
          <div v-if="classProgressCards.length" class="report-grid">
            <article v-for="item in classProgressCards" :key="item.label" class="learning-section">
              <h3>{{ item.value }}</h3>
              <p class="learning-line">{{ item.label }}</p>
            </article>
          </div>
          <div v-else class="empty-state">当前还没有班级进度数据。</div>
        </section>

        <section class="workspace-panel wide">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">学生洞察</div>
              <h2>点击查看学生详细诊断</h2>
            </div>
          </div>
          <div class="action-row">
            <el-button :loading="loading.insights" @click="fetchInsights(selectedClassId)">刷新洞察</el-button>
          </div>
          <div class="report-grid">
            <article
              v-for="student in insights"
              :key="student.user_id"
              class="learning-section clickable-card"
              @click="openStudentDetail(student)"
            >
              <h3>{{ student.student_name }}</h3>
              <p class="learning-line">当前掌握度：{{ student.mastery }}%</p>
              <p class="learning-line">最近学习重点：{{ student.recent_focus }}</p>
              <p class="learning-line">错题数量：{{ student.mistake_count }}</p>
              <p class="learning-line">教师建议：{{ student.report_summary }}</p>
            </article>
          </div>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">作业布置</div>
              <h2>创建教学任务</h2>
            </div>
          </div>
          <el-form :model="homeworkForm" label-position="top">
            <el-form-item label="班级 ID">
              <el-input-number v-model="homeworkForm.class_id" :min="1" />
            </el-form-item>
            <el-form-item label="作业标题">
              <el-input v-model="homeworkForm.title" />
            </el-form-item>
            <el-form-item label="作业描述">
              <el-input v-model="homeworkForm.description" type="textarea" :rows="4" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="success" :loading="loading.assign" @click="assignHomework">布置作业</el-button>
          </div>
          <pre v-if="assignResult" class="result-box">{{ JSON.stringify(assignResult, null, 2) }}</pre>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">作业批改</div>
              <h2>提交批改结果</h2>
            </div>
          </div>
          <el-form :model="reviewForm" label-position="top">
            <el-form-item label="分数">
              <el-input-number v-model="reviewForm.score" :min="0" :max="100" />
            </el-form-item>
            <el-form-item label="评语">
              <el-input v-model="reviewForm.comment" type="textarea" :rows="4" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="warning" :loading="loading.review" @click="reviewHomework">提交批改</el-button>
            <el-button plain @click="logout">退出登录</el-button>
          </div>
          <pre v-if="reviewResult" class="result-box">{{ JSON.stringify(reviewResult, null, 2) }}</pre>
        </section>
      </div>
    </div>
  </div>

  <el-drawer
    v-model="detailVisible"
    size="48%"
    title="学生学习详情"
    :destroy-on-close="false"
  >
    <div v-if="loading.detail" class="empty-state">正在加载学生详情...</div>
    <div v-else-if="selectedStudentDetail" class="teacher-detail-stack">
      <section class="workspace-panel">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">学生画像</div>
            <h2>{{ selectedStudentDetail.student_name }}</h2>
          </div>
        </div>
        <div class="report-grid">
          <article class="learning-section">
            <h3>{{ selectedStudentDetail.mastery }}%</h3>
            <p class="learning-line">当前掌握度</p>
          </article>
          <article class="learning-section">
            <h3>{{ selectedStudentDetail.mistake_count }}</h3>
            <p class="learning-line">错题数量</p>
          </article>
        </div>
        <p class="learning-line">最近学习重点：{{ selectedStudentDetail.recent_focus }}</p>
        <p class="learning-line">教师摘要：{{ selectedStudentDetail.report_summary }}</p>
      </section>

      <section class="workspace-panel">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">错题本</div>
            <h2>近期重点错题</h2>
          </div>
        </div>
        <div v-if="selectedStudentDetail.mistake_notebook.length" class="learning-content">
          <article
            v-for="item in selectedStudentDetail.mistake_notebook"
            :key="item.exercise_id"
            class="exercise-card"
          >
            <div class="exercise-head">
              <el-tag type="danger">题目 {{ item.exercise_id }}</el-tag>
              <el-tag>{{ item.knowledge_point }}</el-tag>
              <el-tag type="warning">{{ item.question_type }}</el-tag>
            </div>
            <p class="learning-line">学生答案：{{ item.user_answer }}</p>
            <p class="learning-line">正确答案：{{ item.correct_answer }}</p>
            <p class="learning-line">解析：{{ item.analysis }}</p>
            <p class="learning-line">建议：{{ item.suggested_action }}</p>
          </article>
        </div>
        <div v-else class="empty-state">当前没有可展示的错题记录。</div>
      </section>

      <section class="workspace-panel">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">阶段报告</div>
            <h2>{{ selectedStudentDetail.stage_report.title }}</h2>
          </div>
        </div>
        <p class="learning-line">{{ selectedStudentDetail.stage_report.summary }}</p>
        <div class="report-block">
          <strong>优势</strong>
          <p
            v-for="item in selectedStudentDetail.stage_report.strengths"
            :key="`stage-strength-${item}`"
            class="learning-line"
          >
            {{ item }}
          </p>
        </div>
        <div class="report-block">
          <strong>薄弱点</strong>
          <p
            v-for="item in selectedStudentDetail.stage_report.weaknesses"
            :key="`stage-weakness-${item}`"
            class="learning-line"
          >
            {{ item }}
          </p>
        </div>
      </section>

      <section class="workspace-panel">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">综合报告</div>
            <h2>{{ selectedStudentDetail.comprehensive_report.title }}</h2>
          </div>
        </div>
        <p class="learning-line">{{ selectedStudentDetail.comprehensive_report.summary }}</p>
        <div class="report-block">
          <strong>下一步建议</strong>
          <p
            v-for="item in selectedStudentDetail.comprehensive_report.next_actions"
            :key="`comp-action-${item}`"
            class="learning-line"
          >
            {{ item }}
          </p>
        </div>
      </section>
    </div>
    <div v-else class="empty-state">请选择一位学生查看详情。</div>
  </el-drawer>
</template>
