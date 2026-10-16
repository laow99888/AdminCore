/**
 * 可信微前端登记表。入口、路由前缀和权限必须在源码中审核后发布，
 * 不接受服务端返回的任意 URL，也不把 JWT 放进子应用 props。
 */
export interface TrustedMicroApp {
  key: string
  name: string
  entry: string
  routeBase: string
  permission: string
}

export const trustedMicroApps: readonly TrustedMicroApp[] = [
  // 将子应用部署到同源 /subapps/example/ 后，显式打开构建开关即可使用。
  { key: 'example-subapp', name: 'example-subapp', entry: '/subapps/example/', routeBase: '/micro/example-subapp', permission: 'example:read' },
]

export function findTrustedMicroApp(key: string) {
  return trustedMicroApps.find(app => app.key === key)
}

export function microFrontendsEnabled() {
  return __ADMINCORE_MICRO_FRONTENDS_ENABLED__ && !__ADMINCORE_MINIMAL_BUILD__
}
