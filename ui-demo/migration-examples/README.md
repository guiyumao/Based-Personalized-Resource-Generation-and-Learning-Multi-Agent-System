# 迁移示例说明

## 迁移模式

每个面板从 StudentView.vue 迁移到独立视图的标准流程：

### 第 1 步：复制模板
从 `StudentView.vue` 的 `<template>` 中，找到对应面板的 `<section>` 块，
**完整复制**到新视图的 `<template>` 中。

### 第 2 步：复制逻辑
从 `<script setup>` 中复制相关代码：
- 该面板使用的 `ref` / `reactive` / `computed`
- 该面板使用的 `async function`（API 调用）
- 该面板依赖的类型 import

### 第 3 步：去除全屏壳
删除这些旧包装：
```html
<!-- 删除这些 -->
<div class="dashboard-shell student-workspace-shell">
<div class="aurora aurora-a"></div>
<div class="aurora aurora-b"></div>
```

AppLayout 已经提供了统一的背景和布局。

### 第 4 步：替换 CSS 类
所有卡片/面板使用主题 CSS 变量：

| 旧写法（硬编码深色） | 新写法（主题变量） |
|---|---|
| `background: rgba(248,251,255,0.98)` | `background: var(--panel)` |
| `border-color: rgba(129,160,204,0.14)` | `border: 1px solid var(--line)` |
| `color: #14253d` | `color: var(--text)` |
| `color: #5d6f8e` | `color: var(--muted)` |
| `color: #0f7f79` | `color: var(--accent)` |
| `box-shadow: 0 24px 70px rgba(2,10,24,0.4)` | `box-shadow: var(--shadow)` |

### 第 5 步：保留功能完整性
- API 调用逻辑完全保留（包括 fallback 处理）
- Element Plus 组件保持原样
- 错误处理机制不变
- sessionStorage 持久化逻辑不变

---

## 各视图当前状态

| 视图 | 状态 | 需要做什么 |
|---|---|---|
| DashboardView | 简化版 mock | 复制 hero-panel + card-grid + sidebar-briefing 的真实逻辑 |
| LearningPathView | 简化版 mock | 复制 path panel 的 generateLearningPath/Coordination 逻辑 |
| CoursewareView | **未动**，风格冲突 | 去掉 dashboard-shell 壳，使用主题变量 |
| ExerciseView | 简化版 mock | 复制 exercise 面板的 generate/submit/feedback 逻辑 |
| MistakeNotebookView | **未动**，风格冲突 | 去掉 dashboard-shell 壳，使用主题变量 |
| KnowledgeGraphView | stub 占位 | 复制 vis-network 渲染逻辑 + 图数据 API（用户说暂缓） |
| ReportView | stub 占位 | 复制 report panel 的 fetchReports/阶段报告展示 |
| QaView | stub 空壳 | 完整复制 askQaAgent + 结构化分析展示 + fallback |
