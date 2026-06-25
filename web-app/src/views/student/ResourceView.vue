<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
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
} from '../../api'

const knowledgeLoading = ref(false)
const resourceLoading = ref(false)
const searchText = ref('')
const selectedSubject = ref('')
const subjects = ref<string[]>([])
const articles = ref<KnowledgeBaseArticle[]>([])
const selectedArticle = ref<KnowledgeBaseArticle | null>(null)
const resources = ref<ManagedResourceItem[]>([])
const selectedResource = ref<ManagedResourceItem | null>(null)
const showDetail = ref(false)
const error = ref('')
const importingUrl = ref('')

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

const typeLabel: Record<string, string> = { courseware: '课件', exercise: '练习', notes: '笔记', exam: '试卷' }
const statusLabel: Record<string, string> = { draft: '草稿', ready: '就绪', archived: '归档' }
const statusNext: Record<string, 'draft' | 'ready' | 'archived'> = { draft: 'ready', ready: 'archived', archived: 'draft' }
const sourceLabel: Record<string, string> = { generated: '系统生成', external_import: '官方课件' }
const kindLabel: Record<string, string> = {
  mooc_course: 'MOOC 课程',
  textbook: '教材资料',
  lecture_notes: '讲义笔记',
  course: '课程资源',
  video: '视频课程',
  interactive: '互动资源',
  practice: '习题练习',
}

onMounted(() => {
  void refreshPage()
})

async function refreshPage() {
  await Promise.all([fetchKnowledgeBase(selectedSubject.value), fetchResources()])
}

async function fetchKnowledgeBase(subject = '') {
  knowledgeLoading.value = true
  error.value = ''
  try {
    const { data } = await agentApi.get<KnowledgeBaseListResponse>('/knowledge-base', {
      params: subject ? { subject } : {},
    })
    subjects.value = data.subjects
    articles.value = data.items
    selectedArticle.value = data.items[0] ?? null
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? 'æªç¥éè¯¯'
    articles.value = []
    selectedArticle.value = null
    error.value = `å è½½å¤§å­¦ç¥è¯åºå¤±è´¥ï¼${detail}`
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
    const detail = err?.response?.data?.detail ?? err?.message ?? 'æªç¥éè¯¯'
    resources.value = []
    error.value = error.value || `å è½½å·²ä¿å­èµæºå¤±è´¥ï¼${detail}`
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
      params: { q: query, top_k: 12 },
    })
    articles.value = selectedSubject.value
      ? data.items.filter((item) => item.subject === selectedSubject.value)
      : data.items
    selectedArticle.value = articles.value[0] ?? null
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? 'æªç¥éè¯¯'
    error.value = `æç´¢å¤§å­¦ç¥è¯åºå¤±è´¥ï¼${detail}`
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

function openDetail(item: ManagedResourceItem) {
  selectedResource.value = item
  showDetail.value = true
}

function resolveDownloadLink(item: ManagedResourceItem) {
  return item.download_url ? `${serviceEndpoints.resource}${item.download_url}` : ''
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
      window.open(`${serviceEndpoints.resource}${imported.download_url}`, '_blank', 'noreferrer')
    }
    ElMessage.success('è¯¾ä»¶å·²ä¸è½½å¹¶ä¿å­å°èµæºåº')
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? 'æªç¥éè¯¯'
    ElMessage.error(`ä¸è½½è¯¾ä»¶å¤±è´¥ï¼${detail}`)
  } finally {
    importingUrl.value = ''
  }
}

async function exportResource(item: ManagedResourceItem, format: 'pdf' | 'word') {
  try {
    await resourceApi.post(`/resources/${item.id}/export`, { export_format: format })
    ElMessage.success(`å·²åèµ· ${format.toUpperCase()} å¯¼åº`)
  } catch {
    ElMessage.error('å¯¼åºå¤±è´¥')
  }
}

async function updateStatus(item: ManagedResourceItem, status: 'draft' | 'ready' | 'archived') {
  try {
    await resourceApi.patch(`/resources/${item.id}/status`, { status })
    item.status = status
    ElMessage.success('ç¶æå·²æ´æ°')
  } catch {
    ElMessage.error('ç¶ææ´æ°å¤±è´¥')
  }
}

async function deleteSelectedResource() {
  const item = selectedResource.value
  if (!item) {
    return
  }

  try {
    await ElMessageBox.confirm(
      `å é¤åï¼â${item.title}âå°ä»èµæºåºç§»é¤${item.is_downloadable ? 'ï¼æ¬å°ä¸è½½æä»¶ä¹ä¼ä¸å¹¶å é¤' : ''}ã`,
      'å é¤èµæº',
      {
        confirmButtonText: 'ç¡®è®¤å é¤',
        cancelButtonText: 'åæ¶',
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
    await fetchResources()
    ElMessage.success('èµæºå·²å é¤')
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? 'æªç¥éè¯¯'
    ElMessage.error(`å é¤èµæºå¤±è´¥ï¼${detail}`)
  }
}

async function deleteAllResources() {
  if (!resources.value.length) {
    ElMessage.warning('å½åæ²¡æå¯å é¤çèµæº')
    return
  }

  try {
    await ElMessageBox.confirm(
      `ç¡®è®¤ä¸é®å é¤å¨é¨ ${resources.value.length} é¡¹å·²ä¿å­èµæºåï¼å·²ä¸è½½çæ¬å°æä»¶ä¹ä¼ä¸å¹¶å é¤ã`,
      'ä¸é®å é¤å¨é¨èµæº',
      {
        confirmButtonText: 'ç¡®è®¤å é¤',
        cancelButtonText: 'åæ¶',
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
    await fetchResources()
    ElMessage.success(`å·²å é¤ ${data.data?.deleted_count ?? 0} é¡¹èµæº`)
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.message ?? 'æªç¥éè¯¯'
    ElMessage.error(`ä¸é®å é¤å¤±è´¥ï¼${detail}`)
  }
}
</script>

<template>
  <div class="resource-page">
    <header class="resource-header">
      <div>
        <div class="panel-kicker">University Courseware</div>
        <h2>大学知识库与课件下载</h2>
        <p>大学知识库和学习资源已合并。选择知识点后，可直接下载关联课件；已下载文件会保存在下方资源库中。</p>
      </div>
      <div class="header-actions">
        <button :disabled="isLoading" class="secondary-button" @click="refreshPage">
          {{ isLoading ? 'å·æ°ä¸­...' : 'å·æ°èµæº' }}
        </button>
        <button :disabled="resourceLoading || !resources.length" class="danger-button" @click="deleteAllResources">
          ä¸é®å é¤
        </button>
      </div>
    </header>

    <section class="resource-summary">
      <article>
        <span>ç¥è¯åºä¸é¢</span>
        <strong>{{ articles.length }}</strong>
      </article>
      <article>
        <span>å¯ä¸è½½å®æ¹è¯¾ä»¶</span>
        <strong>{{ selectedArticle?.external_resources.length ?? 0 }}</strong>
      </article>
      <article>
        <span>å·²ä¿å­è¯¾ä»¶</span>
        <strong>{{ importedResources.length }}</strong>
      </article>
      <article>
        <span>ç³»ç»çæèµæº</span>
        <strong>{{ generatedResources.length }}</strong>
      </article>
    </section>

    <div v-if="error" class="resource-error">{{ error }}</div>

    <section class="resource-toolbar">
      <div class="resource-search">
        <input
          v-model="searchText"
          placeholder="æç´¢è¯¾ç¨ãæ¦å¿µæå³é®è¯ï¼ä¾å¦ï¼äºå¡ãéå½ãTCPãç©éµ"
          @keyup.enter="searchKnowledgeBase"
        />
        <button :disabled="knowledgeLoading" @click="searchKnowledgeBase">æç´¢</button>
      </div>
      <div class="subject-row">
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

    <section class="resource-layout">
      <aside class="article-list">
        <article
          v-for="article in articles"
          :key="article.id"
          class="article-card"
          :class="{ active: selectedArticle?.id === article.id }"
          @click="selectArticle(article)"
        >
          <div class="meta-row">
            <span>{{ article.subject }}</span>
            <span>{{ article.level }}</span>
          </div>
          <h3>{{ article.title }}</h3>
          <p>{{ article.summary }}</p>
        </article>
        <div v-if="!knowledgeLoading && !articles.length" class="empty-state">
          ææ å¹éçå¤§å­¦ç¥è¯åºåå®¹ã
        </div>
      </aside>

      <main class="courseware-panel">
        <template v-if="selectedArticle">
          <div class="detail-head">
            <div>
              <div class="meta-row">
                <span>{{ selectedArticle.subject }}</span>
                <span>{{ selectedArticle.level }}</span>
              </div>
              <h2>{{ selectedArticle.title }}</h2>
              <p>{{ selectedArticle.summary }}</p>
            </div>
          </div>

          <section class="download-section">
            <div class="section-title">
              <h3>ä¸è½½è¯¾ä»¶</h3>
              <p>è¿éæ¾ç¤ºå½åç¥è¯ç¹å³èçå®æ¹è¯¾ä»¶ãè®²ä¹ãææåä¸è½½åã</p>
            </div>

            <div v-if="selectedArticle.external_resources.length" class="download-grid">
              <article
                v-for="resource in selectedArticle.external_resources"
                :key="resource.url"
                class="download-card"
              >
                <div class="meta-row">
                  <span>{{ resource.provider }}</span>
                  <span>{{ kindLabel[resource.kind] ?? resource.kind }}</span>
                </div>
                <h4>{{ resource.title }}</h4>
                <p>{{ resource.notes }}</p>
                <div class="download-actions">
                  <a :href="resource.url" target="_blank" rel="noreferrer">æå¼åç«</a>
                  <button :disabled="importingUrl === resource.url" @click="importResource(resource)">
                    {{
                      importingUrl === resource.url
                        ? 'ä¸è½½ä¸­...'
                        : findDownloadedResource(resource)
                          ? 'æå¼å·²ä¿å­æä»¶'
                          : 'ä¸è½½è¯¾ä»¶'
                    }}
                  </button>
                </div>
              </article>
            </div>
            <div v-else class="empty-state">å½åç¥è¯ç¹ææ å¯ä¸è½½è¯¾ä»¶ã</div>
          </section>

          <section class="downloaded-section">
            <div class="section-title">
              <h3>å½åç¥è¯ç¹å·²ä¸è½½</h3>
              <p>å·²ä¸è½½è¯¾ä»¶ä¼è½çä¿å­ï¼å¯éå¤æå¼æä¸è½½ã</p>
            </div>
            <div v-if="currentArticleDownloaded.length" class="saved-grid">
              <button
                v-for="item in currentArticleDownloaded"
                :key="item.id"
                class="saved-item"
                @click="openDetail(item)"
              >
                <strong>{{ item.title }}</strong>
                <span>{{ item.provider }} / {{ item.format }}</span>
              </button>
            </div>
            <div v-else class="empty-state compact">è¿æ²¡æä¸è½½å½åç¥è¯ç¹çè¯¾ä»¶ã</div>
          </section>
        </template>
        <div v-else class="empty-state panel-empty">è¯·éæ©ä¸ä¸ªç¥è¯åºä¸é¢ã</div>
      </main>
    </section>

    <section class="library-section">
      <div class="section-title">
        <h3>å¨é¨å·²ä¿å­èµæº</h3>
        <p>åå«ä»å¤§å­¦ç¥è¯åºä¸è½½çå®æ¹è¯¾ä»¶ï¼ä»¥åç³»ç»çæçä¸ªæ§åå­¦ä¹ èµæºã</p>
      </div>

      <div v-if="resources.length" class="library-grid">
        <article v-for="item in resources" :key="item.id" class="library-card" @click="openDetail(item)">
          <div class="library-card-head">
            <div class="meta-row">
              <span>{{ typeLabel[item.type] ?? item.type }}</span>
              <span>{{ sourceLabel[item.source_type] ?? item.source_type }}</span>
            </div>
            <span class="status-badge">{{ statusLabel[item.status] ?? item.status }}</span>
          </div>
          <h4>{{ item.title }}</h4>
          <p>ç¥è¯ç¹ï¼{{ item.knowledge_point }}</p>
          <p>æ ¼å¼ï¼{{ item.format }}<template v-if="item.provider"> / {{ item.provider }}</template></p>
        </article>
      </div>
      <div v-else-if="!resourceLoading" class="empty-state">
        ææ å·²ä¿å­èµæºãåå¨ä¸æ¹éæ©ç¥è¯ç¹å¹¶ä¸è½½è¯¾ä»¶ã
      </div>
    </section>

    <div v-if="showDetail && selectedResource" class="modal-mask" @click.self="showDetail = false">
      <div class="resource-modal">
        <div class="modal-head">
          <div class="meta-row">
            <span>{{ typeLabel[selectedResource.type] ?? selectedResource.type }}</span>
            <span>{{ sourceLabel[selectedResource.source_type] ?? selectedResource.source_type }}</span>
          </div>
          <button class="icon-button" @click="showDetail = false">x</button>
        </div>

        <h3>{{ selectedResource.title }}</h3>
        <div class="modal-info">
          <div>ç¥è¯ç¹ï¼{{ selectedResource.knowledge_point }}</div>
          <div>ç¶æï¼{{ statusLabel[selectedResource.status] ?? selectedResource.status }}</div>
          <div>æ ¼å¼ï¼{{ selectedResource.format }}</div>
          <div v-if="selectedResource.provider">æä¾æ¹ï¼{{ selectedResource.provider }}</div>
          <div v-if="selectedResource.source_kind">èµæºç±»åï¼{{ kindLabel[selectedResource.source_kind] ?? selectedResource.source_kind }}</div>
          <div v-if="selectedResource.file_name">æä»¶åï¼{{ selectedResource.file_name }}</div>
          <a v-if="selectedResource.external_url" :href="selectedResource.external_url" target="_blank" rel="noreferrer">
            æ¥çåå§æ¥æº
          </a>
          <div v-if="selectedResource.notes">{{ selectedResource.notes }}</div>
        </div>

        <div class="modal-actions">
          <a
            v-if="selectedResource.is_downloadable && selectedResource.download_url"
            :href="resolveDownloadLink(selectedResource)"
            target="_blank"
            rel="noreferrer"
            class="primary-link"
          >
            ä¸è½½è¯¾ä»¶æä»¶
          </a>
          <button v-if="selectedResource.source_type === 'generated'" @click="exportResource(selectedResource, 'pdf')">
            å¯¼åº PDF
          </button>
          <button v-if="selectedResource.source_type === 'generated'" @click="exportResource(selectedResource, 'word')">
            å¯¼åº Word
          </button>
          <button @click="updateStatus(selectedResource, statusNext[selectedResource.status])">
            åæ¢ä¸º {{ statusLabel[statusNext[selectedResource.status]] }}
          </button>
          <button class="danger-button" @click="deleteSelectedResource">
            å é¤èµæº
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.resource-page {
  display: grid;
  gap: 18px;
}

.resource-header,
.resource-toolbar,
.courseware-panel,
.library-section {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 18px;
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
  background: var(--panel-strong);
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.resource-summary article {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--panel);
}

.resource-summary span {
  color: var(--muted);
  font-size: 13px;
}

.resource-summary strong {
  color: var(--accent);
  font-size: 22px;
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
  border: 1px solid var(--line);
  background: var(--panel-strong);
  color: var(--text);
  border-radius: 12px;
  padding: 12px 14px;
  font-family: inherit;
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
}

.article-card,
.download-card,
.library-card,
.saved-item {
  border: 1px solid var(--line);
  background: var(--panel);
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
}

.article-card h3,
.download-card h4,
.library-card h4 {
  margin: 10px 0 8px;
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
}

.saved-item span {
  color: var(--muted);
}

.library-card {
  cursor: pointer;
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
  border: 1px dashed var(--line);
  border-radius: 14px;
  color: var(--muted);
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
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel-strong);
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
  .saved-item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
