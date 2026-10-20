<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const { configs, selectedConfigKey, configForm, loading, fetchConfigs, syncSelectedConfigValue, updateConfig } = useAdminWorkspace('settings')
</script>
<template>
<div class="admin-module">        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">系统配置</div>
              <h2>关键参数维护</h2>
            </div>
          </div>
          <el-form label-position="top">
            <el-form-item label="配置键">
              <el-select v-model="selectedConfigKey" @change="syncSelectedConfigValue">
                <el-option v-for="item in configs" :key="item.key" :label="item.key" :value="item.key" />
              </el-select>
            </el-form-item>
            <el-form-item label="配置值">
              <el-input v-model="configForm.value" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="warning" :loading="loading.updateConfig" @click="updateConfig">更新配置</el-button>
            <el-button :loading="loading.configs" @click="fetchConfigs">刷新配置</el-button>
          </div>
          <div class="list-stack">
            <div v-for="item in configs" :key="item.key" class="list-card static">
              <strong>{{ item.key }}</strong>
              <span>{{ item.value }}</span>
            </div>
            <div v-if="loading.configs" class="empty-state">正在加载配置...</div>
            <div v-else-if="!configs.length" class="empty-state">暂无可维护的系统配置。</div>
          </div>
        </section></div>
</template>
<style src="./admin.css"></style>
