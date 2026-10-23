<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '../../api/http'

const { subjects, loading, fetchSubjects } = useAdminWorkspace('subjects')

type Check = { subjects: { id:number; name:string; code:string|null; match:string; point_count:number }[]; unlinked_documents: { id:string; title:string; corpus_subject:string }[]; tasks:{ id:number; status:string; operation_type:string }[]; chroma_metadata:string }
type SubjectStat = { id:number; name:string; code:string|null; total_points:number; covered_points:number; published_points:number; document_count:number; unlinked_documents:number; coverage:number|null }
type PointDoc = { id:string; title:string; status:string; index_status:string; usable:boolean }
type PointRow = { id:number; name:string; chapter:string; difficulty:number; importance:number; construction_status:string; objectives:string[]; prerequisites:string[]; documents:PointDoc[]; covered:boolean }
type Coverage = { subject_id:number; subject_name:string; code:string|null; total_points:number; covered_points:number; missing_points:{id:number;name:string}[]; points:PointRow[]; unlinked_documents:PointDoc[]; coverage:number|null }

const overview = ref<Record<number, SubjectStat>>({})
const coverageById = ref<Record<number, Coverage>>({})
const expandedId = ref<number|null>(null)
const busyId = ref<number|null>(null)
const pointFilter = ref('')
const missingOnly = ref(false)

const check = ref<Check|null>(null), checkedName = ref(''), checkName = ref(''), selectedDocs = ref<string[]>([]), targetSubject = ref<number>(), error = ref(''), saving = ref(false)
const linkPointIds = ref<number[]>([]), linkPointsLoading = ref(false)

async function loadOverview() {
  try { overview.value = ((await agentApi.get('/knowledge-base/admin/subjects/overview')).data.items as SubjectStat[]).reduce((acc, item) => ({ ...acc, [item.id]: item }), {} as Record<number, SubjectStat>) }
  catch { overview.value = {} }
}

async function loadCoverage(id: number, force = false): Promise<Coverage | null> {
  if (!force && coverageById.value[id]) return coverageById.value[id]
  busyId.value = id
  try {
    const data = (await agentApi.get(`/knowledge-base/admin/subjects/${id}/coverage`)).data as Coverage
    coverageById.value = { ...coverageById.value, [id]: data }
    return data
  } catch (e:any) { error.value = e?.response?.data?.detail || '读取知识覆盖失败'; return null }
  finally { busyId.value = null }
}

async function toggle(id: number) {
  if (expandedId.value === id) { expandedId.value = null; return }
  expandedId.value = id; pointFilter.value = ''; missingOnly.value = false
  await loadCoverage(id)
}

const currentCoverage = computed(() => (expandedId.value ? coverageById.value[expandedId.value] ?? null : null))

const chapters = computed(() => {
  const data = currentCoverage.value
  if (!data) return []
  const keyword = pointFilter.value.trim()
  const groups = new Map<string, { chapter: string; total: number; covered: number; points: PointRow[] }>()
  data.points.forEach((point) => {
    if (missingOnly.value && point.covered) return
    if (keyword && !`${point.name}${point.chapter}`.includes(keyword)) return
    const key = point.chapter || '未分章'
    const group = groups.get(key) ?? { chapter: key, total: 0, covered: 0, points: [] }
    group.total += 1
    if (point.covered) group.covered += 1
    group.points.push(point)
    groups.set(key, group)
  })
  return [...groups.values()]
})

const visiblePointCount = computed(() => chapters.value.reduce((sum, chapter) => sum + chapter.points.length, 0))

function stat(id: number): SubjectStat | undefined { return overview.value[id] }
function percent(value: number | null | undefined) { return value === null || value === undefined ? '尚无规划' : `${Math.round(value * 100)}%` }
function docLabel(doc: PointDoc) {
  if (doc.usable) return doc.title
  if (doc.status === 'REJECTED') return `${doc.title}（已驳回）`
  if (doc.status === 'ARCHIVED') return `${doc.title}（已归档）`
  if (doc.index_status !== 'INDEXED') return `${doc.title}（索引未同步）`
  return `${doc.title}（待审核发布）`
}

async function inspect() {
  if (!checkName.value.trim()) { error.value = '请输入要检查的学科名称'; return }
  error.value = ''; check.value = null; selectedDocs.value = []
  try { check.value = (await agentApi.get('/knowledge-base/admin/subjects/preflight', { params: { name: checkName.value } })).data; checkedName.value = checkName.value }
  catch(e:any) { error.value = e?.response?.data?.detail || '检查失败' }
}

async function pickTarget(id: number | undefined) {
  linkPointIds.value = []
  if (!id) return
  linkPointsLoading.value = true
  try { await loadCoverage(id) } finally { linkPointsLoading.value = false }
}

const targetPoints = computed(() => {
  const data = targetSubject.value ? coverageById.value[targetSubject.value] : null
  return data ? data.points : []
})

async function associate() {
  if (!targetSubject.value || !selectedDocs.value.length) return
  saving.value = true
  try {
    await agentApi.post('/knowledge-base/admin/documents/classify', { document_ids: selectedDocs.value, subject_id: targetSubject.value, point_ids: linkPointIds.value, tags: [], chapter: '' })
    ElMessage.success(`已把 ${selectedDocs.value.length} 篇资料归位到 ${linkPointIds.value.length} 个知识点`)
    error.value = ''; selectedDocs.value = []; linkPointIds.value = []
    await Promise.all([fetchSubjects(), loadOverview(), loadCoverage(targetSubject.value, true)])
    if (checkName.value.trim()) await inspect()
  }
  catch(e:any) { error.value = e?.response?.data?.detail || '关联失败' }
  finally { saving.value = false }
}

async function showCoverage(id: number) { expandedId.value = id; await loadCoverage(id, true) }

onMounted(loadOverview)
</script>

<template>
<div class="admin-module">
  <section class="workspace-panel">
    <div class="panel-heading">
      <div>
        <div class="panel-kicker">学科管理</div>
        <h2>学科目录与知识覆盖</h2>
      </div>
    </div>
    <p class="admin-evidence-note">这一页回答三个问题：每个学科有哪些知识点、每个知识点是否已有可用的已发布资料、哪些资料还没认领知识点。能否用于出题/讲课还要以「实时检索」为准，可在知识点下方看到关联资料及其状态。</p>
    <p v-if="error" role="alert" style="color:var(--danger,#c0392b)">{{ error }}</p>
    <div class="list-stack">
      <div v-for="item in subjects" :key="item.id" class="list-card static subject-card">
        <div class="subject-head">
          <div class="subject-title">
            <strong>{{ item.name }}</strong>
            <code v-if="stat(item.id)?.code">{{ stat(item.id)?.code }}</code>
            <em v-if="stat(item.id)" class="subject-badge" :class="{ ok: (stat(item.id)?.coverage ?? 0) >= 1, warn: stat(item.id)?.total_points && !stat(item.id)?.covered_points }">
              {{ percent(stat(item.id)?.coverage) }}
            </em>
          </div>
          <div class="subject-metrics" v-if="stat(item.id)">
            <span><b>{{ stat(item.id)?.total_points }}</b> 知识点</span>
            <span><b>{{ stat(item.id)?.covered_points }}</b> 有可用资料</span>
            <span v-if="stat(item.id)?.unlinked_documents"><b>{{ stat(item.id)?.unlinked_documents }}</b> 篇资料未认领知识点</span>
          </div>
          <el-button size="small" :loading="busyId === item.id" @click="toggle(item.id)">
            {{ expandedId === item.id ? '收起知识点' : `查看知识点${stat(item.id)?.total_points ? `（${stat(item.id)?.total_points}）` : ''}` }}
          </el-button>
        </div>
        <span class="subject-desc">{{ item.description }}</span>

        <div v-if="expandedId === item.id" class="point-panel">
          <template v-if="currentCoverage">
            <div class="point-toolbar">
              <p class="point-summary">
                共 {{ currentCoverage.total_points }} 个知识点，已关联可用资料 {{ currentCoverage.covered_points }} 个，覆盖率 {{ percent(currentCoverage.coverage) }}<template v-if="currentCoverage.missing_points.length">，缺资料 {{ currentCoverage.missing_points.length }} 个</template>。
              </p>
              <div class="point-filters">
                <el-input v-model="pointFilter" placeholder="搜索知识点" clearable size="small" style="width:170px" />
                <el-checkbox v-model="missingOnly" size="small">只看缺资料</el-checkbox>
              </div>
            </div>

            <p v-if="!currentCoverage.total_points" class="admin-evidence-note">该学科还没有知识点，请到「学科规划与知识点」用 AI 规划课程大纲并确认结构。</p>
            <template v-else>
              <div v-for="chapter in chapters" :key="chapter.chapter" class="chapter-block">
                <div class="chapter-head">
                  <strong>{{ chapter.chapter }}</strong>
                  <span>{{ chapter.covered }}/{{ chapter.total }} 有资料</span>
                </div>
                <ul class="point-list">
                  <li v-for="point in chapter.points" :key="point.id">
                    <span class="point-name">{{ point.name }}</span>
                    <el-tag size="small" :type="point.covered ? 'success' : 'info'" effect="light">{{ point.covered ? '资料就绪' : '缺资料' }}</el-tag>
                    <span class="point-status">{{ point.construction_status === 'PUBLISHED' ? '已发布' : point.construction_status === 'PENDING_REVIEW' ? '待审核' : '规划中' }}</span>
                    <span v-if="point.documents.length" class="point-docs">{{ point.documents.map(docLabel).join('、') }}</span>
                    <span v-else class="point-docs muted">尚未关联任何资料</span>
                  </li>
                </ul>
              </div>
              <p v-if="!visiblePointCount" class="admin-evidence-note">没有符合筛选条件的知识点。</p>
            </template>

            <p v-if="currentCoverage.unlinked_documents.length" class="link-warning">
              这个学科下有 {{ currentCoverage.unlinked_documents.length }} 篇资料还没有认领任何知识点（{{ currentCoverage.unlinked_documents.map(d => d.title).join('、') }}），它们不会计入覆盖率；请在下方「资料归位」里选择对应知识点后重新归位。
            </p>
            <div class="point-actions">
              <el-button size="small" :loading="busyId === item.id" @click="showCoverage(item.id)">刷新覆盖数据</el-button>
            </div>
          </template>
          <p v-else class="empty-state">正在读取知识覆盖...</p>
        </div>
      </div>
      <div v-if="loading.subjects" class="empty-state">正在加载学科...</div>
      <div v-else-if="!subjects.length" class="empty-state">暂无学科，请到「学科规划与知识点」让 AI 规划创建。</div>
    </div>
  </section>

  <section class="workspace-panel">
    <div class="panel-heading">
      <div>
        <div class="panel-kicker">资料归位</div>
        <h2>把散落资料挂到学科与知识点</h2>
      </div>
    </div>
    <p class="admin-evidence-note">输入学科名称检查：会列出名称相近的已有学科（不会自动合并）、尚未关联到任何学科的资料，以及相关建设任务。勾选资料后必须同时选择它对应的知识点，覆盖率才会把这篇资料算进去。</p>
    <div class="action-row">
      <el-input v-model="checkName" placeholder="学科名称，例如：离散数学" maxlength="100" @keyup.enter="inspect" />
      <el-button @click="inspect">检查</el-button>
    </div>
    <section v-if="check && checkedName === checkName" aria-label="学科知识检查" style="margin-top:14px">
      <div v-for="s in check.subjects" :key="s.id" class="list-card static">
        <strong>{{ s.name }} · {{ s.match === 'EXACT' ? '名称或别名一致' : '相似名称' }}</strong>
        <span>{{ s.point_count }} 个知识点 · {{ s.code || '尚无代码' }}</span>
        <el-button size="small" @click="showCoverage(s.id)">查看覆盖</el-button>
      </div>
      <p v-if="!check.subjects.length" class="admin-evidence-note">没有匹配的已有学科。若确需新建，请到「学科规划与知识点」由 AI 规划生成。</p>
      <template v-if="check.unlinked_documents.length">
        <p>未关联资料（勾选后归位）：</p>
        <el-checkbox-group v-model="selectedDocs">
          <el-checkbox v-for="d in check.unlinked_documents" :key="d.id" :value="d.id">{{ d.title }}（{{ d.corpus_subject }}）</el-checkbox>
        </el-checkbox-group>
        <div class="action-row">
          <el-select v-model="targetSubject" placeholder="选择要归位到的学科" style="max-width:260px" @change="pickTarget">
            <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
          <el-select
            v-model="linkPointIds"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            :loading="linkPointsLoading"
            :disabled="!targetSubject"
            placeholder="选择这批资料对应的知识点（可多选）"
            style="min-width:280px;flex:1"
          >
            <el-option v-for="p in targetPoints" :key="p.id" :label="`${p.chapter ? p.chapter + ' / ' : ''}${p.name}`" :value="p.id" />
          </el-select>
          <el-button type="primary" :loading="saving" :disabled="!targetSubject || !selectedDocs.length || !linkPointIds.length" @click="associate">
            归位所选资料（{{ selectedDocs.length }}）
          </el-button>
        </div>
        <p v-if="targetSubject && !targetPoints.length && !linkPointsLoading" class="admin-evidence-note">该学科还没有知识点，先到「学科规划与知识点」创建结构，资料归位后才能计入覆盖率。</p>
        <p v-else-if="targetSubject && !linkPointIds.length" class="admin-evidence-note">请选择知识点：只挂到学科而不认领知识点，覆盖率不会变化，出题也检索不到。</p>
      </template>
      <p v-else class="admin-evidence-note">未找到标题或目录匹配的未关联资料。</p>
      <p v-if="check.tasks.length">相关建设任务：{{ check.tasks.map(t => `#${t.id} ${t.operation_type} ${t.status}`).join('；') }}</p>
    </section>
  </section>
</div>
</template>
<style src="./admin.css"></style>
<style scoped>
.subject-card { display:flex; flex-direction:column; gap:10px; }
.subject-head { display:flex; align-items:center; justify-content:space-between; gap:14px; flex-wrap:wrap; }
.subject-title { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.subject-title code { padding:2px 7px; border-radius:6px; background:var(--surface-soft); color:var(--muted); font-size:11px; }
.subject-badge { padding:2px 8px; border-radius:999px; background:var(--surface-soft); color:var(--muted); font-size:11px; font-style:normal; }
.subject-badge.ok { background:color-mix(in srgb,#16a34a 16%,transparent); color:#15803d; }
.subject-badge.warn { background:color-mix(in srgb,#dc2626 12%,transparent); color:#b91c1c; }
.subject-metrics { display:flex; gap:14px; flex-wrap:wrap; color:var(--muted); font-size:12px; }
.subject-metrics b { color:var(--text); font-size:13px; }
.subject-desc { color:var(--muted); font-size:12px; line-height:1.7; }
.point-panel { display:flex; flex-direction:column; gap:12px; margin-top:4px; padding:14px; border:1px solid var(--line); border-radius:12px; background:var(--surface-soft); }
.point-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.point-summary { margin:0; color:var(--text); font-size:12px; line-height:1.7; }
.point-filters { display:flex; align-items:center; gap:10px; }
.chapter-block { padding:10px 12px; border-radius:10px; background:var(--panel); border:1px solid var(--line); }
.chapter-head { display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin-bottom:6px; }
.chapter-head strong { font-size:13px; color:var(--text); }
.chapter-head span { color:var(--muted); font-size:11px; }
.point-list { margin:0; padding:0; list-style:none; display:flex; flex-direction:column; gap:6px; }
.point-list li { display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:6px 0; border-top:1px dashed var(--line); font-size:12px; }
.point-list li:first-child { border-top:0; }
.point-name { min-width:96px; color:var(--text); font-weight:600; }
.point-status { color:var(--muted); font-size:11px; }
.point-docs { color:var(--muted); font-size:11px; flex:1; min-width:160px; }
.point-docs.muted { color:color-mix(in srgb,#dc2626 60%,var(--muted)); }
.link-warning { margin:0; padding:10px 12px; border-radius:10px; background:color-mix(in srgb,#f59e0b 12%,transparent); color:#92400e; font-size:12px; line-height:1.7; }
.point-actions { display:flex; gap:10px; }
</style>
