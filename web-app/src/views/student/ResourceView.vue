<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { resourceApi } from '../../api'

interface ResourceItem {
  id: number; title: string; type: string; format: string; status: string
  knowledge_point: string; owner_user_id?: number | null
}

const resources = ref<ResourceItem[]>([])
const loading = ref(false)
const error = ref('')
const selected = ref<ResourceItem | null>(null)
const showDetail = ref(false)

async function fetchResources() {
  loading.value = true; error.value = ''
  try {
    const { data } = await resourceApi.get('/resources')
    resources.value = (data as any).data ?? (Array.isArray(data) ? data : [])
  } catch (e: any) {
    const detail = e?.response?.data?.detail ?? e?.message ?? '未知错误'
    error.value = `加载失败：${detail}`
  } finally { loading.value = false }
}

function openDetail(r: ResourceItem) {
  selected.value = r; showDetail.value = true
}

async function exportResource(r: ResourceItem, format: 'pdf' | 'word') {
  try {
    await resourceApi.post(`/resources/${r.id}/export`, { export_format: format })
    ElMessage.success(`已发起 ${format.toUpperCase()} 导出`)
  } catch (e: any) {
    ElMessage.error('导出失败')
  }
}

async function updateStatus(r: ResourceItem, status: 'draft' | 'ready' | 'archived') {
  try {
    await resourceApi.patch(`/resources/${r.id}/status`, { status })
    r.status = status
    ElMessage.success('状态已更新')
  } catch (e: any) {
    ElMessage.error('状态更新失败')
  }
}

const typeLabel: Record<string, string> = { courseware: '课件', exercise: '练习', notes: '笔记', exam: '试卷' }
const statusLabel: Record<string, string> = { draft: '草稿', ready: '就绪', archived: '归档' }
const statusNext: Record<string, string> = { draft: 'ready', ready: 'archived', archived: 'draft' }

onMounted(fetchResources)
</script>

<template>
  <div>
    <div style="margin-bottom:24px;display:flex;justify-content:space-between;align-items:center">
      <div>
        <h2 style="font-size:24px;font-weight:750">📁 学习资源</h2>
        <p style="color:var(--muted);font-size:14px">管理课件、练习、笔记等学习资源</p>
      </div>
      <button :disabled="loading" @click="fetchResources"
        style="padding:10px 20px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--text);cursor:pointer;font-weight:600;font-family:inherit">
        {{ loading ? '加载中...' : '刷新' }}
      </button>
    </div>

    <div v-if="error" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:16px;font-size:14px">{{ error }}</div>

    <!-- Resource cards grid -->
    <div v-if="resources.length" style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
      <div v-for="r in resources" :key="r.id"
        style="padding:20px;border-radius:18px;background:var(--panel);border:1px solid var(--line);cursor:pointer;transition:all .2s"
        @click="openDetail(r)"
        @mouseenter="(e:any) => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.transform = 'translateY(-2px)' }"
        @mouseleave="(e:any) => { e.currentTarget.style.borderColor = 'var(--line)'; e.currentTarget.style.transform = '' }">
        <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:10px">
          <span style="padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent)">{{ typeLabel[r.type] ?? r.type }}</span>
          <span style="padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600"
            :style="r.status==='ready'?{background:'color-mix(in srgb,var(--green) 10%,transparent)',color:'var(--green)'}:r.status==='draft'?{background:'color-mix(in srgb,var(--muted) 10%,transparent)',color:'var(--muted)'}:{background:'color-mix(in srgb,var(--accent-deep) 10%,transparent)',color:'var(--accent-deep)'}">
            {{ statusLabel[r.status] ?? r.status }}
          </span>
        </div>
        <h4 style="margin:0 0 6px;font-size:15px">{{ r.title }}</h4>
        <div style="font-size:12px;color:var(--muted);display:flex;gap:12px">
          <span>{{ r.knowledge_point }}</span>
          <span>{{ r.format }}</span>
        </div>
      </div>
    </div>
    <div v-else-if="!loading && !error" style="text-align:center;padding:60px;color:var(--muted);border-radius:18px;background:var(--panel);border:1px solid var(--line)">
      暂无学习资源
    </div>

    <!-- Detail overlay -->
    <div v-if="showDetail && selected" style="position:fixed;inset:0;z-index:200;background:rgba(0,0,0,.5);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center"
      @click.self="showDetail = false">
      <div style="background:var(--panel-strong);border:1px solid var(--line);border-radius:20px;padding:28px;width:min(92vw,520px);box-shadow:0 40px 100px rgba(0,0,0,.5)">
        <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:16px">
          <div>
            <span style="padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent);margin-right:8px">{{ typeLabel[selected.type] ?? selected.type }}</span>
            <span style="padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent)">{{ selected.format }}</span>
          </div>
          <button @click="showDetail = false" style="background:none;border:none;font-size:20px;cursor:pointer;color:var(--muted)">✕</button>
        </div>
        <h3 style="margin:0 0 8px;font-size:20px">{{ selected.title }}</h3>
        <div style="font-size:14px;color:var(--muted);margin-bottom:20px">
          <div>知识点：{{ selected.knowledge_point }}</div>
          <div style="margin-top:4px">状态：{{ statusLabel[selected.status] ?? selected.status }}
            <button @click="updateStatus(selected, statusNext[selected.status] as any)"
              style="margin-left:8px;padding:2px 10px;border-radius:999px;border:1px solid var(--line);background:var(--panel);color:var(--text);cursor:pointer;font-size:11px;font-family:inherit">
              切换为 {{ statusLabel[statusNext[selected.status]] ?? statusNext[selected.status] }}
            </button>
          </div>
        </div>
        <div style="display:flex;gap:10px">
          <button @click="exportResource(selected, 'pdf')"
            style="padding:10px 20px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--text);cursor:pointer;font-weight:600;font-family:inherit">
            导出 PDF
          </button>
          <button @click="exportResource(selected, 'word')"
            style="padding:10px 20px;border-radius:12px;border:1px solid var(--line);background:var(--panel);color:var(--text);cursor:pointer;font-weight:600;font-family:inherit">
            导出 Word
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
