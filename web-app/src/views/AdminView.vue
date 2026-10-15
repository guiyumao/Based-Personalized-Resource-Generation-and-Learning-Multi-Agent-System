<script setup lang="ts">
import { computed, onMounted, reactive, ref, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Collection, Key, Setting, Tickets } from '@element-plus/icons-vue'

import {
  systemApi,
  type ApiEnvelope,
  type AuditLogItem,
  type RoleAssignmentPayload,
  type SubjectCreatePayload,
  type SubjectItem,
  type SystemConfigItem,
  type SystemConfigUpdatePayload,
} from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const subjects = ref<SubjectItem[]>([])
const configs = ref<SystemConfigItem[]>([])
const logs = ref<AuditLogItem[]>([])
const selectedConfigKey = ref('resource_generation_timeout')

const roleForm = reactive<RoleAssignmentPayload>({
  user_id: 1,
  role: 'teacher',
})

const subjectForm = reactive<SubjectCreatePayload>({
  name: '离散数学',
  description: '逻辑、集合、图论基础',
})

const configForm = reactive<SystemConfigUpdatePayload>({
  value: '20',
})

const logFilter = ref('')
const roleResult = ref<Record<string, unknown> | null>(null)

const loading = reactive({
  role: false,
  subjects: false,
  createSubject: false,
  configs: false,
  updateConfig: false,
  logs: false,
})

const configKeys = computed(() => configs.value.map((item) => item.key))
const visibleLogs = computed(() => logs.value)
const adminStats = computed<{ label: string; value: number; icon: Component; hint: string }[]>(() => [
  { label: '学科数量', value: subjects.value.length, icon: Collection, hint: '当前已配置学科' },
  { label: '系统配置', value: configs.value.length, icon: Setting, hint: '可在线维护参数' },
  { label: '审计记录', value: logs.value.length, icon: Tickets, hint: '当前筛选范围' },
  { label: '角色管理', value: 3, icon: Key, hint: '学生、教师、管理员' },
])

async function assignRole() {
  loading.role = true
  try {
    const { data } = await systemApi.post<ApiEnvelope<Record<string, unknown>>>('/system/roles/assign', roleForm)
    roleResult.value = data.data
    ElMessage.success('角色分配成功')
    await fetchLogs()
  } catch {
    ElMessage.error('角色分配失败')
  } finally {
    loading.role = false
  }
}

async function fetchSubjects() {
  loading.subjects = true
  try {
    const { data } = await systemApi.get<ApiEnvelope<SubjectItem[]>>('/system/subjects')
    subjects.value = data.data
  } catch {
    ElMessage.error('学科列表获取失败')
  } finally {
    loading.subjects = false
  }
}

async function createSubject() {
  loading.createSubject = true
  try {
    const { data } = await systemApi.post<ApiEnvelope<SubjectItem>>('/system/subjects', subjectForm)
    subjects.value.push(data.data)
    ElMessage.success('学科创建成功')
    await fetchLogs()
  } catch {
    ElMessage.error('学科创建失败')
  } finally {
    loading.createSubject = false
  }
}

async function fetchConfigs() {
  loading.configs = true
  try {
    const { data } = await systemApi.get<ApiEnvelope<SystemConfigItem[]>>('/system/configs')
    configs.value = data.data
    if (configs.value.length > 0 && !configKeys.value.includes(selectedConfigKey.value)) {
      selectedConfigKey.value = configs.value[0].key
      configForm.value = configs.value[0].value
    }
  } catch {
    ElMessage.error('系统配置获取失败')
  } finally {
    loading.configs = false
  }
}

function syncSelectedConfigValue() {
  const current = configs.value.find((item) => item.key === selectedConfigKey.value)
  configForm.value = current?.value ?? ''
}

async function updateConfig() {
  loading.updateConfig = true
  try {
    const { data } = await systemApi.put<ApiEnvelope<SystemConfigItem>>(
      `/system/configs/${selectedConfigKey.value}`,
      configForm,
    )
    const targetIndex = configs.value.findIndex((item) => item.key === data.data.key)
    if (targetIndex >= 0) {
      configs.value[targetIndex] = data.data
    } else {
      configs.value.push(data.data)
    }
    ElMessage.success('系统配置更新成功')
    await fetchLogs()
  } catch {
    ElMessage.error('系统配置更新失败')
  } finally {
    loading.updateConfig = false
  }
}

async function fetchLogs() {
  loading.logs = true
  try {
    const query = logFilter.value ? `?level=${encodeURIComponent(logFilter.value)}` : ''
    const { data } = await systemApi.get<ApiEnvelope<AuditLogItem[]>>(`/system/logs${query}`)
    logs.value = data.data
  } catch {
    ElMessage.error('日志获取失败')
  } finally {
    loading.logs = false
  }
}

async function logout() {
  authStore.clear()
  ElMessage.success('已退出登录')
  await router.push({ name: 'login' })
}

onMounted(async () => {
  await fetchSubjects()
  await fetchConfigs()
  syncSelectedConfigValue()
  await fetchLogs()
})
</script>

<template>
  <div class="role-shell">
    <div class="role-card large">
      <header class="console-hero">
        <div>
          <div class="login-kicker">SYSTEM ADMINISTRATION</div>
          <h1>管理控制台</h1>
          <p>统一管理角色、学科、系统配置与审计日志，所有操作继续使用现有系统服务接口。</p>
        </div>
        <div class="role-meta"><span>{{ authStore.user?.username }}</span><span>管理员</span></div>
      </header>

      <section class="admin-stat-grid">
        <article v-for="item in adminStats" :key="item.label">
          <span><component :is="item.icon" /></span>
          <div><small>{{ item.label }}</small><strong>{{ item.value }}</strong><p>{{ item.hint }}</p></div>
        </article>
      </section>

      <div class="workspace-grid teacher-grid">
        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">角色管理</div>
              <h2>用户角色分配</h2>
            </div>
          </div>
          <el-form :model="roleForm" label-position="top">
            <el-form-item label="用户 ID">
              <el-input-number v-model="roleForm.user_id" :min="1" />
            </el-form-item>
            <el-form-item label="目标角色">
              <el-select v-model="roleForm.role">
                <el-option label="student" value="student" />
                <el-option label="teacher" value="teacher" />
                <el-option label="admin" value="admin" />
              </el-select>
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="primary" :loading="loading.role" @click="assignRole">分配角色</el-button>
            <el-button plain @click="logout">退出登录</el-button>
          </div>
          <pre v-if="roleResult" class="result-box">{{ JSON.stringify(roleResult, null, 2) }}</pre>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">学科管理</div>
              <h2>新增并查看学科</h2>
            </div>
          </div>
          <el-form :model="subjectForm" label-position="top">
            <el-form-item label="学科名称">
              <el-input v-model="subjectForm.name" />
            </el-form-item>
            <el-form-item label="学科描述">
              <el-input v-model="subjectForm.description" type="textarea" :rows="3" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="success" :loading="loading.createSubject" @click="createSubject">新增学科</el-button>
            <el-button :loading="loading.subjects" @click="fetchSubjects">刷新学科</el-button>
          </div>
          <div class="list-stack">
            <div v-for="item in subjects" :key="item.id" class="list-card static">
              <strong>{{ item.name }}</strong>
              <span>{{ item.description }}</span>
            </div>
            <div v-if="loading.subjects" class="empty-state">正在加载学科...</div>
            <div v-else-if="!subjects.length" class="empty-state">暂无学科，可使用上方表单新增。</div>
          </div>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">系统配置</div>
              <h2>关键参数维护</h2>
            </div>
          </div>
          <el-form label-position="top">
            <el-form-item label="配置键">
              <el-select v-model="selectedConfigKey" @change="syncSelectedConfigValue">
                <el-option v-for="item in configs" :key="item.key" :label="item.key" :value="item.key" />
              </el-select>
            </el-form-item>
            <el-form-item label="配置值">
              <el-input v-model="configForm.value" />
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="warning" :loading="loading.updateConfig" @click="updateConfig">更新配置</el-button>
            <el-button :loading="loading.configs" @click="fetchConfigs">刷新配置</el-button>
          </div>
          <div class="list-stack">
            <div v-for="item in configs" :key="item.key" class="list-card static">
              <strong>{{ item.key }}</strong>
              <span>{{ item.value }}</span>
            </div>
            <div v-if="loading.configs" class="empty-state">正在加载配置...</div>
            <div v-else-if="!configs.length" class="empty-state">暂无可维护的系统配置。</div>
          </div>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">审计日志</div>
              <h2>系统操作记录</h2>
            </div>
          </div>
          <div class="action-row">
            <el-select v-model="logFilter" placeholder="全部级别" style="max-width: 180px">
              <el-option label="全部级别" value="" />
              <el-option label="INFO" value="INFO" />
              <el-option label="WARN" value="WARN" />
            </el-select>
            <el-button :loading="loading.logs" @click="fetchLogs">刷新日志</el-button>
          </div>
          <div class="list-stack">
            <div v-for="item in visibleLogs" :key="`${item.level}-${item.event}-${item.message}`" class="list-card static">
              <strong>{{ item.level }} / {{ item.event }}</strong>
              <span>{{ item.message }}</span>
            </div>
            <div v-if="loading.logs" class="empty-state">正在加载审计日志...</div>
            <div v-else-if="!visibleLogs.length" class="empty-state">当前筛选条件下暂无审计记录。</div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.console-hero { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin-bottom:20px; padding:28px; border:1px solid color-mix(in srgb,var(--accent) 16%,var(--line)); border-radius:18px; background:linear-gradient(135deg,var(--panel),color-mix(in srgb,var(--accent) 7%,var(--panel))); box-shadow:var(--shadow-soft); }
.console-hero h1 { margin:8px 0 7px; color:var(--text); font-size:32px; letter-spacing:-.04em; }.console-hero p { max-width:760px; margin:0; color:var(--muted); line-height:1.75; }.role-meta { display:flex; flex-wrap:wrap; gap:7px; }.role-meta span { padding:7px 10px; border-radius:8px; color:var(--accent); background:var(--accent-soft); font-size:11px; font-weight:700; }
.admin-stat-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:20px; }.admin-stat-grid article { display:grid; grid-template-columns:42px 1fr; gap:13px; padding:18px; border:1px solid var(--line); border-radius:15px; background:var(--panel); box-shadow:var(--shadow-soft); }.admin-stat-grid article > span { width:42px; height:42px; display:grid; place-items:center; border-radius:11px; color:var(--accent); background:var(--accent-soft); }.admin-stat-grid small,.admin-stat-grid strong,.admin-stat-grid p { display:block; }.admin-stat-grid small { color:var(--muted); font-size:11px; }.admin-stat-grid strong { margin-top:2px; color:var(--text); font-size:24px; }.admin-stat-grid p { margin:3px 0 0; color:var(--muted); font-size:10px; }
:deep(.workspace-grid) { margin-top:0; align-items:start; }:deep(.workspace-panel) { min-height:420px; }
@media (max-width:1100px) { .admin-stat-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media (max-width:680px) { .console-hero { align-items:flex-start; flex-direction:column; padding:21px; }.admin-stat-grid { grid-template-columns:1fr; } }
</style>
