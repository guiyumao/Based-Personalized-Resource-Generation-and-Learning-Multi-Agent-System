<script setup lang="ts">
/**
 * 全局学习内容渲染器（Markdown + KaTeX 的唯一入口）。
 *
 * 任何由模型生成或用户录入的学习正文（题干、选项、答案、解析、总结、笔记、
 * 报告段落）都必须走这个组件，而不是 `{{ }}` 普通文本插值，否则 `$...$` /
 * `\(...\)` / `\[...\]` 公式会以源码形式显示。
 *
 * 样式统一由 `src/styles.css` 中的 `.learning-markdown` 规则提供，本组件不带
 * 私有样式，保证错题本 / 收藏本 / 练习 / 课件 / 笔记各处的排版一致。
 *
 * 注意：渲染结果来自 `renderLearningMarkdown`，其 HTML 已禁用（`html: false`）
 * 且 KaTeX 关闭 trust，因此 v-html 只可能输出受控的 Markdown/公式标记。
 */
import { computed } from 'vue'
import { renderLearningMarkdown } from '../utils/renderLearningMarkdown'

const props = withDefaults(
  defineProps<{
    /** 原始内容；空值时按 empty 兜底。 */
    content?: string | number | null | undefined
    /** 行内渲染（不产生 <p>），用于选项、标签、答案短文本。 */
    inline?: boolean
    /** 渲染容器标签，默认 div。 */
    tag?: string
    /** 内容为空时显示的占位文案；为空则不渲染节点。 */
    empty?: string
    /** 预览行数，>0 时超出折叠（视觉截断，不会切断公式源码）。 */
    clampLines?: number
  }>(),
  { content: '', inline: false, tag: 'div', empty: '', clampLines: 0 },
)

const text = computed(() => (props.content === null || props.content === undefined ? '' : String(props.content)))
const html = computed(() => {
  const value = text.value
  if (!value.trim()) return ''
  return props.inline ? renderLearningMarkdown(value, true) : renderLearningMarkdown(value)
})
const clampStyle = computed(() =>
  props.clampLines > 0 ? { '-webkit-line-clamp': String(props.clampLines) } : undefined,
)
const isEmpty = computed(() => !html.value)
</script>

<template>
  <component
    :is="tag"
    v-if="!isEmpty"
    class="learning-content learning-markdown"
    :class="{ 'is-inline': inline, 'is-clamped': clampLines > 0 }"
    :style="clampStyle"
    v-html="html"
  />
  <component :is="tag" v-else-if="empty" class="learning-content learning-content-empty">{{ empty }}</component>
</template>
