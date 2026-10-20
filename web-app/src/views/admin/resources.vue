<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const { resourceError, resourceFilter, selectedResource, loading, visibleResources, rewriteInstruction, rewriteStyle, rewriteResult, rewriteBusy, resourceSections, imageProvider, fetchManagedResources, showResource, changeResourceStatus, rewriteSelectedResource, applyRewrite, loadResourceSections } = useAdminWorkspace('resources')
</script>
<template>
<div class="admin-module">        <section class="workspace-panel">
          <div class="panel-heading"><div><div class="panel-kicker">资源管理</div><h2>审核状态与发布</h2></div></div>
          <p class="admin-evidence-note">列表来自现有资源库；只有审核通过的资源可发布。</p>
          <div class="action-row"><el-input v-model="resourceFilter" clearable placeholder="按标题或 ID 筛选" /><el-button :loading="loading.resources" @click="fetchManagedResources">刷新</el-button></div>
          <p v-if="resourceError" role="alert" class="admin-evidence-note">{{ resourceError }}</p>
          <div class="list-stack">
            <div v-for="item in visibleResources.slice(0, 30)" :key="item.id" class="list-card static admin-user-row">
              <div><strong>#{{ item.id }} {{ item.title }}</strong><span>{{ item.type }} · {{ item.audit_status }} · {{ item.publish_status }} · {{ item.status }}</span></div>
              <div class="action-row"><el-button size="small" @click="showResource(item)">预览</el-button><el-button size="small" :disabled="loading.resourceStatus || item.audit_status !== 'passed'" @click="changeResourceStatus(item, 'ready')">发布</el-button><el-button size="small" :disabled="loading.resourceStatus" @click="changeResourceStatus(item, 'archived')">归档</el-button></div>
            </div>
            <div v-if="!loading.resources && !visibleResources.length" class="empty-state">当前没有匹配资源。</div>
          </div>
          <p v-if="visibleResources.length > 30" class="admin-evidence-note">当前显示前 30 条，请用标题或 ID 缩小范围。</p>
          <div v-if="selectedResource" class="result-box"><strong>{{ selectedResource.title }}</strong><p>审核：{{ selectedResource.audit_status }}；原因：{{ selectedResource.audit_reason || '无' }}</p><pre>{{ selectedResource.content || '该资源没有可预览的文本内容。' }}</pre></div>
        </section>

        <section v-if="selectedResource" class="workspace-panel">
          <div class="panel-heading"><div><div class="panel-kicker">P1-07 改写</div><h2>AI 改写当前资源</h2></div></div>
          <p class="admin-evidence-note">改写调用已配置的文本模型，会记录真实用量；结果需人工审核后应用，应用前保留上一版本快照。</p>
          <div class="action-row">
            <el-input v-model="rewriteInstruction" placeholder="改写要求，如：简化语言、补充示例、适合初中生" maxlength="2000" />
            <el-select v-model="rewriteStyle" style="width:180px">
              <el-option label="平实" value="plain" />
              <el-option label="精简" value="concise" />
              <el-option label="详细" value="detailed" />
              <el-option label="案例驱动" value="case" />
              <el-option label="互动" value="interactive" />
            </el-select>
            <el-button type="primary" :loading="rewriteBusy" @click="rewriteSelectedResource">生成改写</el-button>
          </div>
          <div v-if="rewriteResult" class="result-box">
            <p v-if="rewriteResult.status !== 'generated'" class="admin-evidence-note">{{ rewriteResult.reason }}</p>
            <pre v-if="rewriteResult.rewritten_content">{{ rewriteResult.rewritten_content }}</pre>
            <div v-if="rewriteResult.status === 'generated'" class="action-row">
              <el-button type="warning" @click="applyRewrite">应用改写</el-button>
            </div>
          </div>
        </section>

        <section v-if="selectedResource" class="workspace-panel">
          <div class="panel-heading"><div><div class="panel-kicker">P1-07 图文编排</div><h2>章节配图</h2></div></div>
          <div class="action-row"><el-button @click="loadResourceSections">读取章节</el-button></div>
          <p v-if="imageProvider && imageProvider.status === 'blocked'" class="admin-evidence-note">图片 Provider：BLOCKED —— {{ imageProvider.reason }}</p>
          <div class="list-stack">
            <div v-for="section in resourceSections" :key="section.title" class="list-card static admin-user-row">
              <div><strong>{{ section.title }}</strong><span>{{ section.chars }} 字符</span></div>
              <span class="admin-evidence-note" style="margin:0">BLOCKED（未配置图片 Provider）</span>
            </div>
            <div v-if="!resourceSections.length" class="empty-state">点击“读取章节”查看可配图的正文小节。</div>
          </div>
        </section></div>
</template>
<style src="./admin.css"></style>
