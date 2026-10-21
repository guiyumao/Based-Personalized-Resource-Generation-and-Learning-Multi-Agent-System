import type { Component } from 'vue'
import {
  Aim,
  ChatDotRound,
  Collection,
  CollectionTag,
  DocumentChecked,
  EditPen,
  Guide,
  Histogram,
  House,
  Notebook,
  Reading,
  School,
  Share,
  TrendCharts,
  User,
  UserFilled,
} from '@element-plus/icons-vue'
import { adminNavigation } from './adminNavigation'

export type AppRole = 'student' | 'teacher' | 'admin'

export interface NavigationItem {
  key: string
  label: string
  description: string
  icon: Component
  route: string
  routeName: string
  group: string
  roles: readonly AppRole[]
}

export const navigationItems: NavigationItem[] = [
  { key: 'dashboard', label: '学习概览', description: '学习指标、画像与近期活动', icon: House, route: '/student/dashboard', routeName: 'student-dashboard', group: '学习工作台', roles: ['student'] },
  { key: 'learning-path', label: '学习路径', description: '规划阶段任务与学习顺序', icon: Guide, route: '/student/learning-path', routeName: 'student-learning-path', group: '学习工作台', roles: ['student'] },
  { key: 'workspace', label: '学习工作区', description: '目录、资源与助手共享学习上下文', icon: Reading, route: '/student/workspace', routeName: 'student-workspace', group: '学习工作台', roles: ['student'] },
  { key: 'courseware', label: '课件中心', description: '生成、阅读与管理个性化课件', icon: Reading, route: '/student/courseware', routeName: 'student-courseware', group: '学习工作台', roles: ['student'] },
  { key: 'classroom', label: '班级空间', description: '课程作业、讨论与教学通知', icon: School, route: '/student/classroom', routeName: 'student-classroom', group: '学习工作台', roles: ['student'] },
  { key: 'exercise', label: '练习测评', description: '分层练习、提交与反馈', icon: EditPen, route: '/student/exercise', routeName: 'student-exercise', group: '练习与诊断', roles: ['student'] },
  { key: 'mistakes', label: '错题本', description: '错因分析与针对性重练', icon: Notebook, route: '/student/mistakes', routeName: 'student-mistakes', group: '练习与诊断', roles: ['student'] },
  { key: 'favorites', label: '收藏本', description: '收藏题目与重点解析', icon: CollectionTag, route: '/student/favorites', routeName: 'student-favorites', group: '练习与诊断', roles: ['student'] },
  { key: 'study-tools', label: '笔记与闪卡', description: '记录学习要点并复习到期闪卡', icon: Notebook, route: '/student/study-tools', routeName: 'student-study-tools', group: '练习与诊断', roles: ['student'] },
  { key: 'knowledge-graph', label: '知识图谱', description: '知识依赖、缺口与关联资源', icon: Share, route: '/student/knowledge-graph', routeName: 'student-knowledge-graph', group: '练习与诊断', roles: ['student'] },
  { key: 'report', label: '学习报告', description: '阶段成果、证据与下一步建议', icon: TrendCharts, route: '/student/report', routeName: 'student-report', group: '智能支持', roles: ['student'] },
  { key: 'analytics', label: '学习分析', description: '学习趋势、活动热力图、作答与复习统计', icon: Histogram, route: '/student/analytics', routeName: 'student-analytics', group: '智能支持', roles: ['student'] },
  { key: 'profile', label: '学习画像', description: '编辑学习偏好并查看真实行为证据', icon: User, route: '/student/profile', routeName: 'student-profile', group: '智能支持', roles: ['student'] },
  { key: 'transcripts', label: '成绩单分析', description: '导入成绩、定位薄弱点并生成学习方案', icon: DocumentChecked, route: '/student/transcripts', routeName: 'student-transcripts', group: '智能支持', roles: ['student'] },
  { key: 'qa', label: '智能问答', description: '结合画像与知识库的上下文问答', icon: ChatDotRound, route: '/student/qa', routeName: 'student-qa', group: '智能支持', roles: ['student'] },
  { key: 'resources', label: '学习资源', description: '知识库、官方课件与已保存资源', icon: Collection, route: '/student/resources', routeName: 'student-resources', group: '智能支持', roles: ['student'] },
  { key: 'teacher-overview', label: '教师总览', description: '班级、学生与教学任务概览', icon: School, route: '/teacher/overview', routeName: 'teacher-overview', group: '教学工作台', roles: ['teacher'] },
  { key: 'teacher-classes', label: '班级管理', description: '班级创建、进度与学生名册', icon: UserFilled, route: '/teacher/classes', routeName: 'teacher-classes', group: '教学工作台', roles: ['teacher'] },
  { key: 'teacher-knowledge-base', label: '课程知识库', description: '检索课程内容并生成教学草稿', icon: Collection, route: '/teacher/knowledge-base', routeName: 'teacher-knowledge-base', group: '教学内容', roles: ['teacher'] },
  { key: 'teacher-scopes', label: '学习范围', description: '划定知识点、目标与课件投放', icon: Aim, route: '/teacher/scopes', routeName: 'teacher-scopes', group: '教学内容', roles: ['teacher'] },
  { key: 'teacher-students', label: '学生洞察', description: '学生掌握度、错题与学习诊断', icon: User, route: '/teacher/students', routeName: 'teacher-students', group: '分析与任务', roles: ['teacher'] },
  { key: 'teacher-analytics', label: '教学分析', description: '班级统计、薄弱知识点与建议', icon: Histogram, route: '/teacher/analytics', routeName: 'teacher-analytics', group: '分析与任务', roles: ['teacher'] },
  { key: 'teacher-transcripts', label: '成绩单分析', description: '批量导入班级成绩并生成分层教学建议', icon: DocumentChecked, route: '/teacher/transcripts', routeName: 'teacher-transcripts', group: '分析与任务', roles: ['teacher'] },
  { key: 'teacher-homework', label: '作业管理', description: '布置教学任务并提交批改结果', icon: DocumentChecked, route: '/teacher/homework', routeName: 'teacher-homework', group: '分析与任务', roles: ['teacher'] },
  ...adminNavigation,
]

export function navigationForRole(role?: string) {
  return navigationItems.filter((item) => item.roles.includes(role as AppRole))
}

export function navigationItemForRoute(routeName?: string | null) {
  return navigationItems.find((item) => item.routeName === routeName)
}
