<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { evaluationApi } from '../../api/http'
import { useAuthStore } from '../../stores/auth'

type Day = { date:string; study_seconds:number|null; answers:number; graded_answers:number; correct_answers:number; resource_events:number; questions_asked:number; card_reviews:number }
type Insight = { days:number; daily:Day[]; summary:{study_seconds:number|null;active_days:number;current_streak_days:number;accuracy_percent:number|null;answers:number}; week_comparison:{this_week_study_seconds:number|null;previous_week_study_seconds:number|null}; knowledge_accuracy:{knowledge_point_id:number;name:string;accuracy_percent:number|null;graded_answers:number}[]; notes:number; flashcards:{total:number;due:number;new:number;long_interval:number;reviews_in_period:number}; conversation:{questions:number;sessions:number;questions_per_session:number|null}; suggestions:{title:string;description:string;route:string;topic?:string}[]; answer_hours:{hour:number;answers:number;graded:number;correct:number}[]; quiz:{question_type:{label:string;answers:number;graded:number;accuracy_percent:number|null}[];difficulty:{label:string;answers:number;graded:number;accuracy_percent:number|null}[]} }
const auth = useAuthStore(), router = useRouter()
const days = ref(30), tab = ref('overview'), data = ref<Insight|null>(null), busy = ref(false), error = ref(''), picked = ref<Day|null>(null)
let sequence = 0
async function load() {
  const ticket = ++sequence; busy.value = true; error.value = ''; picked.value = null
  try { const response = await evaluationApi.get(`/evaluation/analytics/${auth.user!.userId}/insights`, {params:{days:days.value}}); if(ticket === sequence) data.value = response.data.data }
  catch(e:any) { if(ticket === sequence) { data.value=null; error.value = e?.response?.data?.detail || '学习分析暂时无法读取，请重试。' } }
  finally { if(ticket === sequence) busy.value = false }
}
const duration = (seconds:number|null|undefined) => seconds == null ? '暂无记录' : seconds < 60 ? `${Math.round(seconds)}秒` : `${Math.floor(seconds/3600)}小时${Math.floor(seconds%3600/60)}分`
const pct = (value:number|null|undefined) => value == null ? '待积累' : `${value}%`
const today = computed(()=>data.value?.daily.at(-1))
const cards = computed(()=>data.value ? [
  {label:'今日学习',value:duration(today.value?.study_seconds),note:'服务端有效活动时长'},
  {label:`近${days.value}天学习`,value:duration(data.value.summary.study_seconds),note:'不回填历史未知时长'},
  {label:'活跃天数',value:`${data.value.summary.active_days}天`,note:`当前连续 ${data.value.summary.current_streak_days} 天`},
  {label:'答题正确率',value:pct(data.value.summary.accuracy_percent),note:`${data.value.summary.answers} 次作答，按已判分记录计算`},
  {label:'闪卡复习',value:`${data.value.flashcards.reviews_in_period}次`,note:`${data.value.flashcards.due} 张当前到期`},
] : [])
const cells = computed(()=>{ const items=data.value?.daily || []; const pad=items.length ? (new Date(items[0]!.date+'T12:00:00').getDay()+6)%7 : 0; return [...Array.from({length:pad},()=>null),...items] })
const events = (day:Day)=>day.answers+day.resource_events+day.questions_asked+day.card_reviews+(day.study_seconds ? 1 : 0)
const shade = (day:Day)=>events(day)===0?0:Math.min(4,Math.ceil(Math.log2(events(day)+1)))
const peakSeconds = computed(()=>Math.max(60,...(data.value?.daily.map(d=>d.study_seconds||0)||[])))
const trend = computed(()=> (data.value?.daily||[]).map((d,i,arr)=>`${20+i*560/Math.max(1,arr.length-1)},${145-(d.study_seconds||0)/peakSeconds.value*120}`).join(' '))
const accuracyDots = computed(()=> (data.value?.daily||[]).map((d,i,arr)=>({...d,x:20+i*560/Math.max(1,arr.length-1),y:d.graded_answers?145-d.correct_answers/d.graded_answers*120:null})).filter(d=>d.y!==null))
const questionPeak = computed(()=>Math.max(1,...(data.value?.daily.map(d=>d.questions_asked)||[])))
const hourPeak = computed(()=>Math.max(1,...(data.value?.answer_hours.map(d=>d.answers)||[])))
function go(s:{route:string;topic?:string}) { router.push({path:s.route,query:s.topic?{topic:s.topic}:{}}) }
onMounted(load)
</script>
<template>
  <div class="learner-insights" aria-label="学习分析工作台">
    <header class="insight-heading"><div><p class="insight-kicker">LEARNING INSIGHTS</p><h1>学习分析仪表盘</h1><p>从练习、阅读、对话与复习记录中，看见学习的变化。</p></div><div class="insight-controls"><label>统计范围 <select v-model.number="days" @change="load"><option :value="7">近7天</option><option :value="30">近30天</option><option :value="90">近90天</option></select></label><button @click="load" :disabled="busy">刷新分析</button></div></header>
    <p v-if="error" class="insight-error" role="alert">{{ error }} <button @click="load">重试</button></p><p v-if="busy" role="status">正在读取学习记录…</p>
    <template v-if="data">
      <div class="insight-stats"><article v-for="(card,i) in cards" :key="card.label" class="insight-card" :style="{'--card-accent':['#5689db','#40a58a','#d59b3c','#8d73cb','#d07889'][i]}"><span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.note }}</small></article></div>
      <div class="insight-mini"><article class="insight-card"><span>本周学习</span><strong>{{ duration(data.week_comparison.this_week_study_seconds) }}</strong><small>上周 {{ duration(data.week_comparison.previous_week_study_seconds) }} · 按北京时间自然周</small></article><article class="insight-card"><span>学习笔记</span><strong>{{ data.notes }}篇</strong><router-link to="/student/study-tools">打开笔记与闪卡 →</router-link></article><article class="insight-card"><span>对话与提问</span><strong>{{ data.conversation.questions }}条</strong><small>所选时段 {{ data.conversation.sessions }} 个会话</small></article></div>
      <div class="insight-tabs" role="tablist" aria-label="学习分析分类"><button v-for="item in [{key:'overview',label:'学习概览'},{key:'conversation',label:'对话分布'},{key:'review',label:'复习助手'}]" :key="item.key" role="tab" :aria-selected="tab===item.key" @click="tab=item.key">{{ item.label }}</button></div>
      <template v-if="tab==='overview'">
        <section class="insight-panel"><div class="insight-panel-title"><h2>学习建议</h2><span>依据已记录行为生成</span></div><div class="insight-suggestions"><button v-for="suggestion in data.suggestions" :key="suggestion.title" @click="go(suggestion)"><strong>{{ suggestion.title }} ↗</strong><span>{{ suggestion.description }}</span></button></div></section>
        <section class="insight-panel"><div class="insight-panel-title"><h2>学习活动热力图</h2><span>近{{ days }}天 · 点击查看当天记录</span></div><div class="heatmap-scroll"><div class="learning-heatmap" :style="{'grid-template-columns':`repeat(${Math.ceil(cells.length/7)}, 18px)`}"><template v-for="(day,i) in cells" :key="day?.date||i"><button v-if="day" :data-level="shade(day)" :aria-label="`${day.date} ${events(day)}条活动`" :title="`${day.date}：作答${day.answers}次，学习${duration(day.study_seconds)}`" @click="picked=day"></button><span v-else></span></template></div></div><p class="insight-note">颜色表示学习记录密度；空白表示未记录到活动。学习时长仅计入已采集的有效活动区间。</p><div v-if="picked" class="day-detail" aria-live="polite"><strong>{{ picked.date }}</strong><span>学习 {{ duration(picked.study_seconds) }} · 作答 {{ picked.answers }} 次 · 资源交互 {{ picked.resource_events }} 次 · 提问 {{ picked.questions_asked }} 条 · 闪卡复习 {{ picked.card_reviews }} 次</span></div></section>
        <div class="insight-columns"><section class="insight-panel"><h2>学习时长趋势</h2><svg v-if="data.summary.study_seconds!==null" viewBox="0 0 600 165" role="img" aria-label="每日已记录学习时长"><path d="M20 145H580" stroke="var(--line)"/><polyline :points="trend" fill="none" stroke="var(--accent)" stroke-width="3"/><text x="20" y="160">{{ data.daily[0]?.date }}</text><text x="490" y="160">{{ today?.date }}</text></svg><p v-else>当前尚未采集有效时长。完成学习活动后刷新查看。</p></section><section class="insight-panel"><h2>答题正确率趋势</h2><svg viewBox="0 0 600 165" role="img" aria-label="每日已判分作答正确率"><path d="M20 25H580M20 145H580" stroke="var(--line)"/><text x="20" y="18">100%</text><circle v-for="dot in accuracyDots" :key="dot.date" :cx="dot.x" :cy="dot.y!" r="5" fill="var(--green)"><title>{{ dot.date }}：{{ Math.round(dot.correct_answers/dot.graded_answers*100) }}%（{{ dot.graded_answers }}次已判分）</title></circle></svg><p class="insight-note">没有已判分作答的日期不画分数点，不以0分代替未知。</p></section></div>
        <div class="insight-columns"><section class="insight-panel"><h2>题型表现</h2><table class="insight-table"><thead><tr><th>题型</th><th>作答</th><th>已判分</th><th>正确率</th></tr></thead><tbody><tr v-for="row in data.quiz.question_type" :key="row.label"><td>{{ row.label }}</td><td>{{ row.answers }}</td><td>{{ row.graded }}</td><td>{{ pct(row.accuracy_percent) }}</td></tr></tbody></table><p v-if="!data.quiz.question_type.length">尚无练习记录。</p></section><section class="insight-panel"><h2>知识点表现</h2><div v-for="point in data.knowledge_accuracy" :key="point.knowledge_point_id" class="knowledge-performance"><strong>{{ point.name }}</strong><span>{{ pct(point.accuracy_percent) }} · {{ point.graded_answers }}次判分</span><progress v-if="point.accuracy_percent!==null" :value="point.accuracy_percent" max="100"></progress><button @click="go({route:'/student/exercise',topic:point.name})">针对性练习</button></div><p v-if="!data.knowledge_accuracy.length">完成练习后展示知识点正确率。</p></section></div>
      </template>
      <template v-else-if="tab==='conversation'"><section class="insight-panel"><h2>每日提问分布</h2><div class="daily-bars"><div v-for="day in data.daily" :key="day.date" :title="`${day.date}：${day.questions_asked}条提问`"><span :style="{height:`${day.questions_asked/questionPeak*140}px`}"></span></div></div><p>所选时段 {{ data.conversation.questions }} 条本人提问，分布在 {{ data.conversation.sessions }} 个会话。</p><router-link to="/student/qa">继续学习对话 →</router-link></section><section class="insight-panel"><h2>答题时段分布</h2><div class="hour-bars"><div v-for="hour in data.answer_hours" :key="hour.hour"><span :style="{height:`${hour.answers/hourPeak*100}px`}" :title="`${hour.hour}时：${hour.answers}次作答`"></span><small>{{ hour.hour }}</small></div></div><p class="insight-note">北京时间记录的作答次数，不据此推断个人注意力或最佳学习时段。</p></section></template>
      <template v-else><section class="insight-panel"><h2>闪卡复习概览</h2><div class="review-summary"><div><strong>{{ data.flashcards.total }}</strong><span>全部闪卡</span></div><div><strong>{{ data.flashcards.due }}</strong><span>当前到期</span></div><div><strong>{{ data.flashcards.new }}</strong><span>尚未复习</span></div><div><strong>{{ data.flashcards.long_interval }}</strong><span>间隔≥21天</span></div></div><p>所选时段已完成 {{ data.flashcards.reviews_in_period }} 次复习。间隔较长只表示当前调度状态。</p><router-link class="insight-primary" to="/student/study-tools">开始复习与整理笔记 →</router-link></section></template>
      <footer class="insight-note"><router-link to="/student/report">查看详细学习报告</router-link> · <router-link to="/student/profile">查看我的学习画像</router-link> · 本页读取真实记录，不触发模型调用。</footer>
    </template>
  </div>
</template>
<style src="./learningInsights.css"></style>
