/** 随开放凭证页面加载，避免可选页面文案进入登录首屏。 */
export const apiCredentialMessages: Record<string, string> = {
  "只读开放 API 使用独立密钥；仅能读取已授权的任务或示例工单摘要。": "The read-only Open API uses separate secrets to read authorized task or example work item summaries.",
  "密钥不能登录、修改业务或管理账号。修改密码、全部设备下线、权限撤销及到期后会失效。": "Secrets cannot sign in, change business data or manage accounts. Password changes, global sign-out, permission revocation and expiry invalidate access.",
  "只读能力": "Read-only Capabilities",
  "当前没有可签发的只读能力，请检查模块和本人权限。": "No read-only capabilities are available. Check the enabled modules and your permissions.",
  "有效天数": "Validity in Days",
  "确认创建": "Create Credential",
  "正在加载开放凭证": "Loading API credentials",
  "撤销凭证": "Revoke Credential",
  "确认创建本人只读开放凭证？密钥只展示一次。": "Create a personal read-only API credential? The secret is shown only once.",
  "确认撤销所选开放凭证？撤销后不能恢复。": "Revoke this API credential? Revocation cannot be undone.",
  "操作未确认，请检查密码、权限和有效期后重试。": "The operation was not confirmed. Check your password, permissions and expiry, then try again.",
  "密钥仅展示一次": "Secret Shown Once",
  "请立即保存到你的密钥管理工具；关闭后无法再次查看。不要把密钥放入网址、日志或代码仓库。": "Save this secret in your secret manager now. It cannot be viewed again after closing. Keep it out of URLs, logs and source repositories.",
  "开放 API 密钥": "Open API Secret",
  "请求头格式：Authorization: ApiToken 加上密钥。仅支持独立开放 API 地址。": "Use the header Authorization: ApiToken followed by the secret. Only dedicated Open API routes accept it.",
  "已保存，关闭": "Saved, Close",
  "最近使用": "Last Used",
  "撤销时间": "Revoked At",
  "开放凭证加载失败，请刷新重试。": "API credentials could not be loaded. Refresh to try again."
}
