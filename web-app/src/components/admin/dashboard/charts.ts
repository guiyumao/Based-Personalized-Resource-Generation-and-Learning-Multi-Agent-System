export const palette = ['#536dff', '#20c997', '#ffab24', '#aa87f4', '#36a2eb', '#f06988']
export const stateLabels: Record<string,string> = { success:'成功', failed:'失败', running:'执行中', waiting:'等待中', cancelled:'已取消', other:'其他状态' }
export const stateColors: Record<string,string> = { success:'#20c997', failed:'#ff6384', running:'#3787ff', waiting:'#ffb547', cancelled:'#a8afc4', other:'#a78bfa' }
export const statusNames: Record<string,string> = { SUCCEEDED:'成功', COMPLETED:'成功', FAILED:'失败', RUNNING:'执行中', CANCEL_REQUESTED:'正在取消', PENDING:'等待中', QUEUED:'等待中', CANCELLED:'已取消', CANCELED:'已取消', STARTED:'未闭合', ONLINE:'在线', STALE:'心跳过期', STOPPED:'已退出', DEGRADED:'运行异常', OFFLINE:'离线' }
export const operationNames: Record<string,string> = { courseware:'课件生成', exercise:'习题生成', artifact:'学习产物', resource_video:'课件视频', courseware_revision:'章节修订', KNOWLEDGE_HEALTH_CHECK:'知识巡检', INDEX_REPAIR:'索引修复', AI_SUBJECT_PLAN:'学科规划', MAINTENANCE_RUN:'维护任务', resource_generation:'资源生成', exercise_generation:'练习生成', agent_coordination:'智能体协作', qa:'智能问答', path_adaptation:'路径调整', SEARCH_SOURCES:'搜索候选来源', FETCH_SOURCE:'抓取来源', BUILD_POINT:'知识点建设', HEALTH_CHECK:'知识巡检', PUBLISH_CANDIDATE:'发布候选', RECONCILE_PUBLICATIONS:'发布对账' }
export const operationName = (v: string) => operationNames[v] || (v?.startsWith('assistant:') ? operationNames[v.slice(10)] || v : v) || '未归属'
export const number = (v: number | null | undefined) => v == null ? '—' : v.toLocaleString('zh-CN')
export const timestamp = (v?: string | null) => v ? new Intl.DateTimeFormat('sv-SE', {timeZone:'UTC', year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(/[zZ]|[+-]\d\d:\d\d$/.test(v) ? v : v+'Z')) : '未记录'
export function cartesian(labels: string[], series: any[], unit='次') {
  return {color:palette, textStyle:{fontFamily:'inherit',color:'#7a87a5'}, aria:{enabled:true},
    tooltip:{trigger:'axis',confine:true,renderMode:'richText',backgroundColor:'#fff',borderColor:'#e9edf7',textStyle:{color:'#344164'}},
    legend:{top:4,left:0,type:'scroll',textStyle:{fontSize:11,color:'#667597'},icon:'circle',itemWidth:8,itemHeight:8},
    grid:{left:8,right:10,bottom:8,top:58,containLabel:true},
    xAxis:{type:'category',data:labels,axisLine:{lineStyle:{color:'#edf0f8'}},axisTick:{show:false},axisLabel:{fontSize:10,hideOverlap:true}},
    yAxis:{type:'value',name:unit,nameTextStyle:{align:'left',fontSize:10},minInterval:1,splitLine:{lineStyle:{color:'#edf1f9'}},axisLabel:{fontSize:10}},
    series:series.map(s=>({smooth:true,symbolSize:6,barMaxWidth:28,emphasis:{focus:'series'},...s}))}
}
export function spark(values: (number|null)[], color: string, type='line') {
  return {grid:{left:2,right:2,top:4,bottom:2},xAxis:{type:'category',show:false,data:values.map((_,i)=>i)},yAxis:{type:'value',show:false},series:[{type,data:values,smooth:true,symbol:'none',itemStyle:{color},lineStyle:{width:2,color},areaStyle:{color,opacity:.12}}]}
}
