<script setup lang="ts">
import { computed, onUnmounted, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { generationMonitor, startGenerationMonitor, stopGenerationMonitor, refreshGenerationMonitor } from '../stores/generationMonitor'
import { generationRequests } from '../stores/generationRequests'
import GenerationProgress from './GenerationProgress.vue'
const auth = useAuthStore()
watch(() => auth.user?.userId, id => { if (id) startGenerationMonitor(id); else stopGenerationMonitor() }, { immediate: true })
const tasks = computed(() => [
  ...generationMonitor.items.map(item => ({ ...item, id: `${item.source}:${item.id}` })),
  ...Object.entries(generationRequests).filter(([, item]) => item.userId === auth.user?.userId).map(([key, item]) => ({ ...item, key, id: key })),
])
const count = computed(() => tasks.value.filter(item => item.status !== 'UNKNOWN').length)
const refresh = () => void refreshGenerationMonitor()
window.addEventListener('generation-tasks-changed', refresh)
onUnmounted(() => { window.removeEventListener('generation-tasks-changed', refresh); stopGenerationMonitor() })
</script>
<template>
  <details v-if="tasks.length" class="generation-task-panel" open>
    <summary>生成任务 · {{ count }} 项进行中<span v-if="tasks.length > count"> · {{ tasks.length - count }} 项待确认</span></summary>
    <p class="generation-task-hint">任务在后台继续执行。这里显示你正在生成的所有资源，切换页面或返回后会自动同步。</p>
    <p v-if="generationMonitor.error" class="generation-sync-error" role="alert">{{ generationMonitor.error }}</p>
    <div class="generation-task-list">
      <article v-for="task in tasks" :key="task.key" class="generation-task-item">
        <GenerationProgress :job="task" :label="`${task.topic ? task.topic + ' · ' : ''}${task.label}`" />
        <router-link v-if="task.route" :to="task.route">查看{{ task.label }}</router-link>
      </article>
    </div>
  </details>
</template>
<style scoped>
.generation-task-panel { margin-bottom:18px; padding:16px; border:1px solid var(--line); border-radius:14px; background:var(--panel); }
summary { cursor:pointer; font-weight:600; color:var(--text); }
.generation-task-hint,.generation-sync-error { font-size:13px; line-height:1.6; color:var(--muted); }
.generation-sync-error { color:var(--el-color-warning); }
.generation-task-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr)); gap:12px; max-height:340px; overflow:auto; }
.generation-task-item { min-width:0; padding-bottom:8px; }
.generation-task-item :deep(.generation-progress) { margin:0 0 8px; }
.generation-task-item a { font-size:13px; color:var(--accent); }
</style>
