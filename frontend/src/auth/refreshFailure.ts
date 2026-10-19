/** 仅传输故障和明确可重试的 HTTP 状态保留会话；协议错误继续关闭访问。 */
export function retryableRefresh(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const failure = error as { isAxiosError?: boolean; response?: { status?: number }; code?: string }
  const status = failure.response?.status
  return status === 429 || (typeof status === 'number' && status >= 500) ||
    (status === undefined && (failure.isAxiosError === true || ['ERR_NETWORK', 'ECONNABORTED', 'ETIMEDOUT'].includes(failure.code || '')))
}
