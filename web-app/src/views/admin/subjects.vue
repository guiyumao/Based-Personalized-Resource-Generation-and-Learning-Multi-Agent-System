<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
import { ref } from 'vue'
import { agentApi } from '../../api/http'
const { subjects, subjectForm, loading, fetchSubjects } = useAdminWorkspace('subjects')
type Check = { subjects: { id:number; name:string; code:string|null; match:string; point_count:number }[]; unlinked_documents: { id:string; title:string; corpus_subject:string }[]; tasks:{ id:number; status:string; operation_type:string }[]; chroma_metadata:string }
const check = ref<Check|null>(null), checkedName = ref(''), code = ref(''), selectedDocs = ref<string[]>([]), targetSubject = ref<number>(), error = ref(''), saving = ref(false), covered = ref<any>(null)
async function inspect() {
  error.value = ''; check.value = null; selectedDocs.value = []; covered.value = null
  try { check.value = (await agentApi.get('/knowledge-base/admin/subjects/preflight', { params: { name: subjectForm.name } })).data; checkedName.value = subjectForm.name }
  catch(e:any) { error.value = e?.response?.data?.detail || '检查失败' }
}
async function link(id:number) {
  if (selectedDocs.value.length) await agentApi.post('/knowledge-base/admin/documents/classify', { document_ids:selectedDocs.value, subject_id:id, point_ids:[], tags:[], chapter:'' })
  targetSubject.value = id; covered.value = (await agentApi.get(`/knowledge-base/admin/subjects/${id}/coverage`)).data
}
async function create() {
  if (!check.value || checkedName.value !== subjectForm.name) { error.value = '请先检查当前学科名称'; return }
  saving.value = true; error.value = ''
  try {
    const { data } = await agentApi.post('/knowledge-base/construction/subjects', { name:subjectForm.name, code:code.value, description:subjectForm.description })
    await link(data.id); await fetchSubjects(); await inspect()
  } catch(e:any) { error.value = e?.response?.data?.detail || '创建或关联失败；已创建的学科可在列表查看并重试关联' }
  finally { saving.value = false }
}
async function associate() { if (!targetSubject.value) return; try { await link(targetSubject.value); error.value = ''; await fetchSubjects() } catch(e:any) { error.value = e?.response?.data?.detail || '关联失败' } }
async function showCoverage(id:number) { try { targetSubject.value = id; covered.value = (await agentApi.get(`/knowledge-base/admin/subjects/${id}/coverage`)).data } catch(e:any) { error.value = e?.response?.data?.detail || '读取覆盖率失败' } }
</script>
<template>
<div class="admin-module">        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">学科管理</div>
              <h2>新增并查看学科</h2>
            </div>
          </div>
          <p v-if="error" role="alert">{{ error }}</p>
          <el-form :model="subjectForm" label-position="top">
            <el-form-item label="学科名称">
              <el-input v-model="subjectForm.name" />
            </el-form-item>
            <el-form-item label="学科描述">
              <el-input v-model="subjectForm.description" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="稳定学科代码（字母开头，可含数字和下划线）"><el-input v-model="code" placeholder="例如 linear_algebra" /></el-form-item>
          </el-form>
          <div class="action-row">
            <el-button @click="inspect">检查已有知识</el-button>
            <el-button type="success" :loading="saving" :disabled="!check || checkedName !== subjectForm.name || !code || check.subjects.some(s => s.match === 'EXACT')" @click="create">确认创建{{ selectedDocs.length ? '并关联资料' : '学科基础信息' }}</el-button>
            <el-button :loading="loading.subjects" @click="fetchSubjects">刷新学科</el-button>
          </div>
          <section v-if="check && checkedName === subjectForm.name" aria-label="学科知识检查">
            <p>以下仅为候选匹配，请核对后明确选择。相似名称不会自动合并；Chroma实时metadata尚未查询，可从文档详情查看片段。</p>
            <div v-for="s in check.subjects" :key="s.id" class="list-card static"><strong>{{ s.name }} · {{ s.match === 'EXACT' ? '名称或别名一致' : '相似名称' }}</strong><span>{{ s.point_count }} 个知识点 · {{ s.code || '尚无代码' }}</span><el-button @click="showCoverage(s.id)">查看已有学科覆盖</el-button></div>
            <p v-if="!check.subjects.length">没有匹配的已有学科。</p>
            <el-checkbox-group v-model="selectedDocs"><el-checkbox v-for="d in check.unlinked_documents" :key="d.id" :value="d.id">{{ d.title }}（{{ d.corpus_subject }}）</el-checkbox></el-checkbox-group>
            <p v-if="!check.unlinked_documents.length">未找到标题或目录匹配的未关联资料。</p>
            <el-select v-model="targetSubject" placeholder="选择要关联的已有学科" style="width:220px"><el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" /></el-select><el-button :disabled="!targetSubject || !selectedDocs.length" @click="associate">确认关联所选资料</el-button>
            <p>相关建设任务：{{ check.tasks.map(t => `#${t.id} ${t.operation_type} ${t.status}`).join('；') || '无' }}</p>
          </section>
          <p v-if="covered">知识点 {{ covered.total_points }} 个；已有有效关联 {{ covered.covered_points }} 个；覆盖率 {{ covered.coverage === null ? '尚无规划' : `${Math.round(covered.coverage * 100)}%` }}。仅计入明确关联、审核发布、活动版本且索引清单一致的资料，实时检索需另行验证。</p>
          <div class="list-stack">
            <div v-for="item in subjects" :key="item.id" class="list-card static">
              <strong>{{ item.name }}</strong>
              <span>{{ item.description }}</span>
              <el-button @click="showCoverage(item.id)">查看知识覆盖</el-button>
            </div>
            <div v-if="loading.subjects" class="empty-state">正在加载学科...</div>
            <div v-else-if="!subjects.length" class="empty-state">暂无学科，可使用上方表单新增。</div>
          </div>
        </section></div>
</template>
<style src="./admin.css"></style>
