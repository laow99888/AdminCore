export const featureFlagMessages: Record<string, string> = {
  '新增开关': 'New flag', '编辑开关': 'Edit flag', '开关标识': 'Flag key',
  '启用开关': 'Enable flag', '灰度比例': 'Rollout', '灰度比例（%）': 'Rollout (%)', '已关闭': 'Disabled',
  '指定包含用户': 'Included users', '指定排除用户': 'Excluded users', '指定包含角色': 'Included roles',
  '搜索开关标识或名称': 'Search flag key or name',
  '开关控制功能投放，原有权限仍然生效。关闭开关会立即停止投放。': 'Flags control feature rollout. Existing permissions still apply. Disabling a flag stops rollout immediately.',
  '使用小写字母开头的字母、数字、点、横线或下划线，创建后不可修改。': 'Start with a lowercase letter; use letters, numbers, dots, hyphens or underscores. The key cannot change after creation.',
  '同一用户分组保持稳定；100% 表示全部用户，排除名单优先。': 'User assignment is stable. 100% includes everyone. Exclusions take priority.',
  '每次显示最多50个搜索结果，可输入用户名或角色名称继续搜索。': 'Up to 50 search matches are shown. Type a username or role name to refine the results.',
  '选项目标加载失败，请重新搜索': 'Could not load targets. Search again.',
  '请检查开关标识、名称、灰度比例及包含排除名单': 'Check the key, name, rollout and inclusion/exclusion lists.',
  '确定删除此开关？使用该标识的功能将按关闭处理。': 'Delete this flag? Features using this key will evaluate to disabled.',
}
