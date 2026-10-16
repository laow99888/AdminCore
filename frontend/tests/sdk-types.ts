/** 由 test:typecheck 编译；负例若不再报错，@ts-expect-error 将使门禁失败。 */
import { sdk } from '../src/api/sdk'

export async function verifySDKTypes() {
  const status = await sdk('tasks_backups_retrieve')
  const enabled: boolean = status.data.enabled
  const restore = await sdk('tasks_backups_restore_create', {
    path: { timestamp: '20261016-010203' }, body: { preflight_id: 'fixture', confirmation: '恢复备份', current_password: 'fixture' },
  })
  const id: string = restore.data.id
  const blob: Blob = await sdk('files_download_retrieve', { path: { id: 'fixture' }, responseType: 'blob' })
  const empty: undefined = await sdk('auth_sessions_destroy', { path: { id: 'fixture' } })
  await sdk('files_create', { contentType: 'multipart/form-data', body: { file: new File(['fixture'], 'fixture.txt') } })
  // @ts-expect-error 未登记路径
  await sdk('not_registered')
  // @ts-expect-error 该接口不支持删除操作
  await sdk('tasks_backups_destroy')
  // @ts-expect-error 缺少路径参数
  await sdk('tasks_backups_preflight_create')
  // @ts-expect-error 路径参数名称错误
  await sdk('tasks_backups_preflight_create', { path: { id: 'wrong' } })
  // @ts-expect-error 缺少当前密码
  await sdk('tasks_backups_restore_create', { path: { timestamp: 'fixture' }, body: { preflight_id: 'fixture', confirmation: '恢复备份' } })
  // @ts-expect-error 未登记的请求体字段
  await sdk('tasks_backups_restore_create', { path: { timestamp: 'fixture' }, body: { preflight_id: 'fixture', confirmation: '恢复备份', current_password: 'fixture', unexpected: true } })
  // @ts-expect-error 查询字段类型错误
  await sdk('users_list', { query: { page: 'wrong' } })
  // @ts-expect-error 二进制响应必须显式选择 Blob
  await sdk('files_download_retrieve', { path: { id: 'fixture' } })
  // @ts-expect-error 上传文件必须是 Blob/File
  await sdk('files_create', { contentType: 'multipart/form-data', body: { file: 'file-path' } })
  // @ts-expect-error 响应类型来自生成契约
  const wrong: string = status.data.enabled
  void [enabled, id, blob, empty, wrong]
}
