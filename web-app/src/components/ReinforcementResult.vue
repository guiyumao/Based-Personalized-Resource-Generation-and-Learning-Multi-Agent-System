<script setup lang="ts">
import type { ReinforcementAttempt } from '../api'
import LearningContent from './LearningContent.vue'
defineProps<{ result: ReinforcementAttempt }>()
</script>
<template>
  <section class="reinforcement-result">
    <h3>逐题结果与错题反馈</h3>
    <article v-for="item in result.results" :key="item.question_index" class="result-question">
      <div><strong>第{{ item.question_index + 1 }}题 · {{ item.knowledge_point }}</strong> <el-tag :type="item.is_correct === null ? 'info' : item.is_correct ? 'success' : 'danger'">{{ item.is_correct === null ? '待模型判定' : item.is_correct ? '正确' : '错题 · 已加入错题本' }}</el-tag></div>
      <LearningContent :content="item.prompt" /><p>学生答案：{{ item.student_answer }}</p><strong>参考答案</strong><LearningContent :content="item.reference_answer" /><LearningContent :content="item.analysis" /><p v-if="item.comment">模型评分依据：{{ item.comment }}</p>
    </article>
    <el-alert v-if="['pending', 'analyzing'].includes(result.status)" title="已展示参考答案；模型正在分析作答，简答题判定完成后会自动更新错题本。" type="info" :closable="false" />
    <el-alert v-if="result.error" :title="result.error" type="warning" :closable="false" />
    <div v-if="result.analysis"><h3>模型辅助分析</h3><LearningContent :content="result.analysis" /><ul><li v-for="suggestion in result.recommendations" :key="suggestion">{{ suggestion }}</li></ul><small>以上为模型辅助建议，教师可结合实际教学进一步判断。</small></div>
  </section>
</template>
<style scoped>.reinforcement-result{display:grid;gap:14px}.result-question{display:grid;gap:10px;padding:14px;border:1px solid var(--line);border-radius:12px;min-width:0;overflow-wrap:anywhere}.reinforcement-result h3,.reinforcement-result p{margin:0}.reinforcement-result small{color:var(--muted)}</style>
