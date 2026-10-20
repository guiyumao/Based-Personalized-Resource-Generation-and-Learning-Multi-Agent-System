<script setup lang="ts">
import { useAdminWorkspace } from '../../composables/useAdminWorkspace'
const { authStore, userPage, userKeyword, userRole, newUser, currentUserPage, roleForm, roleResult, loading, fetchUsers, selectUser, createUser, setUserStatus, assignRole, logout } = useAdminWorkspace('users')
</script>
<template>
<div class="admin-module">        <section class="workspace-panel">
          <div class="panel-heading"><div><div class="panel-kicker">用户管理</div><h2>账号目录</h2></div></div>
          <el-form :model="newUser" label-position="top" class="admin-create-user">
            <div class="action-row"><el-input v-model="newUser.username" placeholder="新用户名" /><el-input v-model="newUser.password" type="password" show-password placeholder="初始密码，至少 6 位" /></div>
            <div class="action-row"><el-input v-model="newUser.email" placeholder="邮箱（可选）" /><el-select v-model="newUser.role" style="min-width:130px"><el-option label="学生" value="student" /><el-option label="教师" value="teacher" /><el-option label="管理员" value="admin" /></el-select><el-button type="primary" :loading="loading.createUser" @click="createUser">创建账号</el-button></div>
          </el-form>
          <div class="action-row">
            <el-input v-model="userKeyword" clearable placeholder="搜索用户名或邮箱" @keyup.enter="fetchUsers(1)" />
            <el-select v-model="userRole" style="max-width:150px" @change="fetchUsers(1)">
              <el-option label="全部角色" value="" /><el-option label="学生" value="student" /><el-option label="教师" value="teacher" /><el-option label="管理员" value="admin" />
            </el-select>
            <el-button :loading="loading.users" @click="fetchUsers(1)">查询</el-button>
          </div>
          <div class="list-stack">
            <div v-for="item in userPage?.items ?? []" :key="item.id" class="list-card static admin-user-row">
              <div><strong>#{{ item.id }} {{ item.username }}</strong><span>{{ item.email || '未填写邮箱' }} · {{ item.role }} · {{ item.is_active ? '标记启用' : '标记停用' }}</span></div>
              <div class="action-row"><el-button size="small" @click="selectUser(item)">选择分配角色</el-button><el-button size="small" :disabled="loading.status || item.id === authStore.user?.userId" @click="setUserStatus(item)">{{ item.is_active ? '停用' : '启用' }}</el-button></div>
            </div>
            <div v-if="loading.users" class="empty-state">正在加载用户...</div>
            <div v-else-if="!userPage?.items.length" class="empty-state">没有匹配的账号。</div>
          </div>
          <el-pagination v-if="userPage && userPage.total > userPage.size" :current-page="currentUserPage" :page-size="userPage.size" :total="userPage.total" layout="prev, pager, next" style="margin-top:14px" @current-change="fetchUsers" />
        </section>        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">角色管理</div>
              <h2>用户角色分配</h2>
            </div>
          </div>
          <el-form :model="roleForm" label-position="top">
            <el-form-item label="用户 ID">
              <el-input-number v-model="roleForm.user_id" :min="1" />
            </el-form-item>
            <el-form-item label="目标角色">
              <el-select v-model="roleForm.role">
                <el-option label="student" value="student" />
                <el-option label="teacher" value="teacher" />
                <el-option label="admin" value="admin" />
              </el-select>
            </el-form-item>
          </el-form>
          <div class="action-row">
            <el-button type="primary" :loading="loading.role" @click="assignRole">分配角色</el-button>
            <el-button plain @click="logout">退出登录</el-button>
          </div>
          <pre v-if="roleResult" class="result-box">{{ JSON.stringify(roleResult, null, 2) }}</pre>
        </section></div>
</template>
<style src="./admin.css"></style>
