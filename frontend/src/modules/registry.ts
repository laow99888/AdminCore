/** 编译时显式登记扩展页面；不从服务端执行任意组件路径。 */
export const frontendExtensions = [{
  key: 'example', path: '/example', permission: 'example:read', title: '示例工单',
  component: () => import('../views/example/WorkItemListView.vue'),
}, {
  key: 'api_credentials', path: '/integrations/credentials', permission: 'api_credential:read', title: '开放凭证',
  component: () => import('../views/settings/APICredentialsView.vue'),
}, ...(__ADMINCORE_MINIMAL_BUILD__ ? [] : [{
  key: 'feature_flags', path: '/system/feature-flags', permission: 'feature_flag:read', title: '特性开关',
  component: () => import('../views/system/FeatureFlagsView.vue'),
}, {
  key: 'sso', path: '/integrations/identities', permission: 'sso:read', title: '企业身份绑定',
  component: () => import('../views/settings/ExternalIdentitiesView.vue'),
}])] as const
