import { registerUiMessages } from '@/i18n/uiText'
registerUiMessages({
  '引用保护': 'Reference protection',
  '正在检查引用…': 'Checking references…',
  '无法检查引用，请重试': 'Unable to check references. Please retry.',
  '文件受引用保护': 'This file is protected by references',
  '当前未发现受保护引用': 'No protected references currently found',
  '业务记录或历史快照仍在引用此文件，不能移入回收站或彻底删除。请在来源业务中处理引用；审批历史保留期间持续保护。': 'A business record or historical snapshot still references this file. It cannot be recycled or purged. Manage references in the source business; approval history remains protected for as long as it is retained.',
  '此结果仅反映当前状态，删除时服务端会再次检查。': 'This reflects the current state. The server checks again when deleting.',
  '引用不授予附件访问权限，也不会显示无权查看的业务信息。': 'References do not grant file access or reveal business information you cannot view.',
})
