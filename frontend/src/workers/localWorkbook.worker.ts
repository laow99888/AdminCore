import { writeLocalWorkbook } from '../utils/writeLocalWorkbook'
import { LocalWorkbookError } from '../utils/localWorkbook'

self.onmessage = (event: MessageEvent<unknown>) => {
  try {
    const bytes = writeLocalWorkbook(event.data)
    self.postMessage({ ok: true, bytes }, { transfer: [bytes] })
  } catch (error) {
    // 不返回原输入、库异常或路径。
    self.postMessage({ ok: false, reason: error instanceof LocalWorkbookError ? 'invalid' : 'failed' })
  }
}
