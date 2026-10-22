<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { ReinforcementQuestion } from '../api'
import LearningContent from './LearningContent.vue'

const props = defineProps<{ questions: ReinforcementQuestion[]; readonly?: boolean }>()
const emit = defineEmits<{ answer: [value: { content: string; complete: boolean; answers: string[] }] }>()
const answers = reactive<Record<number, string>>({})
watch(answers, () => {
  const complete = props.questions.every((_, index) => Boolean(answers[index]?.trim()))
  emit('answer', { complete, answers: props.questions.map((_, index) => answers[index] || ''), content: props.questions.map((q, index) => `第${index + 1}题：${q.prompt}\n我的答案：${answers[index] || '（未作答）'}`).join('\n\n') })
})
</script>

<template>
  <div class="homework-practice">
    <article v-for="(question, index) in questions" :key="index" class="practice-question">
      <strong>第{{ index + 1 }}题 · {{ question.knowledge_point }}</strong><LearningContent :content="question.prompt" />
      <el-radio-group v-if="question.question_type === 'choice'" v-model="answers[index]" :disabled="readonly" class="practice-options"><el-radio v-for="option in question.options" :key="option" :value="option"><span>{{ option }}</span></el-radio></el-radio-group>
      <el-input v-else-if="!readonly" v-model="answers[index]" type="textarea" :rows="3" :placeholder="`填写第${index + 1}题的答案`" />
      <div v-if="question.answer" class="practice-solution"><strong>参考答案</strong><LearningContent :content="question.answer" /><LearningContent :content="question.analysis || ''" /></div>
    </article>
  </div>
</template>

<style scoped>
.homework-practice{display:grid;gap:14px}.practice-question{display:grid;gap:12px;padding:16px;border:1px solid var(--line);border-radius:12px;min-width:0}.practice-options{display:grid;gap:10px}.practice-options :deep(.el-radio){height:auto;white-space:normal;align-items:flex-start;margin:0}.practice-options :deep(.el-radio__label){white-space:normal;line-height:1.6;overflow-wrap:anywhere}.practice-solution{padding:12px;background:var(--panel);border-radius:8px}
</style>
