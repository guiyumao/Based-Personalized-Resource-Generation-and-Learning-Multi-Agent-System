<script setup lang="ts">
import { computed } from 'vue'
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const { prompts, selectedPromptName, promptContent, promptPlaceholders, promptVersions, imageProvider, imageProviderForm, loading, fetchPrompts, loadPrompt, savePrompt, fetchImageProvider, updateImageProvider, loadPromptVersions, restorePromptVersion } = useAdminWorkspace('prompts')

const providerStatusLabel = computed(() => {
  switch (imageProvider.value?.status) {
    case 'configured': return '已配置'
    case 'invalid': return '配置无效'
    case 'disabled': return '已停用'
    case 'blocked': return 'BLOCKED'
    default: return '未知'
  }
})
const providerStatusColor = computed(() => {
  switch (imageProvider.value?.status) {
    case 'configured': return 'var(--accent)'
    case 'blocked': return 'var(--danger, #c0392b)'
    default: return 'var(--danger, #c0392b)'
  }
})
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

      <div class="panel-heading" style="margin-top:12px"><div><h3>版本历史</h3></div></div>
      <p class="admin-evidence-note">每次保存都会保留上一版本；恢复会把当前内容再存档一份，可安全回退。</p>
      <div v-if="promptVersions.length" class="list-stack">
        <div v-for="v in promptVersions" :key="v.version" class="list-card static admin-user-row">
          <div>
            <strong>{{ v.version }}</strong>
            <span>{{ v.chars }} 字符 · 占位符 {{ v.placeholders.length ? v.placeholders.join('、') : '无' }}</span>
          </div>
          <div class="action-row"><el-button size="small" @click="restorePromptVersion(selectedPromptName, v.version)">恢复</el-button></div>
        </div>
      </div>
      <div v-else class="empty-state">暂无历史版本（保存后会自动生成）。</div>
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
        <strong :style="{ color: providerStatusColor }">{{ providerStatusLabel }}</strong>
      </p>
      <p class="admin-evidence-note" style="margin:0">{{ imageProvider.reason }}</p>
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
