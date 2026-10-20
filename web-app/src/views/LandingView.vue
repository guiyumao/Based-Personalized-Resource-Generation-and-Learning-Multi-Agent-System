<script setup lang="ts">
import { computed, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { Aim, ArrowRight, ChatDotRound, Collection, Connection, EditPen, Guide, Notebook, Share, TrendCharts } from '@element-plus/icons-vue'
import heroImage from '../assets/hero.png'
import { useTheme, type ThemeName } from '../composables/useTheme'

const router = useRouter()
const { currentTheme, setTheme } = useTheme()
const currentYear = new Date().getFullYear()
const themes: { key: ThemeName; label: string; color: string }[] = [
  { key: null, label: '靛蓝云台', color: '#4f46e5' },
  { key: 'ocean', label: '深海科技', color: '#00b8a0' },
  { key: 'warm', label: '暖金学术', color: '#d97745' },
  { key: 'cosmic', label: '暗夜紫穹', color: '#8b5cf6' },
  { key: 'minimal', label: '极简晨光', color: '#2563eb' },
  { key: 'forest', label: '森林绿洲', color: '#35b978' },
]

type Feature = { title: string; desc: string; icon: Component; route: string }
const features: Feature[] = [
  { icon: Guide, title: '个性化学习路径', desc: '结合学习画像、知识依赖和教师范围，生成可调整的阶段任务。', route: '/student/learning-path' },
  { icon: Collection, title: '课件与资源', desc: '检索知识库，按需生成课件，并统一管理已保存的学习资源。', route: '/student/resources' },
  { icon: EditPen, title: '自适应练习', desc: '按知识点和难度生成习题，提交后返回真实评估与解析。', route: '/student/exercise' },
  { icon: Notebook, title: '错题巩固', desc: '沉淀错题、错因和建议操作，连接针对性变式练习。', route: '/student/mistakes' },
  { icon: Share, title: '知识图谱', desc: '展示先修依赖、知识缺口与关联资源，辅助理解学习顺序。', route: '/student/knowledge-graph' },
  { icon: ChatDotRound, title: '上下文智能问答', desc: '问答时带入画像、知识图谱和错题上下文，识别学习缺口。', route: '/student/qa' },
]

const roleEntries = [
  { icon: Aim, title: '学生工作台', text: '聚合路径、课件、练习、错题、报告与问答。' },
  { icon: TrendCharts, title: '教师工作台', text: '管理班级、学习范围、学生洞察、教学分析与作业。' },
  { icon: Connection, title: '管理工作台', text: '维护角色、学科、系统配置与审计日志。' },
]

const activeThemeLabel = computed(() => themes.find((theme) => theme.key === currentTheme.value)?.label ?? '靛蓝云台')
function scrollToFeatures() { document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' }) }
</script>

<template>
  <div class="landing-page">
    <nav class="landing-nav">
      <router-link to="/" class="landing-brand"><span><i></i><i></i><i></i></span><b>智学平台</b></router-link>
      <div class="landing-links"><a href="#features">功能</a><a href="#roles">角色</a><a href="#architecture">架构</a></div>
      <button class="landing-login" type="button" @click="router.push('/login')">登录工作台</button>
    </nav>

    <main>
      <section class="landing-hero">
        <div class="landing-hero-copy">
          <span class="landing-eyebrow">多智能体个性化学习平台</span>
          <h1>让学习路径<br />真正因人而异</h1>
          <p>结合学习画像、RAG 知识检索、知识图谱与多智能体协同，为学生、教师和管理员提供可追溯的学习闭环。</p>
          <div class="landing-actions"><button type="button" class="primary" @click="router.push('/login')">开始使用</button><button type="button" class="secondary" @click="scrollToFeatures">查看功能</button></div>
          <div class="hero-capabilities"><span><b>路径</b>任务化</span><span><b>资源</b>按需生成</span><span><b>评估</b>数据驱动</span></div>
        </div>
        <div class="landing-visual">
          <div class="visual-frame"><img :src="heroImage" alt="智学平台分层协同品牌图形" /><div><span>MULTI-AGENT</span><strong>画像、知识、路径、资源、评估</strong></div></div>
          <div class="theme-control" :title="`当前主题：${activeThemeLabel}`"><span>外观</span><button v-for="theme in themes" :key="theme.label" type="button" :aria-label="`切换到${theme.label}`" :class="{ active: currentTheme === theme.key }" :style="{ '--swatch': theme.color }" @click="setTheme(theme.key)"></button></div>
        </div>
      </section>

      <section id="features" class="landing-section">
        <header><span>核心功能</span><h2>从计划到反馈的学习闭环</h2><p>所有模块都对应现有业务路由与后端服务，不使用静态数据代替实际功能。</p></header>
        <div class="landing-feature-grid">
          <article v-for="feature in features" :key="feature.title"><span><component :is="feature.icon" /></span><h3>{{ feature.title }}</h3><p>{{ feature.desc }}</p><button type="button" @click="router.push('/login')">登录后使用<el-icon><ArrowRight /></el-icon></button></article>
        </div>
      </section>

      <section id="roles" class="landing-section role-section">
        <header><h2>每个角色都有自己的工作台</h2><p>界面与功能按实际权限配置展示，路由守卫保留现有角色边界。</p></header>
        <div class="role-entry-grid"><article v-for="entry in roleEntries" :key="entry.title"><component :is="entry.icon" /><div><h3>{{ entry.title }}</h3><p>{{ entry.text }}</p></div></article></div>
      </section>

      <section id="architecture" class="architecture-section">
        <div><span class="landing-eyebrow">系统架构</span><h2>前端、API 网关与多服务保持真实连接</h2><p>Vue 3 前端保留现有 FastAPI 与 LangGraph 服务边界，登录、画像、学习路径、资源、评估和教学管理均通过实际接口完成。</p></div>
        <div class="architecture-flow"><span>Vue 3</span><i></i><span>API Gateway</span><i></i><span>FastAPI Services</span><i></i><span>Data & AI</span></div>
      </section>

      <section class="landing-cta"><div><h2>从今天的学习任务开始</h2><p>登录后，系统会根据你的身份进入对应工作台。</p></div><button type="button" @click="router.push('/login')">进入工作台</button></section>
    </main>

    <footer class="landing-footer"><span>© {{ currentYear }} 智学平台</span><span>个性化资源生成与学习多智能体系统</span></footer>
  </div>
</template>

<style scoped>
.landing-page { min-height:100dvh; color:var(--text); background:var(--bg); }
.landing-nav { width:min(1180px,calc(100% - 40px)); height:70px; margin:auto; display:flex; align-items:center; justify-content:space-between; gap:26px; border-bottom:1px solid var(--line); }
.landing-brand { display:flex; align-items:center; gap:10px; color:var(--text); text-decoration:none; }.landing-brand > span { width:36px; height:36px; display:grid; place-content:center; gap:3px; border-radius:11px; background:linear-gradient(145deg,var(--accent),var(--accent-deep)); }.landing-brand i { display:block; width:16px; height:3px; border-radius:3px; background:#fff; transform:skewY(-16deg); }.landing-brand b { font-size:16px; }
.landing-links { display:flex; align-items:center; gap:28px; }.landing-links a { color:var(--muted); font-size:13px; font-weight:650; text-decoration:none; }.landing-links a:hover { color:var(--accent); }
.landing-login,.landing-actions button,.landing-cta button { border:0; border-radius:10px; font-family:inherit; font-weight:700; cursor:pointer; }.landing-login { padding:10px 16px; color:#fff; background:var(--accent); }.landing-login:hover { background:var(--accent-deep); }
.landing-hero { width:min(1180px,calc(100% - 40px)); min-height:calc(100dvh - 70px); margin:auto; display:grid; grid-template-columns:minmax(0,1.05fr) minmax(360px,.95fr); gap:70px; align-items:center; padding:54px 0; }
.landing-eyebrow,.landing-section header > span { color:var(--accent); font-size:11px; font-weight:800; letter-spacing:.11em; }.landing-hero h1 { max-width:680px; margin:15px 0 20px; font-size:clamp(48px,6vw,78px); line-height:1.08; letter-spacing:-.065em; }.landing-hero-copy > p { max-width:650px; margin:0; color:var(--muted); font-size:17px; line-height:1.85; }
.landing-actions { display:flex; gap:11px; margin-top:30px; }.landing-actions button { min-height:46px; padding:0 23px; }.landing-actions .primary { color:#fff; background:var(--accent); box-shadow:0 12px 26px color-mix(in srgb,var(--accent) 22%,transparent); }.landing-actions .primary:hover { background:var(--accent-deep); transform:translateY(-1px); }.landing-actions .secondary { border:1px solid var(--line); color:var(--text); background:var(--panel); }.landing-actions .secondary:hover { border-color:color-mix(in srgb,var(--accent) 34%,var(--line)); }
.hero-capabilities { display:flex; flex-wrap:wrap; gap:20px; margin-top:30px; color:var(--muted); font-size:11px; }.hero-capabilities span { display:flex; gap:5px; }.hero-capabilities b { color:var(--text); }
.landing-visual { position:relative; }.visual-frame { min-height:500px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:34px; border:1px solid color-mix(in srgb,var(--accent) 16%,var(--line)); border-radius:24px; background:linear-gradient(145deg,var(--panel),color-mix(in srgb,var(--accent) 7%,var(--panel))); box-shadow:var(--shadow); overflow:hidden; position:relative; }.visual-frame::before { content:''; width:310px; height:310px; border-radius:50%; position:absolute; background:color-mix(in srgb,var(--accent) 12%,transparent); filter:blur(10px); }.visual-frame img { width:min(70%,360px); position:relative; z-index:1; filter:drop-shadow(0 28px 32px color-mix(in srgb,var(--accent) 22%,transparent)); }.visual-frame > div { display:grid; gap:5px; text-align:center; position:relative; z-index:1; }.visual-frame span { color:var(--accent); font-size:10px; font-weight:800; letter-spacing:.13em; }.visual-frame strong { font-size:12px; font-weight:650; }
.theme-control { display:flex; align-items:center; gap:7px; padding:9px 11px; border:1px solid var(--line); border-radius:11px; background:var(--panel); box-shadow:var(--shadow-soft); position:absolute; right:18px; bottom:18px; z-index:2; }.theme-control span { margin-right:4px; color:var(--muted); font-size:10px; }.theme-control button { width:15px; height:15px; padding:0; border:2px solid var(--panel); border-radius:5px; outline:1px solid transparent; background:var(--swatch); cursor:pointer; }.theme-control button.active { outline-color:var(--text); }
.landing-section { width:min(1180px,calc(100% - 40px)); margin:auto; padding:100px 0; }.landing-section header { max-width:680px; margin-bottom:42px; }.landing-section h2,.architecture-section h2 { margin:10px 0 12px; font-size:clamp(32px,4vw,48px); line-height:1.2; letter-spacing:-.045em; }.landing-section header p,.architecture-section p { margin:0; color:var(--muted); font-size:14px; line-height:1.8; }
.landing-feature-grid { display:grid; grid-template-columns:repeat(12,1fr); gap:16px; }.landing-feature-grid article { grid-column:span 4; min-height:260px; padding:25px; border:1px solid var(--line); border-radius:16px; background:var(--panel); box-shadow:var(--shadow-soft); }.landing-feature-grid article:first-child,.landing-feature-grid article:nth-child(6) { grid-column:span 8; }.landing-feature-grid article:first-child { background:linear-gradient(135deg,var(--panel),color-mix(in srgb,var(--accent) 8%,var(--panel))); }.landing-feature-grid article:nth-child(6) { background:linear-gradient(135deg,color-mix(in srgb,var(--info) 6%,var(--panel)),var(--panel)); }.landing-feature-grid article > span { width:46px; height:46px; display:grid; place-items:center; border-radius:12px; color:var(--accent); background:var(--accent-soft); }.landing-feature-grid svg { width:22px; }.landing-feature-grid h3 { margin:22px 0 9px; font-size:18px; }.landing-feature-grid p { margin:0; color:var(--muted); font-size:13px; line-height:1.75; }.landing-feature-grid button { display:flex; align-items:center; gap:5px; margin-top:20px; padding:0; border:0; color:var(--accent); background:transparent; font-weight:700; cursor:pointer; }.landing-feature-grid button svg { width:14px; }
.role-section { border-top:1px solid var(--line); }.role-entry-grid { display:grid; gap:12px; }.role-entry-grid article { display:grid; grid-template-columns:52px 1fr; gap:18px; align-items:center; padding:20px; border:1px solid var(--line); border-radius:15px; background:var(--panel); }.role-entry-grid article > svg { width:26px; padding:12px; box-sizing:content-box; border-radius:12px; color:var(--accent); background:var(--accent-soft); }.role-entry-grid h3 { margin:0 0 5px; font-size:17px; }.role-entry-grid p { margin:0; color:var(--muted); line-height:1.7; }
.architecture-section { width:min(1180px,calc(100% - 40px)); margin:auto; display:grid; grid-template-columns:1fr 1fr; gap:60px; align-items:center; padding:100px 0; border-top:1px solid var(--line); }.architecture-flow { display:grid; grid-template-columns:1fr 18px 1fr 18px 1fr 18px 1fr; gap:7px; align-items:center; }.architecture-flow span { min-height:74px; display:grid; place-items:center; padding:10px; border:1px solid var(--line); border-radius:12px; background:var(--panel); color:var(--text); font-size:12px; font-weight:700; text-align:center; }.architecture-flow i { height:2px; background:linear-gradient(90deg,var(--accent),transparent); }
.landing-cta { width:min(1180px,calc(100% - 40px)); margin:0 auto 80px; display:flex; justify-content:space-between; align-items:center; gap:28px; padding:38px; border-radius:20px; color:#eef2ff; background:linear-gradient(135deg,#312e81,#4f46e5); }.landing-cta h2 { margin:0 0 7px; font-size:28px; }.landing-cta p { margin:0; color:rgba(238,242,255,.75); }.landing-cta button { min-height:46px; padding:0 22px; color:var(--accent-deep); background:#fff; white-space:nowrap; }
.landing-footer { width:min(1180px,calc(100% - 40px)); margin:auto; display:flex; justify-content:space-between; gap:20px; padding:28px 0; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }
@media (max-width:900px) { .landing-hero { grid-template-columns:1fr; gap:38px; }.landing-visual { max-width:620px; }.visual-frame { min-height:420px; }.landing-feature-grid article,.landing-feature-grid article:first-child,.landing-feature-grid article:nth-child(6) { grid-column:span 6; }.architecture-section { grid-template-columns:1fr; }.landing-cta { align-items:flex-start; flex-direction:column; } }
@media (max-width:620px) { .landing-nav,.landing-hero,.landing-section,.architecture-section,.landing-cta,.landing-footer { width:min(100% - 28px,1180px); }.landing-links { display:none; }.landing-login { padding-inline:12px; }.landing-hero { padding-top:34px; }.landing-hero h1 { font-size:44px; }.landing-hero-copy > p { font-size:15px; }.hero-capabilities { gap:10px 16px; }.visual-frame { min-height:350px; }.landing-section,.architecture-section { padding:70px 0; }.landing-feature-grid { grid-template-columns:1fr; }.landing-feature-grid article,.landing-feature-grid article:first-child,.landing-feature-grid article:nth-child(6) { grid-column:auto; min-height:0; }.architecture-flow { grid-template-columns:1fr; }.architecture-flow i { width:2px; height:16px; margin:auto; background:linear-gradient(180deg,var(--accent),transparent); }.landing-footer { flex-direction:column; } }
</style>
