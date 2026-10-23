<script setup lang="ts">
import { type Component } from 'vue'
import { useRouter } from 'vue-router'
import { Aim, ArrowRight, ChatDotRound, Collection, Connection, EditPen, Guide, Notebook, Reading, Share, TrendCharts } from '@element-plus/icons-vue'
import heroImage from '../assets/knowledge-landscape.webp'
import ThemePicker from '../components/ThemePicker.vue'

const router = useRouter()
const currentYear = new Date().getFullYear()

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

function scrollToFeatures() { document.getElementById('features')?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }) }
</script>

<template>
  <div class="landing-page">
    <nav class="landing-nav">
      <router-link to="/" class="landing-brand"><span><el-icon><Reading /></el-icon></span><b>智学平台</b></router-link>
      <div class="landing-links"><a href="#features">功能</a><a href="#roles">角色</a><a href="#architecture">架构</a></div>
      <button class="landing-login" type="button" @click="router.push('/login')">登录工作台</button>
    </nav>

    <main>
      <section class="landing-hero">
        <div class="landing-hero-copy">
          <span class="landing-eyebrow">因你而异 · 随学而进</span>
          <h1>让每一次学习<br /><em>都有自己的方向</em></h1>
          <p>从你的目标与学习画像出发，让多智能体一起规划路径、生成课件与练习，把每一次学习反馈，变成下一步的指引。</p>
          <div class="landing-actions"><button type="button" class="primary" @click="router.push('/login')">开启学习旅程 <el-icon><ArrowRight /></el-icon></button><button type="button" class="secondary" @click="scrollToFeatures">探索平台功能 ↓</button></div>
          <div class="hero-capabilities"><span><b>路径</b>任务化</span><span><b>资源</b>按需生成</span><span><b>评估</b>数据驱动</span></div>
        </div>
        <div class="landing-visual">
          <div class="visual-frame">
            <span class="visual-note"><span></span> 多智能体，陪你探索知识</span>
            <img :src="heroImage" width="1200" height="800" fetchpriority="high" alt="学习路径连接起点、知识积木与成长之树，形成独立的知识探索地图" />
            <div class="visual-caption"><span>从找到起点，到收获理解</span><strong>你的目标 · 专属路径 · 持续成长</strong></div>
          </div>
          <div class="visual-theme"><span>选择你喜欢的学习氛围</span><ThemePicker /></div>
        </div>
      </section>

      <section id="features" class="landing-section">
        <header><span>为每一步学习提供支持</span><h2>从“学什么”，到“真正学会”</h2><p>把路径、课件、练习与答疑连接起来，在探索中理解知识，在反馈中巩固掌握。</p></header>
        <div class="landing-feature-grid">
          <article v-for="feature in features" :key="feature.title"><span><component :is="feature.icon" /></span><h3>{{ feature.title }}</h3><p>{{ feature.desc }}</p><button type="button" @click="router.push('/login')">登录后使用<el-icon><ArrowRight /></el-icon></button></article>
        </div>
      </section>

      <section id="roles" class="landing-section role-section">
        <header><span>学习与教学，在这里连接</span><h2>不同的角色，共同的成长</h2><p>学生专注自己的学习，教师看见学习中的需要，管理员维护有序的教学环境。</p></header>
        <div class="role-entry-grid"><article v-for="entry in roleEntries" :key="entry.title"><component :is="entry.icon" /><div><h3>{{ entry.title }}</h3><p>{{ entry.text }}</p></div></article></div>
      </section>

      <section id="architecture" class="architecture-section">
        <div><span class="landing-eyebrow">多智能体协同架构</span><h2>各有所长，<br />为你的学习共同思考</h2><p>学习画像提供背景，路径规划拆解目标，资源生成衔接课件与练习，评估反馈为后续学习提供依据。</p></div>
        <div class="architecture-flow"><span>学习画像<small>了解起点</small></span><i></i><span>路径规划<small>明确方向</small></span><i></i><span>资源生成<small>连接知识</small></span><i></i><span>评估反馈<small>调整下一步</small></span></div>
      </section>

      <section class="landing-cta"><div><h2>从今天的学习任务开始</h2><p>登录后，系统会根据你的身份进入对应工作台。</p></div><button type="button" @click="router.push('/login')">进入工作台</button></section>
    </main>

    <footer class="landing-footer"><span>© {{ currentYear }} 智学平台</span><span>个性化资源生成与学习多智能体系统</span></footer>
  </div>
</template>

<style scoped>
.landing-page { min-height: 100dvh; color: var(--text); background: var(--bg); }
.landing-nav { width: min(1180px, calc(100% - 48px)); min-height: 82px; margin: auto; display: flex; align-items: center; justify-content: space-between; gap: 24px; border-bottom: 1px solid var(--line); }
.landing-brand { display: flex; align-items: center; gap: 10px; color: var(--text); text-decoration: none; }
.landing-brand > span { width: 40px; height: 40px; display: grid; place-content: center; border-radius: 12px; background: var(--accent-soft); color: var(--accent); font-size: 25px; }
.landing-brand b { font-size: 18px; letter-spacing: .05em; }
.landing-links { display: flex; gap: 32px; }
.landing-links a { color: var(--muted); font-size: 13px; text-decoration: none; }
.landing-links a:hover { color: var(--accent); }
.landing-login, .landing-actions button, .landing-cta button { border: 0; border-radius: 10px; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
.landing-login { padding: 11px 19px; color: #fff; background: var(--accent-deep); }
.landing-hero { width: min(1180px, calc(100% - 48px)); min-height: 660px; margin: auto; display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: center; padding: 55px 0 48px; }
.landing-eyebrow, .landing-section header > span { color: var(--accent); font-size: 12px; font-weight: 600; letter-spacing: .12em; }
.landing-hero-copy { padding-bottom: 25px; }
.landing-hero h1 { margin: 23px 0 23px; font-size: clamp(34px, 4.4vw, 60px); font-weight: 650; line-height: 1.35; letter-spacing: -.045em; }
.landing-hero h1 em { font-style: normal; color: var(--accent); }
.landing-hero-copy > p { max-width: 465px; margin: 0; color: var(--muted); font-size: 15px; line-height: 2; }
.landing-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 30px; }
.landing-actions button { display: flex; align-items: center; gap: 12px; min-height: 48px; padding: 0 21px; }
.landing-actions .primary { color: #fff; background: var(--accent-deep); box-shadow: 0 8px 20px var(--accent-soft); }
.landing-actions .primary:hover, .landing-login:hover { background: var(--accent); }
.landing-actions .secondary { color: var(--text); border: 1px solid var(--line); background: var(--panel-strong); }
.hero-capabilities { display: flex; flex-wrap: wrap; gap: 22px; margin-top: 32px; color: var(--muted); font-size: 11px; }
.hero-capabilities span { display: flex; gap: 7px; align-items: center; }
.hero-capabilities b { color: var(--text); font-weight: 600; }
.hero-capabilities span::before { content: ''; width: 4px; height: 4px; background: var(--accent); border-radius: 50%; }
.landing-visual { min-width: 0; }
.visual-frame { position: relative; isolation: isolate; display: flex; flex-direction: column; align-items: center; padding: 22px 0; }
.visual-frame::before { content: ''; position: absolute; inset: 12% 0 0; z-index: -1; background: radial-gradient(ellipse, var(--accent-soft), transparent 68%); }
.visual-note { display: inline-flex; align-items: center; gap: 8px; padding: 8px 13px; border: 1px solid var(--line); border-radius: 30px; background: var(--panel); font-size: 11px; color: var(--muted); }
.visual-note > span { width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
.visual-frame img { width: 100%; height: 375px; object-fit: contain; margin: 8px 0; }
.visual-caption { display: grid; gap: 8px; text-align: center; }
.visual-caption > span { color: var(--text); font-size: 14px; font-weight: 600; }
.visual-caption strong { font-size: 11px; font-weight: 400; color: var(--muted); letter-spacing: .08em; }
.visual-theme { display: flex; align-items: center; justify-content: center; gap: 13px; padding-top: 18px; border-top: 1px solid var(--line); }
.visual-theme > span { color: var(--muted); font-size: 10px; }
.landing-section { width: min(1180px, calc(100% - 48px)); margin: auto; padding: 85px 0; border-top: 1px solid var(--line); scroll-margin-top: 24px; }
.landing-section header { max-width: 680px; margin-bottom: 35px; }
.landing-section h2, .architecture-section h2 { margin: 13px 0; font-size: clamp(26px, 3vw, 38px); line-height: 1.4; font-weight: 650; letter-spacing: -.04em; }
.landing-section header p, .architecture-section p { color: var(--muted); font-size: 14px; line-height: 1.9; margin: 0; }
.landing-feature-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.landing-feature-grid article { padding: 26px; border: 1px solid var(--line); border-radius: 16px; background: var(--panel); transition: border-color .2s, transform .2s; }
.landing-feature-grid article:hover { border-color: var(--accent); transform: translateY(-3px); }
.landing-feature-grid article > span { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 11px; color: var(--accent); background: var(--accent-soft); }
.landing-feature-grid svg { width: 21px; }
.landing-feature-grid h3 { margin: 20px 0 10px; font-size: 17px; font-weight: 600; }
.landing-feature-grid p { min-height: 48px; color: var(--muted); font-size: 12px; line-height: 1.9; margin: 0; }
.landing-feature-grid button { display: flex; align-items: center; gap: 8px; padding: 0; margin-top: 22px; border: 0; background: transparent; color: var(--accent); font-size: 12px; cursor: pointer; }
.landing-feature-grid button svg { width: 14px; }
.role-entry-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; }
.role-entry-grid article { padding: 26px; background: var(--surface-soft); border: 1px solid var(--line); border-radius: 16px; }
.role-entry-grid article > svg { width: 28px; color: var(--accent); margin-bottom: 22px; }
.role-entry-grid h3 { margin: 0 0 10px; font-size: 17px; }
.role-entry-grid p { color: var(--muted); font-size: 12px; line-height: 1.9; margin: 0; }
.architecture-section { width: min(1180px, calc(100% - 48px)); margin: auto; display: grid; grid-template-columns: 1fr 1fr; gap: 50px; align-items: center; padding: 80px 0; border-top: 1px solid var(--line); }
.architecture-flow { display: grid; grid-template-columns: 1fr 12px 1fr 12px 1fr 12px 1fr; gap: 5px; align-items: center; }
.architecture-flow > span { display: grid; align-content: center; gap: 10px; text-align: center; min-height: 105px; padding: 14px 8px; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; font-size: 12px; font-weight: 600; }
.architecture-flow small { color: var(--muted); font-size: 10px; font-weight: 400; }
.architecture-flow i { height: 1px; background: var(--accent); }
.landing-cta { width: min(1180px, calc(100% - 48px)); margin: 0 auto 65px; padding: 36px; display: flex; justify-content: space-between; align-items: center; gap: 24px; border: 1px solid var(--line); border-radius: 18px; background: var(--accent-soft); }
.landing-cta h2 { margin: 0 0 10px; font-size: 26px; }
.landing-cta p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; }
.landing-cta button { padding: 14px 20px; color: #fff; background: var(--accent-deep); white-space: nowrap; }
.landing-footer { width: min(1180px, calc(100% - 48px)); margin: auto; display: flex; justify-content: space-between; gap: 15px; padding: 24px 0; border-top: 1px solid var(--line); color: var(--muted); font-size: 11px; }
.landing-page a:focus-visible, .landing-page button:focus-visible { outline: 3px solid var(--accent); outline-offset: 4px; }
@media (max-width: 1000px) { .landing-hero { gap: 24px; min-height: 580px; } .visual-frame img { height: 300px; } .visual-theme { flex-wrap: wrap; gap: 9px; } .architecture-section { grid-template-columns: 1fr; gap: 30px; } }
@media (max-width: 760px) { .landing-hero { grid-template-columns: 1fr; gap: 18px; padding: 45px 0; } .landing-hero-copy { padding: 0; } .landing-hero h1 { font-size: clamp(32px, 6.5vw, 46px); } .landing-visual { width: 100%; max-width: 500px; margin: auto; } .landing-feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .role-entry-grid { grid-template-columns: 1fr; } .landing-links { gap: 18px; } .landing-section { padding: 60px 0; } }
@media (max-width: 520px) { .landing-nav, .landing-hero, .landing-section, .architecture-section, .landing-cta, .landing-footer { width: calc(100% - 36px); } .landing-nav { min-height: 70px; gap: 10px; } .landing-links { display: none; } .landing-brand { gap: 8px; } .landing-brand b { font-size: 16px; } .landing-login { padding: 10px 12px; font-size: 12px; } .landing-hero-copy > p { font-size: 13px; } .hero-capabilities { gap: 12px; font-size: 10px; } .landing-actions { gap: 9px; } .landing-actions button { padding-inline: 14px; font-size: 12px; } .visual-frame img { height: 250px; } .landing-feature-grid { grid-template-columns: 1fr; } .landing-feature-grid p { min-height: 0; } .architecture-section { padding: 60px 0; } .architecture-flow { grid-template-columns: 1fr 12px 1fr; } .architecture-flow i:nth-of-type(2) { display: none; } .landing-cta { padding: 25px; align-items: flex-start; flex-direction: column; } .landing-cta h2 { font-size: 23px; } .landing-footer { flex-direction: column; } }
@media (prefers-reduced-motion: reduce) { .landing-page * { transition: none !important; } }
</style>
