import { nextTick, useTemplateRef, watch, type Ref } from 'vue'

/** 异步校验失败后让键盘与屏幕阅读器定位到保留输入的错误摘要。 */
export function useErrorSummary(error: Ref<string>) {
  const summary = useTemplateRef<HTMLElement>('errorSummary')
  watch(error, async value => {
    if (value) { await nextTick(); summary.value?.focus() }
  })
}
