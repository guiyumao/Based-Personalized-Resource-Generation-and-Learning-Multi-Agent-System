<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
import KnowledgeDocumentManager from '../../components/admin/KnowledgeDocumentManager.vue'
import LearningGapManager from '../../components/admin/LearningGapManager.vue'
const { knowledgeStatus, knowledgeSources, knowledgeError, loading, fetchKnowledgeStatus, fetchKnowledgeSources, reindexKnowledgeBase } = useAdminWorkspace('knowledge')
</script>
<template>
<div class="admin-module"><LearningGapManager /><KnowledgeDocumentManager />        <section class="workspace-panel">
          <p v-if="knowledgeError" role="alert">{{ knowledgeError }}</p>
          <div class="panel-heading"><div><div class="panel-kicker">知识库</div><h2>语料与索引状态</h2></div></div>
          <p class="admin-evidence-note">读取现有知识库状态，区分本地文档、已索引文档和向量片段。</p>
          <el-button :loading="loading.knowledge" @click="fetchKnowledgeStatus">{{ knowledgeStatus ? '刷新状态' : '加载状态' }}</el-button>
          <el-button :loading="loading.sources" @click="fetchKnowledgeSources">查看来源</el-button>
          <el-button :loading="loading.reindex" @click="reindexKnowledgeBase">增量更新索引</el-button>
          <div v-if="knowledgeStatus" class="kb-status-grid">
            <div><strong>{{ knowledgeStatus.corpus.documents }}</strong><span>本地文档</span></div>
            <div><strong>{{ knowledgeStatus.index.documents }}</strong><span>索引文档</span></div>
            <div><strong>{{ knowledgeStatus.index.chunks }}</strong><span>向量片段</span></div>
            <div><strong>{{ knowledgeStatus.available ? '可用' : '不可用' }}</strong><span>检索服务</span></div>
          </div>
          <p v-if="knowledgeStatus" class="admin-evidence-note">白名单来源 {{ knowledgeStatus.sources.configured }} 个；上次索引 {{ knowledgeStatus.index.updated_at || '暂无记录' }}。</p>
          <div v-if="knowledgeSources.length" class="list-stack"><div v-for="source in knowledgeSources.slice(0, 12)" :key="source.id" class="list-card static"><strong>{{ source.topic || source.subject }}</strong><span>{{ source.status === 'available' ? '已抓取' : '未抓取' }} · {{ source.subject }}</span><a :href="source.url" target="_blank" rel="noreferrer">原始来源</a></div><p v-if="knowledgeSources.length > 12" class="admin-evidence-note">展示前 12 个来源，共 {{ knowledgeSources.length }} 个。</p></div>
        </section></div>
</template>
<style src="./admin.css"></style>
