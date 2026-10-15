<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import {
  ArrowRight,
  CloseBold,
  Collection,
  Delete,
  Download,
  Link,
  MagicStick,
  RefreshRight,
  Search,
} from '@element-plus/icons-vue'
import {
  agentApi,
  resourceApi,
  serviceEndpoints,
  type ApiEnvelope,
  type ExternalResourceImportPayload,
  type KnowledgeBaseArticle,
  type KnowledgeBaseListResponse,
  type KnowledgeBaseSearchResponse,
  type ManagedResourceItem,
  type ResourceInteractionSummary,
  type ResourceRecommendationItem,
} from '../../api'
import LearningAtmosphere from '../../components/LearningAtmosphere.vue'

const knowledgeLoading = ref(false)
const route = useRoute()
const resourceLoading = ref(false)
const searchText = ref('')
const selectedSubject = ref('')
const subjects = ref<string[]>([])
const articles = ref<KnowledgeBaseArticle[]>([])
const selectedArticle = ref<KnowledgeBaseArticle | null>(null)
const resources = ref<ManagedResourceItem[]>([])
const recommendations = ref<ResourceRecommendationItem[]>([])
const recommendationLoading = ref(false)
const selectedResource = ref<ManagedResourceItem | null>(null)
const showDetail = ref(false)
const error = ref('')
const importingUrl = ref('')
const articleListRef = ref<HTMLElement | null>(null)
const downloadSectionRef = ref<HTMLElement | null>(null)
const downloadedSectionRef = ref<HTMLElement | null>(null)
const librarySectionRef = ref<HTMLElement | null>(null)
const externalLearningPanelRef = ref<HTMLElement | null>(null)
const showAllResources = ref(false)

const importedResources = computed(() => resources.value.filter((item) => item.source_type === 'external_import'))
const generatedResources = computed(() => resources.value.filter((item) => item.source_type === 'generated'))
const currentArticleDownloaded = computed(() => {
  const title = selectedArticle.value?.title
  if (!title) {
    return []
  }
  return importedResources.value.filter((item) => item.knowledge_point === title)
})
const isLoading = computed(() => knowledgeLoading.value || resourceLoading.value)
const visibleResources = computed(() => showAllResources.value ? resources.value : resources.value.slice(0, 8))

const typeLabel: Record<string, string> = { courseware: '课件', exercise: '练习', notes: '笔记', exam: '试卷' }
const statusLabel: Record<string, string> = { draft: '草稿', ready: '就绪', archived: '归档' }
const statusNext: Record<string, 'draft' | 'ready' | 'archived'> = { draft: 'ready', ready: 'archived', archived: 'draft' }
const sourceLabel: Record<string, string> = { generated: '系统生成', external_import: '官方课件' }
const recommendationStrategyLabel: Record<string, string> = {
  hybrid_collaborative: '协同学习',
  personalized_heuristic: '画像偏好',
  cold_start_popularity: '热门冷启动',
}
const kindLabel: Record<string, string> = {
  mooc_course: 'MOOC 课程',
  textbook: '教材资料',
  lecture_notes: '讲义笔记',
  course: '课程资源',
  video: '视频课程',
  interactive: '互动资源',
  practice: '习题练习',
}
const subjectLabel: Record<string, string> = {
  computer_networks: '计算机网络',
  data_structures: '数据结构',
  algorithms: '算法与数据结构',
  computer_architecture: '计算机组成原理',
  operating_systems: '操作系统',
}

type ExternalLearningSite = {
  name: string
  shortName: string
  description: string
  url: string
}

type CoreSubject = {
  key: string
  label: string
  code: string
  description: string
}

const coreSubjects: CoreSubject[] = [
  { key: 'computer_networks', label: '计算机网络', code: 'NET', description: '协议分层、TCP/IP、路由与 Web 通信' },
  { key: 'data_structures', label: '数据结构', code: 'DS', description: '线性表、树、图、排序与复杂度分析' },
  { key: 'computer_architecture', label: '计算机组成原理', code: 'CO', description: 'CPU、存储系统、指令与总线结构' },
  { key: 'operating_systems', label: '操作系统', code: 'OS', description: '进程、内存、文件系统与并发控制' },
]

const fallbackKnowledgeArticles: KnowledgeBaseArticle[] = [
  {
    id: 'fallback-computer-organization',
    title: '计算机组成原理',
    subject: '计算机基础',
    level: '大学基础',
    summary: '围绕 CPU、存储器、指令系统、总线和输入输出系统理解计算机如何执行程序，适合作为操作系统和体系结构课程的前置基础。',
    concepts: ['CPU', '寄存器', '指令周期', '存储层次', '总线', 'I/O 系统'],
    syntax: ['取指 -> 译码 -> 执行 -> 写回', '地址总线 / 数据总线 / 控制总线', 'Cache 命中率与访存时间'],
    examples: ['分析一条加法指令从内存取出到执行完成的全过程', '比较寄存器、Cache、内存和磁盘的速度与容量差异'],
    mistakes: ['把 CPU 等同于整台主机', '混淆内存地址和指令内容', '只记部件名称但说不清数据流向'],
    applications: ['性能优化', '嵌入式系统', '操作系统内存管理'],
    checks: ['说明指令周期四个阶段', '解释 Cache 为什么能提升性能', '画出 CPU、内存、总线之间的数据流'],
    external_resources: buildTopicResources('计算机组成原理'),
  },
  {
    id: 'fallback-computer-network',
    title: '计算机网络',
    subject: '计算机基础',
    level: '大学基础',
    summary: '从分层模型、IP 地址、TCP/UDP、HTTP 和路由转发理解网络通信过程，适合支撑 Web 开发、后端接口和网络安全学习。',
    concepts: ['OSI 七层模型', 'TCP/IP', 'IP 地址', 'TCP 三次握手', 'HTTP', 'DNS'],
    syntax: ['HTTP 请求行 + 请求头 + 请求体', 'TCP SYN / SYN-ACK / ACK', 'IP + Port 定位网络进程'],
    examples: ['浏览器访问网页时 DNS、TCP、HTTP 的完整链路', '比较 TCP 和 UDP 的可靠性与实时性'],
    mistakes: ['把 HTTP 和 TCP 混为一谈', '忽视端口号作用', '不理解 DNS 与 IP 的关系'],
    applications: ['Web 后端开发', '接口调试', '网络故障排查'],
    checks: ['解释三次握手为什么需要三步', '说明输入网址后发生了什么', '区分 TCP 和 UDP 的适用场景'],
    external_resources: buildTopicResources('计算机网络'),
  },
  {
    id: 'fallback-python',
    title: 'Python 程序设计',
    subject: '程序设计',
    level: '入门到进阶',
    summary: '覆盖 Python 基础语法、函数、模块、文件、异常和面向对象，适合快速完成数据处理、脚本开发和 AI 应用原型。',
    concepts: ['变量', '列表', '字典', '函数', '模块', '文件操作', '异常处理', '类与对象'],
    syntax: ['def function(args):', 'for item in iterable:', 'with open(path) as f:', 'class Student:'],
    examples: ['读取文本文件并统计词频', '用字典保存学生成绩', '封装一个简单的用户类'],
    mistakes: ['缩进错误', '可变默认参数误用', '混淆列表和元组', '异常捕获过宽'],
    applications: ['自动化脚本', '数据分析', 'Web API', '机器学习实验'],
    checks: ['解释列表和字典的区别', '写一个带返回值的函数', '说明 with open 的好处'],
    external_resources: buildTopicResources('Python 程序设计'),
  },
  {
    id: 'fallback-database-sql',
    title: '数据库系统与 SQL',
    subject: '数据库',
    level: '大学核心',
    summary: '学习关系模型、SQL 查询、连接、索引、事务和并发控制，是后端开发和数据管理的基础能力。',
    concepts: ['关系模型', '主键', '外键', 'SELECT', 'JOIN', '索引', '事务', 'ACID'],
    syntax: ['SELECT ... FROM ... WHERE ...', 'INNER JOIN / LEFT JOIN', 'GROUP BY', 'BEGIN / COMMIT / ROLLBACK'],
    examples: ['查询每个班级的平均成绩', '用 JOIN 查询用户和订单', '给高频查询字段建立索引'],
    mistakes: ['WHERE 和 HAVING 混用', 'JOIN 条件缺失导致笛卡尔积', '认为索引越多越好', '忽略事务一致性'],
    applications: ['后端业务系统', '报表分析', '数据建模', '性能优化'],
    checks: ['写出三表连接查询', '解释索引为什么能加速', '说明事务 ACID 含义'],
    external_resources: buildTopicResources('数据库系统 SQL'),
  },
]

function buildTopicResources(topic: string): KnowledgeBaseArticle['external_resources'] {
  const encoded = encodeURIComponent(topic)
  return [
    {
      title: `${topic} - 中国大学 MOOC 课程`,
      provider: '中国大学 MOOC',
      url: `https://www.icourse163.org/search.htm?search=${encoded}`,
      kind: 'mooc_course',
      license: 'external',
      notes: '打开高校公开课和课程资料搜索结果，适合系统学习完整章节。',
    },
    {
      title: `${topic} - 哔哩哔哩视频讲解`,
      provider: '哔哩哔哩',
      url: `https://search.bilibili.com/all?keyword=${encoded}`,
      kind: 'video',
      license: 'external',
      notes: '打开教学视频搜索结果，适合看概念讲解、例题演示和复习串讲。',
    },
    {
      title: `${topic} - 菜鸟教程示例`,
      provider: '菜鸟教程',
      url: `https://www.runoob.com/?s=${encoded}`,
      kind: 'interactive',
      license: 'external',
      notes: '打开教程和示例检索结果，适合查语法、代码片段和入门说明。',
    },
  ]
}

function fallbackSubjects() {
  return Array.from(new Set(fallbackKnowledgeArticles.map((article) => article.subject)))
}

function applyKnowledgeArticles(
  items: KnowledgeBaseArticle[],
  nextSubjects?: string[],
  useFallback = true,
) {
  const usableItems = items.length ? items : useFallback ? fallbackKnowledgeArticles : []
  articles.value = usableItems
  subjects.value = nextSubjects?.length ? nextSubjects : fallbackSubjects()
  selectedArticle.value = usableItems[0] ?? null
}

function matchesCoreSubject(article: KnowledgeBaseArticle, subjectKey: string) {
  const title = article.title.toLowerCase()
  const subject = article.subject.toLowerCase()
  const rules: Record<string, { subjects: string[]; titleTerms: string[] }> = {
    computer_networks: {
      subjects: ['computer_networks', '计算机网络'],
      titleTerms: ['计算机网络', 'tcp/ip', '网络协议'],
    },
    data_structures: {
      subjects: ['data_structures', 'algorithms', '数据结构', '算法与数据结构'],
      titleTerms: ['数据结构', '算法'],
    },
    computer_architecture: {
      subjects: ['computer_architecture', '计算机组成原理'],
      titleTerms: ['计算机组成原理', '计算机体系结构'],
    },
    operating_systems: {
      subjects: ['operating_systems', '操作系统'],
      titleTerms: ['操作系统', 'xv6'],
    },
  }
  const rule = rules[subjectKey]
  return !rule || rule.subjects.includes(subject) || rule.titleTerms.some((term) => title.includes(term))
}

const externalLearningTopic = computed(() => {
  return normalizeLearningTopic(
    selectedArticle.value?.title
    || searchText.value
    || selectedSubject.value
    || firstAvailableResourceTopic.value,
  )
})

const firstAvailableResourceTopic = computed(() => {
  const resource = resources.value.find((item) => normalizeLearningTopic(item.knowledge_point))
  return resource ? learningTopicForResource(resource) : ''
})

const externalLearningSites = computed(() => buildExternalLearningSites(externalLearningTopic.value))
const summaryCardText = computed(() => ({
  knowledge: selectedArticle.value
    ? `当前专题：${selectedArticle.value.title}`
    : articles.value.length
      ? `已加载 ${articles.value.length} 个知识库专题`
      : `示例专题：${fallbackKnowledgeArticles[0].title}`,
  saved: importedResources.value.length
    ? `最近保存：${importedResources.value[0].title}`
    : '下载后的课件会在这里显示',
  generated: generatedResources.value.length
    ? `最近生成：${generatedResources.value[0].title}`
    : '系统生成资源会在这里统一沉淀',
}))

onMounted(() => {
  void refreshPage()
})

async function refreshPage() {
  const isCoreSubject = coreSubjects.some((subject) => subject.key === selectedSubject.value)
  await Promise.all([
    isCoreSubject ? searchKnowledgeBase() : fetchKnowledgeBase(selectedSubject.value),
    fetchResources(),
    fetchRecommendations(),
  ])
  const linkedResourceId = Number(route.query.resource)
  if (Number.isInteger(linkedResourceId) && linkedResourceId > 0 && !showDetail.value) {
    const linkedResource = resources.value.find((item) => item.id === linkedResourceId)
    if (linkedResource) openDetail(linkedResource)
  }
}

async function fetchRecommendations(showLoading = true) {
  if (showLoading) recommendationLoading.value = true
  try {
    const { data } = await resourceApi.get<ApiEnvelope<ResourceRecommendationItem[]>>('/resources/recommendations', {
      params: { limit: 6 },
    })
    recommendations.value = data.data ?? []
  } catch {
    recommendations.value = []
  } finally {
    if (showLoading) recommendationLoading.value = false
  }
}

async function fetchKnowledgeBase(subject = '') {
  knowledgeLoading.value = true
  error.value = ''
  try {
    const { data } = await agentApi.get<KnowledgeBaseListResponse>('/knowledge-base', {
      params: subject ? { subject } : {},
    })
    applyKnowledgeArticles(data.items, data.subjects)
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    applyKnowledgeArticles([])
    error.value = `加载大学知识库失败，已展示本地示例资源：${detail}`
  } finally {
    knowledgeLoading.value = false
  }
}

async function fetchResources() {
  resourceLoading.value = true
  try {
    const { data } = await resourceApi.get<ApiEnvelope<ManagedResourceItem[]>>('/resources')
    resources.value = data.data ?? []
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    resources.value = []
    error.value = error.value || `加载已保存资源失败：${detail}`
  } finally {
    resourceLoading.value = false
  }
}

async function searchKnowledgeBase() {
  const query = searchText.value.trim()
  if (!query) {
    await fetchKnowledgeBase(selectedSubject.value)
    return
  }
  knowledgeLoading.value = true
  error.value = ''
  try {
    const { data } = await agentApi.get<KnowledgeBaseSearchResponse>('/knowledge-base/search', {
      params: {
        q: query,
        top_k: 12,
        ...(selectedSubject.value ? { subject: selectedSubject.value } : {}),
      },
    })
    const strictItems = coreSubjects.some((subject) => subject.key === selectedSubject.value)
      ? data.items.filter((item) => matchesCoreSubject(item, selectedSubject.value))
      : data.items
    applyKnowledgeArticles(strictItems, subjects.value, false)
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    const normalizedQuery = query.toLowerCase()
    const fallbackMatches = fallbackKnowledgeArticles.filter((article) => {
      const haystack = [article.title, article.subject, article.summary, ...article.concepts].join(' ').toLowerCase()
      return haystack.includes(normalizedQuery)
    })
    const strictFallbackMatches = coreSubjects.some((subject) => subject.key === selectedSubject.value)
      ? fallbackMatches.filter((item) => matchesCoreSubject(item, selectedSubject.value))
      : fallbackMatches
    applyKnowledgeArticles(strictFallbackMatches, subjects.value, false)
    error.value = `搜索大学知识库失败，已展示本地示例资源：${detail}`
  } finally {
    knowledgeLoading.value = false
  }
}

async function selectSubject(subject: string) {
  selectedSubject.value = selectedSubject.value === subject ? '' : subject
  searchText.value = ''
  await fetchKnowledgeBase(selectedSubject.value)
}

function selectArticle(article: KnowledgeBaseArticle) {
  selectedArticle.value = article
}

async function selectCoreSubject(subject: CoreSubject) {
  const isCurrent = selectedSubject.value === subject.key
  selectedSubject.value = isCurrent ? '' : subject.key
  searchText.value = isCurrent ? '' : subject.label
  await searchKnowledgeBase()
}

function isCoreSubjectActive(subject: CoreSubject) {
  return selectedSubject.value === subject.key
}

function displaySubject(subject: string) {
  return subjectLabel[subject] ?? subject
}

function scrollToElement(element: HTMLElement | null) {
  element?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function focusSummaryTarget(target: 'knowledge' | 'saved' | 'generated') {
  if (target === 'knowledge') {
    if (!selectedArticle.value && articles.value.length) {
      selectedArticle.value = articles.value[0]
    }
    scrollToElement(articleListRef.value)
    return
  }

  if (target === 'saved') {
    scrollToElement(downloadedSectionRef.value)
    return
  }

  scrollToElement(librarySectionRef.value)
}

function openDetail(item: ManagedResourceItem) {
  selectedResource.value = item
  showDetail.value = true
  void recordResourceInteraction(item, 'view')
}

async function recordResourceInteraction(
  item: ManagedResourceItem,
  action: 'view' | 'download' | 'open_source',
) {
  try {
    const { data } = await resourceApi.post<ApiEnvelope<ResourceInteractionSummary>>(
      `/resources/${item.id}/interactions`,
      { action },
    )
    const summary = data.data
    const current = recommendations.value.find((candidate) => candidate.id === item.id)
    if (current && summary) {
      current.view_count = summary.view_count
      current.download_count = summary.download_count
    }
    if (summary?.recorded) void fetchRecommendations(false)
  } catch {
    // Resource access should still work when optional behaviour tracking is unavailable.
  }
}

function resolveDownloadLink(item: ManagedResourceItem) {
  return item.download_url ? `${serviceEndpoints.resource}${item.download_url}` : ''
}

function isGarbledText(value?: string | null) {
  const text = value?.trim() ?? ''
  if (!text) {
    return true
  }
  return /\uFFFD/.test(text) || /^\?+$/.test(text) || /\?{4,}/.test(text)
}

function normalizeLearningTopic(value?: string | null) {
  const text = value?.trim() ?? ''
  return isGarbledText(text) ? '' : text
}

function displayKnowledgePoint(item: ManagedResourceItem) {
  const point = normalizeLearningTopic(item.knowledge_point)
  if (point) {
    return point
  }

  const title = normalizeLearningTopic(item.title)
  if (!title) {
    return '未识别知识点'
  }

  const generatedTitleMatch = title.match(/个性化课件[：:]\s*(.+)$/)
  if (generatedTitleMatch?.[1]?.trim()) {
    return generatedTitleMatch[1].trim()
  }

  const inferred = title
    .replace(/个性化课件.*$/, '')
    .replace(/课件.*$/, '')
    .replace(/[：:].*$/, '')
    .trim()
  return inferred || title
}

function learningTopicForResource(item: ManagedResourceItem) {
  const point = displayKnowledgePoint(item)
  if (point !== '未识别知识点') {
    return point
  }
  return normalizeLearningTopic(item.title) || '计算机基础'
}

function buildExternalLearningSites(topic: string): ExternalLearningSite[] {
  const keyword = normalizeLearningTopic(topic) || '计算机基础'
  const encoded = encodeURIComponent(keyword)
  return [
    {
      name: '中国大学 MOOC',
      shortName: 'MOOC',
      description: `搜索“${keyword}”相关大学课程`,
      url: `https://www.icourse163.org/search.htm?search=${encoded}`,
    },
    {
      name: '哔哩哔哩',
      shortName: 'B站',
      description: `搜索“${keyword}”教学视频`,
      url: `https://search.bilibili.com/all?keyword=${encoded}`,
    },
    {
      name: '菜鸟教程',
      shortName: '菜鸟',
      description: `搜索“${keyword}”教程与示例`,
      url: `https://www.runoob.com/?s=${encoded}`,
    },
  ]
}

function findDownloadedResource(resource: KnowledgeBaseArticle['external_resources'][number]) {
  return importedResources.value.find((item) => item.external_url === resource.url)
}

async function importResource(resource: KnowledgeBaseArticle['external_resources'][number]) {
  const article = selectedArticle.value
  if (!article) {
    return
  }
  const downloaded = findDownloadedResource(resource)
  if (downloaded?.download_url) {
    void recordResourceInteraction(downloaded, 'download')
    window.open(resolveDownloadLink(downloaded), '_blank', 'noreferrer')
    return
  }

  const payload: ExternalResourceImportPayload = {
    title: resource.title,
    provider: resource.provider,
    url: resource.url,
    kind: resource.kind,
    license: resource.license,
    notes: resource.notes,
    knowledge_point: article.title,
    owner_user_id: null,
  }

  importingUrl.value = resource.url
  try {
    const { data } = await resourceApi.post<ApiEnvelope<ManagedResourceItem>>('/resources/import-external', payload)
    const imported = data.data
    await fetchResources()
    if (imported?.download_url) {
      void recordResourceInteraction(imported, 'download')
      window.open(`${serviceEndpoints.resource}${imported.download_url}`, '_blank', 'noreferrer')
    }
    ElMessage.success('课件已下载并保存到资源库')
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    ElMessage.error(`下载课件失败：${detail}`)
  } finally {
    importingUrl.value = ''
  }
}

async function exportResource(item: ManagedResourceItem, format: 'pdf' | 'word') {
  try {
    await resourceApi.post(`/resources/${item.id}/export`, { export_format: format })
    ElMessage.success(`已发起 ${format.toUpperCase()} 导出`)
  } catch {
    ElMessage.error('导出失败')
  }
}

async function updateStatus(item: ManagedResourceItem, status: 'draft' | 'ready' | 'archived') {
  try {
    await resourceApi.patch(`/resources/${item.id}/status`, { status })
    item.status = status
    ElMessage.success('状态已更新')
  } catch {
    ElMessage.error('状态更新失败')
  }
}

async function deleteSelectedResource() {
  const item = selectedResource.value
  if (!item) {
    return
  }

  try {
    await ElMessageBox.confirm(
      `删除后，“${item.title}”将从资源库移除${item.is_downloadable ? '，本地下载文件也会一并删除' : ''}。`,
      '删除资源',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  try {
    await resourceApi.delete(`/resources/${item.id}`)
    selectedResource.value = null
    showDetail.value = false
    await Promise.all([fetchResources(), fetchRecommendations()])
    ElMessage.success('资源已删除')
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    ElMessage.error(`删除资源失败：${detail}`)
  }
}

async function deleteAllResources() {
  if (!resources.value.length) {
    ElMessage.warning('当前没有可删除的资源')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确认一键删除全部 ${resources.value.length} 项已保存资源吗？已下载的本地文件也会一并删除。`,
      '一键删除全部资源',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  try {
    const { data } = await resourceApi.delete<ApiEnvelope<{ deleted_count: number }>>('/resources')
    selectedResource.value = null
    showDetail.value = false
    await Promise.all([fetchResources(), fetchRecommendations()])
    ElMessage.success(`已删除 ${data.data?.deleted_count ?? 0} 项资源`)
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    ElMessage.error(`一键删除失败：${detail}`)
  }
}

async function deleteAllGeneratedResources() {
  if (!generatedResources.value.length) {
    ElMessage.warning('当前没有可删除的系统生成资源')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除全部 ${generatedResources.value.length} 项系统生成资源吗？`,
      '删除全部系统生成资源',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  const { data } = await resourceApi.delete<ApiEnvelope<{ deleted_count: number }>>('/resources', {
    params: { source_type: 'generated' },
  })
  await Promise.all([fetchResources(), fetchRecommendations()])
  ElMessage.success(`已删除 ${data.data?.deleted_count ?? 0} 项系统生成资源`)
}

async function deleteAllImportedResources() {
  if (!importedResources.value.length) {
    ElMessage.warning('当前没有可删除的官方课件')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除全部 ${importedResources.value.length} 项官方课件吗？已下载的本地文件也会一并删除。`,
      '删除全部官方课件',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  const { data } = await resourceApi.delete<ApiEnvelope<{ deleted_count: number }>>('/resources', {
    params: { source_type: 'external_import' },
  })
  await Promise.all([fetchResources(), fetchRecommendations()])
  ElMessage.success(`已删除 ${data.data?.deleted_count ?? 0} 项官方课件`)
}
</script>

<template>
  <div class="resource-page">
    <header class="resource-header">
      <div class="hero-copy">
        <div class="panel-kicker"><span></span> Learning Resource Hub</div>
        <h1>大学知识库与课件中心</h1>
        <p>从课程知识点出发，快速检索讲义、教材和公开课件，并把有用内容沉淀到个人资源库。</p>
        <div class="hero-meta">
          <span class="health-badge"><i></i>知识库已连接</span>
          <span>覆盖 4 门计算机核心课</span>
          <button type="button" :disabled="isLoading" class="refresh-button" @click="refreshPage">
            <RefreshRight aria-hidden="true" />
            {{ isLoading ? '刷新中' : '刷新数据' }}
          </button>
        </div>
        <LearningAtmosphere class="resource-atmosphere" variant="side" />
      </div>

      <div class="resource-summary" aria-label="资源概览">
        <button type="button" class="summary-card" :title="summaryCardText.knowledge" @click="focusSummaryTarget('knowledge')">
          <span class="summary-icon"><Collection aria-hidden="true" /></span>
          <span class="summary-copy"><small>知识库专题</small><strong>{{ articles.length }}</strong></span>
        </button>
        <button type="button" class="summary-card" :title="summaryCardText.saved" @click="focusSummaryTarget('saved')">
          <span class="summary-icon"><Download aria-hidden="true" /></span>
          <span class="summary-copy"><small>已保存课件</small><strong>{{ importedResources.length }}</strong></span>
        </button>
        <button type="button" class="summary-card" :title="summaryCardText.generated" @click="focusSummaryTarget('generated')">
          <span class="summary-icon"><MagicStick aria-hidden="true" /></span>
          <span class="summary-copy"><small>系统生成</small><strong>{{ generatedResources.length }}</strong></span>
        </button>
      </div>
    </header>

    <div v-if="error" class="resource-error" role="status" aria-live="polite">{{ error }}</div>

    <section class="resource-toolbar" aria-labelledby="resource-search-title">
      <div class="toolbar-heading">
        <div>
          <span>Knowledge Search</span>
          <h2 id="resource-search-title">今天想学什么？</h2>
        </div>
        <p>输入概念，或直接选择核心课程进入专题。</p>
      </div>

      <form class="resource-search" @submit.prevent="searchKnowledgeBase">
        <Search aria-hidden="true" />
        <input
          v-model="searchText"
          aria-label="搜索知识库"
          placeholder="搜索课程、概念或关键词，例如：TCP、递归、虚拟内存"
        />
        <span class="search-hint">Enter</span>
        <button type="submit" :disabled="knowledgeLoading">
          {{ knowledgeLoading ? '检索中...' : '搜索知识库' }}
        </button>
      </form>

      <div class="core-subject-grid" aria-label="计算机核心课程">
        <button
          v-for="subject in coreSubjects"
          :key="subject.key"
          type="button"
          class="core-subject-card"
          :class="{ active: isCoreSubjectActive(subject) }"
          :aria-pressed="isCoreSubjectActive(subject)"
          @click="selectCoreSubject(subject)"
        >
          <span class="subject-code">{{ subject.code }}</span>
          <span class="subject-copy">
            <strong>{{ subject.label }}</strong>
            <small>{{ subject.description }}</small>
          </span>
          <ArrowRight class="subject-arrow" aria-hidden="true" />
        </button>
      </div>

      <div class="filter-bar">
        <div class="subject-row" aria-label="更多学科筛选">
          <span>更多学科</span>
          <button type="button" :class="{ active: !selectedSubject }" @click="selectSubject('')">全部</button>
          <button
            v-for="subject in subjects"
            :key="subject"
            type="button"
            :class="{ active: selectedSubject === subject }"
            @click="selectSubject(subject)"
          >
            {{ subject }}
          </button>
        </div>
        <div class="external-learning-panel">
          <span><Link aria-hidden="true" />站外补充</span>
          <nav class="external-learning-links" aria-label="外部学习网站">
            <a
              v-for="site in externalLearningSites"
              :key="site.name"
              :href="site.url"
              target="_blank"
              rel="noreferrer"
              :title="site.description"
            >{{ site.shortName }}</a>
          </nav>
        </div>
      </div>
    </section>

    <section class="resource-layout" aria-label="知识库检索结果">
      <aside ref="articleListRef" class="article-list">
        <div class="list-heading">
          <div><span>检索结果</span><strong>{{ articles.length }} 个专题</strong></div>
          <small>{{ selectedSubject ? '已应用学科筛选' : '按相关度排列' }}</small>
        </div>

        <template v-if="knowledgeLoading">
          <div v-for="index in 4" :key="`skeleton-${index}`" class="article-skeleton" aria-hidden="true">
            <span></span><strong></strong><i></i><i></i>
          </div>
        </template>
        <template v-else>
          <button
            v-for="article in articles"
            :key="article.id"
            type="button"
            class="article-card"
            :class="{ active: selectedArticle?.id === article.id }"
            :aria-pressed="selectedArticle?.id === article.id"
            @click="selectArticle(article)"
          >
            <span class="meta-row">
              <span>{{ displaySubject(article.subject) }}</span>
              <span>{{ article.level }}</span>
            </span>
            <strong>{{ article.title }}</strong>
            <span class="article-summary">{{ article.summary }}</span>
            <span class="article-cta">查看课件 <ArrowRight aria-hidden="true" /></span>
          </button>
          <div v-if="!articles.length" class="empty-state">暂无匹配的大学知识库内容。</div>
        </template>
      </aside>

      <main class="courseware-panel">
        <template v-if="selectedArticle">
          <div class="detail-head">
            <div>
              <div class="meta-row">
                <span>{{ displaySubject(selectedArticle.subject) }}</span>
                <span>{{ selectedArticle.level }}</span>
              </div>
              <h2>{{ selectedArticle.title }}</h2>
              <p>{{ selectedArticle.summary }}</p>
            </div>
            <span class="resource-count">{{ selectedArticle.external_resources.length }} 项关联资源</span>
          </div>

          <section ref="downloadSectionRef" class="download-section">
            <div class="section-title">
              <span>COURSE MATERIALS</span>
              <h3>可用课件</h3>
              <p>从原始来源查看资料，或下载并保存到你的个人资源库。</p>
            </div>

            <div v-if="selectedArticle.external_resources.length" class="download-grid">
              <article v-for="resource in selectedArticle.external_resources" :key="resource.url" class="download-card">
                <div class="meta-row">
                  <span>{{ resource.provider }}</span>
                  <span>{{ kindLabel[resource.kind] ?? resource.kind }}</span>
                </div>
                <h4>{{ resource.title }}</h4>
                <p>{{ resource.notes }}</p>
                <div class="download-actions">
                  <a :href="resource.url" target="_blank" rel="noreferrer"><Link aria-hidden="true" />打开原站</a>
                  <button type="button" :disabled="importingUrl === resource.url" @click="importResource(resource)">
                    <Download aria-hidden="true" />
                    {{
                      importingUrl === resource.url
                        ? '下载中...'
                        : findDownloadedResource(resource)
                          ? '打开已保存'
                          : '下载课件'
                    }}
                  </button>
                </div>
              </article>
            </div>
            <div v-else class="empty-state">
              <div>当前知识点暂无可下载课件。</div>
              <div ref="externalLearningPanelRef" class="empty-state-actions">
                <a v-for="site in externalLearningSites" :key="`empty-${site.name}`" :href="site.url" target="_blank" rel="noreferrer">
                  去{{ site.shortName }}
                </a>
              </div>
            </div>
          </section>

          <section ref="downloadedSectionRef" class="downloaded-section">
            <div class="section-title compact-title">
              <h3>当前专题已保存</h3>
              <p>已下载课件可重复打开或下载。</p>
            </div>
            <div v-if="currentArticleDownloaded.length" class="saved-grid">
              <button v-for="item in currentArticleDownloaded" :key="item.id" type="button" class="saved-item" @click="openDetail(item)">
                <span><Download aria-hidden="true" /></span>
                <span><strong>{{ item.title }}</strong><small>{{ item.provider }} / {{ item.format }}</small></span>
                <ArrowRight aria-hidden="true" />
              </button>
            </div>
            <div v-else class="empty-state compact">还没有保存当前专题的课件。</div>
          </section>
        </template>
        <div v-else class="empty-state panel-empty">请选择一个知识库专题。</div>
      </main>
    </section>

    <section class="recommendation-section" aria-labelledby="recommendation-title">
      <div class="recommendation-heading">
        <div class="section-title">
          <span>FOR YOU</span>
          <h3 id="recommendation-title">基于学习行为的推荐</h3>
          <p>融合相似学习者、相似资源、学习画像与全站真实热度动态排序。</p>
        </div>
        <span class="recommendation-signal"><MagicStick aria-hidden="true" />协同 + 画像 + 热度</span>
      </div>

      <div v-if="recommendationLoading" class="recommendation-grid" aria-label="正在加载推荐资源">
        <div v-for="index in 3" :key="`recommendation-skeleton-${index}`" class="recommendation-card recommendation-skeleton" aria-hidden="true">
          <span></span><strong></strong><i></i><i></i>
        </div>
      </div>
      <div v-else-if="recommendations.length" class="recommendation-grid">
        <button
          v-for="(item, index) in recommendations"
          :key="item.id"
          type="button"
          class="recommendation-card"
          :class="{ featured: index === 0 }"
          @click="openDetail(item)"
        >
          <span class="recommendation-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <span class="recommendation-copy">
            <small>{{ item.recommendation_reason }} · {{ recommendationStrategyLabel[item.recommendation_strategy] || '个性化排序' }}</small>
            <strong>{{ item.title }}</strong>
            <span>{{ displayKnowledgePoint(item) }} · {{ item.format }}</span>
          </span>
          <span class="recommendation-metrics">
            <span>{{ item.view_count }} 次查看</span>
            <span>{{ item.download_count }} 次下载</span>
          </span>
          <ArrowRight class="recommendation-arrow" aria-hidden="true" />
        </button>
      </div>
      <div v-else class="empty-state recommendation-empty">
        <MagicStick aria-hidden="true" />
        <div><strong>推荐池正在积累</strong><span>保存或生成资源后，系统会结合你的学习行为自动排序。</span></div>
      </div>
    </section>

    <section ref="librarySectionRef" class="library-section">
      <div class="library-heading">
        <div class="section-title">
          <span>MY LIBRARY</span>
          <h3>个人资源库</h3>
          <p>统一管理下载的官方课件和系统生成的个性化学习资源。</p>
        </div>
        <div class="library-heading-actions">
          <span class="library-total">共 {{ resources.length }} 项</span>
          <details class="library-tools">
            <summary>批量管理</summary>
            <div class="library-tool-menu">
              <button type="button" :disabled="resourceLoading || !generatedResources.length" @click="deleteAllGeneratedResources">
                <Delete aria-hidden="true" />删除系统生成资源
              </button>
              <button type="button" :disabled="resourceLoading || !importedResources.length" @click="deleteAllImportedResources">
                <Delete aria-hidden="true" />删除官方课件
              </button>
              <button type="button" :disabled="resourceLoading || !resources.length" class="danger-button" @click="deleteAllResources">
                <Delete aria-hidden="true" />清空资源库
              </button>
            </div>
          </details>
        </div>
      </div>

      <div v-if="resources.length" class="library-grid">
        <article v-for="item in visibleResources" :key="item.id" class="library-card" @click="openDetail(item)">
          <div class="library-card-head">
            <div class="meta-row">
              <span>{{ typeLabel[item.type] ?? item.type }}</span>
              <span>{{ sourceLabel[item.source_type] ?? item.source_type }}</span>
            </div>
            <span class="status-badge">{{ statusLabel[item.status] ?? item.status }}</span>
          </div>
          <h4>{{ item.title }}</h4>
          <p>知识点：{{ displayKnowledgePoint(item) }}</p>
          <p>格式：{{ item.format }}<template v-if="item.provider"> / {{ item.provider }}</template></p>
          <div class="card-learning-links" @click.stop>
            <a
              v-for="site in buildExternalLearningSites(learningTopicForResource(item))"
              :key="`${item.id}-${site.name}`"
              :href="site.url"
              target="_blank"
              rel="noreferrer"
              :title="site.description"
              @click="recordResourceInteraction(item, 'open_source')"
            >{{ site.shortName }}</a>
          </div>
        </article>
      </div>
      <button v-if="resources.length > 8" type="button" class="show-more-button" @click="showAllResources = !showAllResources">
        {{ showAllResources ? '收起资源' : `查看全部 ${resources.length} 项资源` }}
      </button>
      <div v-else-if="!resourceLoading" class="empty-state">暂无已保存资源。先在上方选择知识点并下载课件。</div>
    </section>

    <div v-if="showDetail && selectedResource" class="modal-mask" role="presentation" @click.self="showDetail = false">
      <div class="resource-modal" role="dialog" aria-modal="true" :aria-label="selectedResource.title">
        <div class="modal-head">
          <div class="meta-row">
            <span>{{ typeLabel[selectedResource.type] ?? selectedResource.type }}</span>
            <span>{{ sourceLabel[selectedResource.source_type] ?? selectedResource.source_type }}</span>
          </div>
          <button type="button" class="icon-button" aria-label="关闭资源详情" @click="showDetail = false"><CloseBold aria-hidden="true" /></button>
        </div>

        <h3>{{ selectedResource.title }}</h3>
        <div class="modal-info">
          <div>知识点：{{ displayKnowledgePoint(selectedResource) }}</div>
          <div>状态：{{ statusLabel[selectedResource.status] ?? selectedResource.status }}</div>
          <div>格式：{{ selectedResource.format }}</div>
          <div v-if="selectedResource.provider">提供方：{{ selectedResource.provider }}</div>
          <div v-if="selectedResource.source_kind">资源类型：{{ kindLabel[selectedResource.source_kind] ?? selectedResource.source_kind }}</div>
          <div v-if="selectedResource.file_name">文件名：{{ selectedResource.file_name }}</div>
          <a v-if="selectedResource.external_url" :href="selectedResource.external_url" target="_blank" rel="noreferrer" @click="recordResourceInteraction(selectedResource, 'open_source')">查看原始来源</a>
          <div v-if="selectedResource.notes">{{ selectedResource.notes }}</div>
        </div>

        <div class="modal-actions">
          <a v-for="site in buildExternalLearningSites(learningTopicForResource(selectedResource))" :key="site.name" :href="site.url" target="_blank" rel="noreferrer" @click="recordResourceInteraction(selectedResource, 'open_source')">
            {{ site.name }}
          </a>
          <a v-if="selectedResource.is_downloadable && selectedResource.download_url" :href="resolveDownloadLink(selectedResource)" target="_blank" rel="noreferrer" class="primary-link" @click="recordResourceInteraction(selectedResource, 'download')">
            下载课件文件
          </a>
          <button v-if="selectedResource.source_type === 'generated'" type="button" @click="exportResource(selectedResource, 'pdf')">导出 PDF</button>
          <button v-if="selectedResource.source_type === 'generated'" type="button" @click="exportResource(selectedResource, 'word')">导出 Word</button>
          <button type="button" @click="updateStatus(selectedResource, statusNext[selectedResource.status])">
            切换为 {{ statusLabel[statusNext[selectedResource.status]] }}
          </button>
          <button type="button" class="danger-button" @click="deleteSelectedResource">从资源库删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped media="not all">
.resource-page {
  display: grid;
  gap: 18px;
  color: var(--text);
  --resource-surface: color-mix(in srgb, var(--panel) 92%, var(--bg));
  --resource-surface-strong: color-mix(in srgb, var(--panel-strong) 94%, var(--bg));
  --resource-surface-soft: color-mix(in srgb, var(--panel) 76%, var(--bg));
  --resource-line: var(--line);
  --resource-accent-glow: color-mix(in srgb, var(--accent) 18%, transparent);
}

.resource-header,
.resource-toolbar,
.courseware-panel,
.recommendation-section,
.library-section {
  border: 1px solid var(--resource-line);
  background:
    radial-gradient(circle at 0% 0%, var(--resource-accent-glow), transparent 34%),
    var(--resource-surface);
  border-radius: 18px;
  box-shadow: 0 18px 46px color-mix(in srgb, #000 22%, transparent);
}

.resource-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  padding: 24px;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.resource-header h2 {
  margin: 8px 0;
  font-size: 26px;
  font-weight: 750;
  color: var(--text);
}

.resource-header p,
.section-title p,
.article-card p,
.download-card p,
.library-card p,
.modal-info {
  color: var(--muted);
  line-height: 1.7;
}

.secondary-button,
.resource-search button,
.download-actions button,
.modal-actions button,
.primary-link {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px 16px;
  background: var(--resource-surface-strong);
  color: var(--text);
  cursor: pointer;
  font-family: inherit;
  font-weight: 650;
  text-decoration: none;
}

.download-actions button,
.primary-link {
  border: none;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  color: #fff;
}

.danger-button {
  border-color: color-mix(in srgb, var(--red) 45%, transparent);
  background: color-mix(in srgb, var(--red) 12%, transparent);
  color: var(--red);
}

.resource-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.resource-summary article {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 18px;
  border: 1px solid var(--resource-line);
  border-radius: 14px;
  background: var(--resource-surface);
  box-shadow: inset 0 1px color-mix(in srgb, var(--text) 8%, transparent);
}

.summary-card {
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.summary-card:hover,
.summary-card:focus-visible {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: color-mix(in srgb, var(--accent) 8%, var(--resource-surface));
  outline: none;
}

.resource-summary span {
  color: var(--muted);
  font-size: 13px;
}

.resource-summary strong {
  color: var(--accent);
  font-size: 22px;
}

.resource-summary small {
  color: var(--muted);
  line-height: 1.5;
  min-height: 2.4em;
}

.resource-error {
  padding: 14px 16px;
  border-radius: 14px;
  color: var(--red);
  background: color-mix(in srgb, var(--red) 8%, transparent);
}

.resource-toolbar {
  display: grid;
  gap: 14px;
  padding: 16px;
}

.resource-search {
  display: flex;
  gap: 10px;
}

.resource-search input {
  flex: 1;
  border: 1px solid var(--resource-line);
  background: var(--resource-surface-strong);
  color: var(--text);
  border-radius: 12px;
  padding: 12px 14px;
  font-family: inherit;
}

.resource-search input::placeholder {
  color: var(--muted);
}

.external-learning-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  padding: 14px;
  border: 1px solid var(--resource-line);
  border-radius: 14px;
  background: color-mix(in srgb, var(--accent) 7%, var(--resource-surface-strong));
}

.external-learning-panel > div {
  display: grid;
  gap: 4px;
}

.external-learning-panel strong {
  color: var(--text);
}

.external-learning-panel span,
.external-learning-links span {
  color: var(--muted);
  font-size: 12px;
}

.external-learning-links,
.card-learning-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.external-learning-links a,
.card-learning-links a,
.modal-actions a:not(.primary-link) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--resource-line));
  border-radius: 10px;
  padding: 7px 10px;
  background: color-mix(in srgb, var(--accent) 9%, transparent);
  color: var(--accent);
  font-weight: 700;
  text-decoration: none;
}

.external-learning-links a:hover,
.card-learning-links a:hover,
.modal-actions a:not(.primary-link):hover {
  border-color: color-mix(in srgb, var(--accent) 52%, transparent);
  background: color-mix(in srgb, var(--accent) 15%, transparent);
}

.external-learning-links b {
  color: var(--text);
}

.subject-row,
.meta-row,
.download-actions,
.modal-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.subject-row button {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  border-radius: 999px;
  padding: 7px 12px;
  cursor: pointer;
  font-family: inherit;
}

.subject-row button.active {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}

.resource-layout {
  display: grid;
  grid-template-columns: minmax(260px, 340px) 1fr;
  gap: 18px;
}

.article-list {
  display: grid;
  align-content: start;
  gap: 12px;
  min-height: 388px;
  padding: 16px;
  border: 1px solid var(--resource-line);
  border-radius: 18px;
  background: var(--resource-surface);
  box-shadow: 0 18px 46px color-mix(in srgb, #000 18%, transparent);
}

.article-card,
.download-card,
.library-card,
.saved-item {
  border: 1px solid var(--resource-line);
  background: var(--resource-surface-soft);
  border-radius: 14px;
}

.article-card {
  padding: 16px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.article-card:hover,
.article-card.active {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, var(--resource-surface));
}

.article-card h3,
.download-card h4,
.library-card h4 {
  margin: 10px 0 8px;
  color: var(--text);
}

.meta-row span,
.status-badge {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
}

.courseware-panel,
.library-section {
  padding: 20px;
}

.detail-head {
  margin-bottom: 20px;
}

.detail-head h2,
.section-title h3 {
  margin: 10px 0 8px;
}

.download-section,
.downloaded-section {
  margin-top: 18px;
}

.download-grid,
.library-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.download-card,
.library-card {
  padding: 16px;
  transition: border-color 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.download-card:hover,
.library-card:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--accent) 36%, transparent);
  background: color-mix(in srgb, var(--accent) 8%, var(--resource-surface));
}

.download-actions {
  justify-content: space-between;
  align-items: center;
  margin-top: 14px;
}

.download-actions a,
.modal-info a {
  color: var(--accent);
  text-decoration: none;
}

.saved-grid {
  display: grid;
  gap: 10px;
}

.saved-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  padding: 12px 14px;
  color: var(--text);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  transition: border-color 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.saved-item:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--accent) 34%, transparent);
  background: color-mix(in srgb, var(--accent) 8%, var(--resource-surface));
}

.saved-item span {
  color: var(--muted);
}

.library-card {
  cursor: pointer;
}

.card-learning-links {
  margin-top: 12px;
}

.card-learning-links a {
  min-height: 28px;
  padding: 5px 9px;
  font-size: 12px;
}

.library-card-head,
.modal-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.empty-state {
  padding: 28px;
  border: 1px dashed color-mix(in srgb, var(--accent) 22%, var(--resource-line));
  border-radius: 14px;
  color: var(--muted);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, transparent), transparent 46%),
    var(--resource-surface-soft) !important;
  text-align: center;
}

.empty-state.compact {
  padding: 16px;
}

.panel-empty {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-style: solid;
}

.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.resource-modal {
  width: min(92vw, 560px);
  padding: 26px;
  border: 1px solid var(--resource-line);
  border-radius: 18px;
  background: var(--resource-surface-strong);
  box-shadow: 0 40px 100px rgba(0, 0, 0, 0.5);
}

.resource-modal h3 {
  margin: 16px 0 10px;
}

.modal-info {
  display: grid;
  gap: 8px;
  margin-bottom: 20px;
  font-size: 14px;
}

.icon-button {
  width: 32px;
  height: 32px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  color: var(--muted);
  cursor: pointer;
}

@media (max-width: 1100px) {
  .resource-summary,
  .resource-layout,
  .download-grid,
  .library-grid {
    grid-template-columns: 1fr;
  }

  .resource-header,
  .header-actions,
  .resource-search,
  .external-learning-panel,
  .saved-item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

<style scoped>
/* Resource workspace redesign: dense, task-first, theme-aware. */
.resource-page {
  --resource-border: color-mix(in srgb, var(--line) 88%, transparent);
  --resource-soft: color-mix(in srgb, var(--surface-soft) 72%, var(--panel));
  display: grid;
  gap: 18px;
  color: var(--text);
}

.resource-page button,
.resource-page input,
.resource-page summary { font: inherit; }

.resource-header,
.resource-toolbar,
.courseware-panel,
.recommendation-section,
.library-section {
  border: 1px solid var(--resource-border);
  background: var(--panel);
  box-shadow: var(--shadow-soft);
}

.resource-header {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(420px, .85fr);
  gap: clamp(28px, 5vw, 72px);
  align-items: center;
  min-height: 230px;
  padding: clamp(26px, 4vw, 44px);
  border-radius: 20px;
  position: relative;
  overflow: hidden;
}

.resource-atmosphere {
  max-width: 260px;
  margin-top: 16px;
  opacity: .9;
}

.resource-header::before {
  content: '';
  width: 5px;
  height: 72px;
  border-radius: 0 4px 4px 0;
  background: var(--accent);
  position: absolute;
  left: 0;
  top: 44px;
}

.panel-kicker {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .13em;
  text-transform: uppercase;
}

.panel-kicker span {
  width: 22px;
  height: 2px;
  border-radius: 2px;
  background: currentColor;
}

.hero-copy h1 {
  width: auto;
  max-width: none;
  margin: 11px 0 10px;
  color: var(--text);
  font-size: clamp(28px, 3.2vw, 40px);
  line-height: 1.2;
  letter-spacing: -.045em;
}

.hero-copy > p {
  max-width: 680px;
  margin: 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.8;
}

.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  align-items: center;
  margin-top: 22px;
  color: var(--muted);
  font-size: 12px;
}

.health-badge { display: inline-flex; align-items: center; gap: 7px; color: var(--text); font-weight: 650; }
.health-badge i { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 4px color-mix(in srgb, var(--green) 14%, transparent); }
.refresh-button { display: inline-flex; align-items: center; gap: 6px; padding: 0; border: 0; color: var(--accent); background: transparent; font-size: 12px; font-weight: 750; cursor: pointer; }
.refresh-button svg { width: 15px; height: 15px; }
.refresh-button:hover:not(:disabled) { color: var(--accent-deep); }
.refresh-button:disabled { opacity: .55; cursor: wait; }

.resource-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.summary-card {
  min-width: 0;
  display: flex;
  gap: 11px;
  align-items: center;
  padding: 15px 14px;
  border: 1px solid var(--resource-border);
  border-radius: 14px;
  color: var(--text);
  background: var(--resource-soft);
  text-align: left;
  cursor: pointer;
  transition: transform .18s ease, border-color .18s ease, background .18s ease;
}

.summary-card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--accent) 34%, var(--line)); background: var(--panel); }
.summary-icon { width: 34px; height: 34px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 10px; color: var(--accent); background: var(--accent-soft); }
.summary-icon svg { width: 17px; height: 17px; }
.summary-copy { min-width: 0; }
.summary-copy small { display: block; overflow: hidden; color: var(--muted); font-size: 10px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.summary-copy strong { display: block; margin-top: 2px; color: var(--text); font-size: 24px; line-height: 1; font-variant-numeric: tabular-nums; }

.resource-error { padding: 12px 15px; border: 1px solid color-mix(in srgb, var(--warning) 36%, var(--line)); border-radius: 12px; color: color-mix(in srgb, var(--warning) 78%, var(--text)); background: color-mix(in srgb, var(--warning) 8%, var(--panel)); font-size: 13px; }

.resource-toolbar { padding: 24px; border-radius: 18px; }
.toolbar-heading { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-bottom: 18px; }
.toolbar-heading span,.section-title > span { color: var(--accent); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.toolbar-heading h2 { margin: 5px 0 0; color: var(--text); font-size: 22px; letter-spacing: -.025em; }
.toolbar-heading p { margin: 0; color: var(--muted); font-size: 12px; }

.resource-search {
  min-height: 52px;
  display: grid;
  grid-template-columns: 22px 1fr auto auto;
  gap: 10px;
  align-items: center;
  padding: 5px 5px 5px 15px;
  border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--line));
  border-radius: 14px;
  background: var(--panel-strong);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 4%, transparent);
}
.resource-search > svg { width: 19px; height: 19px; color: var(--muted); }
.resource-search input { min-width: 0; border: 0; outline: 0; color: var(--text); background: transparent; font-size: 14px; }
.resource-search input::placeholder { color: color-mix(in srgb, var(--muted) 72%, transparent); }
.resource-search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
.search-hint { padding: 4px 7px; border: 1px solid var(--line); border-radius: 6px; color: var(--muted); background: var(--surface-soft); font-size: 9px; letter-spacing: .03em; }
.resource-search button { align-self: stretch; padding: 0 20px; border: 0; border-radius: 10px; color: #fff; background: var(--accent); font-size: 12px; font-weight: 750; cursor: pointer; }
.resource-search button:hover:not(:disabled) { background: var(--accent-deep); }
.resource-search button:disabled { opacity: .6; cursor: wait; }

.core-subject-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 16px; }
.core-subject-card { min-width: 0; display: grid; grid-template-columns: 42px 1fr 16px; gap: 11px; align-items: center; padding: 14px; border: 1px solid var(--resource-border); border-radius: 13px; color: var(--text); background: var(--panel); text-align: left; cursor: pointer; transition: border-color .18s ease, background .18s ease, transform .18s ease; }
.core-subject-card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--accent) 40%, var(--line)); }
.core-subject-card.active { border-color: color-mix(in srgb, var(--accent) 56%, var(--line)); background: var(--accent-soft); }
.subject-code { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 11px; color: var(--accent); background: var(--accent-soft); font-size: 11px; font-weight: 850; letter-spacing: .05em; }
.core-subject-card.active .subject-code { color: #fff; background: var(--accent); }
.subject-copy { min-width: 0; }
.subject-copy strong,.subject-copy small { display: block; }
.subject-copy strong { font-size: 13px; }
.subject-copy small { margin-top: 4px; overflow: hidden; color: var(--muted); font-size: 10px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.subject-arrow { width: 14px; color: var(--muted); }
.core-subject-card:hover .subject-arrow,.core-subject-card.active .subject-arrow { color: var(--accent); }

.filter-bar { display: flex; justify-content: space-between; gap: 18px; align-items: center; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--resource-border); }
.subject-row { min-width: 0; display: flex; gap: 7px; align-items: center; overflow-x: auto; scrollbar-width: none; }
.subject-row::-webkit-scrollbar { display: none; }
.subject-row > span { flex: 0 0 auto; margin-right: 3px; color: var(--muted); font-size: 11px; font-weight: 700; }
.subject-row button { flex: 0 0 auto; padding: 6px 10px; border: 1px solid var(--resource-border); border-radius: 8px; color: var(--muted); background: transparent; font-size: 10px; cursor: pointer; }
.subject-row button:hover,.subject-row button.active { border-color: color-mix(in srgb, var(--accent) 38%, var(--line)); color: var(--accent); background: var(--accent-soft); }
.external-learning-panel { flex: 0 0 auto; display: flex; gap: 9px; align-items: center; padding: 0; border: 0; background: transparent; }
.external-learning-panel > span { display: inline-flex; gap: 5px; align-items: center; color: var(--muted); font-size: 10px; }
.external-learning-panel > span svg { width: 13px; }
.external-learning-links { display: flex; gap: 5px; }
.external-learning-links a { padding: 5px 8px; border-radius: 7px; color: var(--accent); background: var(--accent-soft); font-size: 10px; font-weight: 700; text-decoration: none; }
.external-learning-links a:hover { color: #fff; background: var(--accent); }

.resource-layout { display: grid; grid-template-columns: minmax(280px, 330px) minmax(0, 1fr); gap: 18px; align-items: start; }
.article-list { max-height: 760px; display: grid; gap: 9px; padding: 14px; border: 1px solid var(--resource-border); border-radius: 18px; background: var(--panel); box-shadow: var(--shadow-soft); overflow-y: auto; position: sticky; top: 18px; scrollbar-width: thin; }
.list-heading { display: flex; justify-content: space-between; gap: 10px; align-items: end; padding: 4px 4px 10px; border-bottom: 1px solid var(--resource-border); }
.list-heading div span,.list-heading div strong { display: block; }
.list-heading div span { color: var(--muted); font-size: 10px; }
.list-heading div strong { margin-top: 3px; color: var(--text); font-size: 14px; }
.list-heading > small { color: var(--muted); font-size: 9px; }
.article-card { width: 100%; display: block; padding: 15px; border: 1px solid transparent; border-radius: 13px; color: var(--text); background: var(--resource-soft); text-align: left; cursor: pointer; transition: border-color .18s ease, background .18s ease, transform .18s ease; }
.article-card:hover { transform: translateX(2px); border-color: color-mix(in srgb, var(--accent) 26%, var(--line)); background: var(--panel); }
.article-card.active { border-color: color-mix(in srgb, var(--accent) 46%, var(--line)); background: var(--accent-soft); box-shadow: inset 3px 0 var(--accent); }
.meta-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.meta-row > span { padding: 4px 7px; border-radius: 6px; color: var(--muted); background: var(--surface-soft); font-size: 9px; font-weight: 700; }
.article-card > strong { display: block; margin-top: 10px; color: var(--text); font-size: 14px; line-height: 1.45; }
.article-summary { display: -webkit-box; margin-top: 6px; overflow: hidden; color: var(--muted); font-size: 11px; line-height: 1.65; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.article-cta { display: inline-flex; gap: 4px; align-items: center; margin-top: 10px; color: var(--accent); font-size: 10px; font-weight: 700; }
.article-cta svg { width: 12px; }
.article-skeleton { display: grid; gap: 10px; padding: 16px; border-radius: 13px; background: var(--resource-soft); overflow: hidden; }
.article-skeleton span,.article-skeleton strong,.article-skeleton i { display: block; border-radius: 6px; background: color-mix(in srgb, var(--muted) 12%, transparent); animation: resource-pulse 1.2s ease-in-out infinite alternate; }
.article-skeleton span { width: 38%; height: 15px; }.article-skeleton strong { width: 72%; height: 18px; }.article-skeleton i { width: 100%; height: 10px; }.article-skeleton i:last-child { width: 82%; }
@keyframes resource-pulse { to { opacity: .42; } }

.courseware-panel { min-width: 0; padding: clamp(22px, 3vw, 32px); border-radius: 18px; }
.detail-head { display: flex; justify-content: space-between; gap: 24px; align-items: start; padding-bottom: 24px; border-bottom: 1px solid var(--resource-border); }
.detail-head h2 { margin: 12px 0 8px; color: var(--text); font-size: clamp(24px, 2.6vw, 32px); letter-spacing: -.035em; }
.detail-head p { max-width: 850px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; }
.resource-count { flex: 0 0 auto; padding: 7px 10px; border-radius: 8px; color: var(--accent); background: var(--accent-soft); font-size: 10px; font-weight: 750; }
.download-section { padding-top: 24px; }
.section-title h3 { margin: 4px 0 5px; color: var(--text); font-size: 19px; letter-spacing: -.02em; }
.section-title p { margin: 0; color: var(--muted); font-size: 11px; line-height: 1.65; }
.download-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
.download-card { min-width: 0; display: flex; flex-direction: column; padding: 17px; border: 1px solid var(--resource-border); border-radius: 14px; background: var(--resource-soft); }
.download-card h4 { margin: 12px 0 7px; color: var(--text); font-size: 14px; line-height: 1.5; }
.download-card > p { flex: 1; margin: 0; color: var(--muted); font-size: 10px; line-height: 1.65; }
.download-actions { display: flex; justify-content: space-between; gap: 8px; align-items: center; margin-top: 16px; }
.download-actions a,.download-actions button { display: inline-flex; gap: 5px; align-items: center; min-height: 34px; padding: 0 10px; border-radius: 8px; font-size: 10px; font-weight: 750; text-decoration: none; }
.download-actions svg { width: 13px; }
.download-actions a { border: 1px solid var(--resource-border); color: var(--muted); background: var(--panel); }
.download-actions a:hover { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 38%, var(--line)); }
.download-actions button { border: 1px solid var(--accent); color: #fff; background: var(--accent); cursor: pointer; }
.download-actions button:hover:not(:disabled) { background: var(--accent-deep); }
.download-actions button:disabled { opacity: .6; cursor: wait; }
.downloaded-section { margin-top: 24px; padding-top: 22px; border-top: 1px solid var(--resource-border); }
.compact-title { display: flex; justify-content: space-between; gap: 16px; align-items: baseline; }
.saved-grid { display: grid; gap: 8px; margin-top: 12px; }
.saved-item { display: grid; grid-template-columns: 36px 1fr 16px; gap: 10px; align-items: center; width: 100%; padding: 10px 12px; border: 1px solid var(--resource-border); border-radius: 11px; color: var(--text); background: var(--resource-soft); text-align: left; cursor: pointer; }
.saved-item > span:first-child { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 9px; color: var(--accent); background: var(--accent-soft); }
.saved-item svg { width: 15px; }.saved-item > span:nth-child(2) { min-width: 0; }.saved-item strong,.saved-item small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.saved-item strong { font-size: 12px; }.saved-item small { margin-top: 2px; color: var(--muted); font-size: 9px; }.saved-item > svg { color: var(--muted); }

.recommendation-section { padding: clamp(22px, 3vw, 30px); border-radius: 18px; }
.recommendation-heading { display: flex; justify-content: space-between; gap: 24px; align-items: start; margin-bottom: 18px; }
.recommendation-signal { display: inline-flex; gap: 6px; align-items: center; padding: 7px 10px; border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--line)); border-radius: 8px; color: var(--accent); background: var(--accent-soft); font-size: 10px; font-weight: 750; white-space: nowrap; }
.recommendation-signal svg { width: 13px; }
.recommendation-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 11px; }
.recommendation-card { min-width: 0; display: grid; grid-template-columns: 36px minmax(0, 1fr) 15px; gap: 10px; align-items: start; padding: 16px; border: 1px solid var(--resource-border); border-radius: 13px; color: var(--text); background: var(--resource-soft); text-align: left; cursor: pointer; transition: transform .18s ease, border-color .18s ease, background .18s ease; }
.recommendation-card.featured { grid-column: span 2; padding: 20px; border-color: color-mix(in srgb, var(--accent) 32%, var(--line)); background: color-mix(in srgb, var(--accent) 7%, var(--panel)); }
.recommendation-card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); background: var(--panel); }
.recommendation-index { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 9px; color: var(--accent); background: var(--accent-soft); font-size: 10px; font-weight: 850; font-variant-numeric: tabular-nums; }
.recommendation-copy { min-width: 0; display: block; }
.recommendation-copy small,.recommendation-copy strong,.recommendation-copy > span { display: block; }
.recommendation-copy small { overflow: hidden; color: var(--accent); font-size: 9px; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }
.recommendation-copy strong { margin-top: 6px; overflow: hidden; font-size: 13px; line-height: 1.5; text-overflow: ellipsis; white-space: nowrap; }
.recommendation-card.featured .recommendation-copy strong { font-size: 16px; }
.recommendation-copy > span { margin-top: 5px; overflow: hidden; color: var(--muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.recommendation-metrics { grid-column: 2 / -1; display: flex; flex-wrap: wrap; gap: 12px; padding-top: 9px; border-top: 1px solid var(--resource-border); color: var(--muted); font-size: 9px; }
.recommendation-arrow { width: 14px; margin-top: 9px; color: var(--muted); }
.recommendation-card:hover .recommendation-arrow { color: var(--accent); }
.recommendation-skeleton { min-height: 118px; display: grid; grid-template-columns: 34px 1fr; cursor: default; }
.recommendation-skeleton > span,.recommendation-skeleton > strong,.recommendation-skeleton > i { display: block; border-radius: 6px; background: color-mix(in srgb, var(--muted) 12%, transparent); animation: resource-pulse 1.2s ease-in-out infinite alternate; }
.recommendation-skeleton > span { width: 34px; height: 34px; grid-row: span 3; }.recommendation-skeleton > strong { width: 72%; height: 14px; }.recommendation-skeleton > i { width: 100%; height: 9px; }.recommendation-skeleton > i:last-child { width: 62%; }
.recommendation-empty { display: flex; justify-content: center; gap: 12px; align-items: center; text-align: left; }
.recommendation-empty > svg { width: 24px; color: var(--accent); }.recommendation-empty strong,.recommendation-empty span { display: block; }.recommendation-empty strong { color: var(--text); font-size: 12px; }.recommendation-empty span { margin-top: 3px; font-size: 10px; }

.library-section { padding: clamp(22px, 3vw, 30px); border-radius: 18px; }
.library-heading { display: flex; justify-content: space-between; gap: 24px; align-items: start; margin-bottom: 18px; }
.library-heading-actions { display: flex; gap: 9px; align-items: center; }
.library-total { color: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.library-tools { position: relative; }
.library-tools summary { padding: 7px 10px; border: 1px solid var(--resource-border); border-radius: 8px; color: var(--muted); background: var(--panel); font-size: 10px; font-weight: 700; cursor: pointer; list-style: none; }
.library-tools summary::-webkit-details-marker { display: none; }
.library-tools[open] summary { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, var(--line)); }
.library-tool-menu { width: 190px; display: grid; gap: 4px; padding: 7px; border: 1px solid var(--resource-border); border-radius: 11px; background: var(--panel-strong); box-shadow: var(--shadow); position: absolute; top: calc(100% + 7px); right: 0; z-index: 8; }
.library-tool-menu button { display: flex; gap: 7px; align-items: center; padding: 8px 9px; border: 0; border-radius: 7px; color: var(--text); background: transparent; font-size: 10px; text-align: left; cursor: pointer; }
.library-tool-menu button svg { width: 13px; }.library-tool-menu button:hover:not(:disabled) { background: var(--surface-soft); }.library-tool-menu button.danger-button { color: var(--red); }.library-tool-menu button:disabled { opacity: .4; cursor: not-allowed; }
.library-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 11px; }
.library-card { min-width: 0; padding: 15px; border: 1px solid var(--resource-border); border-radius: 13px; background: var(--resource-soft); cursor: pointer; transition: transform .18s ease, border-color .18s ease, background .18s ease; }
.library-card:hover { transform: translateY(-2px); border-color: color-mix(in srgb, var(--accent) 32%, var(--line)); background: var(--panel); }
.library-card-head { display: flex; justify-content: space-between; gap: 8px; align-items: start; }
.status-badge { flex: 0 0 auto; padding: 4px 7px; border-radius: 6px; color: var(--green); background: color-mix(in srgb, var(--green) 10%, transparent); font-size: 9px; font-weight: 750; }
.library-card h4 { min-height: 42px; margin: 12px 0 9px; overflow: hidden; color: var(--text); font-size: 13px; line-height: 1.55; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.library-card > p { margin: 4px 0; overflow: hidden; color: var(--muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.card-learning-links { display: flex; gap: 5px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--resource-border); }
.card-learning-links a { padding: 4px 7px; border-radius: 6px; color: var(--accent); background: var(--accent-soft); font-size: 9px; font-weight: 700; text-decoration: none; }
.show-more-button { display: block; margin: 18px auto 0; padding: 8px 13px; border: 1px solid var(--resource-border); border-radius: 9px; color: var(--accent); background: var(--panel); font-size: 11px; font-weight: 700; cursor: pointer; }
.show-more-button:hover { border-color: color-mix(in srgb, var(--accent) 42%, var(--line)); background: var(--accent-soft); }

.empty-state { margin-top: 14px; padding: 22px; border: 1px dashed color-mix(in srgb, var(--accent) 24%, var(--line)); border-radius: 12px; color: var(--muted); background: var(--resource-soft); font-size: 11px; text-align: center; }
.empty-state.compact { padding: 14px; }.panel-empty { min-height: 340px; display: grid; place-items: center; margin: 0; }.empty-state-actions { display: flex; justify-content: center; gap: 7px; margin-top: 10px; }.empty-state-actions a { color: var(--accent); }

.modal-mask { display: grid; place-items: center; padding: 20px; background: color-mix(in srgb, #020617 64%, transparent); backdrop-filter: blur(5px); position: fixed; inset: 0; z-index: 100; }
.resource-modal { width: min(640px, 100%); max-height: min(760px, calc(100vh - 40px)); padding: 24px; border: 1px solid var(--resource-border); border-radius: 18px; color: var(--text); background: var(--panel-strong); box-shadow: 0 28px 80px rgba(2, 6, 23, .32); overflow-y: auto; }
.modal-head { display: flex; justify-content: space-between; gap: 16px; align-items: center; }.icon-button { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid var(--resource-border); border-radius: 9px; color: var(--muted); background: var(--panel); cursor: pointer; }.icon-button svg { width: 14px; }.icon-button:hover { color: var(--text); background: var(--surface-soft); }
.resource-modal h3 { margin: 18px 0 12px; font-size: 23px; letter-spacing: -.025em; }.modal-info { display: grid; gap: 8px; padding: 15px; border-radius: 12px; color: var(--muted); background: var(--resource-soft); font-size: 12px; line-height: 1.6; }.modal-info a { color: var(--accent); }.modal-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }.modal-actions a,.modal-actions button { padding: 8px 11px; border: 1px solid var(--resource-border); border-radius: 8px; color: var(--text); background: var(--panel); font-size: 10px; font-weight: 700; text-decoration: none; cursor: pointer; }.modal-actions .primary-link { border-color: var(--accent); color: #fff; background: var(--accent); }.modal-actions .danger-button { color: var(--red); border-color: color-mix(in srgb, var(--red) 30%, var(--line)); }

@media (max-width: 1180px) {
  .resource-header { grid-template-columns: 1fr; min-height: 0; gap: 24px; }
  .resource-summary { max-width: 650px; }
  .core-subject-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .library-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 920px) {
  .resource-layout { grid-template-columns: 1fr; }
  .article-list { max-height: none; grid-template-columns: repeat(2, minmax(0, 1fr)); position: static; overflow: visible; }
  .list-heading { grid-column: 1 / -1; }
  .download-grid { grid-template-columns: 1fr; }
  .library-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .recommendation-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .recommendation-card.featured { grid-column: span 2; }
}

@media (max-width: 700px) {
  .resource-page { gap: 12px; }
  .resource-header { gap: 20px; padding: 24px 20px; border-radius: 16px; }
  .resource-header::before { top: 30px; height: 58px; }
  .hero-copy h1 { font-size: 28px; }
  .hero-copy > p { font-size: 12px; line-height: 1.7; }
  .hero-meta { margin-top: 17px; }
  .resource-summary { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; }
  .summary-card { gap: 7px; padding: 11px 9px; border-radius: 11px; }
  .summary-icon { width: 29px; height: 29px; border-radius: 8px; }.summary-icon svg { width: 14px; }.summary-copy small { font-size: 9px; }.summary-copy strong { font-size: 20px; }
  .resource-toolbar,.courseware-panel,.recommendation-section,.library-section { padding: 18px; border-radius: 15px; }
  .toolbar-heading { align-items: start; flex-direction: column; gap: 6px; margin-bottom: 13px; }.toolbar-heading h2 { font-size: 20px; }.toolbar-heading p { font-size: 10px; }
  .resource-search { grid-template-columns: 19px 1fr auto; min-height: 48px; padding-left: 12px; }.search-hint { display: none; }.resource-search button { padding-inline: 13px; }
  .core-subject-grid { gap: 8px; margin-top: 12px; }.core-subject-card { grid-template-columns: 36px 1fr; gap: 9px; padding: 11px; }.subject-code { width: 36px; height: 36px; }.subject-copy strong { font-size: 12px; }.subject-copy small { display: none; }.subject-arrow { display: none; }
  .filter-bar { align-items: start; flex-direction: column; gap: 10px; margin-top: 12px; padding-top: 11px; }.subject-row { width: 100%; }.external-learning-panel { width: 100%; justify-content: space-between; }
  .article-list { grid-template-columns: 1fr; padding: 10px; border-radius: 15px; }.article-card { padding: 13px; }.article-summary { -webkit-line-clamp: 1; }
  .detail-head { flex-direction: column; gap: 13px; padding-bottom: 18px; }.detail-head h2 { font-size: 24px; }.resource-count { align-self: flex-start; }.download-section { padding-top: 18px; }
  .library-heading { flex-direction: column; gap: 13px; }.library-heading-actions { width: 100%; justify-content: space-between; }.library-tool-menu { right: 0; }
  .library-grid { grid-template-columns: 1fr; }.library-card h4 { min-height: 0; }
  .recommendation-heading { flex-direction: column; gap: 10px; }.recommendation-grid { grid-template-columns: 1fr; }.recommendation-card.featured { grid-column: auto; }.recommendation-card.featured .recommendation-copy strong { font-size: 14px; }
}

@media (max-width: 430px) {
  .hero-meta > span:nth-child(2) { display: none; }
  .summary-card { justify-content: center; }.summary-icon { display: none; }
  .core-subject-grid { grid-template-columns: 1fr; }
  .resource-search button { padding-inline: 10px; font-size: 10px; }
  .compact-title { align-items: start; flex-direction: column; gap: 3px; }
}

@media (prefers-reduced-motion: reduce) {
  .article-skeleton span,.article-skeleton strong,.article-skeleton i { animation: none; }
}
</style>
