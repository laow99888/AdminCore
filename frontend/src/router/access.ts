import type { CurrentUser } from '@/stores/auth'
import { frontendExtensions } from '@/modules/registry'

const permissions: Record<string, string> = {
  ...Object.fromEntries(frontendExtensions.map(extension => [extension.path, extension.permission])),
  '/users': 'user:read', '/roles': 'role:read', '/menus': 'menu:read',
  '/tasks': 'task:read', '/logs': 'log:read',
  '/system/config': 'config:read', '/system/dictionaries': 'dictionary:read',
  '/files/recycle': 'file:recycle',
  '/tasks/schedules': 'schedule:read',
  '/system/information': 'diagnostics:read', '/system/monitor': 'monitor:read',
  '/organization/posts': 'post:read',
  '/system/cache': 'cache:read',
  '/system/online-users': 'session:read',
  '/notifications/templates': 'template:read',
}
export function canAccessPage(path: string, user: CurrentUser | null, declared: Record<string, string> = {}) {
  path = path.length > 1 ? path.replace(/\/+$/, '') : path
  if (!user) return false
  if (['/organization', '/organization/posts', '/reliability/events', '/tasks/schedules', '/system/information', '/system/monitor', '/system/cache', '/system/online-users', '/notifications/templates'].includes(path) && !(user.is_staff || user.is_superuser)) return false
  const required = declared[path] || permissions[path]
  return !required || !!user.permissions?.some(code => code === '*' || code === required)
}
