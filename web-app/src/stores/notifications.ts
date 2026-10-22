import { defineStore } from 'pinia'
import { ref } from 'vue'
import { teacherApi } from '../api/http'
export interface Notice { id:number; title:string; content:string; type:string; related_type:string; related_id:number|null; is_read:boolean; created_at:string; sender_name:string; target_path?:string|null; discussion?:{id:number;title:string;content:string;replies:Array<{id:number;author_name:string;content:string}>} }
export const useNotifications = defineStore('notifications', () => {
  let generation = 0
  const unread = ref(0)
  const revision = ref(0)
  async function count() { const ticket=generation; const {data} = await teacherApi.get('/learning/notifications/unread-count', {timeout:10000}); if(ticket===generation){if(unread.value!==data.data.unread_count)revision.value++; unread.value = data.data.unread_count} }
  async function list(page=1, size=8, onlyUnread=false) { const ticket=generation; const {data} = await teacherApi.get('/learning/notifications/inbox', {params:{page,size,unread:onlyUnread},timeout:10000}); if(ticket!==generation)throw new Error("Account changed"); unread.value=data.data.unread_count; return data.data as {items:Notice[];total:number;unread_count:number} }
  function changed() { revision.value++; localStorage.setItem('notification-sync', String(Date.now())) }
  async function read(item:Notice) { await teacherApi.patch(`/learning/notifications/${item.id}/read`); changed(); await count() }
  async function readAll() { await teacherApi.post('/learning/notifications/read-all'); unread.value=0; changed() }
  async function detail(id:number):Promise<Notice> { const {data} = await teacherApi.get(`/learning/notifications/${id}/detail`); return data.data }
  function reset() { generation++; unread.value=0; revision.value++ }
  return {unread,revision,count,list,read,readAll,detail,reset}
})
