<script setup lang="ts">
import { ref } from 'vue'
import { teacherApi } from '../../api/http'
import { useRouter } from 'vue-router'
import { useNotifications, type Notice } from '../../stores/notifications'
const store=useNotifications(), router=useRouter()
const reply=ref('')
const selected=ref<Notice|null>(null), error=ref(''), busy=ref(false)
async function show(item:Notice) { reply.value=''; busy.value=true; error.value=''; try { const detail=await store.detail(item.id); await store.read(item); selected.value=detail } catch(e:any){error.value=e?.response?.data?.detail || '消息加载失败，请重试'} finally{busy.value=false} }
async function go() { const path=selected.value?.target_path; if(path && /^\/(student|teacher|admin)\//.test(path) && !path.includes('://')) {selected.value=null; await router.push(path)} }
async function sendReply(){if(!selected.value?.discussion||!reply.value.trim())return;busy.value=true;try{await teacherApi.post(`/learning/discussions/${selected.value.discussion.id}/replies`,{content:reply.value});selected.value=await store.detail(selected.value.id);reply.value=''}catch(e:any){error.value=e?.response?.data?.detail||'回复失败，请重试'}finally{busy.value=false}}
defineExpose({show})
</script>
<template><p v-if="error && !selected" role="alert">{{ error }}</p><p v-if="busy" role="status">正在读取消息…</p><el-dialog :model-value="!!selected" title="消息详情" width="min(560px, calc(100vw - 28px))" append-to-body @close="selected=null"><template v-if="selected"><p v-if="error" role="alert">{{ error }}</p><h3>{{ selected.title }}</h3><small>{{ selected.sender_name }}</small><p class="body">{{ selected.content }}</p><section v-if="selected.discussion"><p v-for="entry in selected.discussion.replies" :key="entry.id" class="body"><strong>{{ entry.author_name }}</strong>：{{ entry.content }}</p><el-input v-model="reply" type="textarea" :rows="3" placeholder="回复课程讨论" maxlength="4000"/><el-button :loading="busy" :disabled="!reply.trim()" @click="sendReply">发送回复</el-button></section><el-button v-if="selected.target_path" type="primary" @click="go">前往关联业务</el-button></template></el-dialog></template>
<style scoped>.body{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}</style>
