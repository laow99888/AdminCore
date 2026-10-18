import { registerUiMessages } from '@/i18n/uiText'
registerUiMessages({
  '审批流程（可选）': 'Approval workflow (optional)', '审批流程加载失败': 'Unable to load approval workflows',
  '发布时固定流程版本；只有同名且类型一致的顶层字段可作为流程输入。留空不启用审批。': 'Publishing freezes the workflow version. Inputs must match top-level field names and types. Leave empty to disable approval.',
  审批状态: 'Approval status', 未送审: 'Not submitted', 审批中: 'Pending approval', 已通过: 'Approved', 已驳回: 'Rejected', 已撤回: 'Withdrawn',
  提交审批: 'Submit for approval', 撤回审批: 'Withdraw approval', 查看审批: 'View approvals', 审批已提交: 'Approval submitted', 审批已撤回: 'Approval withdrawn',
  '审批操作失败，请刷新记录后重试': 'Approval action failed. Refresh the record and retry.',
  我的表单记录: 'My form records', 刷新记录: 'Refresh records', 发布版本: 'Release', 提交时间: 'Submitted at',
  查看记录: 'View record', 表单记录: 'Form record', 记录加载中: 'Loading record', 修改记录: 'Edit record', 保存记录: 'Save record',
  记录已保存: 'Record saved', 创建下一版: 'Create next release', 新版草稿已创建: 'New release draft created',
  '历史记录按提交时的表单版本显示，修改仍使用原字段规则': 'Historical records use the original form and validation rules, including when edited.',
  '记录加载失败，请重试': 'Unable to load records. Retry.', '保存失败，请检查字段或重新打开记录': 'Unable to save. Check the fields or reopen the record.',
})
