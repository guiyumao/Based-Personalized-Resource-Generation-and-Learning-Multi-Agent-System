<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Reading, Guide, Document, DataAnalysis, User, Lock } from '@element-plus/icons-vue'

import { userApi, type AuthTokenResponse, type UserLoginPayload } from '../api'
import { useAuthStore } from '../stores/auth'
import { extractErrorMessage } from '../utils/api'
import learningIllustration from '../assets/learning-orbit.webp'
import ThemePicker from '../components/ThemePicker.vue'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const form = reactive<UserLoginPayload>({
  username: '',
  password: '',
})

async function handleLogin() {
  if (loading.value) {
    return
  }

  if (form.username.trim().length < 3) {
    ElMessage.error('用户名至少需要 3 个字符')
    return
  }

  if (form.password.length < 6) {
    ElMessage.error('密码至少需要 6 个字符')
    return
  }

  loading.value = true
  try {
    const { data } = await userApi.post<AuthTokenResponse>('/users/login', form)
    authStore.setAuth({
      token: data.access_token,
      user: {
        userId: data.user_id,
        username: data.username,
        role: data.role,
      },
    })
    ElMessage.success('登录成功')
    if (data.role === 'student') {
      try {
        const { data: status } = await userApi.get(`/users/${data.user_id}/profile/status`)
        if (!status.completed && !status.skipped) {
          await router.replace('/profile-setup')
          return
        }
      } catch {
        // proceed to workspace
      }
    }
    await router.replace(authStore.homeRoute)
  } catch (error: unknown) {
    ElMessage.error(extractErrorMessage(error, '登录失败，请检查用户名和密码'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="learning-login">
    <div class="login-stage">
      <aside class="learning-story" aria-label="平台特色">
        <router-link to="/" class="learning-logo">
          <span class="logo-symbol"><el-icon><Reading /></el-icon></span>
          <span><b>智学平台</b><small>个性化资源生成与学习多智能体系统</small></span>
        </router-link>
        <div class="story-heading">
          <span class="story-eyebrow">因你而异 · 随学而进</span>
          <h1>让学习有方向，<br /><em>让成长看得见。</em></h1>
          <p>从理解你的学习目标开始，让多智能体协同规划路径、生成资源，用每一次学习反馈，找到下一步。</p>
        </div>
        <figure class="learning-artwork">
          <div class="artwork-halo" aria-hidden="true"></div>
          <img :src="learningIllustration" width="1536" height="1024" fetchpriority="high" alt="翻开的书本延伸为知识星球，三个智能学习助手沿轨道协同探索" />
          <figcaption><span class="orbit-dot" aria-hidden="true"></span> 每一次探索，都有智能伙伴同行</figcaption>
        </figure>
        <ul class="learning-highlights" aria-label="平台特色">
          <li><el-icon><Guide /></el-icon><strong>专属学习路径</strong><small>由你的画像出发</small></li>
          <li><el-icon><Document /></el-icon><strong>个性化资源生成</strong><small>让知识适合你</small></li>
          <li><el-icon><DataAnalysis /></el-icon><strong>真实学情反馈</strong><small>让进步有迹可循</small></li>
        </ul>
        <p class="story-footnote"><span></span> 以学习者为中心，连接学生自主学习与教师教学支持</p>
      </aside>

      <main class="login-panel">
        <div class="login-tools"><ThemePicker /><router-link to="/" class="home-link">← 返回首页</router-link></div>
        <div class="login-form-content">
          <span class="welcome-label">欢迎回到智学</span>
          <h2>开启今天的学习旅程</h2>
          <p class="login-description">登录你的专属工作台，接着上一次的探索继续。</p>
          <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
            <el-form-item label="用户名" prop="username"><el-input id="login-username" v-model="form.username" :prefix-icon="User" autocomplete="username" placeholder="请输入用户名" /></el-form-item>
            <el-form-item label="密码" prop="password"><el-input id="login-password" v-model="form.password" :prefix-icon="Lock" type="password" show-password autocomplete="current-password" placeholder="请输入密码" /></el-form-item>
            <el-button native-type="submit" type="primary" :loading="loading" class="login-submit"><span>{{ loading ? '正在登录' : '登录工作台' }}</span><el-icon v-if="!loading"><ArrowRight /></el-icon></el-button>
          </el-form>
          <div class="login-register"><span>第一次来到这里？</span><router-link to="/register">创建学生账号 <span aria-hidden="true">↗</span></router-link></div>
          <div class="workspace-note">
            <div class="workspace-roles"><span>学生学习</span><i></i><span>教师教学</span><i></i><span>平台管理</span></div>
            <p>一个登录入口，按账号身份进入对应工作台</p>
          </div>
        </div>
        <p class="login-bottom">个性化学习 · 多智能体协同 · 真实学习证据</p>
      </main>
    </div>
  </div>
</template>

<style scoped>
.learning-login {
  --login-ink: var(--text);
  --login-muted: var(--muted);
  --login-primary: var(--accent);
  --el-color-primary: var(--accent);
  min-height: 100dvh;
  display: grid;
  place-items: center;
  padding: 32px;
  background: var(--bg);
  color: var(--login-ink);
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
}
.login-stage { width: min(1180px, 100%); display: grid; grid-template-columns: 1.08fr 1fr; border: 1px solid var(--line); border-radius: 24px; overflow: hidden; background: var(--panel-strong); box-shadow: var(--shadow); }
.learning-story { display: flex; flex-direction: column; padding: 36px 44px 28px; background: linear-gradient(150deg, color-mix(in srgb, var(--panel-strong) 94%, var(--accent)), color-mix(in srgb, var(--panel-strong) 86%, var(--accent))); color: var(--text); position: relative; }
.learning-story::before { content: ''; position: absolute; inset: 0; background-image: radial-gradient(var(--line) .7px, transparent .7px); background-size: 18px 18px; pointer-events: none; mask-image: linear-gradient(90deg, transparent, #000); }
.learning-story > * { position: relative; }
.learning-logo { display: flex; align-items: center; gap: 12px; width: fit-content; color: inherit; text-decoration: none; }
.logo-symbol { width: 42px; height: 42px; display: grid; place-items: center; background: var(--panel-strong); border-radius: 12px; color: var(--accent); font-size: 25px; }
.learning-logo b { display: block; font-size: 19px; letter-spacing: .06em; }
.learning-logo small { display: block; margin-top: 4px; font-size: 10px; color: var(--muted); letter-spacing: .03em; }
.story-heading { margin: 34px 0 0; }
.story-eyebrow { display: inline-flex; gap: 8px; align-items: center; color: var(--muted); font-size: 12px; letter-spacing: .18em; }
.story-eyebrow::before { content: ''; width: 20px; height: 1px; background: currentColor; }
.story-heading h1 { font-size: clamp(30px, 3.15vw, 42px); font-weight: 650; letter-spacing: -.035em; line-height: 1.45; margin: 14px 0 15px; }
.story-heading em { font-style: normal; color: var(--accent); }
.story-heading p { max-width: 410px; font-size: 13px; line-height: 1.95; color: var(--muted); margin: 0; }
.learning-artwork { position: relative; isolation: isolate; margin: 10px -26px 20px; text-align: center; }
.learning-artwork img { display: block; position: relative; width: 100%; height: 286px; object-fit: contain; }
.artwork-halo { position: absolute; z-index: -1; inset: 10% 10% 0; border-radius: 50%; background: radial-gradient(ellipse, var(--accent-soft), transparent 65%); }
.learning-artwork figcaption { display: inline-flex; align-items: center; gap: 7px; margin-top: 2px; color: var(--muted); font-size: 10px; letter-spacing: .07em; }
.orbit-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px var(--accent-soft); }
.learning-highlights { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); list-style: none; margin: auto 0 0; padding: 19px 0 0; border-top: 1px solid var(--line); gap: 12px; }
.learning-highlights li { display: flex; flex-direction: column; align-items: flex-start; gap: 7px; }
.learning-highlights .el-icon { color: var(--accent); font-size: 18px; margin-bottom: 2px; }
.learning-highlights strong { font-size: 12px; font-weight: 550; }
.learning-highlights small { color: var(--muted); font-size: 10px; }
.story-footnote { display: flex; align-items: center; gap: 8px; margin: 22px 0 0; font-size: 10px; color: var(--muted); line-height: 1.7; }
.story-footnote > span { width: 5px; height: 5px; border: 1px solid var(--muted); border-radius: 50%; flex-shrink: 0; }
.login-tools { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.login-panel { background: var(--panel-strong); display: flex; flex-direction: column; padding: 35px 44px 26px; }
.home-link { color: var(--login-muted); font-size: 12px; text-decoration: none; align-self: flex-end; }
.login-form-content { width: 100%; max-width: 360px; margin: auto; padding: 54px 0 42px; }
.welcome-label { font-size: 12px; color: var(--login-primary); font-weight: 600; letter-spacing: .1em; }
.login-form-content h2 { font-size: 27px; font-weight: 650; letter-spacing: -.045em; margin: 12px 0; line-height: 1.4; }
.login-description { color: var(--login-muted); font-size: 12px; line-height: 1.8; margin: 0 0 32px; }
.login-form-content :deep(.el-form-item) { margin-bottom: 21px; }
.login-form-content :deep(.el-form-item__label) { color: var(--text); font-size: 12px; font-weight: 600; padding-bottom: 8px; }
.login-form-content :deep(.el-input__wrapper) { min-height: 48px; border-radius: 8px; background: var(--surface-soft); box-shadow: 0 0 0 1px var(--line) inset; padding: 0 14px; transition: box-shadow .2s; }
.login-form-content :deep(.el-input__wrapper:hover) { box-shadow: 0 0 0 1px var(--accent) inset; }
.login-form-content :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px var(--accent) inset, 0 0 0 3px var(--accent-soft); }
.login-form-content :deep(.el-input__inner) { color: var(--text); font-size: 13px; height: 48px; }
.login-form-content :deep(.el-input__inner::placeholder) { color: var(--muted); }
.login-form-content :deep(.el-input__prefix) { color: var(--muted); margin-right: 6px; }
.login-form-content :deep(input:-webkit-autofill) { -webkit-text-fill-color: var(--text); box-shadow: 0 0 0 1000px var(--surface-soft) inset; }
.login-submit.el-button { width: 100%; height: 49px; margin-top: 5px; background: var(--accent); border-color: var(--accent); border-radius: 8px; font-size: 14px; font-weight: 600; box-shadow: 0 6px 14px var(--accent-soft); }
.login-submit.el-button:hover { background: var(--accent-deep); border-color: var(--accent-deep); }
.login-submit :deep(.el-icon) { margin-left: 12px; }
.login-register { display: flex; justify-content: center; gap: 9px; margin-top: 24px; font-size: 12px; color: var(--login-muted); }
.login-register a { color: var(--login-primary); text-decoration: none; font-weight: 600; }
.login-register a:hover, .home-link:hover { text-decoration: underline; color: var(--login-primary); }
.workspace-note { margin-top: 37px; padding-top: 24px; border-top: 1px solid var(--line); text-align: center; }
.workspace-roles { display: flex; align-items: center; justify-content: center; gap: 13px; font-size: 11px; color: var(--muted); }
.workspace-roles i { width: 3px; height: 3px; border-radius: 50%; background: var(--line); }
.workspace-note p { font-size: 10px; color: var(--muted); margin: 10px 0 0; }
.login-bottom { text-align: center; color: var(--muted); font-size: 10px; letter-spacing: .06em; margin: 0; }
.learning-login a:focus-visible, .login-submit:focus-visible { outline: 3px solid var(--accent); outline-offset: 5px; border-radius: 4px; }
@media (min-width: 1600px) { .login-stage { min-height: 760px; } .learning-story { padding: 40px 50px 30px; } .story-heading { margin-top: 36px; } .learning-artwork img { height: 300px; } }
@media (max-width: 1000px) { .learning-story { padding: 30px; } .login-panel { padding-inline: 30px; } .story-heading h1 { font-size: 32px; } .learning-artwork img { height: 240px; } .learning-highlights { gap: 7px; } .learning-highlights strong { font-size: 10px; } .login-form-content h2 { font-size: 24px; } }
@media (max-width: 760px) {
  .learning-login { padding: 16px; }
  .login-stage { grid-template-columns: 1fr; max-width: 480px; border-radius: 18px; }
  .learning-story { padding: 24px; }
  .learning-logo small { font-size: 9px; }
  .story-heading { margin: 25px 0 0; z-index: 1; width: fit-content; }
  .story-eyebrow { font-size: 10px; }
  .story-heading h1 { font-size: 24px; margin: 10px 0 2px; }
  .story-heading p, .learning-highlights, .story-footnote { display: none; }
  .learning-artwork { position: absolute; width: 132px; height: 145px; right: 8px; top: 82px; margin: 0; pointer-events: none; }
  .learning-artwork img { height: 145px; }
  .learning-artwork figcaption { display: none; }
  .login-panel { padding: 22px 24px; }
  .login-form-content { padding: 25px 0 28px; }
  .login-form-content h2 { font-size: 24px; }
  .login-description { margin-bottom: 25px; }
  .workspace-note { margin-top: 26px; padding-top: 20px; }
}
@media (max-width: 370px) { .story-heading h1 { font-size: 21px; } .learning-artwork { width: 95px; right: 4px; } }
@media (prefers-reduced-motion: reduce) { .learning-login *, .learning-login *::before { transition: none !important; } }
</style>
