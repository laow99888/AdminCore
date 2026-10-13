import type { CurrentUser } from '@/stores/auth'

const permissions: Record<string, string> = {
  '/users': 'user:read', '/roles': 'role:read', '/menus': 'menu:read',
  '/tasks': 'task:read', '/logs': 'log:read',
  '/system/config': 'config:read', '/system/dictionaries': 'dictionary:read',
  '/files/recycle': 'file:recycle',
}
export function canAccessPage(path: string, user: CurrentUser | null) {
  if (!user) return false
  if ((path === '/organization' || path === '/reliability/events') && !(user.is_staff || user.is_superuser)) return false
  return !permissions[path] || !!user.permissions?.some(code => code === '*' || code === permissions[path])
}
