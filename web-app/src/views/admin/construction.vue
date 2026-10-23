<script setup lang="ts">
import { computed } from 'vue'
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const {
  constructionSubjects, constructionPoints, constructionSubjectId, constructionSelectedPoints,
  constructionForm, outlineReview, outlineStatus, outlineError, outlinePollCount,
  constructionBusy, manualPoint, constructionFocus, loading,
  createManualConstructionPoint, planConstructionSubject, discardOutline, confirmConstructionOutline,
  loadConstructionPoints, buildConstructionPoints,
} = useAdminWorkspace('construction')

const keptPointCount = computed(() =>
  (outlineReview.value?.chapters ?? []).reduce((sum, chapter) => sum + chapter.points.filter(point => point.kept).length, 0))
const planning = computed(() => outlineStatus.value === 'queued' || outlineStatus.value === 'running')
const planningText = computed(() => {
  if (outlineStatus.value === 'running') return `AI 正在撰写课程大纲…（第 ${outlinePollCount.value} 次检查）`
  return `AI 规划已排队，正在等待开始…（第 ${outlinePollCount.value} 次检查）`
})
</script>
<template>
<div class="admin-module">
  <section class="workspace-panel">
    <div class="panel-heading">
      <div>
        <div class="panel-kicker">知识建设 · 第 1 步</div>
        <h2>AI 规划课程，管理员审核确认</h2>
      </div>
    </div>
    <p class="admin-evidence-note">你只需要填写学科名称和建设要求，章节、知识点、学科代码全部由模型生成；确认后知识点才进入内容建设。</p>
    <el-form label-position="top" :disabled="planning || constructionBusy">
      <el-form-item label="学科名称" required>
        <el-input v-model="constructionForm.name" placeholder="例如：机器学习" maxlength="100" />
      </el-form-item>
      <el-form-item label="学习阶段">
        <el-input v-model="constructionForm.stage" placeholder="默认：本科" maxlength="100" />
      </el-form-item>
      <el-form-item label="建设要求（可选）">
        <el-input v-model="constructionForm.requirements" type="textarea" :rows="3" placeholder="例如：面向工科二年级，重点覆盖监督学习与模型评估" maxlength="4000" />
      </el-form-item>
      <el-form-item label="已有课程资料或目录（可选）">
        <el-input v-model="constructionForm.reference_material" type="textarea" :rows="2" placeholder="粘贴教学大纲、章节目录，模型会参考但不照抄" maxlength="16000" />
      </el-form-item>
    </el-form>
    <div class="action-row">
      <el-button type="primary" :loading="planning || constructionBusy" :disabled="!constructionForm.name.trim()" @click="planConstructionSubject">
        {{ outlineStatus === 'ready' ? '重新生成大纲' : '让 AI 规划课程大纲' }}
      </el-button>
    </div>
    <el-alert v-if="planning" :title="planningText" type="info" :closable="false" show-icon style="margin-top:12px" />
    <el-alert v-if="outlineStatus === 'failed'" :title="outlineError || '规划失败'" type="error" :closable="false" show-icon style="margin-top:12px" />

    <template v-if="outlineReview">
      <section aria-label="大纲审核" style="margin-top:20px">
        <div class="panel-heading"><div><div class="panel-kicker">请审核模型产出</div><h2>课程大纲预览</h2></div></div>
        <p class="admin-evidence-note">以下内容由模型生成：学科「{{ outlineReview.name }}」（代码 {{ outlineReview.code }}）。{{ outlineReview.description }} 勾选要保留的知识点，取消不需要的，确认后即建立课程结构。</p>
        <div v-for="(chapter, chapterIndex) in outlineReview.chapters" :key="chapterIndex" class="list-card static">
          <strong>第 {{ chapterIndex + 1 }} 章 · {{ chapter.name }}</strong>
          <el-checkbox-group
            :model-value="chapter.points.filter(p => p.kept).map(p => p.name)"
            @update:model-value="(names: Array<string | number | boolean>) => chapter.points.forEach(p => { p.kept = names.includes(p.name) })"
          >
            <div v-for="point in chapter.points" :key="point.name" style="display:flex;flex-direction:column;gap:2px;margin-top:6px">
              <el-checkbox :value="point.name">{{ point.name }}</el-checkbox>
              <span v-if="point.objectives.length" style="color:var(--muted);font-size:12px;margin-left:24px">{{ point.objectives[0] }}</span>
            </div>
          </el-checkbox-group>
        </div>
        <div class="action-row" style="margin-top:12px">
          <el-button type="success" :loading="constructionBusy" :disabled="!keptPointCount" @click="confirmConstructionOutline">
            确认课程结构（{{ keptPointCount }} 个知识点）
          </el-button>
          <el-button :disabled="constructionBusy" @click="discardOutline">放弃本次规划</el-button>
        </div>
      </section>
    </template>
  </section>

  <section class="workspace-panel">
    <div class="panel-heading">
      <div>
        <div class="panel-kicker">知识建设 · 第 2 步</div>
        <h2>分批建设知识点内容</h2>
      </div>
    </div>
    <p class="admin-evidence-note">确认结构后，勾选知识点提交 AI 建设；每批 1–10 个，结果进入「审核与发布」队列，不会直接生效。</p>
    <el-select v-model="constructionSubjectId" placeholder="选择已确认结构的学科" style="width:100%" @change="loadConstructionPoints">
      <el-option v-for="item in constructionSubjects" :key="item.id" :label="`${item.name} · ${item.status}`" :value="item.id" />
    </el-select>
    <el-checkbox-group v-model="constructionSelectedPoints" style="margin-top:12px">
      <div v-for="point in constructionPoints" :key="point.id" style="margin:4px 0">
        <el-checkbox :value="point.id">{{ point.chapter }} / {{ point.name }} · {{ point.status }}</el-checkbox>
      </div>
    </el-checkbox-group>
    <p v-if="constructionSubjectId && !constructionPoints.length && !loading.subjects" class="admin-evidence-note">该学科暂无知识点，可在下方手动补充一条。</p>
    <div class="action-row" style="margin-top:12px">
      <el-input v-model="manualPoint.chapter" placeholder="章节" style="max-width:180px" />
      <el-input v-model="manualPoint.name" placeholder="补充单个知识点（可选）" />
      <el-button @click="createManualConstructionPoint">保存知识点</el-button>
    </div>
    <el-input v-model="constructionFocus" placeholder="可选：本次建设的侧重点或可信来源范围" maxlength="300" style="margin-top:12px" />
    <div class="action-row">
      <el-button type="primary" :loading="constructionBusy" @click="buildConstructionPoints('CREATE_POINT')">建设所选知识点</el-button>
      <el-button :loading="constructionBusy" @click="buildConstructionPoints('COMPLETE_POINT')">补充内容</el-button>
      <el-button :loading="constructionBusy" @click="buildConstructionPoints('REVISE_POINT')">修订草稿</el-button>
    </div>
  </section>
</div>
</template>
<style src="./admin.css"></style>
