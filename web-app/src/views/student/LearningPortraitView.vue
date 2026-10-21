<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { userApi } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
type Axis = {key:string;label:string;negative:string;positive:string;value:number|null;source:string}
type Behavior = { score:number|null; source:string; status:string; sample_size:number; confidence:number; interpretation?:string;next_evidence?:string[] }
type Portrait = {updated_at:string|null;axes:Axis[];dimensions:Record<string,string>;dimension_sources:Record<string,unknown>;style_source:string;behavior_profile:{algorithm_version:string;dimensions:Record<string,Behavior>;evidence:{answer_record_count:number}}}
const auth=useAuthStore(), data=ref<Portrait|null>(null), busy=ref(false), saving=ref(false), editing=ref(false), error=ref('')
const axes=reactive<Record<string,number|null>>({}), dimensions=reactive<Record<string,string>>({})
const labels:Record<string,string>={knowledgeBase:'知识基础',cognitiveStyle:'认知风格',errorPreference:'易错偏好',learningSpeed:'学习节奏',interestDirection:'兴趣方向',goalOrientation:'目标导向'}
const behaviorLabels:Record<string,string>={comprehension:'理解表现',memory:'复习保持',application:'应用表现',imagination:'开放任务表现',attention:'作答过程',knowledge_base:'知识基础',learning_goal:'学习目标'}
async function load(){ busy.value=true;error.value='';try{data.value=(await userApi.get(`/users/${auth.user!.userId}/learning-portrait`)).data;editing.value=false}catch(e:any){error.value=e?.response?.data?.detail||'画像暂时无法读取，请重试。'}finally{busy.value=false} }
function edit(){ if(!data.value)return;for(const axis of data.value.axes)axes[axis.key]=axis.value;for(const key of Object.keys(labels))dimensions[key]=data.value.dimensions[key]||'';editing.value=true }
async function save(){saving.value=true;error.value='';try{data.value=(await userApi.put(`/users/${auth.user!.userId}/learning-portrait`,{expected_updated_at:data.value?.updated_at,axes:{...axes},dimensions:{...dimensions}})).data;editing.value=false;ElMessage.success('学习画像已保存')}catch(e:any){error.value=e?.response?.data?.detail||'保存失败，请重试'}finally{saving.value=false} }
const shownAxes=computed(()=>data.value?.axes.map(axis=>({...axis,value:editing.value?axes[axis.key]??null:axis.value}))||[])
const known=computed(()=>shownAxes.value.filter(axis=>axis.value!==null).length)
function position(index:number,scale=1){const angle=-Math.PI/2+index*Math.PI/2;return {x:160+Math.cos(angle)*100*scale,y:150+Math.sin(angle)*100*scale} }
const polygon=computed(()=>shownAxes.value.map((axis,i)=>{const point=position(i,((axis.value??0)+1)/2);return `${point.x},${point.y}`}).join(' '))
const preference=(axis:Axis)=>axis.value===null?'尚未填写':Math.abs(axis.value)<.2?'自述倾向较均衡':`${axis.value<0?axis.negative:axis.positive}倾向 ${Math.round(Math.abs(axis.value)*100)}%`
function setRange(key:string,event:Event){axes[key]=Number((event.target as HTMLInputElement).value)/100}
function toggle(key:string,event:Event){axes[key]=(event.target as HTMLInputElement).checked?0:null}
const sourceLabel=(source:unknown)=>source==='user_reported'?'本人填写':source==='behavior_inference'?'学习记录推断':source==='profile_explicit'?'已有画像记录':source==='insufficient_evidence'?'证据不足':'已有记录'
onMounted(load)
</script>
<template>
  <div class="learner-insights" aria-label="学习画像工作台">
    <header class="insight-heading"><div><p class="insight-kicker">MY LEARNING PORTRAIT</p><h1>我的学习画像</h1><p>你的学习偏好与有据可查的学习表现，分别记录。</p></div><div class="insight-controls"><template v-if="editing"><button @click="editing=false" :disabled="saving">取消</button><button class="insight-primary" @click="save" :disabled="saving">{{ saving?'保存中…':'保存画像' }}</button></template><button v-else @click="edit" :disabled="!data">编辑画像</button><button @click="load" :disabled="busy||saving">刷新画像</button></div></header>
    <p v-if="busy" role="status">正在读取学习画像…</p><p v-if="error" role="alert" class="insight-error">{{ error }}</p>
    <template v-if="data">
      <div class="portrait-layout"><section class="insight-panel portrait-radar"><div class="insight-panel-title"><h2>学习偏好雷达</h2><span>{{ known }}/4项已填写</span></div><svg viewBox="0 0 320 300" role="img" aria-label="本人填写的四维学习偏好雷达"><polygon v-for="ring in [.25,.5,.75,1]" :key="ring" :points="[0,1,2,3].map(i=>`${position(i,ring).x},${position(i,ring).y}`).join(' ')" fill="none" stroke="var(--line)"/><line v-for="i in [0,1,2,3]" :key="i" x1="160" y1="150" :x2="position(i).x" :y2="position(i).y" stroke="var(--line)"/><polygon v-if="known===4" :points="polygon" fill="var(--accent-soft)" stroke="var(--accent)" stroke-width="2"/><template v-for="(axis,i) in shownAxes" :key="axis.key"><circle v-if="axis.value!==null" :cx="position(i,(axis.value+1)/2).x" :cy="position(i,(axis.value+1)/2).y" r="5" fill="var(--accent)"/><text :x="position(i,1.35).x" :y="position(i,1.25).y+5" text-anchor="middle">{{ axis.label }}</text></template></svg><p>{{ data.style_source }}</p><p class="insight-note">未填写的维度保留为空，不显示虚构分数。雷达方向与右侧两端偏好对应，数值大小不代表能力高低。</p><router-link to="/profile-setup">通过对话完善画像 →</router-link></section>
        <div class="portrait-details"><section class="insight-panel"><div class="insight-panel-title"><h2>学习风格维度</h2><span>本人填写 · 可随时修改</span></div><div v-for="axis in shownAxes" :key="axis.key" class="style-axis"><div class="insight-panel-title"><label :for="`style-${axis.key}`">{{ axis.label }}</label><span>{{ preference(axis) }}</span></div><div class="style-axis-track"><span>{{ axis.negative }}</span><div class="style-axis-bar"><div v-if="axis.value!==null" class="style-axis-fill" :style="{left:`${Math.min(50,(axis.value+1)*50)}%`,width:`${Math.abs(axis.value)*50}%`}"></div><i></i></div><span>{{ axis.positive }}</span></div><div v-if="editing" class="axis-editor"><label><input type="checkbox" :checked="axes[axis.key]!==null" @change="toggle(axis.key,$event)" />填写{{ axis.label }}</label><input v-if="axes[axis.key]!==null" :id="`style-${axis.key}`" type="range" min="-100" max="100" step="5" :aria-label="`${axis.label}倾向`" :value="(axes[axis.key]??0)*100" @input="setRange(axis.key,$event)" /></div></div></section>
          <section class="insight-panel"><h2>辅助维度</h2><div class="portrait-dimensions"><article v-for="(label,key) in labels" :key="key"><div class="insight-panel-title"><strong>{{ label }}</strong><small>{{ data.dimensions[key]?sourceLabel(data.dimension_sources[key]):'待补充' }}</small></div><label v-if="editing" :for="`dimension-${key}`" class="visually-hidden">{{ label }}</label><textarea v-if="editing" :id="`dimension-${key}`" v-model="dimensions[key]" :aria-label="label" maxlength="1500" rows="3"></textarea><p v-else>{{ data.dimensions[key]||'尚未填写，可点击编辑画像补充。' }}</p></article></div></section>
        </div>
      </div>
      <section class="insight-panel"><div class="insight-panel-title"><h2>学习表现与证据</h2><span>当前 {{ data.behavior_profile.evidence.answer_record_count }} 条作答记录</span></div><p class="insight-note">复用现有七维画像评分。数值是学习行为代理，不是心理测量结论；记录不足时保持“证据不足”。</p><div class="behavior-dimensions"><article v-for="(item,key) in data.behavior_profile.dimensions" :key="key"><strong>{{ behaviorLabels[key]||key }}</strong><div class="behavior-score">{{ item.score===null?'证据不足':`${item.score}/100` }}</div><progress v-if="item.score!==null" :value="item.score" max="100"></progress><p>{{ sourceLabel(item.source) }} · {{ item.sample_size??0 }}条证据</p><details><summary>查看依据</summary><p>{{ item.interpretation||'请继续积累相关学习记录。' }}</p><p v-for="(next,i) in item.next_evidence||[]" :key="i">{{ next }}</p></details></article></div></section>
      <footer class="insight-note"><router-link to="/student/analytics">查看学习分析</router-link> · <router-link to="/student/profile-analysis">查看已有深度分析</router-link> · 查看和手动编辑不触发模型调用。{{ data.updated_at?`更新于 ${new Date(data.updated_at).toLocaleString()}`:'' }}</footer>
    </template>
  </div>
</template>
<style src="./learningInsights.css"></style>
