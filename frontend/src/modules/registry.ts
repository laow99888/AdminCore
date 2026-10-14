/** 编译时显式登记扩展页面；不从服务端执行任意组件路径。 */
export const frontendExtensions = [{
  key: 'example', path: '/example', permission: 'example:read', title: '示例工单',
  component: () => import('../views/example/WorkItemListView.vue'),
}] as const
