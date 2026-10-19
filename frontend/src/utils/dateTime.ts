import dayjs from 'dayjs'

/** 业务时间戳按浏览器本地时区展示；日期字段保持原日历日期，不做 UTC 位移。 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const date = dayjs(value)
  return date.isValid() ? date.format('YYYY-MM-DD HH:mm') : '—'
}
