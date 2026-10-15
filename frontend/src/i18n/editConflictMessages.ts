/** 随编辑页面加载，避免冲突恢复文案进入登录首屏。 */
export const editConflictMessages: Record<string, string> = {
  '编辑冲突': 'Edit Conflict',
  '记录已被修改，输入已保留；请比较服务器最新值后再决定是否载入。': 'This record has changed. Your input is preserved. Compare the latest server values before loading them.',
  '查看服务器最新值': 'Compare Latest Server Values',
  '载入服务器最新值（替换当前输入）': 'Load Latest Values (Replace Current Input)',
  '最新值加载失败或已无权限，当前输入未改变。': 'Latest values could not be loaded or access has changed. Your input is unchanged.',
  '当前编辑版本：{p0}；服务器版本：{p1}': 'Editing version: {p0}; server version: {p1}',
  '当前输入与服务器最新值': 'Current Input and Latest Server Values',
  '字段': 'Field',
  '当前输入': 'Current Input',
  '服务器最新值': 'Latest Server Value',
  '已发布内容须先撤回才能编辑。': 'Withdraw published content before editing.',
}
