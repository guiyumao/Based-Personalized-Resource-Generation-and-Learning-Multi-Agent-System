<script setup lang="ts">
import { useTheme, type ThemeName } from '../composables/useTheme'

const { currentTheme, setTheme } = useTheme()
const themes: { key: ThemeName; label: string; color: string }[] = [
  { key: null, label: '靛蓝云台', color: '#4f46e5' },
  { key: 'ocean', label: '深海科技', color: '#00b8a0' },
  { key: 'warm', label: '暖金学术', color: '#e8924a' },
  { key: 'cosmic', label: '暗夜紫穹', color: '#a78bfa' },
  { key: 'minimal', label: '极简晨光', color: '#2563eb' },
  { key: 'forest', label: '森林绿洲', color: '#48c884' },
]
</script>

<template>
  <div class="theme-picker" role="group" aria-label="外观主题">
    <span>外观</span>
    <button v-for="theme in themes" :key="theme.label" type="button"
      :title="theme.label" :aria-label="`切换到${theme.label}`" :aria-pressed="currentTheme === theme.key"
      :style="{ '--swatch': theme.color }" @click="setTheme(theme.key)">
      <i aria-hidden="true"></i>
    </button>
  </div>
</template>

<style scoped>
.theme-picker { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 3px; width: fit-content; padding: 6px 9px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel-strong); }
.theme-picker > span { margin-right: 6px; font-size: 11px; color: var(--muted); }
.theme-picker button { display: grid; place-items: center; width: 26px; height: 26px; padding: 3px; border: 1px solid transparent; border-radius: 50%; background: transparent; cursor: pointer; }
.theme-picker button i { display: block; width: 15px; height: 15px; border-radius: 50%; background: var(--swatch); }
.theme-picker button[aria-pressed="true"] { border-color: var(--text); }
.theme-picker button:hover { background: var(--surface-muted); }
.theme-picker button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
