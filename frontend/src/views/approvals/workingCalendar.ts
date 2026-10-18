import { uiText } from '@/i18n/uiText'
export interface WorkingCalendar {
  timezone: string
  weekdays: number[]
  start: string
  end: string
  closed_dates: string[]
  extra_dates: string[]
}
export function validateWorkingCalendar(value: WorkingCalendar) {
  const invalid = () => { throw new Error(uiText('工作日历无效，请检查时区、工作日、时段和日期')) }
  if (!value.timezone || value.timezone.length > 64) invalid()
  try { new Intl.DateTimeFormat('en', { timeZone: value.timezone }).format() } catch { invalid() }
  if (!value.weekdays.length || value.weekdays.some(day => !Number.isInteger(day) || day < 1 || day > 7) || new Set(value.weekdays).size !== value.weekdays.length) invalid()
  const minute = (text: string) => { if (!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(text)) invalid(); const [hour = 0, min = 0] = text.split(':').map(Number); return hour * 60 + min }
  if (minute(value.end) - minute(value.start) < 60) invalid()
  for (const rows of [value.closed_dates, value.extra_dates]) {
    if (rows.length > 366 || new Set(rows).size !== rows.length) invalid()
    for (const row of rows) { const parsed = new Date(row + 'T00:00:00Z'); if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(row) || row.startsWith('0000-') || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== row) invalid() }
  }
  if (value.closed_dates.some(day => value.extra_dates.includes(day))) invalid()
}
