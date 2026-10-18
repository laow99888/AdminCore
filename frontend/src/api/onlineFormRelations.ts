import request, { type ApiResponse } from './request'
import type { OnlineAttachmentContext } from './onlineFormAttachments'

export type OnlineRelation = { id: string; title: string }
export type OnlineRelationChoices = { items: OnlineRelation[]; selected: OnlineRelation | null; has_more: boolean }
export const onlineFormRelationsApi = {
  resources: async (signal?: AbortSignal) => (await request.get<ApiResponse<{ code: string; title: string }[]>>('/online-forms/relation-resources/', { signal })).data.data,
  choices: async (context: OnlineAttachmentContext, field: string,
    options: { selected?: string; q?: string; page?: number; resolve?: boolean }, signal?: AbortSignal) => (
    await request.get<ApiResponse<OnlineRelationChoices>>(`/online-forms/${encodeURIComponent(context.code)}/relations/`, {
      params: { form_id: context.formId, record_id: context.recordId, field, ...options }, signal,
    })).data.data,
}
