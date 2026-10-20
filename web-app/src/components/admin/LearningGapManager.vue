<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { agentApi } from '../../api/http'
const items = ref<{ id: string; subject: string; knowledge_point: string; reason: string; status: string; knowledge_task_id?: number }[]>([])
const error = ref(''); const loading = ref(false)
async function load() {
  error.value = ''; loading.value = true
  try { items.value = (await agentApi.get('/knowledge-base/admin/learning-gaps')).data.items }
  catch (reason: any) { error.value = reason?.response?.data?.detail ?? reason?.message ?? '知识缺口读取失败' }
  finally { loading.value = false }
}
async function construct(id: string) {
  try { await agentApi.post(`/knowledge-base/admin/learning-gaps/${id}/construction`, { client_request_id: crypto.randomUUID() }); await load() }
  catch (reason: any) { error.value = reason?.response?.data?.detail ?? reason?.message ?? '建设任务未创建' }
}
onMounted(load)
</script>
<template><section class="workspace-panel" aria-label="学习知识缺口"><h2>学习知识缺口</h2><p>覆盖检查产生的真实请求；补充任务进入原 Worker 和预算体系，成果仍需审核。</p><el-button :loading="loading" @click="load">刷新知识缺口</el-button><el-alert v-if="error" :title="error" type="error" :closable="false" /><el-table v-else :data="items" empty-text="暂无学习缺口请求"><el-table-column prop="subject" label="学科" /><el-table-column prop="knowledge_point" label="知识点" /><el-table-column prop="reason" label="缺口原因" /><el-table-column prop="status" label="状态" /><el-table-column prop="knowledge_task_id" label="任务" /><el-table-column label="操作"><template #default="scope"><el-button size="small" :disabled="Boolean(scope.row.knowledge_task_id) || scope.row.status === 'RESOLVED'" @click="construct(scope.row.id)">创建受控建设任务</el-button></template></el-table-column></el-table></section></template>
