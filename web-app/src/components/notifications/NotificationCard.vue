<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Bell, ArrowDown } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useNotifications, type Notice } from '../../stores/notifications'
import NotificationItem from './NotificationItem.vue'
import NotificationDetail from './NotificationDetail.vue'
const auth=useAuthStore(), store=useNotifications(), router=useRouter(), route=useRoute()
const root=ref<HTMLElement>(), trigger=ref<HTMLButtonElement>(), open=ref(false), items=ref<Notice[]>([]), loading=ref(false), error=ref('')
const detail=ref<InstanceType<typeof NotificationDetail>>()
const center=computed(()=>`/${auth.user?.role === 'teacher'?'teacher':auth.user?.role === 'admin'?'admin':'student'}/notifications`)
let timer:ReturnType<typeof setTimeout>|undefined, stopped=false, delay=15000, fetching=false, epoch=0
async function load() { const ticket=epoch; loading.value=true; error.value=''; try { const result=await store.list(); if(ticket===epoch)items.value=result.items } catch{if(ticket===epoch){items.value=[];error.value='消息加载失败，点击重试'}} finally{if(ticket===epoch)loading.value=false} }
async function poll() { if(stopped||fetching)return; fetching=true; try{if(auth.token && navigator.onLine && !document.hidden){await store.count();if(open.value)await load()}delay=15000}catch{delay=Math.min(delay*2,120000);error.value='通知同步暂不可用，将自动重试'}finally{fetching=false;if(!stopped)timer=setTimeout(poll,delay)} }
function wake(){if(timer)clearTimeout(timer);if(!fetching)void poll()}
async function toggle(){open.value=!open.value;if(open.value){await load();await nextTick();root.value?.querySelector<HTMLElement>('.notification-panel button')?.focus()}}
function outside(event:PointerEvent){if(!root.value?.contains(event.target as Node))open.value=false}
function key(event:KeyboardEvent){if(event.key==='Escape'&&open.value){open.value=false;trigger.value?.focus()}}
async function all(){try{await store.readAll();await load()}catch{error.value='标记失败，请重试'}}
function sync(event:StorageEvent){if(event.key==='notification-sync')wake()}
watch(()=>route.fullPath,()=>{open.value=false})
watch(()=>auth.token,()=>{epoch++;open.value=false;items.value=[];store.reset();wake()})
watch(()=>store.revision,()=>{if(open.value)void load()})
onMounted(()=>{store.reset();void poll();document.addEventListener('pointerdown',outside);document.addEventListener('keydown',key);document.addEventListener('visibilitychange',wake);window.addEventListener('online',wake);window.addEventListener('storage',sync)})
onUnmounted(()=>{stopped=true;epoch++;if(timer)clearTimeout(timer);document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',key);document.removeEventListener('visibilitychange',wake);window.removeEventListener('online',wake);window.removeEventListener('storage',sync)})
</script>
<template><div ref="root" class="notification-card"><button ref="trigger" class="notification-trigger" type="button" :aria-expanded="open" aria-controls="notification-panel" @click="toggle"><el-icon><Bell /></el-icon><span>消息通知<small>{{ store.unread ? `您有 ${store.unread} 条未读消息` : '查看最新通知' }}</small></span><b v-if="store.unread" aria-live="polite">{{ store.unread>99?'99+':store.unread }}</b><el-icon><ArrowDown /></el-icon></button><Transition name="notice"><section v-if="open" id="notification-panel" class="notification-panel" aria-label="消息通知"><header><strong>消息通知 · {{ store.unread }} 未读</strong><button type="button" @click="all">全部已读</button></header><p v-if="loading" role="status">正在加载…</p><button v-if="error" class="retry" type="button" @click="load">{{ error }}</button><div class="notification-list"><NotificationItem v-for="item in items" :key="item.id" :item="item" @select="detail?.show($event)"/><p v-if="!loading&&!error&&!items.length">暂无消息</p></div><footer><button type="button" @click="open=false;router.push(center)">查看全部消息</button></footer></section></Transition><NotificationDetail ref="detail" /></div></template>
<style scoped>
.notification-card{position:relative;flex-shrink:0}.notification-trigger{display:flex;align-items:center;gap:9px;min-height:44px;padding:7px 11px;border:1px solid var(--line);border-radius:12px;background:var(--panel);color:var(--text);cursor:pointer;text-align:left;font-size:12px}.notification-trigger small{display:block;font-size:10px;color:var(--muted);margin-top:3px}.notification-trigger b{background:#dc3c50;color:white;border-radius:12px;padding:2px 6px;font-size:11px}.notification-panel{position:absolute;right:0;top:calc(100% + 10px);width:390px;max-width:calc(100vw - 28px);border:1px solid var(--line);border-radius:16px;background:var(--panel-strong);box-shadow:var(--shadow);overflow:hidden}.notification-panel header,.notification-panel footer{display:flex;justify-content:space-between;padding:14px;align-items:center;gap:10px}.notification-panel button:not(.notification-item){color:var(--accent);background:transparent;border:0;cursor:pointer;font-size:12px}.notification-list{max-height:min(440px,calc(100dvh - 240px));overflow:auto}.notification-panel p{padding:16px;color:var(--muted)}.notice-enter-active,.notice-leave-active{transition:opacity .15s,transform .15s}.notice-enter-from,.notice-leave-to{opacity:0;transform:translateY(-6px)}button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}@media(max-width:650px){.notification-trigger small,.notification-trigger>.el-icon:last-child{display:none}.notification-trigger{gap:5px;padding:8px}.notification-panel{position:fixed;right:14px;top:72px;width:min(390px,calc(100vw - 28px))}}@media(prefers-reduced-motion:reduce){.notice-enter-active,.notice-leave-active{transition:none}}
</style>
