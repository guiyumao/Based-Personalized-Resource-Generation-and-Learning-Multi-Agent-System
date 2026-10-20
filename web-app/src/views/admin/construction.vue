<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const { constructionSubjects, constructionPoints, constructionSubjectId, constructionSelectedPoints, constructionForm, outlineEditor, outlineTaskId, constructionBusy, manualSubjectCode, manualPoint, constructionFocus, loading, createManualConstructionSubject, createManualConstructionPoint, planConstructionSubject, loadConstructionOutline, confirmConstructionOutline, loadConstructionPoints, buildConstructionPoints } = useAdminWorkspace('construction')
</script>
<template>
<div class="admin-module">        <section class="workspace-panel">
          <div class="panel-heading"><div><div class="panel-kicker">知识建设</div><h2>AI 学科规划与分批建设</h2></div></div>
          <el-input v-model="constructionForm.name" placeholder="学科名称，如机器学习" maxlength="100" />
          <div class="action-row"><el-input v-model="manualSubjectCode" placeholder="手动新增使用的英文代码，如 machine_learning" /><el-button @click="createManualConstructionSubject">手动新增学科</el-button></div>
          <el-input v-model="constructionForm.stage" placeholder="学习阶段" maxlength="100" />
          <el-input v-model="constructionForm.requirements" type="textarea" :rows="3" placeholder="章节、教学目标及建设要求" maxlength="4000" />
          <el-input v-model="constructionForm.reference_material" type="textarea" :rows="2" placeholder="可选：已有课程资料或目录" maxlength="16000" />
          <el-button :loading="constructionBusy" @click="planConstructionSubject">生成候选大纲</el-button>
          <div class="action-row"><el-input-number v-model="outlineTaskId" :min="1" /><el-button @click="loadConstructionOutline">读取规划任务</el-button></div>
          <template v-if="outlineEditor"><el-input v-model="outlineEditor" type="textarea" :rows="12" /><el-button @click="confirmConstructionOutline">确认课程结构</el-button></template>
          <p class="admin-evidence-note">确认只建立课程结构，章节内容经建设、审核和发布后才可用。</p>
          <el-select v-model="constructionSubjectId" placeholder="选择已确认学科" @change="loadConstructionPoints"><el-option v-for="item in constructionSubjects" :key="item.id" :label="`${item.name} · ${item.status}`" :value="item.id" /></el-select>
          <el-checkbox-group v-model="constructionSelectedPoints"><div v-for="point in constructionPoints" :key="point.id"><el-checkbox :value="point.id">{{ point.chapter }} / {{ point.name }} · {{ point.status }}</el-checkbox></div></el-checkbox-group>
          <div class="action-row"><el-input v-model="manualPoint.chapter" placeholder="章节" /><el-input v-model="manualPoint.name" placeholder="新知识点" /><el-button @click="createManualConstructionPoint">保存知识点</el-button></div>
          <el-input v-model="constructionFocus" placeholder="可选：本次需要补充的部分或可信来源范围" maxlength="300" />
          <el-button :loading="constructionBusy" @click="buildConstructionPoints('CREATE_POINT')">建设所选知识点</el-button><el-button :loading="constructionBusy" @click="buildConstructionPoints('COMPLETE_POINT')">补充</el-button><el-button :loading="constructionBusy" @click="buildConstructionPoints('REVISE_POINT')">修订草稿</el-button>
        </section></div>
</template>
<style src="./admin.css"></style>
