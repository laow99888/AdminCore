export const ipPolicyMessages: Record<string, string> = {
  '加载中...': 'Loading...',
  '启用 IP 策略': 'Enable IP policy', '允许网络': 'Allowed networks', '拒绝网络': 'Denied networks',
  '每行一个 IPv4、IPv6 或 CIDR，最多 100 条；拒绝规则优先，允许列表为空表示不限制。': 'One IPv4, IPv6 or CIDR per line, up to 100 entries. Deny rules take priority. An empty allow list permits all sources.',
  '策略作用于 API、后台和实时连接；请先预检当前来源，再输入当前密码保存。': 'The policy applies to APIs, administration and live connections. Preview your current source, then enter your current password to save.',
  '预检当前来源': 'Preview current source', '当前来源：{p0}；结果：{p1}': 'Current source: {p0}; result: {p1}',
  '允许访问': 'Allowed', '拒绝访问': 'Denied', '来源未知': 'Unknown source',
  '策略预检失败，请检查网络格式或重试': 'Preview failed. Check network formats or retry.',
  '请先预检并确认当前来源允许访问': 'Preview first and confirm your current source is allowed.',
  '请输入当前密码确认修改': 'Enter your current password to confirm the change.',
  '保存失败，请检查字段和密码后重试': 'Save failed. Check the fields and password before retrying.',
  '网络条目最多 100 条，每条最多 80 个字符': 'Use up to 100 network entries, each up to 80 characters.',
  '仅具备读取权限，不能修改策略。': 'You have read access only and cannot change the policy.',
}
