<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentApi, type GraphVisualizationResponse, type LearningPathResponse } from '../../api'
import { DataSet, Network } from 'vis-network/standalone'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const user = authStore.user!
const COURSEWARE_STORAGE_KEY = 'student-workspace-courseware'

type StoredCoursewareSnapshot = {
  topic?: string
}

const knowledgePoint = ref('')
const knowledgeSource = ref('')
const loading = ref(false)
const graphVisualization = ref<GraphVisualizationResponse | null>(null)
const dependencyPaths = ref<string[][]>([])
const relatedResources = ref<any[]>([])
const graphError = ref('')
const canvasRef = ref<HTMLDivElement | null>(null)
let network: Network | null = null

const categoryColors: Record<string, string> = {
  current: '#00c8aa', prerequisite: '#4da3e0', recommended: '#a78bfa', resource: '#7b90a8',
}
const categoryLabels: Record<string, string> = {
  current: '当前主题',
  prerequisite: '前置基础',
  recommended: '后续模块',
  resource: '关联资源',
}
const hasKnowledgePoint = computed(() => Boolean(knowledgePoint.value.trim()))
const graphNodes = computed(() => graphVisualization.value?.nodes ?? [])
const graphEdges = computed(() => graphVisualization.value?.edges ?? [])
const categoryStats = computed(() => {
  const stats: Record<string, number> = {}
  for (const node of graphNodes.value as any[]) {
    stats[node.category] = (stats[node.category] ?? 0) + 1
  }
  return stats
})
const groupedNodes = computed(() => {
  const groups: Record<string, any[]> = {
    prerequisite: [],
    recommended: [],
    resource: [],
  }
  for (const node of graphNodes.value as any[]) {
    if (groups[node.category]) {
      groups[node.category].push(node)
    }
  }
  return groups
})
const coreSequence = computed(() => {
  const edges = graphEdges.value as any[]
  const nodesById = new Map((graphNodes.value as any[]).map((node: any) => [node.id, node]))
  return edges
    .filter((edge: any) => ['核心顺序', 'RECOMMENDS'].includes(edge.label))
    .map((edge: any) => nodesById.get(edge.target))
    .filter(Boolean)
})
const graphSummary = computed(() => {
  if (!graphVisualization.value) {
    return []
  }
  return [
    { label: '节点', value: graphNodes.value.length, color: 'var(--accent)' },
    { label: '关系', value: graphEdges.value.length, color: 'var(--accent)' },
    { label: '前置基础', value: categoryStats.value.prerequisite ?? 0, color: '#4da3e0' },
    { label: '后续模块', value: categoryStats.value.recommended ?? 0, color: '#a78bfa' },
  ]
})

onMounted(() => {
  void loadExistingKnowledgePoint()
})

async function loadExistingKnowledgePoint() {
  const stored = readCoursewareSnapshot()
  if (stored?.topic?.trim()) {
    applyKnowledgePoint(stored.topic, '来自已生成课件')
    return
  }

  try {
    const { data } = await agentApi.get<LearningPathResponse>(`/paths/${user.userId}`)
    if (data?.knowledge_point?.trim()) {
      applyKnowledgePoint(data.knowledge_point, '来自当前学习路径')
    }
  } catch {
    knowledgeSource.value = ''
  }
}

function readCoursewareSnapshot(): StoredCoursewareSnapshot | null {
  if (typeof window === 'undefined') {
    return null
  }
  try {
    const raw = window.sessionStorage.getItem(COURSEWARE_STORAGE_KEY)
    return raw ? JSON.parse(raw) as StoredCoursewareSnapshot : null
  } catch {
    return null
  }
}

function applyKnowledgePoint(nextKnowledgePoint: string, source: string) {
  knowledgePoint.value = nextKnowledgePoint.trim()
  knowledgeSource.value = source
}

async function queryGraph() {
  if (!knowledgePoint.value.trim()) {
    await loadExistingKnowledgePoint()
  }
  if (!knowledgePoint.value.trim()) { ElMessage.warning('请先生成学习路径或课件'); return }
  loading.value = true; graphError.value = ''; graphVisualization.value = null; dependencyPaths.value = []
  try {
    const payload = { knowledge_point: knowledgePoint.value, max_depth: 3 }
    const [depRes, visRes] = await Promise.all([
      agentApi.post<{ paths?: string[][]; dependencies?: Array<{ path?: string[] }> }>('/graph/dependencies', payload),
      agentApi.post<GraphVisualizationResponse>('/graph/visualization', payload),
    ])
    graphVisualization.value = (visRes.data as any).data ?? visRes.data
    const depData = (depRes.data as any).data ?? depRes.data
    dependencyPaths.value = Array.isArray(depData?.paths)
      ? depData.paths
      : Array.isArray(depData?.dependencies)
        ? depData.dependencies.map((item: any) => item?.path ?? []).filter((item: string[]) => item.length > 0)
        : []
    ElMessage.success('知识图谱已返回')
    // Fetch related resources in parallel
    try {
      const rrRes = await agentApi.get(`/graph/related-resources/${encodeURIComponent(knowledgePoint.value)}`)
      relatedResources.value = (rrRes.data as any).data ?? (rrRes.data as any).resources ?? []
    } catch { relatedResources.value = [] }
    await nextTick()
    renderGraph()
  } catch (error: any) {
    const detail = error?.response?.data?.detail ?? error?.message ?? '未知错误'
    graphError.value = `查询失败：${detail}`
    ElMessage.error(graphError.value)
  } finally {
    loading.value = false
  }
}

function renderGraph() {
  if (!canvasRef.value || !graphVisualization.value) return
  const nodes = graphVisualization.value.nodes ?? []
  const edges = graphVisualization.value.edges ?? []
  const nodeDataset = new DataSet((nodes as any[]).map((n: any) => ({
    id: n.id,
    label: n.label,
    shape: n.category === 'current' ? 'dot' : 'box',
    size: n.category === 'current' ? 28 : 18,
    margin: 10,
    color: {
      background: categoryColors[n.category] ?? '#7b90a8',
      border: n.category === 'current' ? '#a7fff3' : 'rgba(226,235,244,0.25)',
      highlight: { background: categoryColors[n.category] ?? '#7b90a8', border: '#ffffff' },
    },
    font: { color: '#e2ebf4', size: n.category === 'current' ? 16 : 13, face: 'Inter, sans-serif' },
  })))
  const edgeDataset = new (DataSet as any)((edges as any[]).map((e: any) => ({
    from: e.source,
    to: e.target,
    label: e.label,
    arrows: 'to',
    color: { color: 'rgba(80,160,190,0.38)', highlight: '#00c8aa' },
    font: { color: '#8fa6bb', size: 10, strokeWidth: 0 },
    smooth: { type: 'dynamic' },
  })))
  if (network) network.destroy()
  network = new Network(canvasRef.value, { nodes: nodeDataset, edges: edgeDataset } as any, {
    layout: { improvedLayout: true },
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -95,
        centralGravity: 0.02,
        springLength: 165,
        springConstant: 0.06,
      },
      stabilization: { iterations: 220 },
    },
    interaction: { hover: true, tooltipDelay: 200, navigationButtons: true, keyboard: true },
  } as any)
}
</script>

<template>
  <div>
    <div style="margin-bottom:24px"><h2 style="font-size:24px;font-weight:750">🔗 知识图谱</h2><p style="color:var(--muted);font-size:14px">可视化知识依赖关系</p></div>
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:20px;flex-wrap:wrap">
      <div style="flex:1;min-width:260px;padding:12px 16px;border-radius:14px;border:1px solid var(--line);background:var(--panel);display:flex;align-items:center;justify-content:space-between;gap:12px">
        <div>
          <div style="font-size:12px;color:var(--muted);margin-bottom:4px">当前图谱知识点</div>
          <strong v-if="hasKnowledgePoint" style="font-size:16px;color:var(--text)">{{ knowledgePoint }}</strong>
          <span v-else style="font-size:14px;color:var(--muted)">先生成学习路径或课件，系统会自动带入知识点</span>
        </div>
        <span v-if="knowledgeSource" class="agent-tag">{{ knowledgeSource }}</span>
      </div>
      <button :disabled="loading" @click="queryGraph" style="padding:10px 20px;border-radius:12px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;cursor:pointer;font-weight:600;font-family:inherit">{{ loading ? '查询中...' : '查询图谱' }}</button>
    </div>
    <div v-if="graphError" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:12px;font-size:14px">{{ graphError }}</div>
    <div v-if="graphVisualization" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:14px">
      <div v-for="item in graphSummary" :key="item.label" style="padding:14px 16px;border-radius:12px;background:var(--panel);border:1px solid var(--line)">
        <div style="font-size:12px;color:var(--muted)">{{ item.label }}</div>
        <strong :style="{ fontSize:'24px', color:item.color }">{{ item.value }}</strong>
      </div>
    </div>
    <div v-if="graphVisualization" style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">
      <span v-for="(label,key) in categoryLabels" :key="key" style="display:inline-flex;align-items:center;gap:7px;padding:6px 10px;border-radius:999px;background:var(--panel);border:1px solid var(--line);font-size:12px;color:var(--muted)">
        <i :style="{ width:'9px', height:'9px', borderRadius:'999px', background:categoryColors[String(key)] }"></i>
        {{ label }}
      </span>
    </div>
    <div class="knowledge-graph-layout" :class="{ 'knowledge-graph-layout--ready': graphVisualization }">
      <div ref="canvasRef" style="width:100%;min-height:560px;border-radius:16px;background:var(--panel);border:1px solid var(--line)">
        <div v-if="!graphVisualization && !loading" style="display:flex;align-items:center;justify-content:center;height:450px;color:var(--muted)">{{ hasKnowledgePoint ? '点击“查询图谱”查看知识依赖关系' : '先生成学习路径或课件，系统会自动带入知识点' }}</div>
      </div>
      <div v-if="graphVisualization" style="padding:16px;border-radius:16px;background:var(--panel);border:1px solid var(--line);min-height:560px;display:flex;flex-direction:column;gap:18px">
        <section>
          <div style="font-size:12px;color:var(--muted);margin-bottom:10px">核心学习顺序</div>
          <div style="display:flex;flex-direction:column;gap:8px">
            <div v-for="(node,index) in coreSequence" :key="node.id" style="display:flex;align-items:center;gap:9px;font-size:13px;color:var(--text)">
              <span style="width:22px;height:22px;border-radius:999px;background:color-mix(in srgb,var(--accent) 16%,transparent);color:var(--accent);display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:700">{{ index + 1 }}</span>
              <span>{{ node.label }}</span>
            </div>
          </div>
        </section>
        <section>
          <div style="font-size:12px;color:var(--muted);margin-bottom:10px">前置基础</div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">
            <span v-for="node in groupedNodes.prerequisite" :key="node.id" style="padding:5px 9px;border-radius:999px;background:color-mix(in srgb,#4da3e0 12%,transparent);color:#8dccf5;font-size:12px">{{ node.label }}</span>
          </div>
        </section>
        <section>
          <div style="font-size:12px;color:var(--muted);margin-bottom:10px">进阶拓展</div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">
            <span v-for="node in groupedNodes.recommended.slice(coreSequence.length)" :key="node.id" style="padding:5px 9px;border-radius:999px;background:color-mix(in srgb,#a78bfa 12%,transparent);color:#c9bbff;font-size:12px">{{ node.label }}</span>
          </div>
        </section>
        <section v-if="groupedNodes.resource.length">
          <div style="font-size:12px;color:var(--muted);margin-bottom:10px">图谱资源</div>
          <div style="display:flex;flex-direction:column;gap:7px">
            <span v-for="node in groupedNodes.resource" :key="node.id" style="padding:7px 10px;border-radius:10px;background:rgba(255,255,255,.03);border:1px solid var(--line);font-size:12px;color:var(--text)">{{ node.label }}</span>
          </div>
        </section>
      </div>
    </div>
    <div v-if="dependencyPaths.length" style="margin-top:16px;padding:16px 20px;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
      <div style="font-size:12px;color:var(--muted);margin-bottom:8px">依赖路径</div>
      <div v-for="(path,i) in dependencyPaths" :key="i" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:4px">
        <span v-for="(kp,j) in path" :key="j"><span style="padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent)">{{ kp }}</span><span v-if="j<path.length-1" style="color:var(--muted);margin:0 4px">→</span></span>
      </div>
    </div>
    <div v-if="relatedResources.length" style="margin-top:16px;padding:16px 20px;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
      <div style="font-size:12px;color:var(--muted);margin-bottom:8px">📚 关联资源</div>
      <div v-for="(r,i) in relatedResources" :key="i" style="padding:8px 0;border-bottom:1px solid var(--line);font-size:13px">
        <strong>{{ r.title ?? r.name ?? '资源' }}</strong>
        <span style="color:var(--muted);margin-left:8px">{{ r.type ?? r.resource_type ?? '' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-graph-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
}

.knowledge-graph-layout--ready {
  grid-template-columns: minmax(0, 1fr) 320px;
}

@media (max-width: 980px) {
  .knowledge-graph-layout--ready {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
