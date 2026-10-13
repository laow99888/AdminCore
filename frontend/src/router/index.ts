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
  { path: '/change-password', component: () => import('../views/auth/ChangePasswordView.vue'), meta: { requiresAuth: true } },
  { path: '/files/recycle', component: () => import('../views/files/RecycleBinView.vue'), meta: { title: uiText('文件回收站'), requiresAuth: true } },
  { path: '/reliability/events', component: () => import('../views/system/ReliableEventsView.vue'), meta: { title: uiText('可靠事件'), requiresAuth: true } },
  { path: '/organization', component: () => import('../views/system/OrganizationView.vue'), meta: { requiresAuth: true } },
  { path: '/system/config', component: () => import('../views/system/SystemConfigView.vue'), meta: { requiresAuth: true } },
  { path: '/system/dictionaries', component: () => import('../views/system/DictionaryListView.vue'), meta: { requiresAuth: true } },
  { path: '/403', component: ServiceErrorView },
  { path: '/500', component: ServiceErrorView },
  { path: '/unavailable', component: ServiceErrorView },
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: {
      title: uiText("登录"),
      requiresAuth: false,
    },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: DashboardView,
    meta: {
      title: uiText("仪表盘"),
      requiresAuth: true,
    },
  },
  {
    path: '/users',
    name: 'UserList',
    component: UserListView,
    meta: { title: uiText("用户管理"), requiresAuth: true },
  },
  {
    path: '/roles',
    name: 'RoleList',
    component: RoleListView,
    meta: { title: uiText("角色权限"), requiresAuth: true },
  },
  {
    path: '/menus',
    name: 'MenuList',
    component: MenuListView,
    meta: { title: uiText("菜单管理"), requiresAuth: true },
  },
  {
    path: '/files',
    name: 'FileList',
    component: FileListView,
    meta: { title: uiText("文件管理"), requiresAuth: true },
  },
  {
    path: '/approvals',
    name: 'ApprovalList',
    component: ApprovalListView,
    meta: { title: uiText("审批工作流"), requiresAuth: true },
  },
  {
    path: '/notifications',
    name: 'NotificationList',
    component: NotificationListView,
    meta: { title: uiText("通知中心"), requiresAuth: true },
  },
  {
    path: '/tasks',
    name: 'TaskList',
    component: TaskListView,
    meta: { title: uiText("任务中心"), requiresAuth: true },
  },
  {
    path: '/logs',
    name: 'OperationLog',
    component: OperationLogView,
    meta: { title: uiText("操作日志"), requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: SettingsView,
    meta: { title: uiText("系统设置"), requiresAuth: true, preserveOnLocaleChange: true },
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
