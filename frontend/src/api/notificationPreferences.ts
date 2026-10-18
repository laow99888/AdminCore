import request, { type ApiResponse } from './request'

export type NotificationChannel = 'inapp' | 'email' | 'webhook' | 'sms'
export interface NotificationPreferenceWrite {
  revision: number
  subscriptions: string[]
  channels: NotificationChannel[]
  quiet_enabled: boolean
  quiet_start: string
  quiet_end: string
  timezone: string
  business_delivery_mode?: 'immediate' | 'digest'
  digest_minutes?: 60 | 1440
}
export interface NotificationPreferences extends NotificationPreferenceWrite {
  business_delivery_mode: 'immediate' | 'digest'
  digest_minutes: 60 | 1440
  events: Array<{ code: string; label: string; required: boolean }>
  available_channels: NotificationChannel[]
}
export async function getNotificationPreferences(signal?: AbortSignal): Promise<NotificationPreferences> {
  return (await request.get<ApiResponse<NotificationPreferences>>('/notifications/preferences/', { signal })).data.data
}
export async function saveNotificationPreferences(value: NotificationPreferenceWrite, signal?: AbortSignal): Promise<NotificationPreferences> {
  return (await request.put<ApiResponse<NotificationPreferences>>('/notifications/preferences/', value, { signal })).data.data
}
