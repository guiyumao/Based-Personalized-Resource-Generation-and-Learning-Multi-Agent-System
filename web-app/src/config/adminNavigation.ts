import { Collection, DocumentChecked, EditPen, House, Setting, Tickets, User, School, Cpu } from '@element-plus/icons-vue'

// These feature IDs also select the router components. Only existing operations belong here.
export const adminNavigation = [
  { key:'notifications',label:'消息发布',description:'按角色、班级、课程和个人发布真实通知',group:'教学与资源',icon:Tickets,route:'/admin/notifications',routeName:'admin-notifications',roles:['admin'] as const },
  { key: 'overview', label: '数据看板', description: '平台账号、学习路径、资源与近期作答统计', group: '管理概览', icon: House, route: '/admin', routeName: 'admin', roles: ['admin'] as const },
  { key: 'users', label: '用户管理', description: '账号搜索、分页、新增、启停与角色分配', group: '用户与权限', icon: User, route: '/admin/users', routeName: 'admin-users', roles: ['admin'] as const },
  { key: 'subjects', label: '学科管理', description: '系统学科目录与新增学科', group: '学科与知识库', icon: School, route: '/admin/subjects', routeName: 'admin-subjects', roles: ['admin'] as const },
  { key: 'construction', label: '学科规划与知识点', description: '课程结构确认、知识点管理与分批建设', group: '学科与知识库', icon: School, route: '/admin/knowledge/construction', routeName: 'admin-construction', roles: ['admin'] as const },
  { key: 'knowledge', label: '知识库管理', description: '语料、来源、检索状态与增量索引', group: '学科与知识库', icon: Collection, route: '/admin/knowledge', routeName: 'admin-knowledge', roles: ['admin'] as const },
  { key: 'review', label: '审核与发布', description: '候选审核、发布验证、版本比较与恢复', group: '学科与知识库', icon: DocumentChecked, route: '/admin/knowledge/review', routeName: 'admin-review', roles: ['admin'] as const },
  { key: 'maintenance', label: '自动维护配置', description: '定期巡检、自动补充策略与执行报告', group: '学科与知识库', icon: Setting, route: '/admin/knowledge/maintenance', routeName: 'admin-maintenance', roles: ['admin'] as const },
  { key: 'resources', label: '学习资源管理', description: '资源预览、审核状态、发布与归档', group: '教学与资源', icon: Collection, route: '/admin/resources', routeName: 'admin-resources', roles: ['admin'] as const },
  { key: 'tasks', label: 'AI 用量与任务监控', description: 'Token 调用台账、预算、Worker 心跳、执行尝试及知识建设任务', group: 'AI 与任务管理', icon: Cpu, route: '/admin/tasks', routeName: 'admin-tasks', roles: ['admin'] as const },
  { key: 'prompts', label: '提示词与图文配置', description: 'Prompt 模板维护与图片 Provider 配置状态（BLOCKED 入口）', group: 'AI 内容编排', icon: EditPen, route: '/admin/prompts', routeName: 'admin-prompts', roles: ['admin'] as const },
  { key: 'checkin', label: '打卡与签到审计', description: '全校打卡任务汇总、出勤统计与教师人工调整审计', group: '教学与资源', icon: DocumentChecked, route: '/admin/checkin', routeName: 'admin-checkin', roles: ['admin'] as const },
  { key: 'logs', label: '操作日志', description: '系统审计记录与级别筛选', group: '系统运维', icon: Tickets, route: '/admin/logs', routeName: 'admin-logs', roles: ['admin'] as const },
  { key: 'settings', label: '系统配置', description: '现有非敏感配置参数维护', group: '系统运维', icon: Setting, route: '/admin/settings', routeName: 'admin-settings', roles: ['admin'] as const },
]
