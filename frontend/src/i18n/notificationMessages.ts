/** 通知模板专用文案随模块页面加载。 */
export const notificationMessages: Record<string, string> = {
  'Twilio 短信': 'Twilio SMS',
  '外部渠道成功表示对端接收；短信结果不确定时终止，请核对供应商记录后处理。': 'External success means provider acceptance. Unknown SMS outcomes are terminated; check provider records before taking action.',
  '版本': 'Version',
  '发送中': 'Sending',
  "模板编辑生成新版本；已登记投递保持原版本。邮件仅发送至已验证邮箱。": "Editing creates a new version. Queued deliveries keep their original version. Email requires a verified address.",
  "使用 ${name} 文本占位符，变量名需逐一声明；字面美元符写为 $$。不支持表达式或 HTML。": "Use ${name} text placeholders and declare each variable; use $$ for a literal dollar sign. Expressions and HTML are not supported.",
  "邮件渠道未启用；请联系部署管理员配置。": "Email is disabled. Ask your deployment administrator to configure it.",
  "每位收件人、每个渠道独立记录；最多五次尝试。登记成功后请查看投递记录。": "Each recipient and channel has a separate record, with up to five attempts. Check delivery records after submitting.",
  "通知配置加载失败，请重试": "Could not load notification settings. Please retry.",
  "请填写有效编码、名称、标题和不重复的变量": "Enter a valid code, name, subject and unique variables.",
  "模板已变化，已保留输入，请重新打开编辑窗口": "The template changed. Your input is preserved. Reopen the editor to load the latest version.",
  "保存失败，已保留输入；请检查占位符与声明变量": "Save failed. Input is preserved. Check placeholders and declared variables.",
  "投递渠道加载失败，请关闭后重试": "Could not load delivery channels. Close and retry.",
  "预览失败，请检查变量或重新打开最新模板": "Preview failed. Check variables or reopen the latest template.",
  "确定向所选人员登记通知投递吗？": "Queue notification deliveries to the selected recipients?",
  "已登记投递，请查看结果": "Deliveries queued. Check their results.",
  "发送未确认，已保留输入；检查模板、人员和邮箱后重试": "Sending was not confirmed. Input is preserved. Check the template, recipients and email addresses before retrying.",
  "重试未确认，请刷新检查状态、期限与次数": "Retry was not confirmed. Refresh to check status, expiry and attempts."
}
