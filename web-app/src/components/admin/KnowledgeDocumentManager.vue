<script setup lang="ts">
import { computed, onMounted, reactive, ref, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentApi } from '../../api/http'

type Doc = { id: string; title: string; file_name: string; format: string; content_type: string; subject_id: number | null; subject_name: string; corpus_subject: string; chapter: string; tags: string[]; point_ids: number[]; status: string; index_status: string; source_url: string; source: Record<string, string>; original_available: boolean; text?: string; candidate_id: number | null }
type Subject = { id: number; name: string; code: string | null }
type Chunk = { id: string; text: string; metadata: Record<string, unknown> }
const docs = ref<Doc[]>([]), total = ref(0), inventory = ref<Record<string, number | string>>({})
const subjects = ref<Subject[]>([]), points = ref<{ id: number; name: string }[]>([])
const query = reactive({ q: '', source: '', subject_id: undefined as number | undefined, status: '', format: '', index_status: '', unclassified: false, page: 1, size: 20 })
const selection = ref<Doc[]>([]), selected = ref<Doc | null>(null), chunks = ref<Chunk[]>([])
const error = ref(''), busy = ref(false), chunkError = ref(''), originalUrl = ref(''), tab = ref('text'), chunkOffset = ref(0)
const historyText = ref('')
const classification = reactive({ subject_id: undefined as number | undefined, point_ids: [] as number[], chapter: '', tagsText: '' })
const canStage = computed(() => selected.value && !selected.value.candidate_id && selected.value.status === 'DRAFT')
function explain(e: any) { return e?.response?.data?.detail || e?.message || '操作失败' }
async function load() {
  busy.value = true; error.value = ''
  try { const { data } = await agentApi.get('/knowledge-base/admin/documents', { params: query }); docs.value = data.items; total.value = data.total; inventory.value = data.inventory }
  catch (e) { error.value = explain(e) } finally { busy.value = false }
}
async function loadPoints() {
  classification.point_ids = []; points.value = []
  if (classification.subject_id) {
    try { points.value = (await agentApi.get(`/knowledge-base/construction/subjects/${classification.subject_id}/points`)).data.items }
    catch (e) { error.value = explain(e) }
  }
}
function clearOriginal() { if (originalUrl.value) URL.revokeObjectURL(originalUrl.value); originalUrl.value = '' }
async function open(doc: Doc) {
  clearOriginal(); selected.value = null; chunks.value = []; chunkOffset.value = 0; chunkError.value = ''; tab.value = 'text'; error.value = ''; historyText.value = ''
  try {
    const { data } = await agentApi.get(`/knowledge-base/admin/documents/${doc.id}`)
    selected.value = data; classification.subject_id = data.subject_id || undefined
    await loadPoints(); classification.point_ids = data.point_ids; classification.chapter = data.chapter; classification.tagsText = data.tags.join(', ')
  } catch (e) { error.value = explain(e) }
}
async function readChunks(offset = 0) {
  if (!selected.value) return
  chunks.value = []; chunkError.value = ''; chunkOffset.value = offset
  try { chunks.value = (await agentApi.get(`/knowledge-base/admin/documents/${selected.value.id}/chunks`, { params: { offset, limit: 20 } })).data.items }
  catch (e) { chunkError.value = explain(e) }
}
async function original(download = false) {
  if (!selected.value) return
  try {
    const { data } = await agentApi.get(`/knowledge-base/admin/documents/${selected.value.id}/original`, { responseType: 'blob' })
    clearOriginal(); originalUrl.value = URL.createObjectURL(new Blob([data], { type: selected.value.content_type }))
    if (download) { const link = document.createElement('a'); link.href = originalUrl.value; link.download = selected.value.file_name; link.click() }
  } catch (e) { error.value = explain(e) }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return
  busy.value = true; error.value = ''
  try { const form = new FormData(); form.append('file', file); const { data } = await agentApi.post('/knowledge-base/admin/documents/upload', form); await load(); await open(data); ElMessage.success('解析已保存，待分类审核') }
  catch (e) { error.value = explain(e) } finally { busy.value = false; input.value = '' }
}
async function classify(batch = false) {
  const ids = batch ? selection.value.map(d => d.id) : selected.value ? [selected.value.id] : []
  if (!classification.subject_id || !ids.length) { error.value = '请选择学科和文档'; return }
  busy.value = true; error.value = ''
  try {
    await agentApi.post('/knowledge-base/admin/documents/classify', { document_ids: ids, subject_id: classification.subject_id, point_ids: classification.point_ids, chapter: classification.chapter, tags: classification.tagsText.split(/[,，]/).map(t => t.trim()).filter(Boolean) })
    await load(); ElMessage.success(`已保存 ${ids.length} 份文档分类`)
    if (selected.value) await open(selected.value)
  } catch (e) { error.value = explain(e) } finally { busy.value = false }
}
async function stage() {
  if (!selected.value) return
  try { await agentApi.post(`/knowledge-base/admin/documents/${selected.value.id}/candidate`); await open(selected.value); await load(); ElMessage.success('已创建审核草稿，请在审核与发布中送审并核对授权') }
  catch (e) { error.value = explain(e) }
}
async function archive() {
  if (!selected.value) return
  try { await ElMessageBox.confirm('确认归档这份未送审资料？原件将保留。', '归档资料') } catch { return }
  try { await agentApi.post(`/knowledge-base/admin/documents/${selected.value.id}/archive`); await open(selected.value); await load() } catch (e) { error.value = explain(e) }
}
async function withdraw() {
  if (!selected.value?.candidate_id) return
  try { await ElMessageBox.confirm('撤回后立即停止公开检索，索引清理由后台任务执行。', '撤回发布') } catch { return }
  try { const { data } = await agentApi.post(`/knowledge-base/candidates/${selected.value.candidate_id}/withdraw`); ElMessage.success(`已撤回，清理任务 #${data.cleanup_task.id}`); await open(selected.value); await load() } catch (e) { error.value = explain(e) }
}
async function history() {
  if (!selected.value) return
  try { historyText.value = JSON.stringify((await agentApi.get(`/knowledge-base/admin/documents/${selected.value.id}/history`)).data, null, 2) } catch (e) { error.value = explain(e) }
}
async function reconcile() {
  try { const { data } = await agentApi.post('/knowledge-base/admin/reconcile'); ElMessage.success(`对账任务 #${data.id} 已排队，可在任务页跟踪`) } catch (e) { error.value = explain(e) }
}
function safeSource(url: string) { return /^https?:\/\//i.test(url) ? url : undefined }
onMounted(async () => { await load(); try { subjects.value = (await agentApi.get('/knowledge-base/construction/subjects')).data.items } catch (e) { error.value = explain(e) } })
onBeforeUnmount(clearOriginal)
</script>

<template>
  <section class="workspace-panel document-manager">
    <div class="panel-heading"><div><div class="panel-kicker">文档目录</div><h2>查看正文与资料分类</h2></div><label class="upload-label">上传资料<input type="file" accept=".pdf,.docx,.md,.txt" :disabled="busy" @change="upload" /></label></div>
    <p class="admin-evidence-note">支持文字型 PDF（≤30页）、DOCX、UTF-8 Markdown/TXT，文件≤5MB；提取上限2万字，超出会在正文标明。原件保留。上传后先分类、审核，发布后才进入学生检索。</p>
    <el-button @click="reconcile">恢复发布与索引一致性</el-button>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="inventory-grid"><div v-for="[key, label] in [['documents','文档目录'],['physical_corpus_files','语料文件'],['original_upload_files','上传原件'],['metadata_records','分类记录'],['parsed','有解析正文'],['indexed','清单索引一致'],['source_websites','实际来源网站'],['source_urls','实际来源URL'],['allowlist_rules','白名单规则'],['published','审核发布'],['pending_review','待审核'],['unclassified','未关联学科'],['index_anomalies','清单索引异常']]" :key="key"><strong>{{ inventory[key] ?? '—' }}</strong><span>{{ label }}</span></div></div>
    <el-form inline @submit.prevent="query.page = 1; load()">
      <el-form-item label="搜索"><el-input v-model="query.q" placeholder="文档标题或文件名" clearable /></el-form-item>
      <el-form-item label="来源"><el-input v-model="query.source" placeholder="来源URL或upload://" clearable /></el-form-item>
      <el-form-item label="学科"><el-select v-model="query.subject_id" clearable style="width:150px"><el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" /></el-select></el-form-item>
      <el-form-item label="格式"><el-select v-model="query.format" clearable style="width:100px"><el-option v-for="f in ['pdf','docx','md','txt']" :key="f" :value="f" :label="f" /></el-select></el-form-item>
      <el-form-item label="审核状态"><el-select v-model="query.status" clearable style="width:160px"><el-option v-for="s in ['DRAFT','PENDING_REVIEW','APPROVED','REJECTED','PUBLISHED','LEGACY_CORPUS','ARCHIVED']" :key="s" :value="s" :label="s" /></el-select></el-form-item>
      <el-form-item label="索引"><el-select v-model="query.index_status" clearable style="width:150px"><el-option v-for="s in ['INDEXED','NOT_INDEXED','STALE','MISSING_FILE']" :key="s" :value="s" :label="s" /></el-select></el-form-item>
      <el-checkbox v-model="query.unclassified">只看未关联</el-checkbox><el-button native-type="submit" :loading="busy">查询文档</el-button>
    </el-form>
    <el-table :data="docs" row-key="id" @selection-change="selection = $event">
      <el-table-column type="selection" width="45" /><el-table-column label="文档" min-width="200"><template #default="{ row }"><el-button link type="primary" @click="open(row)">{{ row.title }}</el-button><small class="doc-path">{{ row.file_name }}</small></template></el-table-column>
      <el-table-column label="学科" min-width="150"><template #default="{ row }">{{ row.subject_name || '未关联' }}<small class="doc-path">语料目录：{{ row.corpus_subject || '上传草稿' }}</small></template></el-table-column>
      <el-table-column prop="format" label="格式" width="75" /><el-table-column prop="status" label="审核状态" min-width="155" /><el-table-column prop="index_status" label="索引清单" min-width="130" />
    </el-table>
    <el-pagination v-model:current-page="query.page" :page-size="query.size" :total="total" layout="prev, pager, next, total" @current-change="load" />
    <div class="classification-box">
      <h3>学科与知识点关联</h3><p>用于单份文档或批量关联。目录名称仅作线索；已有发布版本的学科变更须走修订与重新审核。</p>
      <el-form inline>
        <el-form-item label="关联学科"><el-select v-model="classification.subject_id" style="width:160px" @change="loadPoints"><el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" /></el-select></el-form-item>
        <el-form-item label="知识点"><el-select v-model="classification.point_ids" multiple style="width:250px"><el-option v-for="p in points" :key="p.id" :label="p.name" :value="p.id" /></el-select></el-form-item>
        <el-form-item label="章节"><el-input v-model="classification.chapter" maxlength="160" /></el-form-item><el-form-item label="标签"><el-input v-model="classification.tagsText" placeholder="逗号分隔" /></el-form-item>
      </el-form>
      <el-button :disabled="!selection.length" :loading="busy" @click="classify(true)">批量关联已选 {{ selection.length }} 份文档</el-button>
    </div>
    <section v-if="selected" class="document-detail" aria-label="文档详情">
      <h3>{{ selected.title }}</h3><p>{{ selected.file_name }} · {{ selected.status }}</p>
      <el-button @click="classify()">保存当前文档分类</el-button><el-button v-if="canStage" type="primary" @click="stage">创建审核草稿</el-button><router-link v-if="selected.candidate_id" to="/admin/knowledge/review">前往审核与发布（草稿 {{ selected.candidate_id }}）</router-link>
      <el-button v-if="canStage" @click="archive">归档上传资料</el-button><el-button v-if="selected.status === 'PUBLISHED'" type="warning" @click="withdraw">撤回发布</el-button>
      <el-tabs v-model="tab">
        <el-tab-pane label="解析正文" name="text"><pre class="document-text">{{ selected.text || '当前仅有元数据，没有可预览正文。' }}</pre></el-tab-pane>
        <el-tab-pane label="原始文件" name="original"><el-button :disabled="!selected.original_available" @click="original(true)">下载原文件</el-button><el-button v-if="selected.format === 'pdf'" @click="original()">预览 PDF</el-button><p v-if="!selected.original_available">原件不存在，可查看解析正文。</p><iframe v-if="originalUrl && selected.format === 'pdf'" :src="originalUrl" title="PDF原件预览" class="pdf-preview" /><p v-if="selected.format === 'docx'">DOCX原生版式请下载查看；解析正文可在正文标签中查看。</p></el-tab-pane>
        <el-tab-pane label="来源与分类" name="source"><p>关联学科：{{ selected.subject_name || '未关联' }} · 章节：{{ selected.chapter || '未设置' }}</p><p>标签：{{ selected.tags.join('、') || '未设置' }}</p><a v-if="safeSource(selected.source_url)" :href="safeSource(selected.source_url)" target="_blank" rel="noreferrer">打开原始来源</a><pre class="document-text">{{ JSON.stringify(selected.source, null, 2) }}</pre></el-tab-pane>
        <el-tab-pane label="实时向量片段" name="chunks"><el-button @click="readChunks()">加载实时 Chunk</el-button><p v-if="chunkError" role="alert">{{ chunkError }}</p><div v-for="chunk in chunks" :key="chunk.id"><h4>{{ chunk.id }}</h4><pre class="document-text">{{ chunk.text }}</pre><details><summary>metadata</summary><pre class="document-text">{{ JSON.stringify(chunk.metadata, null, 2) }}</pre></details></div><p v-if="!chunks.length && !chunkError">尚无已加载片段；未发布的上传草稿不会进入索引。</p><el-button :disabled="chunkOffset === 0" @click="readChunks(Math.max(0, chunkOffset - 20))">上一页</el-button><el-button :disabled="chunks.length < 20" @click="readChunks(chunkOffset + 20)">下一页</el-button></el-tab-pane>
        <el-tab-pane label="版本与审核记录" name="history"><el-button @click="history">读取版本与审核记录</el-button><pre class="document-text">{{ historyText || '点击读取真实版本、来源任务与操作记录。' }}</pre></el-tab-pane>
      </el-tabs>
    </section>
  </section>
</template>
<style scoped>
.inventory-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(115px,1fr)); gap:12px; margin:18px 0 }
.inventory-grid div { background:var(--bg-soft,#f4f6fa); border:1px solid var(--border-color,#d9e0ea); border-radius:10px; padding:12px }
.inventory-grid strong,.inventory-grid span,.doc-path { display:block; overflow-wrap:anywhere }.inventory-grid strong { font-size:1.35rem }.inventory-grid span,.doc-path { font-size:.8rem; opacity:.75 }
.document-manager { min-width:0 }.classification-box,.document-detail { border-top:1px solid var(--border-color,#d9e0ea); margin-top:22px; padding-top:18px }.document-text { white-space:pre-wrap; overflow-wrap:anywhere; max-height:60vh; overflow:auto; font:inherit; line-height:1.8; padding:16px; background:var(--bg-soft,#f4f6fa) }.pdf-preview { width:100%; height:65vh; border:0 }.upload-label { display:flex; flex-direction:column; gap:6px; max-width:250px } input[type=file] { max-width:100% }
</style>
