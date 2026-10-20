<script setup lang="ts">
import { computed } from 'vue'

export type XiaoZhiState = 'idle' | 'greeting' | 'listening' | 'thinking' | 'searching' | 'working' | 'speaking' | 'success' | 'encouraging' | 'warning' | 'error'

const props = withDefaults(defineProps<{ state?: XiaoZhiState; motion?: boolean; size?: 'small' | 'normal' }>(), {
  state: 'idle',
  motion: true,
  size: 'normal',
})

const expression = computed(() => {
  if (props.state === 'thinking' || props.state === 'working' || props.state === 'searching') return 'focus'
  if (props.state === 'warning' || props.state === 'error') return 'concerned'
  if (props.state === 'success' || props.state === 'encouraging' || props.state === 'greeting') return 'happy'
  return 'calm'
})
</script>

<template>
  <span class="xiaozhi-avatar" :class="[`is-${state}`, `face-${expression}`, `size-${size}`, { 'has-motion': motion }]" role="img" :aria-label="`小智：${state}`">
    <svg viewBox="0 0 120 132" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <linearGradient id="xz-shell" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff"/><stop offset=".6" stop-color="#e7f4ff"/><stop offset="1" stop-color="#9ac7f9"/></linearGradient>
        <linearGradient id="xz-screen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#172c64"/><stop offset="1" stop-color="#244a98"/></linearGradient>
        <linearGradient id="xz-body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7ca9fb"/><stop offset="1" stop-color="#5b56dd"/></linearGradient>
      </defs>
      <ellipse class="xz-shadow" cx="60" cy="124" rx="36" ry="5" fill="#193c77" opacity=".16"/>
      <path class="xz-arm xz-arm-left" d="M29 84 C18 82 16 92 19 101" fill="none" stroke="#6686ea" stroke-width="11" stroke-linecap="round"/>
      <path class="xz-arm xz-arm-right" d="M91 84 C102 82 104 92 101 101" fill="none" stroke="#6686ea" stroke-width="11" stroke-linecap="round"/>
      <rect x="37" y="104" width="16" height="13" rx="6" fill="#6f79df"/><rect x="67" y="104" width="16" height="13" rx="6" fill="#6f79df"/>
      <rect x="31" y="72" width="58" height="41" rx="21" fill="url(#xz-body)" stroke="#d8e4ff" stroke-width="3"/>
      <circle cx="60" cy="91" r="12" fill="#fff" opacity=".18"/><path d="m60 83 2.3 5.3 5.7 2.2-5.7 2.2L60 98l-2.3-5.3-5.7-2.2 5.7-2.2Z" fill="#fff"/>
      <rect x="13" y="36" width="18" height="34" rx="9" fill="#6284e9" stroke="#d6e5ff" stroke-width="3"/>
      <rect x="89" y="36" width="18" height="34" rx="9" fill="#6284e9" stroke="#d6e5ff" stroke-width="3"/>
      <rect x="17" y="41" width="8" height="23" rx="4" fill="#79d5ff" opacity=".9"/><rect x="95" y="41" width="8" height="23" rx="4" fill="#79d5ff" opacity=".9"/>
      <path d="M60 20V10" stroke="#6686ea" stroke-width="5" stroke-linecap="round"/><circle class="xz-antenna" cx="60" cy="8" r="6" fill="#37d4b2"/>
      <rect x="24" y="22" width="72" height="62" rx="25" fill="url(#xz-shell)" stroke="#fff" stroke-width="3"/>
      <rect x="32" y="32" width="56" height="42" rx="17" fill="url(#xz-screen)"/>
      <ellipse class="xz-eye xz-eye-left" cx="48" cy="52" rx="4" ry="7" fill="#a9f4ff"/>
      <ellipse class="xz-eye xz-eye-right" cx="72" cy="52" rx="4" ry="7" fill="#a9f4ff"/>
      <path class="xz-mouth" d="M53 63 Q60 69 67 63" fill="none" stroke="#a9f4ff" stroke-width="2.4" stroke-linecap="round"/>
      <circle cx="39" cy="63" r="3" fill="#f7a4d6" opacity=".55"/><circle cx="81" cy="63" r="3" fill="#f7a4d6" opacity=".55"/>
      <path d="M38 30 Q60 19 82 30" fill="none" stroke="#fff" stroke-width="3" opacity=".7"/>
    </svg>
    <span v-if="state === 'working' || state === 'searching'" class="avatar-spark" aria-hidden="true">✦</span>
  </span>
</template>

<style scoped>
.xiaozhi-avatar { position:relative; display:inline-block; width:86px; height:94px; flex:none; filter:drop-shadow(0 8px 10px rgba(37,64,144,.2)); }
.xiaozhi-avatar.size-small { width:38px; height:42px; }
.xiaozhi-avatar svg { display:block; width:100%; height:100%; overflow:visible; }
.xz-eye,.xz-mouth,.xz-arm,.xz-shadow,.xz-antenna { transform-box:fill-box; transform-origin:center; }
.face-focus .xz-eye { transform:scaleY(.46) scaleX(1.2); }
.face-concerned .xz-eye { transform:rotate(12deg); }
.face-concerned .xz-mouth { transform:scaleY(-.8) translateY(-2px); }
.face-happy .xz-eye { transform:scaleY(.72); }
.face-happy .xz-mouth { transform:scale(1.3,1.25); }
.has-motion.is-speaking .xz-mouth { animation:xz-speak .55s ease-in-out infinite alternate; }
.has-motion:not(.is-working):not(.is-searching) { animation:xz-float 3s ease-in-out infinite; }
.has-motion.face-calm .xz-eye { animation:xz-blink 5s ease-in-out infinite; }
.has-motion.is-greeting .xz-arm-right,.has-motion.is-success .xz-arm-right { animation:xz-wave .8s ease-in-out 2 alternate; }
.has-motion.is-thinking .xz-antenna,.has-motion.is-working .xz-antenna,.has-motion.is-searching .xz-antenna { animation:xz-glow 1.8s ease-in-out infinite; }
.avatar-spark { position:absolute; top:5%; right:4%; color:#67cbff; font-size:22px; }
.has-motion .avatar-spark { animation:xz-glow 1.8s ease-in-out infinite; }
@keyframes xz-float { 50% { transform:translateY(-5px); } }
@keyframes xz-blink { 0%,43%,47%,100% { scale:1 1; } 45% { scale:1 .12; } }
@keyframes xz-wave { to { transform:rotate(-18deg); } }
@keyframes xz-glow { 50% { opacity:.35; filter:drop-shadow(0 0 5px #5debd3); } }
@keyframes xz-speak { to { transform:scaleY(.45); } }
@media (prefers-reduced-motion:reduce) { .xiaozhi-avatar,.xiaozhi-avatar * { animation:none !important; transition:none !important; } }
</style>
