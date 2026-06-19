<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  agentApi,
  resourceApi,
  type ExternalResourceImportPayload,
  type KnowledgeBaseArticle,
  type KnowledgeBaseListResponse,
  type KnowledgeBaseSearchResponse,
} from '../../api'

const loading = ref(false)
const searchText = ref('')
const selectedSubject = ref('')
const subjects = ref<string[]>([])
const articles = ref<KnowledgeBaseArticle[]>([])
const selectedArticle = ref<KnowledgeBaseArticle | null>(null)
const error = ref('')
const importingUrl = ref('')

const filteredArticles = computed(() => articles.value)

onMounted(() => {
  void fetchKnowledgeBase()
})

async function fetchKnowledgeBase(subject = '') {
  loading.value = true
  error.value = ''
  try {
    const { data } = await agentApi.get<KnowledgeBaseListResponse>('/knowledge-base', {
      params: subject ? { subject } : {},
    })
    subjects.value = data.subjects
    articles.value = data.items
    selectedArticle.value = data.items[0] ?? null
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    error.value = `知识库加载失败：${detail}`
    articles.value = []
    selectedArticle.value = null
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

async function searchKnowledgeBase() {
  const query = searchText.value.trim()
  if (!query) {
    await fetchKnowledgeBase(selectedSubject.value)
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await agentApi.get<KnowledgeBaseSearchResponse>('/knowledge-base/search', {
      params: { q: query, top_k: 12 },
    })
    articles.value = selectedSubject.value
      ? data.items.filter((item) => item.subject === selectedSubject.value)
      : data.items
    selectedArticle.value = articles.value[0] ?? null
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    error.value = `知识库搜索失败：${detail}`
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

async function selectSubject(subject: string) {
  selectedSubject.value = selectedSubject.value === subject ? '' : subject
  searchText.value = ''
  await fetchKnowledgeBase(selectedSubject.value)
}

function openArticle(article: KnowledgeBaseArticle) {
  selectedArticle.value = article
}

function applyToGraph(article: KnowledgeBaseArticle) {
  window.sessionStorage.setItem(
    'student-workspace-courseware',
    JSON.stringify({
      topic: article.title,
      subject: article.subject,
      generatedAt: Date.now(),
    }),
  )
  ElMessage.success('已设为当前知识点，可前往知识图谱查看依赖关系')
}

async function importResource(resource: KnowledgeBaseArticle['external_resources'][number]) {
  const article = selectedArticle.value
  if (!article) {
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
    await resourceApi.post('/resources/import-external', payload)
    ElMessage.success('官方课件已导入到学习资源')
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误'
    ElMessage.error(`导入失败：${detail}`)
  } finally {
    importingUrl.value = ''
  }
}
</script>

<template>
  <div>
    <header class="knowledge-base-hero">
      <div>
        <div class="panel-kicker">University Knowledge Base</div>
        <h2>大学知识库</h2>
        <p>这里负责知识点讲解与课程要点浏览，不再直接充当学习资源页。</p>
      </div>
      <button :disabled="loading" class="kb-refresh-button" @click="fetchKnowledgeBase(selectedSubject)">
        {{ loading ? '加载中...' : '刷新知识库' }}
      </button>
    </header>

    <section class="kb-toolbar">
      <div class="kb-search">
        <input
          v-model="searchText"
          placeholder="搜索课程、概念或关键词，例如：事务、递归、TCP、矩阵"
          @keyup.enter="searchKnowledgeBase"
        />
        <button :disabled="loading" @click="searchKnowledgeBase">搜索</button>
      </div>
      <div class="kb-subjects">
        <button
          v-for="subject in subjects"
          :key="subject"
          :class="{ active: selectedSubject === subject }"
          @click="selectSubject(subject)"
        >
          {{ subject }}
        </button>
      </div>
    </section>

    <div v-if="error" class="kb-error">{{ error }}</div>

    <section class="kb-layout">
      <aside class="kb-list">
        <article
          v-for="article in filteredArticles"
          :key="article.id"
          class="kb-card"
          :class="{ active: selectedArticle?.id === article.id }"
          @click="openArticle(article)"
        >
          <div class="kb-card-meta">
            <span>{{ article.subject }}</span>
            <span>{{ article.level }}</span>
          </div>
          <h3>{{ article.title }}</h3>
          <p>{{ article.summary }}</p>
        </article>
        <div v-if="!loading && !filteredArticles.length" class="empty-state">
          暂无匹配的大学知识库内容。
        </div>
      </aside>

      <main v-if="selectedArticle" class="kb-detail">
        <div class="kb-detail-head">
          <div>
            <div class="kb-card-meta">
              <span>{{ selectedArticle.subject }}</span>
              <span>{{ selectedArticle.level }}</span>
            </div>
            <h2>{{ selectedArticle.title }}</h2>
            <p>{{ selectedArticle.summary }}</p>
          </div>
          <button @click="applyToGraph(selectedArticle)">设为图谱知识点</button>
        </div>

        <section v-if="selectedArticle.external_resources.length" class="kb-resource-panel">
          <div class="kb-resource-header">
            <div>
              <h3>官方课件与扩展资源</h3>
              <p>这里列出知识库关联的外部课程讲义、下载包和官方资料，可一键导入到学习资源。</p>
            </div>
          </div>
          <div class="kb-resource-list">
            <article
              v-for="resource in selectedArticle.external_resources"
              :key="resource.url"
              class="kb-resource-card"
            >
              <div class="kb-card-meta">
                <span>{{ resource.provider }}</span>
                <span>{{ resource.kind }}</span>
              </div>
              <h4>{{ resource.title }}</h4>
              <p>{{ resource.notes }}</p>
              <div class="kb-resource-actions">
                <a :href="resource.url" target="_blank" rel="noreferrer">打开原站</a>
                <button
                  :disabled="importingUrl === resource.url"
                  @click="importResource(resource)"
                >
                  {{ importingUrl === resource.url ? '导入中...' : '导入到学习资源' }}
                </button>
              </div>
            </article>
          </div>
        </section>

        <div class="kb-section-grid">
          <section class="kb-section">
            <h3>核心概念</h3>
            <ul>
              <li v-for="item in selectedArticle.concepts" :key="item">{{ item }}</li>
            </ul>
          </section>

          <section class="kb-section">
            <h3>关键语法 / 形式化表达</h3>
            <pre v-for="item in selectedArticle.syntax" :key="item">{{ item }}</pre>
          </section>

          <section class="kb-section">
            <h3>大学课程案例</h3>
            <p v-for="item in selectedArticle.examples" :key="item">{{ item }}</p>
          </section>

          <section class="kb-section">
            <h3>常见误区</h3>
            <ul>
              <li v-for="item in selectedArticle.mistakes" :key="item">{{ item }}</li>
            </ul>
          </section>

          <section class="kb-section">
            <h3>应用场景</h3>
            <ul>
              <li v-for="item in selectedArticle.applications" :key="item">{{ item }}</li>
            </ul>
          </section>

          <section class="kb-section">
            <h3>自检问题</h3>
            <ul>
              <li v-for="item in selectedArticle.checks" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>
      </main>

      <main v-else class="kb-detail empty-state">
        请选择一条知识库内容查看详情。
      </main>
    </section>
  </div>
</template>

<style scoped>
.knowledge-base-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  padding: 28px 32px;
  border-radius: 22px;
  background: var(--panel);
  border: 1px solid var(--line);
  margin-bottom: 18px;
}

.knowledge-base-hero h2 {
  margin: 8px 0;
  font-size: 28px;
}

.knowledge-base-hero p {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.kb-refresh-button,
.kb-search button,
.kb-detail-head button,
.kb-resource-actions button {
  border: none;
  border-radius: 12px;
  padding: 10px 18px;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  color: #fff;
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;
}

.kb-toolbar {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 18px;
  background: var(--panel);
  border: 1px solid var(--line);
  margin-bottom: 18px;
}

.kb-search {
  display: flex;
  gap: 10px;
}

.kb-search input {
  flex: 1;
  border: 1px solid var(--line);
  background: var(--panel-strong);
  color: var(--text);
  border-radius: 12px;
  padding: 12px 14px;
  font-family: inherit;
}

.kb-subjects {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.kb-subjects button {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  border-radius: 999px;
  padding: 7px 12px;
  cursor: pointer;
  font-family: inherit;
}

.kb-subjects button.active {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}

.kb-layout {
  display: grid;
  grid-template-columns: minmax(280px, 360px) 1fr;
  gap: 18px;
}

.kb-list,
.kb-detail {
  min-height: 520px;
}

.kb-list {
  display: grid;
  align-content: start;
  gap: 12px;
}

.kb-card,
.kb-detail,
.kb-section,
.kb-resource-panel,
.kb-resource-card {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 18px;
}

.kb-card {
  padding: 18px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.kb-card:hover,
.kb-card.active {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--accent) 38%, transparent);
}

.kb-card h3 {
  margin: 10px 0 8px;
}

.kb-card p,
.kb-detail p,
.kb-section li,
.kb-resource-card p {
  color: var(--muted);
  line-height: 1.75;
}

.kb-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.kb-card-meta span {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--accent);
}

.kb-detail {
  padding: 24px;
}

.kb-detail-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
}

.kb-detail-head h2 {
  margin: 10px 0;
}

.kb-resource-panel {
  padding: 18px;
  margin-bottom: 18px;
}

.kb-resource-header h3 {
  margin: 0 0 8px;
}

.kb-resource-header p {
  margin: 0 0 14px;
}

.kb-resource-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.kb-resource-card {
  padding: 16px;
}

.kb-resource-card h4 {
  margin: 10px 0 8px;
}

.kb-resource-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}

.kb-resource-actions a {
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
}

.kb-section-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.kb-section {
  padding: 18px;
}

.kb-section h3 {
  margin: 0 0 12px;
}

.kb-section ul {
  margin: 0;
  padding-left: 18px;
}

.kb-section pre {
  white-space: pre-wrap;
  color: var(--text);
  background: var(--panel-strong);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.kb-error {
  padding: 14px 16px;
  margin-bottom: 16px;
  border-radius: 14px;
  color: var(--red);
  background: color-mix(in srgb, var(--red) 8%, transparent);
}

@media (max-width: 1100px) {
  .kb-layout,
  .kb-section-grid,
  .kb-resource-list {
    grid-template-columns: 1fr;
  }

  .knowledge-base-hero,
  .kb-detail-head,
  .kb-search,
  .kb-resource-actions {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
