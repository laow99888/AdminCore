/** 可选模块页面只在完整构建中发布。 */
import type { RouteRecordRaw } from 'vue-router'

export const moduleRoutes: RouteRecordRaw[] = [
  {
    path: '/files',
    name: 'FileList',
    component: () => import('../views/files/FileListView.vue'),
    meta: { title: "文件管理", requiresAuth: true },
  },

  {
    path: '/approvals',
    name: 'ApprovalList',
    component: () => import('../views/approvals/ApprovalListView.vue'),
    meta: { title: "审批工作流", requiresAuth: true },
  },

  {
    path: '/notifications',
    name: 'NotificationList',
    component: () => import('../views/notifications/NotificationListView.vue'),
    meta: { title: "通知中心", requiresAuth: true },
  },

  {
    path: '/tasks',
    name: 'TaskList',
    component: () => import('../views/tasks/TaskListView.vue'),
    meta: { title: "任务中心", requiresAuth: true },
  },

  { path: '/notifications/announcements', name: 'Announcements', component: () => import('../views/notifications/AnnouncementView.vue'), meta: { title: '通知公告', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/notifications/templates', name: 'MessageTemplates', component: () => import('../views/notifications/MessageTemplatesView.vue'), meta: { title: '通知模板', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/system/cache', name: 'CacheManagement', component: () => import('../views/system/CacheManagementView.vue'), meta: { title: '缓存管理', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/organization/posts', name: 'PostManagement', component: () => import('../views/system/PostManagementView.vue'), meta: { title: '岗位与任职', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/system/information', name: 'SystemInformation', component: () => import('../views/system/SystemDiagnosticsView.vue'), meta: { title: '系统信息', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/system/monitor', name: 'SystemMonitor', component: () => import('../views/system/SystemDiagnosticsView.vue'), props: { monitor: true }, meta: { title: '服务监控', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/tasks/schedules', name: 'MaintenanceSchedules', component: () => import('../views/tasks/MaintenanceScheduleView.vue'), meta: { title: '定时维护', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/tasks/backups', name: 'BackupManagement', component: () => import('../views/tasks/BackupManagementView.vue'), meta: { title: '备份与恢复', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/files/recycle', name: 'RecycleBin', component: () => import('../views/files/RecycleBinView.vue'), meta: { title: '文件回收站', requiresAuth: true } },
  { path: '/organization', name: 'Organization', component: () => import('../views/system/OrganizationView.vue'), meta: { title: '组织与数据权限', requiresAuth: true, hasPageHeading: true } },
  { path: '/system/config', name: 'SystemConfig', component: () => import('../views/system/SystemConfigView.vue'), meta: { title: '系统参数', requiresAuth: true } },
  { path: '/system/dictionaries', name: 'Dictionaries', component: () => import('../views/system/DictionaryListView.vue'), meta: { title: '数据字典', requiresAuth: true } },
]
