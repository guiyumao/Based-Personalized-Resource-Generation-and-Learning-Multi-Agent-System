<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
import { adminNavigation } from '../../config/adminNavigation'
import TaskOperationsPanel from '../../components/admin/TaskOperationsPanel.vue'
const { dashboard, adminStats } = useAdminWorkspace('overview')
</script>
<template>
<div class="admin-module">      <section class="admin-stat-grid">
        <article v-for="item in adminStats" :key="item.label">
          <span><component :is="item.icon" /></span>
          <div><small>{{ item.label }}</small><strong>{{ item.value }}</strong><p>{{ item.hint }}</p></div>
        </article>
      </section>
      <p class="admin-evidence-note">近 7 天作答 {{ dashboard?.answers_last_7_days ?? '—' }} 次。统计来自持久化记录；任务用量可在 AI 与任务管理中查看。</p>
      <TaskOperationsPanel />

<section class="admin-shortcuts" aria-label="管理功能快捷入口">
  <router-link v-for="item in adminNavigation.filter(item => item.key !== 'overview')" :key="item.key" :to="item.route">
    <span>{{ item.group }}</span><strong>{{ item.label }}</strong><p>{{ item.description }}</p>
  </router-link>
</section>
</div>
</template>
<style src="./admin.css"></style>
