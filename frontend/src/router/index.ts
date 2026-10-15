import { uiText } from "@/i18n/uiText"
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'
import { useModuleStore } from '@/stores/modules'
import { canAccessPage } from './access'
import { frontendExtensions } from '@/modules/registry'
import { moduleRoutes } from '@/router/moduleRoutes'

// 懒加载视图
const LoginView = () => import('../views/auth/LoginView.vue')
const DashboardView = () => import('../views/dashboard/DashboardView.vue')
const UserListView = () => import('../views/users/UserListView.vue')
const RoleListView = () => import('../views/system/RoleListView.vue')
const MenuListView = () => import('../views/system/MenuListView.vue')
const OperationLogView = () => import('../views/logs/OperationLogView.vue')
const SettingsView = () => import('../views/settings/SettingsView.vue')
const NotFoundView = () => import('../views/errors/NotFoundView.vue')
const ServiceErrorView = () => import('../views/errors/ServiceErrorView.vue')

const routes: RouteRecordRaw[] = [
  ...(__ADMINCORE_MINIMAL_BUILD__ ? [] : [{ path: '/enterprise-login', name: 'EnterpriseLogin', component: () => import('../views/auth/EnterpriseLoginView.vue'), meta: { title: '企业身份登录', requiresAuth: false, preserveOnLocaleChange: true } }]),
  ...(__ADMINCORE_MINIMAL_BUILD__ ? [] : moduleRoutes),
  ...frontendExtensions.map(extension => ({ path: extension.path, name: 'Extension-' + extension.key, component: extension.component,
    meta: { title: extension.title, requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } })),
  { path: '/settings/two-factor', name: 'TwoFactor', component: () => import('../views/settings/TwoFactorView.vue'), meta: { title: '双因素认证', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/recover-password', name: 'RecoverPassword', component: () => import('../views/auth/RecoverPasswordView.vue'), meta: { title: '找回密码', requiresAuth: false, preserveOnLocaleChange: true } },
  { path: '/settings/sessions', name: 'DeviceSessions', component: () => import('../views/settings/SessionManagementView.vue'), meta: { title: '会话与设备', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/system/online-users', name: 'OnlineUsers', component: () => import('../views/settings/SessionManagementView.vue'), props: { admin: true }, meta: { title: '在线用户', requiresAuth: true, hasPageHeading: true, preserveOnLocaleChange: true } },
  { path: '/change-password', component: () => import('../views/auth/ChangePasswordView.vue'), meta: { requiresAuth: true } },
  { path: '/reliability/events', name: 'ReliableEvents', component: () => import('../views/system/ReliableEventsView.vue'), meta: { title: '可靠事件', requiresAuth: true } },
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
  } else if (['/login', '/enterprise-login'].includes(to.path) && isAuthenticated) {
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
      } catch (error) {
        if (__ADMINCORE_MINIMAL_BUILD__ && error instanceof Error && error.message === '精简前端无法加载已启用的可选模块，请同步重新构建完整前后端镜像') ElMessage.error(error.message)
        next('/unavailable')
        return
      }
      if (!modules.pathEnabled(to.path)) { next('/'); return }
      if (!canAccessPage(to.path, auth.user, modules.pagePermissions)) {
        ElMessage.error(uiText("没有访问此页面的权限"))
        next('/403')
        return
      }
    }
    next()
  }
})

export default router
