<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const { prompts, selectedPromptName, promptContent, promptPlaceholders, imageProvider, imageProviderForm, loading, fetchPrompts, loadPrompt, savePrompt, fetchImageProvider, updateImageProvider } = useAdminWorkspace('prompts')
</script>
<template>
<div class="admin-module">
  <section class="workspace-panel">
    <div class="panel-heading">
      <div>
        <div class="panel-kicker">AI 内容编排</div>
        <h2>提示词模板维护</h2>
      </div>
    </div>
    <p class="admin-evidence-note">只列出白名单内的生成提示词；保存会校验必须保留的 <code>{占位符}</code>，误删将导致下一次生成失败。</p>

    <div class="list-stack">
      <div v-for="item in prompts" :key="item.name" class="list-card static admin-user-row">
        <div>
          <strong>{{ item.name }}</strong>
          <span>{{ item.chars }} 字符 · 占位符 {{ item.placeholders.length ? item.placeholders.join('、') : '无' }}</span>
        </div>
        <div class="action-row"><el-button size="small" @click="loadPrompt(item.name)">编辑</el-button></div>
      </div>
      <div v-if="!loading.prompts && !prompts.length" class="empty-state">没有可维护的提示词模板。</div>
    </div>

    <template v-if="selectedPromptName">
      <div class="panel-heading" style="margin-top:16px"><div><h2>编辑 {{ selectedPromptName }}</h2></div></div>
      <p v-if="promptPlaceholders.length" class="admin-evidence-note">必须保留占位符：{{ promptPlaceholders.join('、') }}</p>
      <el-input v-model="promptContent" type="textarea" :rows="16" />
      <div class="action-row">
        <el-button type="primary" @click="savePrompt">保存提示词</el-button>
        <el-button @click="fetchPrompts">刷新列表</el-button>
      </div>
    </template>
  </section>

  <section class="workspace-panel">
    <div class="panel-heading">
      <div>
        <div class="panel-kicker">图片 Provider</div>
        <h2>图文生成配置</h2>
      </div>
    </div>
    <p class="admin-evidence-note">图片生成凭据在部署环境配置，管理界面只记录非敏感的名称与模型；未配置时图文生成返回明确的 BLOCKED 状态。</p>
    <div v-if="imageProvider" class="result-box">
      <p>
        状态：
        <strong :style="{ color: imageProvider.status === 'blocked' ? 'var(--danger, #c0392b)' : 'var(--accent)' }">{{ imageProvider.status === 'blocked' ? 'BLOCKED' : '已配置' }}</strong>
      </p>
      <p v-if="imageProvider.status === 'blocked'" class="admin-evidence-note" style="margin:0">{{ imageProvider.reason }}</p>
    </div>
    <el-form label-position="top">
      <el-form-item label="Provider 名称">
        <el-input v-model="imageProviderForm.provider" placeholder="例如 openai_images" maxlength="80" />
      </el-form-item>
      <el-form-item label="模型">
        <el-input v-model="imageProviderForm.model" placeholder="例如 dall-e-3" maxlength="120" />
      </el-form-item>
    </el-form>
    <div class="action-row">
      <el-button type="warning" :loading="loading.imageProvider" @click="updateImageProvider">保存配置</el-button>
      <el-button :loading="loading.imageProvider" @click="fetchImageProvider">刷新状态</el-button>
    </div>
  </section>
</div>
</template>
<style src="./admin.css"></style>
