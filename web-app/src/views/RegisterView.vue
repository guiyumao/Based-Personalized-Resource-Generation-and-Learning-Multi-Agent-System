<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

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
    <div class="auth-card">
      <div class="login-kicker">Learning Agent Platform</div>
      <h1>注册新账号</h1>
      <p>创建账号后，系统会根据你的身份自动进入学生端、教师端或管理员端。</p>

      <el-form :model="form" label-position="top" @submit.prevent="handleRegister">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入至少 6 位密码" />
        </el-form-item>
        <el-form-item label="身份">
          <el-select v-model="form.role" placeholder="请选择身份">
            <el-option label="学生" value="student" />
            <el-option label="教师" value="teacher" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="请输入邮箱（可选）" />
        </el-form-item>
        <el-button native-type="submit" type="primary" :loading="loading" class="auth-button">
          注册并进入系统
        </el-button>
      </el-form>

      <div class="auth-footer">
        <span>已经有账号？</span>
        <router-link to="/login">返回登录</router-link>
      </div>
    </div>
  </div>
</template>
