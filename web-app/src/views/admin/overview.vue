<script setup lang="ts">
import { ref } from 'vue'
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
import { adminNavigation } from '../../config/adminNavigation'
import TaskOperationsPanel from '../../components/admin/TaskOperationsPanel.vue'
import OperationsDashboard from '../../components/admin/dashboard/OperationsDashboard.vue'
const { dashboard, adminStats } = useAdminWorkspace('overview')
const legacyOpen = ref(false)
</script>
<template>
<div class="admin-module"><OperationsDashboard /><details class="platform-statistics"><summary>平台账号、学习路径与资源统计</summary><section class="admin-stat-grid">
        <article v-for="item in adminStats" :key="item.label">
          <span><component :is="item.icon" /></span>
          <div><small>{{ item.label }}</small><strong>{{ item.value }}</strong><p>{{ item.hint }}</p></div>
        </article>
      </section>
      <p class="admin-evidence-note">近 7 天作答 {{ dashboard?.answers_last_7_days ?? '—' }} 次。统计来自持久化记录；任务用量可在 AI 与任务管理中查看。</p>
      </details>
      <details class="platform-statistics" @toggle="legacyOpen = ($event.target as HTMLDetailsElement).open"><summary>原有运营明细、预算预留与每日任务分布</summary><TaskOperationsPanel v-if="legacyOpen" /></details>

<details class="platform-statistics"><summary>管理功能快捷入口</summary><section class="admin-shortcuts" aria-label="管理功能快捷入口">
  <router-link v-for="item in adminNavigation.filter(item => item.key !== 'overview')" :key="item.key" :to="item.route">
    <span>{{ item.group }}</span><strong>{{ item.label }}</strong><p>{{ item.description }}</p>
  </router-link>
</section></details>
</div>
</template>
<style src="./admin.css"></style>
<style scoped>.platform-statistics{margin:0 0 16px;padding:16px;border:1px solid var(--line);border-radius:14px;background:var(--panel)}.platform-statistics>summary{cursor:pointer;font-size:12px;color:var(--muted)}.platform-statistics[open]>summary{margin-bottom:20px}</style>
