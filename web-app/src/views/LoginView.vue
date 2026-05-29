<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

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
    <div class="auth-card">
      <div class="login-kicker">Learning Agent Platform</div>
      <h1>登录个性化学习系统</h1>
      <p>使用学生、教师或管理员账号登录，系统会自动进入对应工作台。</p>

      <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
            placeholder="请输入密码"
          />
        </el-form-item>
        <el-button native-type="submit" type="primary" :loading="loading" class="auth-button">
          登录
        </el-button>
      </el-form>

      <div class="auth-footer">
        <span>还没有账号？</span>
        <router-link to="/register">立即注册</router-link>
      </div>
    </div>
  </div>
</template>
