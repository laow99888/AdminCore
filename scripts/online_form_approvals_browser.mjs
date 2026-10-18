/** 在线表单审批闭环；只写独占本机验收夹具。 */
import { resolve } from 'node:path';

export async function validateOnlineFormApprovals({ page, context, headers, name, evidence, expect, checks }) {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:18471') throw new Error('表单审批验收只允许独占本机夹具');
  const suffix = name.toLowerCase().replace(/[^a-z0-9-]/g, '-').slice(0, 25);
  const code = `form-approval-${suffix}`, flowCode = `form-review-${suffix}`;
  const base = '/api/v1/online-forms/', forms = `${base}forms/`, records = `${base}${code}/records/`;
  async function api(method, url, data, status = 200, enveloped = true) {
    const response = await context.request[method](url, { headers, ...(data === undefined ? {} : { data }) });
    expect(response.status(), await response.text()).toBe(status);
    const result = await response.json(); return enveloped ? result.data : result;
  }
  async function uiResponse(url, method, action, status = 200) {
    const pending = page.waitForResponse(response => new URL(response.url()).pathname === url && response.request().method() === method);
    await action(); const response = await pending;
    expect(response.status(), await response.text()).toBe(status); return (await response.json()).data;
  }
  async function screenshot(suffix) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `online-form-approvals-${name}-${suffix}.png`), fullPage: true, animations: 'disabled' });
  }
  let flow = await api('post', '/api/v1/approvals/flows/', { name: `表单审核-${name}`, code: flowCode,
    definition: { schema_version: 2, inputs: [{ key: 'title', type: 'text' }],
      nodes: [{ id: 'start', type: 'start' }, { id: 'review', type: 'user', assignee: { source: 'applicant' } }, { id: 'end', type: 'end' }],
      edges: [{ from: 'start', to: 'review' }, { from: 'review', to: 'end' }] } }, 201);
  flow = await api('post', `/api/v1/approvals/flows/${flow.id}/publish/`, { version: flow.version });
  let form = await api('post', forms, { code, name: `表单审批闭环-${name}`, definition: { schema_version: 2,
    fields: [{ key: 'title', label: '审批申请说明', type: 'text', required: true }] } }, 201);
  await page.goto('/online-forms');
  await page.getByRole('row').filter({ hasText: code }).click();
  const picker = page.getByRole('combobox', { name: '审批流程（可选）', exact: true });
  await page.locator('.el-form-item').filter({ hasText: '审批流程（可选）' }).locator('.el-select__wrapper').click();
  await page.getByRole('option', { name: `表单审核-${name} (${flowCode}) · ${flow.revision}`, exact: true }).click();
  form = await uiResponse(`${forms}${form.id}/`, 'PUT', () => page.getByRole('button', { name: '保存草稿', exact: true }).click());
  expect(form.approval_flow_code).toBe(flowCode);
  form = await uiResponse(`${forms}${form.id}/publish/`, 'POST', () => page.getByRole('button', { name: '发布', exact: true }).click());
  expect(form.approval_flow).toBe(flow.id); expect(form.approval_flow_version).toBe(flow.version);
  await page.goto(`/online-forms/${code}`);
  await page.getByRole('textbox', { name: '审批申请说明', exact: true }).fill(`冻结业务内容-${name}`);
  let row = await uiResponse(records, 'POST', () => page.getByRole('button', { name: '提交', exact: true }).click(), 201);
  const region = page.getByRole('region', { name: '我的表单记录', exact: true });
  await region.getByRole('button', { name: '查看记录', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '表单记录', exact: true });
  const textbox = dialog.getByRole('textbox', { name: '审批申请说明', exact: true });
  row = await uiResponse(`${records}${row.id}/submit-approval/`, 'POST', () => dialog.getByRole('button', { name: '提交审批', exact: true }).click());
  expect(row.approval_status).toBe('pending'); expect(row.version).toBe(2);
  const originalApplication = row.approval_request;
  await expect(textbox).toBeDisabled(); await expect(dialog.getByRole('button', { name: '修改记录', exact: true })).toHaveCount(0);
  await screenshot('pending');
  row = await uiResponse(`${records}${row.id}/withdraw-approval/`, 'POST', () => dialog.getByRole('button', { name: '撤回审批', exact: true }).click());
  expect(row.approval_status).toBe('cancelled'); expect(row.version).toBe(3);
  await expect(dialog.getByRole('button', { name: '修改记录', exact: true })).toBeVisible();
  row = await uiResponse(`${records}${row.id}/submit-approval/`, 'POST', () => dialog.getByRole('button', { name: '提交审批', exact: true }).click());
  expect(row.approval_request).not.toBe(originalApplication);
  const cancelled = await api('get', `/api/v1/approvals/${originalApplication}/`, undefined, 200, false);
  expect(cancelled.status).toBe('cancelled');
  const application = await api('get', `/api/v1/approvals/${row.approval_request}/`, undefined, 200, false);
  expect(application.flow).toBe(flow.id); expect(application.flow_version).toBe(flow.version);
  expect(application.business_snapshot.fields['审批申请说明 (title)']).toBe(`冻结业务内容-${name}`);
  expect(application.extra_data).toEqual({});
  // 表单入口进入审批中心，真实终审 API 与 UI 刷新核验使用同一事务闭环。
  await dialog.getByRole('link', { name: '查看审批', exact: true }).click();
  await expect(page).toHaveURL(/\/approvals(?:\?|$)/);
  await api('post', `/api/v1/approvals/${row.approval_request}/approve/`, { comment: '浏览器验收通过',
    expected_workflow_version: application.workflow_version, step_id: application.steps.find(step => step.status === 'pending').id });
  await page.goto(`/online-forms/${code}`);
  await region.getByRole('button', { name: '查看记录', exact: true }).click();
  await expect(dialog).toContainText('已通过'); await expect(textbox).toBeDisabled();
  await expect(dialog.getByRole('button', { name: '修改记录', exact: true })).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: '提交审批', exact: true })).toHaveCount(0);
  const final = await api('get', `${records}${row.id}/`);
  expect(final.approval_status).toBe('approved'); expect(final.version).toBe(5);
  await screenshot('approved');
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  checks.push(`${name}: online form approval picker/save/publish freezes flow identity, submit/withdraw/resubmit versions, retained cancelled history, protected snapshot, approval-center navigation, actual terminal decision writeback, immutable approved UI and responsive layout`);
}
