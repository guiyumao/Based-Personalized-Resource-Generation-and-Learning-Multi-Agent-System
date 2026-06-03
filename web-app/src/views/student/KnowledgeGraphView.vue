<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentApi, type GraphVisualizationResponse } from '../../api'
import { DataSet, Network } from 'vis-network/standalone'

const knowledgePoint = ref('')
const loading = ref(false)
const graphVisualization = ref<GraphVisualizationResponse | null>(null)
const dependencyPaths = ref<string[][]>([])
const graphError = ref('')
const canvasRef = ref<HTMLDivElement | null>(null)
let network: Network | null = null

const categoryColors: Record<string, string> = {
  current: '#00c8aa', prerequisite: '#4da3e0', recommended: '#a78bfa', resource: '#7b90a8',
}

async function queryGraph() {
  if (!knowledgePoint.value.trim()) { ElMessage.warning('请输入知识点'); return }
  loading.value = true; graphError.value = ''; graphVisualization.value = null; dependencyPaths.value = []
  try {
    const payload = { knowledge_point: knowledgePoint.value, max_depth: 3 }
    const [depRes, visRes] = await Promise.all([
      agentApi.post<{ paths: string[][] }>('/graph/dependencies', payload),
      agentApi.post<GraphVisualizationResponse>('/graph/visualization', payload),
    ])
    graphVisualization.value = (visRes.data as any).data ?? visRes.data
    const depData = (depRes.data as any).data ?? depRes.data
    dependencyPaths.value = depData?.paths ?? []
    ElMessage.success('知识图谱已返回')
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
  const nodeDataset = new DataSet((nodes as any[]).map((n: any) => ({ id: n.id, label: n.label, color: { background: categoryColors[n.category] ?? '#7b90a8', border: 'transparent' }, font: { color: '#e2ebf4', size: 14 } })))
  const edgeDataset = new (DataSet as any)((edges as any[]).map((e: any) => ({ from: e.source, to: e.target, arrows: 'to', color: { color: 'rgba(80,160,190,0.3)' } })))
  if (network) network.destroy()
  network = new Network(canvasRef.value, { nodes: nodeDataset, edges: edgeDataset } as any, { physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -40, centralGravity: 0.005 } }, interaction: { hover: true, tooltipDelay: 200 } } as any)
}
</script>

<template>
  <div>
    <div style="margin-bottom:24px"><h2 style="font-size:24px;font-weight:750">🔗 知识图谱</h2><p style="color:var(--muted);font-size:14px">可视化知识依赖关系</p></div>
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:20px">
      <input v-model="knowledgePoint" placeholder="输入知识点" style="flex:1;max-width:360px;padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:var(--bg);color:var(--text);font-size:14px;outline:none;font-family:inherit" />
      <button :disabled="loading" @click="queryGraph" style="padding:10px 20px;border-radius:12px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;cursor:pointer;font-weight:600;font-family:inherit">{{ loading ? '查询中...' : '查询图谱' }}</button>
    </div>
    <div v-if="graphError" style="padding:16px;border-radius:12px;background:color-mix(in srgb,var(--red) 8%,transparent);color:var(--red);margin-bottom:12px;font-size:14px">{{ graphError }}</div>
    <div ref="canvasRef" style="width:100%;min-height:450px;border-radius:18px;background:var(--panel);border:1px solid var(--line)">
      <div v-if="!graphVisualization && !loading" style="display:flex;align-items:center;justify-content:center;height:450px;color:var(--muted)">输入知识点查询知识依赖关系</div>
    </div>
    <div v-if="dependencyPaths.length" style="margin-top:16px;padding:16px 20px;border-radius:14px;background:var(--panel);border:1px solid var(--line)">
      <div style="font-size:12px;color:var(--muted);margin-bottom:8px">依赖路径</div>
      <div v-for="(path,i) in dependencyPaths" :key="i" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:4px">
        <span v-for="(kp,j) in path" :key="j"><span style="padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--accent)">{{ kp }}</span><span v-if="j<path.length-1" style="color:var(--muted);margin:0 4px">→</span></span>
      </div>
    </div>
  </div>
</template>
