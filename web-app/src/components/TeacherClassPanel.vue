<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { teacherApi, type TeacherClassItem, type ApiEnvelope } from '../api'
const props = defineProps<{ classroom: TeacherClassItem }>()
const emit = defineEmits<{ refresh: [] }>()
const members = ref<{ user_id: number; username: string; joined_at: string }[]>([])
const error = ref(''), busy = ref(false)
const memberOpen = ref(true)
const form = reactive({ name: '', subject: '', teacher_name: '', status: 'active' })
let memberRequest = 0
async function load() {
  const ticket = ++memberRequest
  const classId = props.classroom.id
  error.value = ''; busy.value = true; members.value = []
  try {
    const { data } = await teacherApi.get<ApiEnvelope<typeof members.value>>(`/teacher/classes/${classId}/members`)
    if (ticket === memberRequest) members.value = data.data
  }
  catch (e: any) { if (ticket === memberRequest) error.value = e?.response?.data?.detail || '成员列表加载失败，请重试' }
  finally { if (ticket === memberRequest) busy.value = false }
}
watch(() => props.classroom, c => { Object.assign(form, c); void load() }, { immediate: true })
async function save() {
  busy.value = true
  try { await teacherApi.patch(`/teacher/classes/${props.classroom.id}`, form); emit('refresh'); ElMessage.success('班级信息已保存') }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || '保存失败') }
  finally { busy.value = false }
}
async function rotate() {
  try { await ElMessageBox.confirm('重新生成后旧邀请码立即失效，已加入的学生不受影响。', '更新邀请码') } catch { return }
  try { await teacherApi.post(`/teacher/classes/${props.classroom.id}/invite`); emit('refresh') }
  catch { ElMessage.error('更新邀请码失败') }
}
async function remove(id: number) {
  try { await ElMessageBox.confirm('移出后该学生无法继续读取班级作业和教学范围，原提交与成绩保留。', '移出成员') }
  catch { return }
  try { await teacherApi.delete(`/teacher/classes/${props.classroom.id}/members/${id}`); await load(); emit('refresh') }
  catch { ElMessage.error('移出成员失败') }
}
async function copy() {
  try { await navigator.clipboard.writeText(props.classroom.invite_code || ''); ElMessage.success('邀请码已复制') }
  catch { ElMessage.info('请选中下方邀请码手动复制') }
}
function formatJoined(value: string) {
  return value.replace('T', ' ').replace(/\.\d+$/, '').slice(0, 16)
}
</script>
<template>
  <section v-loading="busy" class="class-detail">
    <h2>班级详情与成员</h2>
    <p>班级编号：{{ classroom.id }} · {{ classroom.student_count }} 名学生 · {{ classroom.assignment_count }} 项作业</p>
    <p>邀请码：<code data-testid="class-invite">{{ classroom.invite_code }}</code></p>
    <div class="action-row"><el-button @click="copy">复制邀请码</el-button><el-button @click="rotate">重新生成邀请码</el-button><el-button @click="emit('refresh')">刷新成员</el-button></div>
    <el-form label-position="top">
      <el-form-item label="修改班级名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="修改学科"><el-input v-model="form.subject" /></el-form-item>
      <el-form-item label="班级状态"><el-select v-model="form.status"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select></el-form-item>
      <el-button @click="save">保存班级信息</el-button>
    </el-form>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-empty v-else-if="!busy && !members.length" description="暂无学生，请分享邀请码让学生加入" />
    <div v-else class="member-box" :class="{ closed: !memberOpen }">
      <button type="button" class="member-box-head" @click="memberOpen = !memberOpen">
        <span>班级成员 · {{ members.length }} 人</span>
        <span class="member-box-arrow" aria-hidden="true">▾</span>
      </button>
      <div v-show="memberOpen" class="member-scroll">
        <div v-for="member in members" :key="member.user_id" class="list-card member-row">
          <strong class="member-name">{{ member.username }}</strong>
          <span class="member-joined">已加入 · {{ formatJoined(member.joined_at) }}</span>
          <el-button class="member-remove" type="danger" plain size="small" @click="remove(member.user_id)">移出</el-button>
        </div>
      </div>
    </div>
  </section>
</template>
<style scoped>
.class-detail{display:grid;gap:14px;margin-bottom:24px}
.class-detail code{overflow-wrap:anywhere;user-select:all}
.class-detail p{margin:0;color:var(--muted)}
.member-box{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:color-mix(in srgb, var(--panel) 60%, transparent)}
.member-box-head{display:flex;align-items:center;justify-content:space-between;width:100%;padding:10px 14px;border:none;background:transparent;font:inherit;font-weight:600;color:var(--text);cursor:pointer;user-select:none}
.member-box-head:hover{background:color-mix(in srgb, var(--accent) 8%, transparent)}
.member-box-arrow{display:inline-block;transition:transform .2s ease;color:var(--muted);font-size:14px}
.member-box.closed .member-box-arrow{transform:rotate(-90deg)}
.member-scroll{display:grid;gap:8px;padding:10px 12px 12px;max-height:320px;overflow-y:auto}
.member-row{display:flex;align-items:center;gap:12px;padding:8px 14px;border-radius:12px;cursor:default}
.member-name{flex:none;min-width:88px}
.member-joined{flex:1;min-width:0;font-size:13px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.member-remove{flex:none;margin-left:auto}
</style>
