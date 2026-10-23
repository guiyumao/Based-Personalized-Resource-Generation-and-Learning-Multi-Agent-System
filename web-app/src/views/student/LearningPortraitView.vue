<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { userApi } from '../../api/http'
import RadarChart from '../../components/RadarChart.vue'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
type Axis = {key:string;label:string;negative:string;positive:string;value:number|null;source:string;confidence:number|null;evidence:string}
type Behavior = { score:number|null; source:string; status:string; sample_size:number; confidence:number; interpretation?:string;next_evidence?:string[] }
type Inference = {status:string;generated_at:string|null;model:string|null;stale:boolean;summary:string;evidence:Record<string,number>}
type Portrait = {updated_at:string|null;axes:Axis[];dimensions:Record<string,string>;dimension_sources:Record<string,unknown>;style_source:string;inference:Inference;behavior_profile:{algorithm_version:string;dimensions:Record<string,Behavior>;evidence:{answer_record_count:number}}}
const auth=useAuthStore(), data=ref<Portrait|null>(null), busy=ref(false), saving=ref(false), generating=ref(false), editing=ref(false), error=ref(''), aiMessage=ref('')
const axes=reactive<Record<string,number|null>>({}), dimensions=reactive<Record<string,string>>({})
const labels:Record<string,string>={knowledgeBase:'知识基础',cognitiveStyle:'认知风格',errorPreference:'易错偏好',learningSpeed:'学习节奏',interestDirection:'兴趣方向',goalOrientation:'目标导向'}
const behaviorLabels:Record<string,string>={comprehension:'理解表现',memory:'复习保持',application:'应用表现',imagination:'开放任务表现',attention:'作答过程',knowledge_base:'知识基础',learning_goal:'学习目标'}
async function load(){ busy.value=true;error.value='';try{data.value=(await userApi.get(`/users/${auth.user!.userId}/learning-portrait`)).data;editing.value=false}catch(e:any){error.value=e?.response?.data?.detail||'画像暂时无法读取，请重试。'}finally{busy.value=false} }
async function generate(){
  if(!data.value||generating.value)return
  generating.value=true;error.value='';aiMessage.value=''
  try{
    const {data:result}=await userApi.post(`/users/${auth.user!.userId}/learning-portrait/infer`,{force:false})
    if(result.snapshot)data.value=result.snapshot
    aiMessage.value=result.message||''
    if(result.status==='completed')ElMessage.success(result.message||'模型已生成学习画像')
    else ElMessage.warning(result.message||'暂时无法生成画像')
  }catch(e:any){error.value=e?.response?.data?.detail||'生成失败，请稍后重试'}finally{generating.value=false}
}
function edit(){
  if(!data.value)return
  // 编辑层只承载本人填写；模型推断项需勾选后才转为本人填写。
  for(const axis of data.value.axes)axes[axis.key]=axis.source==='user_reported'?axis.value:null
  for(const key of Object.keys(labels))dimensions[key]=data.value.dimensions[key]||''
  editing.value=true
}
async function save(){saving.value=true;error.value='';try{data.value=(await userApi.put(`/users/${auth.user!.userId}/learning-portrait`,{expected_updated_at:data.value?.updated_at,axes:{...axes},dimensions:{...dimensions}})).data;editing.value=false;ElMessage.success('学习画像已保存')}catch(e:any){error.value=e?.response?.data?.detail||'保存失败，请重试'}finally{saving.value=false} }
const shownAxes=computed(()=>data.value?.axes.map(axis=>({...axis,value:editing.value?axes[axis.key]??null:axis.value}))||[])
const known=computed(()=>shownAxes.value.filter(axis=>axis.value!==null).length)
const inferenceEvidence=computed(()=>{
  const evidence=data.value?.inference?.evidence||{}
  const parts:string[]=[]
  if(evidence.answers)parts.push(`${evidence.answers} 条作答`)
  if(evidence.resources)parts.push(`${evidence.resources} 条资源浏览`)
  if(evidence.conversations)parts.push(`${evidence.conversations} 条画像对话`)
  if(evidence.notes)parts.push(`${evidence.notes} 条笔记`)
  if(evidence.reviews)parts.push(`${evidence.reviews} 张闪卡`)
  return parts.join('、')
})
const preference=(axis:Axis)=>axis.value===null?'尚未获得':Math.abs(axis.value)<.2?'自述倾向较均衡':`${axis.value<0?axis.negative:axis.positive}倾向 ${Math.round(Math.abs(axis.value)*100)}%`
function setRange(key:string,event:Event){axes[key]=Number((event.target as HTMLInputElement).value)/100}
function toggle(key:string,event:Event){axes[key]=(event.target as HTMLInputElement).checked?0:null}
const sourceLabel=(source:unknown)=>source==='user_reported'?'本人填写':source==='model_inferred'?'模型推断':source==='behavior_inference'?'学习记录推断':source==='profile_explicit'?'已有画像记录':source==='insufficient_evidence'?'证据不足':'已有记录'
const axisSource=(axis:Axis)=>sourceLabel(axis.source)
onMounted(load)
</script>
<template>
  <div class="learner-insights" aria-label="学习画像工作台">
    <header class="insight-heading"><div><p class="insight-kicker">MY LEARNING PORTRAIT</p><h1>我的学习画像</h1><p>模型会根据平台上已收集的自述与学习记录推断学习偏好，也保留本人填写的入口。</p></div><div class="insight-controls">
      <template v-if="editing"><button @click="editing=false" :disabled="saving">取消</button><button class="insight-primary" @click="save" :disabled="saving">{{ saving?'保存中…':'保存画像' }}</button></template>
      <template v-else>
        <button class="insight-primary" @click="generate" :disabled="!data||busy||generating">{{ generating?'AI 生成中…':(data&&data.inference.status==='completed'?'AI 更新画像':'AI 生成画像') }}</button>
        <button @click="edit" :disabled="!data">编辑画像</button>
        <button @click="load" :disabled="busy||saving||generating">刷新画像</button>
      </template>
    </div></header>
    <p v-if="busy" role="status">正在读取学习画像…</p>
    <p v-if="error" role="alert" class="insight-error">{{ error }}</p>
    <p v-if="aiMessage" role="status" class="insight-note">{{ aiMessage }}</p>
    <template v-if="data">
      <div class="portrait-layout">
        <section class="insight-panel portrait-radar">
          <div class="insight-panel-title"><h2>学习偏好雷达</h2><span>{{ known }}/4项已获得</span></div>
          <RadarChart :axes="shownAxes" :min="-1" :max="1" label="四维学习偏好雷达，包含本人填写与模型推断" />
          <p>{{ data.style_source }}</p>
          <p v-if="data.inference.status==='completed'" class="insight-note">
            模型依据：{{ inferenceEvidence||'已有自述' }}<template v-if="data.inference.summary"> · {{ data.inference.summary }}</template>
          </p>
          <p v-else class="insight-note">还没有模型生成的画像。点击“AI 生成画像”，模型会读取已收集的自述、作答、资源浏览和画像对话来推断四个维度。</p>
          <p v-if="data.inference.stale" class="insight-note">检测到新的学习记录，可点击“AI 更新画像”重新推断。</p>
          <p class="insight-note">连线与填充区域仅连接已获得的偏好；蓝点为模型推断、主色点为本人填写，未获得证据的维度保持为空。数值方向对应两端偏好，不代表能力高低。</p>
          <router-link to="/profile-setup">通过对话完善画像 →</router-link>
        </section>
        <div class="portrait-details">
          <section class="insight-panel">
            <div class="insight-panel-title"><h2>学习风格维度</h2><span>{{ editing?'本人填写优先 · 勾选后覆盖推断':'本人填写优先 · 其余由模型推断' }}</span></div>
            <div v-for="axis in shownAxes" :key="axis.key" class="style-axis">
              <div class="insight-panel-title"><label :for="`style-${axis.key}`">{{ axis.label }}</label><span><em class="axis-source" :class="axis.source">{{ axisSource(axis) }}</em>{{ preference(axis) }}</span></div>
              <div class="style-axis-track"><span>{{ axis.negative }}</span><div class="style-axis-bar"><div v-if="axis.value!==null" class="style-axis-fill" :style="{left:`${Math.min(50,(axis.value+1)*50)}%`,width:`${Math.abs(axis.value)*50}%`}"></div><i></i></div><span>{{ axis.positive }}</span></div>
              <p v-if="!editing&&axis.source==='model_inferred'" class="axis-evidence">依据：{{ axis.evidence||'已有学习记录' }}<template v-if="axis.confidence!==null"> · 置信度 {{ Math.round((axis.confidence||0)*100) }}%</template></p>
              <div v-if="editing" class="axis-editor"><label><input type="checkbox" :checked="axes[axis.key]!==null" @change="toggle(axis.key,$event)" />填写{{ axis.label }}</label><input v-if="axes[axis.key]!==null" :id="`style-${axis.key}`" type="range" min="-100" max="100" step="5" :aria-label="`${axis.label}倾向`" :value="(axes[axis.key]??0)*100" @input="setRange(axis.key,$event)" /></div>
            </div>
          </section>
          <section class="insight-panel"><h2>辅助维度</h2><div class="portrait-dimensions"><article v-for="(label,key) in labels" :key="key"><div class="insight-panel-title"><strong>{{ label }}</strong><small>{{ data.dimensions[key]?sourceLabel(data.dimension_sources[key]):'待补充' }}</small></div><label v-if="editing" :for="`dimension-${key}`" class="visually-hidden">{{ label }}</label><textarea v-if="editing" :id="`dimension-${key}`" v-model="dimensions[key]" :aria-label="label" maxlength="1500" rows="3"></textarea><p v-else>{{ data.dimensions[key]||'尚未填写，可点击编辑画像补充。' }}</p></article></div></section>
        </div>
      </div>
      <section class="insight-panel"><div class="insight-panel-title"><h2>学习表现与证据</h2><span>当前 {{ data.behavior_profile.evidence.answer_record_count }} 条作答记录</span></div><p class="insight-note">复用现有七维画像评分。数值是学习行为代理，不是心理测量结论；记录不足时保持“证据不足”。</p><div class="behavior-dimensions"><article v-for="(item,key) in data.behavior_profile.dimensions" :key="key"><strong>{{ behaviorLabels[key]||key }}</strong><div class="behavior-score">{{ item.score===null?'证据不足':`${item.score}/100` }}</div><progress v-if="item.score!==null" :value="item.score" max="100"></progress><p>{{ sourceLabel(item.source) }} · {{ item.sample_size??0 }}条证据</p><details><summary>查看依据</summary><p>{{ item.interpretation||'请继续积累相关学习记录。' }}</p><p v-for="(next,i) in item.next_evidence||[]" :key="i">{{ next }}</p></details></article></div></section>
      <footer class="insight-note"><router-link to="/student/analytics">查看学习分析</router-link> · <router-link to="/student/profile-analysis">查看已有深度分析</router-link> · 读取和手动编辑不触发模型调用，只有“AI 生成画像”会调用一次模型。{{ data.updated_at?`更新于 ${new Date(data.updated_at).toLocaleString()}`:'' }}</footer>
    </template>
  </div>
</template>
<style src="./learningInsights.css"></style>
