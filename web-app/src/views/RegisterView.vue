<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Connection, DataAnalysis, Guide } from '@element-plus/icons-vue'

import { userApi, type AuthTokenResponse, type UserRegisterPayload } from '../api'
import { useAuthStore } from '../stores/auth'
import { extractErrorMessage } from '../utils/api'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const form = reactive<UserRegisterPayload>({
  username: '',
  password: '',
  role: 'student',
  email: '',
})

async function handleRegister() {
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
    const { data } = await userApi.post<AuthTokenResponse>('/users/register', form)
    authStore.setAuth({
      token: data.access_token,
      user: {
        userId: data.user_id,
        username: data.username,
        role: data.role,
      },
    })
    ElMessage.success('注册成功，已自动登录')
    if (data.role === 'student') {
      await router.replace('/profile-setup')
      return
    }
    await router.replace(authStore.homeRoute)
  } catch (error: unknown) {
    ElMessage.error(extractErrorMessage(error, '注册失败，请检查输入信息'))
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
          <h1>从一份真实画像<br />开始个性化学习</h1>
          <p>注册后学生可构建学习画像，教师可管理班级与教学范围，管理员可维护平台配置。</p>
        </div>
        <div class="auth-feature-list">
          <div><el-icon><Guide /></el-icon><span><strong>角色工作台</strong><small>注册后自动进入对应功能与数据范围</small></span></div>
          <div><el-icon><DataAnalysis /></el-icon><span><strong>可追溯评估</strong><small>用实际练习和错题记录支撑学习建议</small></span></div>
          <div><el-icon><Connection /></el-icon><span><strong>智能体协同</strong><small>画像、路径、资源与评估保持上下文衔接</small></span></div>
        </div>
      </aside>

      <main class="auth-card register-card">
        <div class="login-kicker">创建账号</div>
        <h2>开始使用智学平台</h2>
        <p>请选择真实身份，系统将据此分配工作台与数据权限。</p>
        <el-form :model="form" label-position="top" @submit.prevent="handleRegister">
          <el-form-item label="用户名"><el-input v-model="form.username" autocomplete="username" placeholder="至少 3 个字符" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" placeholder="至少 6 位密码" /></el-form-item>
          <el-form-item label="身份"><el-select v-model="form.role" placeholder="请选择身份" style="width:100%"><el-option label="学生" value="student" /><el-option label="教师" value="teacher" /><el-option label="管理员" value="admin" /></el-select></el-form-item>
          <el-form-item label="邮箱（可选）"><el-input v-model="form.email" type="email" autocomplete="email" placeholder="name@example.com" /></el-form-item>
          <el-button native-type="submit" type="primary" :loading="loading" class="auth-button">注册并进入系统</el-button>
        </el-form>
        <div class="auth-footer"><span>已经有账号？</span><router-link to="/login">返回登录</router-link></div>
        <router-link to="/" class="auth-back-link">返回产品首页</router-link>
      </main>
    </div>
  </div>
</template>
