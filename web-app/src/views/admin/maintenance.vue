<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const { taskSubject, maintenancePlans, maintenanceReport, planForm, knowledgeError, loading, createMaintenancePlan, toggleMaintenancePlan, viewMaintenanceReports } = useAdminWorkspace('maintenance')
</script>
<template>
<div class="admin-module"><section class="workspace-panel">          <div class="panel-heading"><div><div class="panel-kicker">自动维护</div><h2>巡检计划</h2></div></div>
          <p class="admin-evidence-note">按指定时间自动生成知识库巡检任务；时间按当前浏览器时区输入，服务端以 UTC 保存。计划由知识 Worker 派发。</p>
          <el-input v-model="taskSubject" aria-label="维护学科代码" placeholder="学科代码（可选）" />
          <div class="action-row"><el-select v-model="planForm.mode"><el-option label="仅检查" value="INSPECT_ONLY" /><el-option label="自动补充后审核" value="AUTO_SUPPLEMENT_REVIEW" /></el-select><el-input v-model="planForm.chapter" placeholder="章节（可选）" /><el-input-number v-model="planForm.maxPoints" :min="0" :max="10" /><el-checkbox v-model="planForm.repairIndex">修复索引</el-checkbox></div>
          <div class="action-row"><el-input v-model="planForm.name" maxlength="120" placeholder="计划名称" /><el-input v-model="planForm.firstRun" type="datetime-local" /><el-select v-model="planForm.intervalHours" style="min-width:120px"><el-option label="一次" value="once" /><el-option label="每天" value="24" /><el-option label="每周" value="168" /><el-option label="每 30 天" value="720" /></el-select><el-button :loading="loading.maintenancePlans" @click="createMaintenancePlan">创建计划</el-button></div>
          <div v-if="maintenancePlans.length" class="list-stack"><div v-for="plan in maintenancePlans" :key="plan.id" class="list-card static"><strong>{{ plan.name }}</strong><span>{{ plan.subject || '全部学科' }} · {{ plan.enabled ? '启用' : '暂停或已完成' }} · 下次 {{ plan.next_run_at ? new Date(plan.next_run_at).toLocaleString() : '无' }}</span><span v-if="plan.last_task_id">最近任务 #{{ plan.last_task_id }}</span><el-button size="small" @click="viewMaintenanceReports(plan)">历史报告</el-button><el-button v-if="plan.next_run_at" size="small" @click="toggleMaintenancePlan(plan)">{{ plan.enabled ? '暂停' : '启用' }}</el-button></div></div>
          <details v-if="maintenanceReport"><summary>维护执行报告</summary><pre>{{ maintenanceReport }}</pre></details><p v-if="knowledgeError" class="admin-evidence-note">{{ knowledgeError }}</p>
</section></div>
</template>
<style src="./admin.css"></style>
