<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  agentApi,
  teacherApi,
  type ApiEnvelope,
  type HomeworkAssignPayload,
  type KnowledgeBaseArticle,
  type KnowledgeBaseListResponse,
  type KnowledgeBaseSearchResponse,
  type HomeworkReviewPayload,
  type StudentInsight,
  type StudentLearningDetail,
  type TeacherClassCreatePayload,
  type TeacherClassItem,
  type TeacherTeachingAnalytics,
  type TeachingScopeCreatePayload,
  type TeachingScopeItem,
} from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const teacherPageMeta = {
  overview: {
    title: '教师管理系统',
    description: '教师端用于划定学习范围与方向、投放大学课程课件、布置与批改作业、查看学生错题和班级统计，并为教学安排提供数据建议。',
  },
  classes: {
    title: '班级管理',
    description: '创建班级、选择当前班级并查看班级学习进度，作为后续学习范围、课件、作业与统计分析的数据入口。',
  },
  'knowledge-base': {
    title: '大学课程知识库',
    description: '面向教师备课与课程设计，按学科检索大学课程知识点、案例、误区，并可一键生成学习范围与课件草稿。',
  },
  scopes: {
    title: '学习范围与课件投放',
    description: '为全班或指定学生划定学习知识点、学习方向与教学目标，并同步投放对应课件内容。',
  },
  students: {
    title: '学生洞察',
    description: '查看不同学生的掌握度、近期学习重点、错题数量与诊断建议，支持进入学生详情查看错题与报告。',
  },
  analytics: {
    title: '教学统计与建议',
    description: '聚合学生作答、错题知识点、影响人数与正确率，为教师下一步教学方向提供数据建议。',
  },
  homework: {
    title: '作业管理',
    description: '按班级布置作业任务，提交作业批改结果，并沉淀后续学习反馈数据。',
  },
}

type TeacherPageKey = keyof typeof teacherPageMeta

const activeTeacherPage = computed<TeacherPageKey>(() => {
  const page = route.path.split('/')[2] as TeacherPageKey | undefined
  return page && page in teacherPageMeta ? page : 'overview'
})

const currentTeacherPage = computed(() => teacherPageMeta[activeTeacherPage.value])

function isTeacherPage(...pages: TeacherPageKey[]) {
  return pages.includes(activeTeacherPage.value)
}

const classes = ref<TeacherClassItem[]>([])
const progress = ref<Record<string, unknown> | null>(null)
const insights = ref<StudentInsight[]>([])
const selectedClassId = ref(0)
const detailVisible = ref(false)
const selectedStudentDetail = ref<StudentLearningDetail | null>(null)
const teachingScopes = ref<TeachingScopeItem[]>([])
const teachingAnalytics = ref<TeacherTeachingAnalytics | null>(null)
const knowledgeSubjects = ref<string[]>([])
const knowledgeArticles = ref<KnowledgeBaseArticle[]>([])
const selectedKnowledgeArticle = ref<KnowledgeBaseArticle | null>(null)
const knowledgeSearchText = ref('')
const selectedKnowledgeSubject = ref('')
const knowledgeAuditVisible = ref(false)
const knowledgeAuditDraft = reactive({
  knowledge_points: '',
  learning_direction: '',
  teaching_goal: '',
  courseware_title: '',
  courseware_content: '',
})

const classForm = reactive<TeacherClassCreatePayload>({
  name: '',
  subject: '',
  teacher_name: authStore.user?.username ?? '',
})

const homeworkForm = reactive<HomeworkAssignPayload>({
  class_id: 0,
  title: '',
  description: '',
})

const reviewForm = reactive<HomeworkReviewPayload>({
  score: 0,
  comment: '',
})
const reviewSubmissionId = ref(0)
const scopeKnowledgeText = ref('')
const scopeForm = reactive<TeachingScopeCreatePayload>({
  class_id: 0,
  student_user_id: null,
  knowledge_points: [],
  learning_direction: '',
  courseware_title: '',
  courseware_content: '',
  teaching_goal: '',
})

const loading = reactive({
  classes: false,
  create: false,
  progress: false,
  insights: false,
  detail: false,
  assign: false,
  review: false,
  scopes: false,
  analytics: false,
  knowledgeBase: false,
})

const assignResult = ref<Record<string, unknown> | null>(null)
const reviewResult = ref<Record<string, unknown> | null>(null)

const teacherActionGuides = [
  {
    title: '先建班级与学科',
    detail: '创建班级后，后续进度、学生洞察、学习范围、作业任务都会自动关联到当前班级。',
  },
  {
    title: '划定学习范围',
    detail: '为全班或指定学生设置知识点、学习方向、教学目标，并同步投放课件内容。',
  },
  {
    title: '看错题与统计',
    detail: '学生产生作答后，教师端会汇总错题知识点、影响人数和下一步教学建议。',
  },
  {
    title: '形成教学闭环',
    detail: '按“范围设定 → 课件投放 → 作业布置 → 批改反馈 → 数据分析”持续迭代。',
  },
]

const teacherCapabilityCards = [
  { label: '学习范围', value: '定范围 / 定方向 / 定目标' },
  { label: '课件投放', value: '面向全班或单个学生' },
  { label: '错题追踪', value: '按学生与知识点聚合' },
  { label: '教学建议', value: '基于统计结果生成方向' },
]

const teacherOverviewCards = computed(() => [
  { label: '已创建班级', value: classes.value.length ? `${classes.value.length} 个` : '待创建' },
  { label: '当前班级', value: selectedClassId.value ? `#${selectedClassId.value}` : '未选择' },
  { label: '学生洞察', value: insights.value.length ? `${insights.value.length} 条` : '待生成' },
  { label: '学习范围', value: teachingScopes.value.length ? `${teachingScopes.value.length} 条` : '待划定' },
])

const classProgressCards = computed(() => {
  if (!progress.value) {
    return []
  }

  return [
    { label: '班级人数', value: String(progress.value.student_count ?? '-') },
    { label: '已完成任务', value: String(progress.value.completed_tasks ?? '-') },
    {
      label: '平均掌握度',
      value: progress.value.average_mastery == null ? '-' : `${String(progress.value.average_mastery)}%`,
    },
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
      scopeForm.class_id = classes.value[0].id
    } else {
      selectedClassId.value = 0
      homeworkForm.class_id = 0
      scopeForm.class_id = 0
      progress.value = null
      insights.value = []
      teachingScopes.value = []
      teachingAnalytics.value = null
    }
  } catch {
    classes.value = []
    selectedClassId.value = 0
    homeworkForm.class_id = 0
    scopeForm.class_id = 0
    progress.value = null
    insights.value = []
    teachingScopes.value = []
    teachingAnalytics.value = null
    ElMessage.error('获取班级列表失败')
  } finally {
    loading.classes = false
  }
}

async function createClass() {
  if (!classForm.name.trim() || !classForm.subject.trim() || !classForm.teacher_name.trim()) {
    ElMessage.warning('请先填写班级名称、学科和教师姓名')
    return
  }
  loading.create = true
  try {
    const { data } = await teacherApi.post<ApiEnvelope<TeacherClassItem>>('/teacher/classes', classForm)
    classes.value.unshift(data.data)
    selectedClassId.value = data.data.id
    homeworkForm.class_id = data.data.id
    scopeForm.class_id = data.data.id
    ElMessage.success('班级创建成功')
  } catch {
    ElMessage.error('班级创建失败')
  } finally {
    loading.create = false
  }
}

async function fetchProgress(classId: number) {
  if (!classId) {
    progress.value = null
    ElMessage.warning('请先选择或创建班级')
    return
  }
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
  if (!classId) {
    insights.value = []
    ElMessage.warning('请先选择或创建班级')
    return
  }
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

async function fetchTeachingScopes(classId: number) {
  if (!classId) {
    teachingScopes.value = []
    return
  }
  loading.scopes = true
  try {
    const { data } = await teacherApi.get<ApiEnvelope<TeachingScopeItem[]>>(
      `/teacher/classes/${classId}/teaching-scopes`,
    )
    teachingScopes.value = data.data
  } catch {
    ElMessage.error('获取学习范围失败')
  } finally {
    loading.scopes = false
  }
}

async function fetchTeachingAnalytics(classId: number) {
  if (!classId) {
    teachingAnalytics.value = null
    return
  }
  loading.analytics = true
  try {
    const { data } = await teacherApi.get<ApiEnvelope<TeacherTeachingAnalytics>>(
      `/teacher/classes/${classId}/teaching-analytics`,
    )
    teachingAnalytics.value = data.data
  } catch {
    ElMessage.error('获取教学分析失败')
  } finally {
    loading.analytics = false
  }
}

async function fetchTeacherKnowledgeBase(subject = '') {
  loading.knowledgeBase = true
  try {
    const { data } = await agentApi.get<KnowledgeBaseListResponse>('/knowledge-base', {
      params: subject ? { subject } : {},
    })
    knowledgeSubjects.value = data.subjects
    knowledgeArticles.value = data.items
    selectedKnowledgeArticle.value = data.items[0] ?? null
  } catch {
    knowledgeArticles.value = []
    selectedKnowledgeArticle.value = null
    ElMessage.error('获取大学课程知识库失败')
  } finally {
    loading.knowledgeBase = false
  }
}

async function searchTeacherKnowledgeBase() {
  const query = knowledgeSearchText.value.trim()
  if (!query) {
    await fetchTeacherKnowledgeBase(selectedKnowledgeSubject.value)
    return
  }
  loading.knowledgeBase = true
  try {
    const { data } = await agentApi.get<KnowledgeBaseSearchResponse>('/knowledge-base/search', {
      params: { q: query, top_k: 12 },
    })
    knowledgeArticles.value = selectedKnowledgeSubject.value
      ? data.items.filter((item) => item.subject === selectedKnowledgeSubject.value)
      : data.items
    selectedKnowledgeArticle.value = knowledgeArticles.value[0] ?? null
  } catch {
    ElMessage.error('搜索大学课程知识库失败')
  } finally {
    loading.knowledgeBase = false
  }
}

async function selectKnowledgeSubject(subject: string) {
  selectedKnowledgeSubject.value = selectedKnowledgeSubject.value === subject ? '' : subject
  knowledgeSearchText.value = ''
  await fetchTeacherKnowledgeBase(selectedKnowledgeSubject.value)
}

function openKnowledgeArticle(article: KnowledgeBaseArticle) {
  selectedKnowledgeArticle.value = article
}

function openKnowledgeAudit(article: KnowledgeBaseArticle) {
  knowledgeAuditDraft.knowledge_points = article.concepts.join('、')
  knowledgeAuditDraft.learning_direction = `围绕「${article.title}」建立概念理解、形式化表达、典型例题与常见误区纠偏。`
  knowledgeAuditDraft.teaching_goal = `完成 ${article.subject} 中「${article.title}」的核心概念讲解与迁移应用训练。`
  knowledgeAuditDraft.courseware_title = `${article.title} 教学课件`
  knowledgeAuditDraft.courseware_content = [
    `课程摘要：${article.summary}`,
    `核心概念：${article.concepts.join('、')}`,
    `关键表达：${article.syntax.join('；')}`,
    `典型案例：${article.examples.join('；')}`,
    `常见误区：${article.mistakes.join('；')}`,
    `自检问题：${article.checks.join('；')}`,
  ].join('\n')
  knowledgeAuditVisible.value = true
}

async function confirmKnowledgeAudit() {
  if (
    !knowledgeAuditDraft.knowledge_points.trim() ||
    !knowledgeAuditDraft.learning_direction.trim() ||
    !knowledgeAuditDraft.courseware_title.trim() ||
    !knowledgeAuditDraft.courseware_content.trim()
  ) {
    ElMessage.warning('请先审核并补全知识点、学习方向、课件标题和课件内容')
    return
  }
  scopeKnowledgeText.value = knowledgeAuditDraft.knowledge_points
  scopeForm.learning_direction = knowledgeAuditDraft.learning_direction
  scopeForm.teaching_goal = knowledgeAuditDraft.teaching_goal
  scopeForm.courseware_title = knowledgeAuditDraft.courseware_title
  scopeForm.courseware_content = knowledgeAuditDraft.courseware_content
  knowledgeAuditVisible.value = false
  ElMessage.success('审核通过，已填入学习范围表单，请确认后保存')
  await router.push('/teacher/scopes')
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
  scopeForm.class_id = classId
  void fetchProgress(classId)
  void fetchInsights(classId)
  void fetchTeachingScopes(classId)
  void fetchTeachingAnalytics(classId)
}

async function createTeachingScope() {
  const knowledgePoints = scopeKnowledgeText.value
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
  if (
    !scopeForm.class_id ||
    !knowledgePoints.length ||
    !scopeForm.learning_direction.trim() ||
    !scopeForm.courseware_title.trim() ||
    !scopeForm.courseware_content.trim()
  ) {
    ElMessage.warning('请填写班级、知识点、学习方向和课件内容')
    return
  }
  loading.scopes = true
  try {
    const payload: TeachingScopeCreatePayload = {
      ...scopeForm,
      student_user_id: scopeForm.student_user_id || null,
      knowledge_points: knowledgePoints,
    }
    const { data } = await teacherApi.post<ApiEnvelope<TeachingScopeItem>>('/teacher/teaching-scopes', payload)
    teachingScopes.value.unshift(data.data)
    ElMessage.success('学习范围与课件已保存')
  } catch {
    ElMessage.error('保存学习范围失败')
  } finally {
    loading.scopes = false
  }
}

async function assignHomework() {
  if (!homeworkForm.class_id || !homeworkForm.title.trim() || !homeworkForm.description.trim()) {
    ElMessage.warning('请先选择班级并填写作业标题、描述')
    return
  }
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
  if (!reviewSubmissionId.value || !reviewForm.comment.trim()) {
    ElMessage.warning('请先填写提交记录 ID 和批改评语')
    return
  }
  loading.review = true
  try {
    const { data } = await teacherApi.post<ApiEnvelope<Record<string, unknown>>>(
      `/teacher/homework/${reviewSubmissionId.value}/review`,
      reviewForm,
    )
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
    if (!selectedClassId.value) {
      return
    }
    void fetchProgress(selectedClassId.value)
    void fetchInsights(selectedClassId.value)
    void fetchTeachingScopes(selectedClassId.value)
    void fetchTeachingAnalytics(selectedClassId.value)
  })
  void fetchTeacherKnowledgeBase()
})
</script>

<template>
  <div class="role-shell teacher-role-shell">
    <div class="role-card large teacher-console-card">
      <div class="login-kicker">Teacher Console</div>
      <h1>{{ currentTeacherPage.title }}</h1>
      <p>
        {{ currentTeacherPage.description }}
      </p>

      <div class="role-meta">
        <span>用户：{{ authStore.user?.username }}</span>
        <span>角色：{{ authStore.user?.role }}</span>
        <span>当前班级：{{ selectedClassId || '未选择' }}</span>
      </div>

      <section v-if="isTeacherPage('overview')" class="workspace-panel wide teacher-overview-panel">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">教师工作台</div>
            <h2>教学管理总览</h2>
          </div>
        </div>
        <div class="report-grid teacher-overview-grid">
          <article v-for="item in teacherOverviewCards" :key="item.label" class="learning-section">
            <h3>{{ item.value }}</h3>
            <p class="learning-line">{{ item.label }}</p>
          </article>
        </div>
        <div class="teacher-capability-grid">
          <article v-for="item in teacherCapabilityCards" :key="item.label" class="teacher-capability-card">
            <strong>{{ item.label }}</strong>
            <span>{{ item.value }}</span>
          </article>
        </div>
      </section>

      <section v-if="isTeacherPage('overview') && !classes.length" class="workspace-panel wide teacher-guide-panel">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">开始使用</div>
            <h2>教师端操作流程</h2>
          </div>
        </div>
        <div class="teacher-guide-grid">
          <article v-for="(item, index) in teacherActionGuides" :key="item.title" class="teacher-guide-card">
            <span>{{ index + 1 }}</span>
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.detail }}</p>
            </div>
          </article>
        </div>
      </section>

      <div class="workspace-grid teacher-grid">
        <section v-if="isTeacherPage('classes')" class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">班级管理</div>
              <h2>创建与查看班级</h2>
            </div>
          </div>
          <el-form :model="classForm" label-position="top">
            <el-form-item label="班级名称">
              <el-input v-model="classForm.name" placeholder="请输入班级名称" />
            </el-form-item>
            <el-form-item label="学科">
              <el-input v-model="classForm.subject" placeholder="请输入学科" />
            </el-form-item>
            <el-form-item label="教师姓名">
              <el-input v-model="classForm.teacher_name" placeholder="请输入教师姓名" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="primary" :loading="loading.create" @click="createClass">创建班级</el-button>
            <el-button :loading="loading.classes" @click="fetchClasses">刷新列表</el-button>
          </div>
          <div v-if="classes.length" class="list-stack">
            <button
              v-for="item in classes"
              :key="item.id"
              class="list-card"
              type="button"
              @click="openClassWorkspace(item.id)"
            >
              <strong>{{ item.name }}</strong>
              <span>{{ item.subject }} / {{ item.teacher_name }} / 班级 #{{ item.id }}</span>
            </button>
          </div>
          <div v-else class="empty-state teacher-empty-guide">
            <strong>还没有班级</strong>
            <span>先创建班级，后续学习范围、课件投放、作业和统计都会关联到班级。</span>
          </div>
        </section>

        <section v-if="isTeacherPage('classes')" class="workspace-panel">
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
          <div v-else class="empty-state teacher-empty-guide">
            <strong>暂无班级进度</strong>
            <span>学生完成学习任务后，这里会展示班级人数、完成任务数和平均掌握度。</span>
          </div>
        </section>

        <section v-if="isTeacherPage('knowledge-base')" class="workspace-panel wide teacher-knowledge-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">大学课程知识库</div>
              <h2>面向教师备课与学习范围划定</h2>
            </div>
          </div>
          <div class="teacher-kb-toolbar">
            <el-input
              v-model="knowledgeSearchText"
              placeholder="搜索课程、概念或关键词，例如：事务、递归、TCP、矩阵"
              @keyup.enter="searchTeacherKnowledgeBase"
            />
            <el-button type="primary" :loading="loading.knowledgeBase" @click="searchTeacherKnowledgeBase">搜索</el-button>
            <el-button :loading="loading.knowledgeBase" @click="fetchTeacherKnowledgeBase(selectedKnowledgeSubject)">刷新</el-button>
          </div>
          <div class="teacher-kb-subjects">
            <button
              v-for="subject in knowledgeSubjects"
              :key="subject"
              :class="{ active: selectedKnowledgeSubject === subject }"
              type="button"
              @click="selectKnowledgeSubject(subject)"
            >
              {{ subject }}
            </button>
          </div>
          <div class="teacher-kb-layout">
            <aside class="teacher-kb-list">
              <button
                v-for="article in knowledgeArticles"
                :key="article.id"
                class="teacher-kb-card"
                :class="{ active: selectedKnowledgeArticle?.id === article.id }"
                type="button"
                @click="openKnowledgeArticle(article)"
              >
                <span>{{ article.subject }} / {{ article.level }}</span>
                <strong>{{ article.title }}</strong>
                <small>{{ article.summary }}</small>
              </button>
              <div v-if="!loading.knowledgeBase && !knowledgeArticles.length" class="empty-state teacher-empty-guide">
                <strong>暂无课程知识库内容</strong>
                <span>请检查智能体服务是否运行，或更换关键词后重新搜索。</span>
              </div>
            </aside>
            <main v-if="selectedKnowledgeArticle" class="teacher-kb-detail">
              <div class="teacher-kb-detail-head">
                <div>
                  <div class="panel-kicker">{{ selectedKnowledgeArticle.subject }}</div>
                  <h3>{{ selectedKnowledgeArticle.title }}</h3>
                  <p>{{ selectedKnowledgeArticle.summary }}</p>
                </div>
                <el-button type="success" @click="openKnowledgeAudit(selectedKnowledgeArticle)">
                  生成审核草稿
                </el-button>
              </div>
              <div class="teacher-kb-section-grid">
                <section>
                  <strong>核心概念</strong>
                  <ul>
                    <li v-for="item in selectedKnowledgeArticle.concepts" :key="item">{{ item }}</li>
                  </ul>
                </section>
                <section>
                  <strong>关键表达</strong>
                  <p v-for="item in selectedKnowledgeArticle.syntax" :key="item">{{ item }}</p>
                </section>
                <section>
                  <strong>课程案例</strong>
                  <p v-for="item in selectedKnowledgeArticle.examples" :key="item">{{ item }}</p>
                </section>
                <section>
                  <strong>常见误区</strong>
                  <ul>
                    <li v-for="item in selectedKnowledgeArticle.mistakes" :key="item">{{ item }}</li>
                  </ul>
                </section>
              </div>
            </main>
            <main v-else class="teacher-kb-detail empty-state teacher-empty-guide">
              <strong>请选择课程条目</strong>
              <span>选择后可查看概念、案例、误区，并生成待教师审核的学习范围与课件草稿。</span>
            </main>
          </div>
        </section>

        <section v-if="isTeacherPage('students')" class="workspace-panel wide">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">学生洞察</div>
              <h2>查看不同学生的学习诊断</h2>
            </div>
          </div>
          <div class="action-row">
            <el-button :loading="loading.insights" @click="fetchInsights(selectedClassId)">刷新洞察</el-button>
          </div>
          <div v-if="insights.length" class="report-grid">
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
          <div v-else class="empty-state teacher-empty-guide">
            <strong>暂无学生洞察</strong>
            <span>学生产生学习记录、作答记录或错题后，可查看掌握度、近期重点和个性化建议。</span>
          </div>
        </section>

        <section v-if="isTeacherPage('scopes')" class="workspace-panel wide">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">学习范围与方向</div>
              <h2>划定学生学习范围并投放课件</h2>
            </div>
          </div>
          <el-form :model="scopeForm" label-position="top">
            <div class="form-two-columns">
              <el-form-item label="班级 ID">
                <el-input-number v-model="scopeForm.class_id" :min="1" />
              </el-form-item>
              <el-form-item label="指定学生 ID（可选）">
                <el-input-number v-model="scopeForm.student_user_id" :min="1" />
              </el-form-item>
            </div>
            <el-form-item label="学习知识点范围">
              <el-input v-model="scopeKnowledgeText" placeholder="用逗号、顿号或换行分隔多个知识点" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="学习方向">
              <el-input v-model="scopeForm.learning_direction" placeholder="例如：先补基础概念，再做错题变式与迁移应用" />
            </el-form-item>
            <el-form-item label="教学目标">
              <el-input v-model="scopeForm.teaching_goal" placeholder="例如：本周将该范围正确率提升到 80% 以上" />
            </el-form-item>
            <el-form-item label="课件标题">
              <el-input v-model="scopeForm.courseware_title" placeholder="请输入课件标题" />
            </el-form-item>
            <el-form-item label="课件内容">
              <el-input v-model="scopeForm.courseware_content" type="textarea" :rows="5" placeholder="请输入要投放给学生的课件摘要、重点或学习材料" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="primary" :loading="loading.scopes" @click="createTeachingScope">保存范围与课件</el-button>
            <el-button :loading="loading.scopes" @click="fetchTeachingScopes(selectedClassId)">刷新范围</el-button>
          </div>
          <div v-if="teachingScopes.length" class="learning-content">
            <article v-for="item in teachingScopes" :key="item.id" class="learning-section">
              <div class="exercise-head">
                <el-tag type="success">范围 {{ item.id }}</el-tag>
                <el-tag v-if="item.student_user_id">学生 {{ item.student_user_id }}</el-tag>
                <el-tag v-else>全班</el-tag>
              </div>
              <h3>{{ item.courseware_title }}</h3>
              <p class="learning-line">知识点：{{ item.knowledge_points.join('、') }}</p>
              <p class="learning-line">学习方向：{{ item.learning_direction }}</p>
              <p v-if="item.teaching_goal" class="learning-line">教学目标：{{ item.teaching_goal }}</p>
              <p class="learning-line">课件摘要：{{ item.courseware_content }}</p>
            </article>
          </div>
          <div v-else class="empty-state teacher-empty-guide">
            <strong>暂无学习范围</strong>
            <span>可填写知识点、学习方向、教学目标与课件内容，为全班或指定学生投放学习任务。</span>
          </div>
        </section>

        <section v-if="isTeacherPage('analytics')" class="workspace-panel wide">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">教学统计与建议</div>
              <h2>基于学生错题分析教学方向</h2>
            </div>
          </div>
          <div class="action-row">
            <el-button type="primary" :loading="loading.analytics" @click="fetchTeachingAnalytics(selectedClassId)">刷新教学分析</el-button>
          </div>
          <div v-if="teachingAnalytics" class="teacher-analytics-stack">
            <div class="report-grid">
              <article class="learning-section">
                <h3>{{ teachingAnalytics.student_count }}</h3>
                <p class="learning-line">学生总数</p>
              </article>
              <article class="learning-section">
                <h3>{{ teachingAnalytics.answered_students }}</h3>
                <p class="learning-line">已有作答学生</p>
              </article>
              <article class="learning-section">
                <h3>{{ teachingAnalytics.total_answers }}</h3>
                <p class="learning-line">总作答数</p>
              </article>
              <article class="learning-section">
                <h3>{{ teachingAnalytics.correct_rate == null ? '-' : `${teachingAnalytics.correct_rate}%` }}</h3>
                <p class="learning-line">整体正确率</p>
              </article>
              <article class="learning-section">
                <h3>{{ teachingAnalytics.total_mistakes }}</h3>
                <p class="learning-line">错题总数</p>
              </article>
            </div>
            <div v-if="teachingAnalytics.weak_knowledge_points.length" class="learning-content">
              <article
                v-for="item in teachingAnalytics.weak_knowledge_points"
                :key="item.knowledge_point"
                class="learning-section"
              >
                <h3>{{ item.knowledge_point }}</h3>
                <p class="learning-line">错题数：{{ item.mistake_count }}</p>
                <p class="learning-line">影响学生：{{ item.affected_students }}</p>
                <p class="learning-line">建议方向：{{ item.suggested_direction }}</p>
              </article>
            </div>
            <div v-else class="empty-state teacher-empty-guide">
              <strong>暂无错题统计</strong>
              <span>学生产生错题后，这里会按知识点展示错题数量、影响学生数和建议讲解方向。</span>
            </div>
            <div v-if="teachingAnalytics.teaching_suggestions.length" class="learning-section">
              <h3>教学方向建议</h3>
              <p v-for="item in teachingAnalytics.teaching_suggestions" :key="item" class="learning-line">{{ item }}</p>
            </div>
          </div>
          <div v-else class="empty-state teacher-empty-guide">
            <strong>暂无教学统计</strong>
            <span>当学生完成练习或作业后，系统会聚合错题知识点、影响人数、正确率，并给出教学方向建议。</span>
          </div>
        </section>

        <section v-if="isTeacherPage('homework')" class="workspace-panel">
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
              <el-input v-model="homeworkForm.title" placeholder="请输入作业标题" />
            </el-form-item>
            <el-form-item label="作业描述">
              <el-input v-model="homeworkForm.description" type="textarea" :rows="4" placeholder="请输入作业要求、范围和提交说明" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="success" :loading="loading.assign" @click="assignHomework">布置作业</el-button>
          </div>
          <pre v-if="assignResult" class="result-box">{{ JSON.stringify(assignResult, null, 2) }}</pre>
        </section>

        <section v-if="isTeacherPage('homework')" class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">作业批改</div>
              <h2>提交批改结果</h2>
            </div>
          </div>
          <el-form :model="reviewForm" label-position="top">
            <el-form-item label="提交记录 ID">
              <el-input-number v-model="reviewSubmissionId" :min="1" />
            </el-form-item>
            <el-form-item label="分数">
              <el-input-number v-model="reviewForm.score" :min="0" :max="100" />
            </el-form-item>
            <el-form-item label="评语">
              <el-input v-model="reviewForm.comment" type="textarea" :rows="4" placeholder="请输入批改评语和后续建议" />
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
    class="teacher-detail-drawer"
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
          <article v-for="item in selectedStudentDetail.mistake_notebook" :key="item.exercise_id" class="exercise-card">
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
        <div v-else class="empty-state teacher-empty-guide">
          <strong>暂无错题记录</strong>
          <span>该学生产生错题后，会在这里展示题目、答案、解析和后续建议。</span>
        </div>
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
          <strong>薄弱点</strong>
          <p v-for="item in selectedStudentDetail.stage_report.strengths" :key="`stage-strength-${item}`" class="learning-line">
            {{ item }}
          </p>
        </div>
        <div class="report-block">
          <strong>优势</strong>
          <p v-for="item in selectedStudentDetail.stage_report.weaknesses" :key="`stage-weakness-${item}`" class="learning-line">
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
    <div v-else class="empty-state teacher-empty-guide">
      <strong>请选择学生</strong>
      <span>点击学生洞察卡片后，可查看该学生的错题、阶段报告和综合建议。</span>
    </div>
  </el-drawer>

  <el-dialog
    v-model="knowledgeAuditVisible"
    class="teacher-audit-dialog"
    width="760px"
    title="教师人工审核"
    :close-on-click-modal="false"
  >
    <div class="teacher-audit-tip">
      AI 仅生成学习范围与课件草稿，需教师审核、修改并确认后，才会填入学习范围表单；最终投放仍需点击“保存范围与课件”。
    </div>
    <el-form :model="knowledgeAuditDraft" label-position="top">
      <el-form-item label="学习知识点范围">
        <el-input
          v-model="knowledgeAuditDraft.knowledge_points"
          type="textarea"
          :rows="3"
          placeholder="请审核知识点是否适合当前班级或学生"
        />
      </el-form-item>
      <el-form-item label="学习方向">
        <el-input
          v-model="knowledgeAuditDraft.learning_direction"
          type="textarea"
          :rows="3"
          placeholder="请审核学习方向是否符合教学计划"
        />
      </el-form-item>
      <el-form-item label="教学目标">
        <el-input
          v-model="knowledgeAuditDraft.teaching_goal"
          type="textarea"
          :rows="2"
          placeholder="请审核教学目标是否可执行、可评价"
        />
      </el-form-item>
      <el-form-item label="课件标题">
        <el-input v-model="knowledgeAuditDraft.courseware_title" placeholder="请审核课件标题" />
      </el-form-item>
      <el-form-item label="课件内容">
        <el-input
          v-model="knowledgeAuditDraft.courseware_content"
          type="textarea"
          :rows="8"
          placeholder="请审核课件内容是否准确、完整、适合学生"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="knowledgeAuditVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmKnowledgeAudit">审核通过并填入表单</el-button>
      </div>
    </template>
  </el-dialog>
</template>

