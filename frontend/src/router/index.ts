import { uiText } from "@/i18n/uiText"
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'
import { useModuleStore } from '@/stores/modules'
import { canAccessPage } from './access'

// 懒加载视图
const LoginView = () => import('../views/auth/LoginView.vue')
const DashboardView = () => import('../views/dashboard/DashboardView.vue')
const UserListView = () => import('../views/users/UserListView.vue')
const RoleListView = () => import('../views/system/RoleListView.vue')
const MenuListView = () => import('../views/system/MenuListView.vue')
const FileListView = () => import('../views/files/FileListView.vue')
const ApprovalListView = () => import('../views/approvals/ApprovalListView.vue')
const NotificationListView = () => import('../views/notifications/NotificationListView.vue')
const TaskListView = () => import('../views/tasks/TaskListView.vue')
const OperationLogView = () => import('../views/logs/OperationLogView.vue')
const SettingsView = () => import('../views/settings/SettingsView.vue')
const NotFoundView = () => import('../views/errors/NotFoundView.vue')
const ServiceErrorView = () => import('../views/errors/ServiceErrorView.vue')

const routes: RouteRecordRaw[] = [
  { path: '/system/cache', name: 'CacheManagement', component: () => import('../views/system/CacheManagementView.vue'), meta: { title: '缓存管理', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/organization/posts', name: 'PostManagement', component: () => import('../views/system/PostManagementView.vue'), meta: { title: '岗位与任职', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/system/information', name: 'SystemInformation', component: () => import('../views/system/SystemDiagnosticsView.vue'), meta: { title: '系统信息', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/system/monitor', name: 'SystemMonitor', component: () => import('../views/system/SystemDiagnosticsView.vue'), props: { monitor: true }, meta: { title: '服务监控', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/tasks/schedules', name: 'MaintenanceSchedules', component: () => import('../views/tasks/MaintenanceScheduleView.vue'), meta: { title: '定时维护', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/change-password', component: () => import('../views/auth/ChangePasswordView.vue'), meta: { requiresAuth: true } },
  { path: '/files/recycle', name: 'RecycleBin', component: () => import('../views/files/RecycleBinView.vue'), meta: { title: '文件回收站', requiresAuth: true } },
  { path: '/reliability/events', name: 'ReliableEvents', component: () => import('../views/system/ReliableEventsView.vue'), meta: { title: '可靠事件', requiresAuth: true } },
  { path: '/organization', name: 'Organization', component: () => import('../views/system/OrganizationView.vue'), meta: { title: '组织与数据权限', requiresAuth: true, hasPageHeading: true } },
  { path: '/system/config', name: 'SystemConfig', component: () => import('../views/system/SystemConfigView.vue'), meta: { title: '系统参数', requiresAuth: true } },
  { path: '/system/dictionaries', name: 'Dictionaries', component: () => import('../views/system/DictionaryListView.vue'), meta: { title: '数据字典', requiresAuth: true } },
  { path: '/403', component: ServiceErrorView },
  { path: '/500', component: ServiceErrorView },
  { path: '/unavailable', component: ServiceErrorView },
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: {
      title: "登录",
      requiresAuth: false,
    },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: DashboardView,
    meta: {
      title: "仪表盘",
      requiresAuth: true,
    },
  },
  {
    path: '/users',
    name: 'UserList',
    component: UserListView,
    meta: { title: "用户管理", requiresAuth: true },
  },
  {
    path: '/roles',
    name: 'RoleList',
    component: RoleListView,
    meta: { title: "角色权限", requiresAuth: true },
  },
  {
    path: '/menus',
    name: 'MenuList',
    component: MenuListView,
    meta: { title: "菜单管理", requiresAuth: true },
  },
  {
    path: '/files',
    name: 'FileList',
    component: FileListView,
    meta: { title: "文件管理", requiresAuth: true },
  },
  {
    path: '/approvals',
    name: 'ApprovalList',
    component: ApprovalListView,
    meta: { title: "审批工作流", requiresAuth: true },
  },
  {
    path: '/notifications',
    name: 'NotificationList',
    component: NotificationListView,
    meta: { title: "通知中心", requiresAuth: true },
  },
  {
    path: '/tasks',
    name: 'TaskList',
    component: TaskListView,
    meta: { title: "任务中心", requiresAuth: true },
  },
  {
    path: '/logs',
    name: 'OperationLog',
    component: OperationLogView,
    meta: { title: "操作日志", requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: SettingsView,
    meta: { title: "系统设置", requiresAuth: true, preserveOnLocaleChange: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: NotFoundView,
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// 路由守卫（权限检查）
router.beforeEach(async (to, _from, next) => {
  const isAuthenticated = localStorage.getItem('token') !== null

  if (to.meta.requiresAuth && !isAuthenticated && to.path !== '/login') {
    next('/login')
  } else if (to.path === '/login' && isAuthenticated) {
    next('/')
  } else {
    if (to.meta.requiresAuth) {
      const auth = useAuthStore()
      const modules = useModuleStore()
      await auth.fetchUser(to.path === '/change-password')
      if (!auth.user) { next(localStorage.getItem('token') ? '/unavailable' : '/login'); return }
      if (auth.user.must_change_password) {
        if (to.path === '/change-password') next()
        else next('/change-password')
        return
      }
      if (to.path === '/change-password') { next('/settings'); return }
      try {
        await modules.load()
      } catch {
        next('/unavailable')
        return
      }
      if (!modules.pathEnabled(to.path)) { next('/'); return }
      if (!canAccessPage(to.path, auth.user)) {
        ElMessage.error(uiText("没有访问此页面的权限"))
        next('/403')
        return
      }
    }
    next()
  }
})

export default router
