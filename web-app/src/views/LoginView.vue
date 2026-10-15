<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Connection, DataAnalysis, Guide } from '@element-plus/icons-vue'

import { userApi, type AuthTokenResponse, type UserLoginPayload } from '../api'
import { useAuthStore } from '../stores/auth'
import { extractErrorMessage } from '../utils/api'

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
  <div class="auth-shell">
    <div class="auth-stage">
      <aside class="auth-brand-panel">
        <router-link to="/" class="auth-logo"><span><i></i><i></i><i></i></span><b>智学平台</b></router-link>
        <div class="auth-brand-copy">
          <span class="auth-eyebrow">PERSONALIZED LEARNING OS</span>
          <h1>让每一次学习<br />都有清晰的下一步</h1>
          <p>多智能体协同生成学习路径、课件与练习，并用真实学习数据持续调整。</p>
        </div>
        <div class="auth-feature-list">
          <div><el-icon><Guide /></el-icon><span><strong>个性化路径</strong><small>根据画像与掌握度动态调整</small></span></div>
          <div><el-icon><DataAnalysis /></el-icon><span><strong>学习证据</strong><small>报告、错题和进度都来自真实记录</small></span></div>
          <div><el-icon><Connection /></el-icon><span><strong>多端协同</strong><small>学生、教师和管理员进入各自工作台</small></span></div>
        </div>
      </aside>

      <main class="auth-card">
        <div class="login-kicker">欢迎回来</div>
        <h2>登录学习工作台</h2>
        <p>系统会根据账号角色进入对应的学生端、教师端或管理端。</p>
        <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
          <el-form-item label="用户名"><el-input v-model="form.username" autocomplete="username" placeholder="请输入用户名" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" placeholder="请输入密码" /></el-form-item>
          <el-button native-type="submit" type="primary" :loading="loading" class="auth-button">登录</el-button>
        </el-form>
        <div class="auth-footer"><span>还没有账号？</span><router-link to="/register">立即注册</router-link></div>
        <router-link to="/" class="auth-back-link">返回产品首页</router-link>
      </main>
      </div>
  </div>
</template>
