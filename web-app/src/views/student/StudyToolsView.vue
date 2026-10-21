<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { userApi } from '../../api'

type Note = { id: number; title: string; body: string; source_resource_id: number | null; updated_at: string; version:string; source_locator?:string|null; source_resource_version?:string|null; classification:{subject:string;knowledge_point:string;knowledge_point_id:number|null} }
type Card = { id: number; front: string; back: string; source_note_id: number | null; due_at: string; review_count: number; interval_days: number; knowledge_point?:string; review_evidence?:{review_count:number;recall_rate:number}|null }
type ReviewEvent = { id: number; grade: number; interval_days: number; next_due_at: string; reviewed_at: string }
type Page<T> = { total: number; items: T[] }
type CardPage = Page<Card> & { due_count: number }
type NoteSuggestion = { organized_note: string; cards: { front: string; back: string }[]; input_truncated: boolean }

const notes = ref<Note[]>([])
const route = useRoute()
const cards = ref<Card[]>([])
const noteTotal = ref(0)
const cardTotal = ref(0)
const dueCount = ref(0)
const notePage = ref(1)
const cardPage = ref(1)
const dueOnly = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const noteId = ref<number | null>(null)
const noteTitle = ref('')
const noteBody = ref('')
const noteResourceId = ref<number | undefined>()
const noteVersion=ref<string>();const noteLocator=ref('')
const noteSearch=ref('');const subjectFilter=ref('');const resourceFilter=ref<number>();const pointFilter=ref<number>()
const noteHistory=ref<{id:number;version:string;snapshot:{title:string;body:string};created_at:string}[]>([])
const historyNote=ref<Note>();const historyOpen=ref(false)
const reviewRequests=ref<Record<number,{id:string;grade:number}>>({})
const cardFront = ref('')
const cardBack = ref('')
const cardNoteId = ref<number | undefined>()
const revealedCards = ref(new Set<number>())
const reviewHistory = ref<Record<number, ReviewEvent[]>>({})
const historyCardId = ref<number | null>(null)
const organizingId = ref<number | null>(null)
const suggestion = ref<NoteSuggestion | null>(null)
const suggestionNoteId = ref<number | null>(null)
const suggestionSource = ref<Note | null>(null)
const noteSize = 10
const cardSize = 10
const canSaveNote = computed(() => !!noteTitle.value.trim() && !!noteBody.value.trim())
const canSaveCard = computed(() => !!cardFront.value.trim() && !!cardBack.value.trim())
function asUtcDate(value: string) {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`)
}
function isDue(card: Card) { return asUtcDate(card.due_at).getTime() <= Date.now() }
function dueLabel(card: Card) { return isDue(card) ? '现在可复习' : `下次复习 ${asUtcDate(card.due_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}` }

async function loadNotes() {
  const { data } = await userApi.get<Page<Note>>('/study/notes',{params:{page:notePage.value,size:noteSize,q:noteSearch.value||undefined,subject:subjectFilter.value||undefined,resource_id:resourceFilter.value||undefined,knowledge_point_id:pointFilter.value||undefined}})
  notes.value = data.items
  noteTotal.value = data.total
}

async function loadCards() {
  const { data } = await userApi.get<CardPage>(`/study/cards?page=${cardPage.value}&size=${cardSize}&due_only=${dueOnly.value}`)
  cards.value = data.items
  cardTotal.value = data.total
  dueCount.value = data.due_count
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadNotes(), loadCards()])
  } catch {
    error.value = '笔记和闪卡加载失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

function editNote(note: Note) {
  noteId.value = note.id
  noteTitle.value = note.title
  noteBody.value = note.body
  noteResourceId.value = note.source_resource_id ?? undefined
  noteVersion.value=note.version;noteLocator.value=note.source_locator||''
  document.getElementById('note-editor')?.scrollIntoView({ behavior: 'smooth' })
}

function clearNote() {
  noteId.value = null
  noteTitle.value = ''
  noteBody.value = ''
  noteResourceId.value = undefined
  noteVersion.value=undefined;noteLocator.value=''
}

async function loadNoteHistory(note:Note) {try {noteHistory.value=(await userApi.get(`/study/notes/${note.id}/history`)).data.items;historyNote.value=note;historyOpen.value=true} catch {ElMessage.error('修改历史读取失败')}}
function useHistory(item:{snapshot:{title:string;body:string}}) {if(historyNote.value){editNote(historyNote.value);noteTitle.value=item.snapshot.title;noteBody.value=item.snapshot.body;historyOpen.value=false}}
async function filterNotes() {notePage.value=1;await loadNotes()}

async function organizeNote(note: Note) {
  organizingId.value = note.id
  suggestion.value = null
  try {
    const { data } = await userApi.post<NoteSuggestion>(`/study/notes/${note.id}/organize`)
    suggestion.value = data
    suggestionNoteId.value = note.id
    suggestionSource.value = note
  } catch {
    ElMessage.error('AI 整理暂不可用；原笔记已保留。')
  } finally {
    organizingId.value = null
  }
}

function useOrganizedNote() {
  const note = suggestionSource.value
  if (!note || !suggestion.value) return
  editNote(note)
  noteBody.value = suggestion.value.organized_note
}

async function addSuggestedCard(front: string, back: string) {
  try {
    await userApi.post('/study/cards', { front, back, source_note_id: suggestionNoteId.value })
    await loadCards()
    ElMessage.success('闪卡已保存')
  } catch {
    ElMessage.error('闪卡保存失败')
  }
}

async function saveNote() {
  if (!canSaveNote.value) return
  saving.value = true
  try {
    const payload = { title: noteTitle.value.trim(), body: noteBody.value.trim(), source_resource_id: noteResourceId.value ?? null,expected_version:noteVersion.value,source_locator:noteLocator.value||null }
    if (noteId.value) await userApi.put(`/study/notes/${noteId.value}`, payload)
    else await userApi.post('/study/notes', payload)
    clearNote()
    notePage.value = 1
    await loadNotes()
    ElMessage.success('笔记已保存')
  } catch (reason:any) {
    ElMessage.error(reason?.response?.status===409?'笔记已被其他页面修改，请刷新后重新编辑；当前输入已保留。':'笔记保存失败，请检查关联资源是否可用')
  } finally {
    saving.value = false
  }
}

async function deleteNote(note: Note) {
  try {
    await ElMessageBox.confirm(`删除笔记“${note.title}”？关联闪卡会保留。`, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await userApi.delete(`/study/notes/${note.id}`)
    if (noteId.value === note.id) clearNote()
    await loadNotes()
    ElMessage.success('笔记已删除')
  } catch { ElMessage.error('删除笔记失败，请稍后重试') }
}

async function saveCard() {
  if (!canSaveCard.value) return
  saving.value = true
  try {
    await userApi.post('/study/cards', { front: cardFront.value.trim(), back: cardBack.value.trim(), source_note_id: cardNoteId.value ?? null })
    cardFront.value = ''
    cardBack.value = ''
    cardNoteId.value = undefined
    cardPage.value = 1
    await loadCards()
    ElMessage.success('闪卡已添加')
  } catch {
    ElMessage.error('闪卡保存失败，请检查关联笔记是否可用')
  } finally {
    saving.value = false
  }
}

function toggleReveal(cardId: number) {
  const next = new Set(revealedCards.value)
  if (next.has(cardId)) next.delete(cardId)
  else next.add(cardId)
  revealedCards.value = next
}

async function review(card: Card, grade: number) {
  try {
    if(!reviewRequests.value[card.id]||reviewRequests.value[card.id]!.grade!==grade) reviewRequests.value[card.id]={id:crypto.randomUUID(),grade}
    await userApi.post(`/study/cards/${card.id}/review`, { grade,client_request_id:reviewRequests.value[card.id]!.id })
    delete reviewRequests.value[card.id]
    revealedCards.value = new Set([...revealedCards.value].filter(id => id !== card.id))
    await loadCards()
    if (historyCardId.value === card.id) await loadCardHistory(card.id)
    ElMessage.success('复习结果已记录')
  } catch {
    ElMessage.error('复习记录失败，请刷新后重试')
  }
}

async function loadCardHistory(cardId: number) {
  try {
    const { data } = await userApi.get<ReviewEvent[]>(`/study/cards/${cardId}/reviews`)
    reviewHistory.value = { ...reviewHistory.value, [cardId]: data }
    historyCardId.value = cardId
  } catch {
    ElMessage.error('复习记录加载失败')
  }
}

function toggleCardHistory(cardId: number) {
  if (historyCardId.value === cardId) historyCardId.value = null
  else loadCardHistory(cardId)
}

async function deleteCard(card: Card) {
  try {
    await ElMessageBox.confirm(`删除闪卡“${card.front}”？`, '确认删除', { type: 'warning' })
  } catch { return }
  try {
    await userApi.delete(`/study/cards/${card.id}`)
    await loadCards()
    ElMessage.success('闪卡已删除')
  } catch { ElMessage.error('删除闪卡失败，请稍后重试') }
}

onMounted(() => {
  const rawId = route.query.resourceId
  const resourceId = Number(Array.isArray(rawId) ? rawId[0] : rawId)
  if (Number.isSafeInteger(resourceId) && resourceId > 0) {
    noteResourceId.value = resourceId
    const title = route.query.resourceTitle
    const sourceTitle = Array.isArray(title) ? title[0] : title
    if (sourceTitle) noteTitle.value = `${String(sourceTitle).slice(0, 145)} 学习笔记`
  }
  refresh()
})
</script>

<template>
  <main class="study-tools">
    <header class="study-header"><div><span class="panel-kicker">学习沉淀</span><h1>笔记与闪卡</h1><p>保存自己的理解，再用到期闪卡巩固。内容仅对当前账号可见。</p></div><el-button :loading="loading" @click="refresh">刷新</el-button></header>
    <p v-if="error" class="study-error" role="alert">{{ error }}</p>
    <div class="study-grid">
      <section class="study-panel" aria-label="学习笔记">
        <div class="section-heading"><h2>学习笔记</h2><span>共 {{ noteTotal }} 篇</span></div>
        <div class="editor-box" aria-label="笔记分类筛选"><el-input v-model="noteSearch" placeholder="搜索标题或正文" aria-label="搜索笔记"/><el-input v-model="subjectFilter" placeholder="按学科名称筛选" aria-label="笔记学科"/><el-input-number v-model="resourceFilter" :min="1" placeholder="按资源ID筛选" aria-label="筛选资源ID"/><el-input-number v-model="pointFilter" :min="1" placeholder="按知识点ID筛选" aria-label="筛选知识点ID"/><el-button @click="filterNotes">筛选笔记</el-button></div>
        <div id="note-editor" class="editor-box">
          <h3>{{ noteId ? '编辑笔记' : '新建笔记' }}</h3>
          <el-input v-model="noteTitle" maxlength="160" show-word-limit placeholder="笔记标题" aria-label="笔记标题" />
          <el-input v-model="noteBody" type="textarea" :rows="6" maxlength="20000" show-word-limit placeholder="写下要点、疑问和自己的理解" aria-label="笔记内容" />
          <el-input-number v-model="noteResourceId" :min="1" placeholder="关联资源 ID（可选）" aria-label="关联资源 ID" />
          <el-input v-model="noteLocator" maxlength="300" placeholder="正文摘录位置，例如：第2节 / 第3段" aria-label="笔记摘录位置"/>
          <div class="button-row"><el-button type="primary" :disabled="!canSaveNote" :loading="saving" @click="saveNote">保存笔记</el-button><el-button v-if="noteId" @click="clearNote">取消编辑</el-button></div>
        </div>
        <div v-if="suggestion" class="suggestion-box">
          <div class="section-heading"><h3>AI 整理建议</h3><el-button size="small" @click="suggestion = null">关闭</el-button></div>
          <p v-if="suggestion.input_truncated" class="source-line">笔记较长，本次只分析了前 6000 字。</p>
          <p class="note-body">{{ suggestion.organized_note }}</p>
          <el-button size="small" type="primary" @click="useOrganizedNote">放入编辑器，检查后保存</el-button>
          <div v-for="(item, index) in suggestion.cards" :key="index" class="suggested-card"><strong>{{ item.front }}</strong><p>{{ item.back }}</p><el-button size="small" @click="addSuggestedCard(item.front, item.back)">保存这张闪卡</el-button></div>
        </div>
        <div v-if="!notes.length && !loading" class="empty-state">还没有笔记，先记录一个学习要点。</div>
        <article v-for="note in notes" :key="note.id" class="study-item">
          <div class="item-head"><h3>{{ note.title }}</h3><small>{{ note.updated_at?.slice(0, 10) }}</small></div>
          <p class="note-body">{{ note.body }}</p>
          <p v-if="note.source_resource_id" class="source-line">关联资源 #{{ note.source_resource_id }}</p>
          <p class="source-line">{{note.classification?.subject||'未分类学科'}} · {{note.classification?.knowledge_point||'未关联知识点'}}<template v-if="note.classification?.knowledge_point_id"> #{{note.classification.knowledge_point_id}}</template></p><p v-if="note.source_locator||note.source_resource_version" class="source-line">{{note.source_locator}} · 来源版本 {{note.source_resource_version?.slice(0,12)}}</p>
          <div class="button-row"><el-button size="small" @click="editNote(note)">编辑</el-button><el-button size="small" @click="loadNoteHistory(note)">修改历史</el-button><el-button size="small" :loading="organizingId === note.id" @click="organizeNote(note)">AI 整理与闪卡建议</el-button><el-button size="small" type="danger" plain @click="deleteNote(note)">删除</el-button></div>
        </article>
        <el-pagination v-if="noteTotal > noteSize" v-model:current-page="notePage" :page-size="noteSize" :total="noteTotal" layout="prev, pager, next" @current-change="loadNotes" />
      </section>
      <section class="study-panel" aria-label="复习闪卡">
        <div class="section-heading"><h2>复习闪卡</h2><span>{{ dueCount }} 张待复习</span></div>
        <div class="editor-box">
          <h3>新增闪卡</h3>
          <el-input v-model="cardFront" maxlength="500" placeholder="正面：问题或概念" aria-label="闪卡正面" />
          <el-input v-model="cardBack" type="textarea" :rows="3" maxlength="10000" placeholder="背面：答案或解释" aria-label="闪卡背面" />
          <el-select v-model="cardNoteId" clearable placeholder="关联笔记（可选）" aria-label="关联笔记"><el-option v-for="note in notes" :key="note.id" :label="note.title" :value="note.id" /></el-select>
          <el-button type="primary" :disabled="!canSaveCard" :loading="saving" @click="saveCard">添加闪卡</el-button>
        </div>
        <el-checkbox v-model="dueOnly" @change="cardPage = 1; loadCards()">只看待复习</el-checkbox>
        <div v-if="!cards.length && !loading" class="empty-state">{{ dueOnly ? '当前没有到期闪卡。' : '还没有闪卡，可从笔记中提炼一个问题。' }}</div>
        <article v-for="card in cards" :key="card.id" class="study-item">
          <div class="item-head"><h3>{{ card.front }}</h3><small>复习 {{ card.review_count }} 次</small></div>
          <button class="reveal-button" type="button" :aria-expanded="revealedCards.has(card.id)" @click="toggleReveal(card.id)">{{ revealedCards.has(card.id) ? '收起答案' : '显示答案' }}</button>
          <p v-if="revealedCards.has(card.id)" class="note-body">{{ card.back }}</p>
          <p class="source-line">{{ dueLabel(card) }}</p>
          <p v-if="card.knowledge_point" class="source-line">知识点：{{card.knowledge_point}} · 自评复习证据</p><p v-if="card.review_evidence" class="source-line">该知识点累计复习 {{card.review_evidence.review_count}} 次，自评记住率 {{Math.round(card.review_evidence.recall_rate*100)}}%；与习题评分分别统计。</p>
          <div class="button-row"><el-button size="small" :disabled="!revealedCards.has(card.id) || !isDue(card)" @click="review(card, 1)">还需练习</el-button><el-button size="small" type="success" :disabled="!revealedCards.has(card.id) || !isDue(card)" @click="review(card, 4)">已经记住</el-button><el-button size="small" @click="toggleCardHistory(card.id)">{{ historyCardId === card.id ? '收起记录' : '复习记录' }}</el-button><el-button size="small" type="danger" plain @click="deleteCard(card)">删除</el-button></div>
          <div v-if="historyCardId === card.id" class="review-history"><h4>最近 50 次复习</h4><p v-if="!reviewHistory[card.id]?.length" class="source-line">还没有复习记录。</p><p v-for="event in reviewHistory[card.id] ?? []" :key="event.id">{{ asUtcDate(event.reviewed_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) }} · {{ event.grade < 3 ? '还需练习' : '已记住' }} · {{ event.interval_days ? `${event.interval_days} 天后复习` : '10 分钟后复习' }}</p></div>
        </article>
        <el-pagination v-if="cardTotal > cardSize" v-model:current-page="cardPage" :page-size="cardSize" :total="cardTotal" layout="prev, pager, next" @current-change="loadCards" />
      </section>
    </div>
    <el-dialog v-model="historyOpen" title="笔记修改历史" append-to-body width="min(700px,94vw)"><p>仅记录接入历史功能后的保存；原笔记更早的修改不会补造。</p><p v-if="!noteHistory.length">暂无已记录的历史版本。</p><article v-for="item in noteHistory" :key="item.id"><h3>{{item.snapshot.title}}</h3><small>{{item.created_at}} · {{item.version.slice(0,12)}}</small><p class="note-body">{{item.snapshot.body}}</p><el-button @click="useHistory(item)">载入此版本正文到编辑器</el-button></article></el-dialog>
  </main>
</template>

<style scoped>
.study-tools { padding-bottom:30px; }.study-header { display:flex; align-items:start; justify-content:space-between; gap:15px; margin-bottom:20px; }.study-header h1 { margin:5px 0; font-size:27px; color:var(--text); }.study-header p { margin:0; color:var(--muted); font-size:13px; }.study-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }.study-panel { min-width:0; padding:20px; border:1px solid var(--line); border-radius:16px; background:var(--panel); }.section-heading,.item-head,.button-row { display:flex; align-items:center; justify-content:space-between; gap:10px; }.section-heading h2 { margin:0; font-size:19px; }.section-heading span,.item-head small,.source-line { color:var(--muted); font-size:12px; }.editor-box { display:grid; gap:11px; padding:16px; margin:18px 0; border-radius:14px; background:var(--surface-soft); }.editor-box h3 { margin:0; font-size:14px; }.button-row { justify-content:flex-start; flex-wrap:wrap; margin-top:11px; }.study-item { margin-top:12px; padding:16px; border:1px solid var(--line); border-radius:13px; }.item-head h3 { margin:0; font-size:15px; overflow-wrap:anywhere; }.note-body { white-space:pre-wrap; overflow-wrap:anywhere; color:var(--text); font-size:13px; line-height:1.7; }.source-line { margin:9px 0; }.reveal-button { border:0; padding:8px 0; background:transparent; color:var(--accent); cursor:pointer; font:inherit; font-size:12px; }.empty-state { padding:28px 12px; text-align:center; color:var(--muted); }.study-error { color:var(--red); }.editor-box :deep(.el-input-number) { width:100%; }.editor-box :deep(.el-input-number .el-input__inner) { text-align:left; }.suggestion-box { margin:18px 0; padding:17px; border:1px solid var(--accent); border-radius:14px; }.suggested-card { padding:12px 0; border-top:1px solid var(--line); }.suggested-card p { color:var(--muted); font-size:13px; white-space:pre-wrap; }@media(max-width:900px){.study-grid{grid-template-columns:1fr;}}
.review-history { margin-top:14px; padding:12px; border-radius:10px; background:var(--surface-soft); }.review-history h4 { margin:0 0 8px; font-size:13px; }.review-history p { margin:5px 0; color:var(--muted); font-size:12px; }
</style>
