<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme'

const router = useRouter()
const { currentTheme, setTheme } = useTheme()

// ── Mouse glow ──
const glowRef = ref<HTMLDivElement | null>(null)
let mx = 0.5, my = 0.5
let curMx = 0.5, curMy = 0.5
let raf = 0

function onMouseMove(e: MouseEvent) {
  mx = e.clientX / window.innerWidth
  my = e.clientY / window.innerHeight
}

function updateGlow() {
  curMx += (mx - curMx) * 0.06
  curMy += (my - curMy) * 0.06
  const x = (curMx * 100).toFixed(1), y = (curMy * 100).toFixed(1)
  if (glowRef.value) {
    glowRef.value.style.background = `
      radial-gradient(420px circle at ${x}% ${y}%, var(--accent), transparent 70%),
      radial-gradient(600px circle at ${x}% ${y}%, var(--accent-deep), transparent 50%)
    `
    glowRef.value.style.opacity = '0.12'
  }
  raf = requestAnimationFrame(updateGlow)
}

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  updateGlow()
})
onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  cancelAnimationFrame(raf)
})

// ── Theme dots for corner ──
const themeDots = [
  { key: 'ocean',   color: '#00c8aa' },
  { key: 'warm',    color: '#e8924a' },
  { key: 'cosmic',  color: '#a78bfa' },
  { key: 'minimal', color: '#2563eb' },
  { key: 'forest',  color: '#48c884' },
]

function scrollToFeatures() {
  document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })
}

// ── Feature cards data ──
const features = [
  { icon:'🗺️', title:'个性化学习路径', desc:'AI 根据掌握度与学习风格，自动生成分阶段学习路径，动态调整难度' },
  { icon:'📚', title:'智能课件生成', desc:'基于 RAG 检索增强生成，多源整合产出结构化课件，支持难度分级与变体' },
  { icon:'✏️', title:'自适应练习测评', desc:'自动生成分层习题，即时反馈与解析，支持多种题型' },
  { icon:'📝', title:'智能错题本', desc:'自动收录错题，AI 分析根因，一键生成变式题巩固训练' },
  { icon:'🔗', title:'知识图谱可视化', desc:'构建学科知识依赖网络，节点颜色反映掌握程度' },
  { icon:'💬', title:'多智能体问答', desc:'结合学习画像深度分析，识别知识差距，给出针对性建议' },
]
</script>

<template>
  <!-- ═══ Mouse Glow Background ═══ -->
  <div class="landing-bg">
    <div ref="glowRef" class="mouse-glow-layer"></div>
    <div class="grid-overlay"></div>
  </div>

  <!-- ═══ Theme Dots ═══ -->
  <div class="corner-themes">
    <span v-for="t in themeDots" :key="t.key"
      class="theme-dot"
      :class="{ active: currentTheme === t.key }"
      :style="{ background: t.color, color: t.color }"
      @click="setTheme(t.key as any)"
    ></span>
  </div>

  <!-- ═══ Nav ═══ -->
  <nav class="landing-nav">
    <div class="nav-brand">
      <div class="brand-dot"></div>
      <span>智学平台</span>
    </div>
    <div class="nav-links">
      <a href="#features">功能</a>
      <a href="#tech">技术</a>
      <button class="nav-cta" @click="router.push('/login')">免费体验</button>
    </div>
  </nav>

  <!-- ═══ Hero ═══ -->
  <section class="hero-section">
    <div class="hero-eyebrow">AI-POWERED LEARNING PLATFORM</div>
    <h1 class="hero-title">科技赋能教育<br>AI 引领未来</h1>
    <p class="hero-subtitle">
      基于多智能体协同的个性化学习系统 —— 为每位学习者定制专属路径、课件与练习
    </p>
    <div class="hero-buttons">
      <button class="btn-hero-primary" @click="router.push('/login')">免费体验</button>
      <button class="btn-hero-secondary" @click="scrollToFeatures">了解更多 ↓</button>
    </div>
    <div class="scroll-hint">
      <span>滚 动 探 索</span>
      <div class="scroll-line"></div>
    </div>
  </section>

  <!-- ═══ Features ═══ -->
  <section class="section" id="features">
    <div class="section-inner">
      <div class="section-label">核心功能</div>
      <h2 class="section-title">八大智能学习模块</h2>
      <p class="section-desc">从学习路径规划到课后自测，从知识图谱到智能问答 —— AI 多智能体系统为每个学习环节提供精准支持</p>

      <div class="feature-grid">
        <div v-for="f in features" :key="f.title" class="feature-card">
          <div class="feature-icon">{{ f.icon }}</div>
          <h3>{{ f.title }}</h3>
          <p>{{ f.desc }}</p>
        </div>
      </div>
    </div>
  </section>

  <!-- ═══ AI Tech ═══ -->
  <section class="section" id="tech">
    <div class="section-inner">
      <div class="section-label">AI 技术</div>
      <h2 class="section-title">多智能体驱动的学习引擎</h2>
      <p class="section-desc">系统采用多智能体协同架构，各 Agent 分工协作，覆盖资源生成、学习诊断、路径规划的完整链路</p>

      <div class="tech-grid">
        <div v-for="tech in [
          { icon:'🧠', title:'多智能体协同', desc:'资源生成、学习诊断、路径规划等多个 Agent 通过消息队列异步协作', tags:['LangGraph','Multi-Agent','RabbitMQ'] },
          { icon:'🔍', title:'RAG 检索增强', desc:'课件和习题生成前从向量知识库检索相关片段，确保内容准确有据', tags:['ChromaDB','Elasticsearch','Embedding'] },
          { icon:'🕸️', title:'知识图谱推理', desc:'基于 Neo4j 图数据库构建学科知识网络，支持先修依赖推理和缺口检测', tags:['Neo4j','Graph Reasoning','vis-network'] },
          { icon:'🎯', title:'学习画像与自适应', desc:'持续追踪学习行为，构建多维度画像，动态调整内容难度和推荐策略', tags:['Learner Profile','Adaptive','VARK'] },
        ]" :key="tech.title" class="tech-card">
          <div class="tech-icon-lg">{{ tech.icon }}</div>
          <h3>{{ tech.title }}</h3>
          <p>{{ tech.desc }}</p>
          <div class="tag-row">
            <span v-for="t in tech.tags" :key="t" class="ai-tag">{{ t }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ═══ CTA ═══ -->
  <section class="cta-section">
    <h2>准备好开始智能学习了吗？</h2>
    <p>立即体验 AI 驱动的个性化学习平台，让科技为您的学习之旅赋能</p>
    <button class="btn-hero-primary" @click="router.push('/login')">免费体验 →</button>
  </section>

  <!-- ═══ Footer ═══ -->
  <footer class="landing-footer">
    <span>© 2024 智学平台 · AI-Powered Learning</span>
    <span>
      <a href="#" @click.prevent="router.push('/login')">工作台</a> ·
      <a href="#features">功能</a> ·
      <a href="#tech">技术</a>
    </span>
  </footer>
</template>

<style scoped>
/* ── Background ── */
.landing-bg { position:fixed; inset:0; pointer-events:none; z-index:0; }
.mouse-glow-layer { position:absolute; inset:0; transition:opacity 0.6s; background:radial-gradient(420px circle at 50% 50%, var(--accent), transparent 70%); opacity:0.1; }
.grid-overlay { position:absolute; inset:0; background-image:linear-gradient(rgba(129,160,204,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(129,160,204,.05) 1px,transparent 1px); background-size:32px 32px; mask-image:radial-gradient(circle at 50% 50%, rgba(0,0,0,.4), transparent 60%); }

/* ── Corner themes ── */
.corner-themes { position:fixed; top:18px; right:24px; z-index:100; display:flex; gap:8px; }
.theme-dot { width:16px;height:16px;border-radius:50%;cursor:pointer;border:2px solid transparent;transition:all .25s; }
.theme-dot:hover { transform:scale(1.25); }
.theme-dot.active { border-color:var(--text); box-shadow:0 0 10px currentColor; }

/* ── Nav ── */
.landing-nav { position:fixed; top:0;left:0;right:0;z-index:50; padding:14px 28px; display:flex; align-items:center; justify-content:space-between; backdrop-filter:blur(20px);background:color-mix(in srgb, var(--bg) 72%, transparent); border-bottom:1px solid var(--line); }
.nav-brand { display:flex; align-items:center; gap:10px; color:var(--text); font-weight:700; font-size:17px; }
.brand-dot { width:28px;height:28px;border-radius:9px;background:linear-gradient(135deg,var(--accent),var(--accent-deep)); }
.nav-links { display:flex; align-items:center; gap:8px; }
.nav-links a { color:var(--muted); text-decoration:none; font-size:13px; font-weight:550; padding:8px 16px; border-radius:999px; transition:all .2s; }
.nav-links a:hover { color:var(--text); background:color-mix(in srgb,var(--accent) 6%,transparent); }
.nav-cta { padding:9px 22px; border-radius:999px; border:none; background:linear-gradient(135deg,var(--accent),var(--accent-deep)); color:#fff; font-weight:700; cursor:pointer; font-size:13px; font-family:inherit; }
.nav-cta:hover { transform:translateY(-2px); box-shadow:0 6px 20px color-mix(in srgb,var(--accent) 30%,transparent); }

/* ── Hero ── */
.hero-section { position:relative;z-index:1; min-height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:120px 24px 80px; }
.hero-eyebrow { font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:var(--accent);margin-bottom:20px; display:flex;align-items:center;gap:12px; }
.hero-eyebrow::before,.hero-eyebrow::after { content:"";width:36px;height:1px;background:linear-gradient(90deg,transparent,var(--accent)); }
.hero-eyebrow::after { background:linear-gradient(90deg,var(--accent),transparent); }
.hero-title { font-size:clamp(38px,7vw,80px);font-weight:850;line-height:1.18;letter-spacing:.04em; background:linear-gradient(160deg,var(--text)20%,var(--accent)45%,var(--accent-deep)65%,var(--text)85%);background-size:200% auto; -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text; animation:shimmer 6s ease-in-out infinite; filter:drop-shadow(0 0 32px color-mix(in srgb,var(--accent) 35%,transparent)); margin-bottom:20px; }
@keyframes shimmer { 0%,100%{background-position:0% center} 50%{background-position:100% center} }
.hero-subtitle { font-size:clamp(16px,2.2vw,20px);color:var(--muted);max-width:36em;line-height:1.8;margin-bottom:36px; }
.hero-buttons { display:flex;gap:16px;flex-wrap:wrap;justify-content:center; }
.btn-hero-primary { padding:14px 36px;border-radius:999px;border:none;background:linear-gradient(135deg,var(--accent),var(--accent-deep));color:#fff;font-size:16px;font-weight:700;cursor:pointer;font-family:inherit;box-shadow:0 8px 32px color-mix(in srgb,var(--accent) 30%,transparent);transition:all .2s; }
.btn-hero-primary:hover { transform:translateY(-3px);box-shadow:0 14px 42px color-mix(in srgb,var(--accent) 45%,transparent); }
.btn-hero-secondary { padding:14px 36px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--text);font-size:16px;font-weight:600;cursor:pointer;font-family:inherit;backdrop-filter:blur(12px);transition:all .2s; }
.btn-hero-secondary:hover { border-color:color-mix(in srgb,var(--accent) 30%,transparent);background:color-mix(in srgb,var(--accent) 5%,transparent); }
.scroll-hint { position:absolute;bottom:28px;display:flex;flex-direction:column;align-items:center;gap:8px;color:var(--muted);font-size:11px;letter-spacing:.1em;animation:bounce 2s ease-in-out infinite; }
.scroll-line { width:1px;height:36px;background:linear-gradient(180deg,var(--accent),transparent); }
@keyframes bounce { 0%,100%{transform:translateY(0)} 50%{transform:translateY(8px)} }

/* ── Sections ── */
.section { position:relative;z-index:1;padding:80px 24px;scroll-snap-align:start; }
.section-inner { max-width:1100px;margin:0 auto; }
.section-label { font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin-bottom:10px; }
.section-title { font-size:clamp(26px,4vw,42px);font-weight:750;line-height:1.2;margin-bottom:12px; }
.section-desc { color:var(--muted);font-size:15px;line-height:1.7;max-width:48em;margin-bottom:40px; }

/* ── Feature cards ── */
.feature-grid { display:grid;grid-template-columns:repeat(3,1fr);gap:20px; }
.feature-card { padding:28px;border-radius:18px;background:var(--panel);border:1px solid var(--line);backdrop-filter:blur(14px);transition:all .28s;position:relative;overflow:hidden; }
.feature-card:hover { transform:translateY(-4px);border-color:color-mix(in srgb,var(--accent) 30%,transparent);box-shadow:var(--shadow); }
.feature-card::after { content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--accent),var(--accent-deep));opacity:0;transition:opacity .28s; }
.feature-card:hover::after { opacity:1; }
.feature-icon { font-size:28px;margin-bottom:14px; }
.feature-card h3 { font-size:17px;font-weight:700;margin-bottom:8px; }
.feature-card p { font-size:13px;color:var(--muted);line-height:1.7; }

/* ── Tech ── */
.tech-grid { display:grid;grid-template-columns:repeat(2,1fr);gap:20px; }
.tech-card { padding:32px;border-radius:18px;background:var(--panel);border:1px solid var(--line);backdrop-filter:blur(14px);transition:all .28s; }
.tech-card:hover { border-color:color-mix(in srgb,var(--accent) 30%,transparent);box-shadow:var(--shadow); }
.tech-icon-lg { font-size:40px;margin-bottom:16px; }
.tech-card h3 { font-size:20px;font-weight:700;margin-bottom:8px; }
.tech-card p { color:var(--muted);line-height:1.7;font-size:14px; }
.tag-row { display:flex;gap:8px;flex-wrap:wrap;margin-top:16px; }
.ai-tag { padding:5px 14px;border-radius:999px;font-size:11px;font-weight:650;background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent); }

/* ── CTA ── */
.cta-section { position:relative;z-index:1;text-align:center;padding:100px 24px;}
.cta-section h2 { font-size:clamp(28px,5vw,44px);font-weight:750;margin-bottom:14px; }
.cta-section p { color:var(--muted);font-size:16px;max-width:32em;margin:0 auto 32px;line-height:1.7; }

/* ── Footer ── */
.landing-footer { position:relative;z-index:1;border-top:1px solid var(--line);padding:40px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;color:var(--muted);font-size:13px; }
.landing-footer a { color:var(--muted);text-decoration:none;transition:color .2s; }
.landing-footer a:hover { color:var(--accent); }

@media (max-width:900px) { .feature-grid{grid-template-columns:repeat(2,1fr)} .tech-grid{grid-template-columns:1fr} }
@media (max-width:600px) { .feature-grid{grid-template-columns:1fr} .nav-links a:not(.nav-cta){display:none} }
</style>
