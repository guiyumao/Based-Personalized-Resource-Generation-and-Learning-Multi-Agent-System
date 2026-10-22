<script setup lang="ts">
import type { Notice } from '../../stores/notifications'
defineProps<{item:Notice}>()
defineEmits<{select:[item:Notice]}>()
const labels:Record<string,string> = {assignment:'新作业', review:'批改结果', submission:'作业提交', class:'班级',discussion:'讨论',announcement:'公告',maintenance:'系统维护',account:'账号',course:'课程',task:'学习任务'}
function time(value:string) { return new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value+'Z').toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}) }
</script>
<template><button class="notification-item" :class="{unread:!item.is_read}" type="button" @click="$emit('select',item)"><span class="meta">{{ labels[item.type] || '通知' }} · {{ item.sender_name || '系统通知' }}<i v-if="!item.is_read" aria-label="未读" /></span><strong>{{ item.title }}</strong><span class="summary">{{ item.content }}</span><time>{{ time(item.created_at) }}</time></button></template>
<style scoped>
.notification-item{display:grid;gap:6px;width:100%;padding:14px;text-align:left;border:0;border-bottom:1px solid var(--line);background:var(--panel);color:var(--text);cursor:pointer;overflow-wrap:anywhere}.notification-item:hover,.notification-item.unread{background:var(--accent-soft)}.meta,time{font-size:11px;color:var(--muted)}strong{font-size:14px}.summary{font-size:12px;line-height:1.6;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-left:8px}
</style>
