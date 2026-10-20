<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const { logs, logFilter, loading, visibleLogs, fetchLogs } = useAdminWorkspace('logs')
</script>
<template>
<div class="admin-module">        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">审计日志</div>
              <h2>系统操作记录</h2>
            </div>
          </div>
          <div class="action-row">
            <el-select v-model="logFilter" placeholder="全部级别" style="max-width: 180px">
              <el-option label="全部级别" value="" />
              <el-option label="INFO" value="INFO" />
              <el-option label="WARN" value="WARN" />
            </el-select>
            <el-button :loading="loading.logs" @click="fetchLogs">刷新日志</el-button>
          </div>
          <div class="list-stack">
            <div v-for="item in visibleLogs" :key="`${item.level}-${item.event}-${item.message}`" class="list-card static">
              <strong>{{ item.level }} / {{ item.event }}</strong>
              <span>{{ item.message }}</span>
            </div>
            <div v-if="loading.logs" class="empty-state">正在加载审计日志...</div>
            <div v-else-if="!visibleLogs.length" class="empty-state">当前筛选条件下暂无审计记录。</div>
          </div>
        </section></div>
</template>
<style src="./admin.css"></style>
