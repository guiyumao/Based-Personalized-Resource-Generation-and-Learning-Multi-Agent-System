---
name: routing-guard-plan
description: 首页路由守卫和登录跳转逻辑的待实现计划
metadata:
  type: project
---

# 首页路由守卫与登录拦截计划

## 需求

首页 (landing page) 是公开页面，不需要登录即可访问。点击"免费体验"按钮后的跳转逻辑：

1. **首页不拦截**：`/` 或 `/landing` 路由不设 `requiresAuth`，任何人可访问
2. **检查登录状态**：点击"免费体验"时，前端检查是否已登录
   - 已登录 → 跳转到 `/student` (学生) 或 `/teacher` (教师) 或 `/admin` (管理员)
   - 未登录 → 跳转到 `/login`
3. **登录后跳转**：登录成功后根据角色自动跳转到对应工作台

## 当前状态

目前 ui-demo 中的按钮是静态 HTML，直接跳转到 `login.html`。
后续集成到 Vue 项目时需要改为动态逻辑。

## 实现方案（参考）

```
// router.ts
{ path: '/',         component: LandingView, meta: { requiresAuth: false } },
{ path: '/login',    component: LoginView,   meta: { requiresAuth: false, guestOnly: true } },
{ path: '/student',  component: StudentView, meta: { requiresAuth: true, roles: ['student','teacher','admin'] } },
{ path: '/teacher',  component: TeacherView, meta: { requiresAuth: true, roles: ['teacher'] } },
{ path: '/admin',    component: AdminView,   meta: { requiresAuth: true, roles: ['admin'] } },
```

```
// 按钮点击逻辑
function handleEnterClick() {
  const token = authStore.token
  if (token && authStore.user) {
    router.push(authStore.homeRoute)  // 基于角色
  } else {
    router.push('/login')
  }
}
```

## 后端配合

- 公开接口（首页数据）不加 `Depends(get_current_user)`
- `/users/login`、`/users/register` 等接口不加认证依赖
- 业务接口保持 JWT Bearer Token 校验

**Why:** 用户点击"免费体验"后应该根据登录状态智能跳转，而不是无脑跳到登录页。目前先跳登录页作为模板占位。

**How to apply:** 实现路由守卫和按钮逻辑时参考以上方案。
