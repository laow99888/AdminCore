import request, { type ApiResponse } from './request'

export type OnlineAttachmentContext = { code: string; formId?: string; recordId?: string }
export type OnlineAttachment = { id: string; original_name: string; file_type: string; size: number }
export type OnlineAttachmentChoices = { items: OnlineAttachment[]; selected: OnlineAttachment | null; has_more: boolean }

export const onlineFormAttachmentsApi = {
  validatePreview: async (formId: string, definition: unknown, data: unknown) => (
    await request.post('/online-forms/validate/', { form_id: formId, definition, data })
  ).data,
  choices: async (context: OnlineAttachmentContext, field: string,
    options: { selected?: string; q?: string; page?: number; resolve?: boolean }, signal?: AbortSignal) => (
    await request.get<ApiResponse<OnlineAttachmentChoices>>(`/online-forms/${encodeURIComponent(context.code)}/attachments/`, {
      params: { form_id: context.formId, record_id: context.recordId, field, ...options }, signal,
    })).data.data,
}
