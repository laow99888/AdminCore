/** 独占本机夹具：在线表单具体附件版本、真实上传和历史保护桌面/手机验收。 */
import { resolve } from 'node:path';

export async function validateOnlineFormAttachments({ page, context, headers, name, evidence, expect, checks }) {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:18471') throw new Error('附件验收仅允许独占本机夹具');
  const code = `attachments-${name.toLowerCase().replace(/[^a-z0-9-]/g, '-').slice(0, 25)}`;
  const base = '/api/v1/online-forms/', records = `${base}${code}/records/`;
  async function api(method, url, data, status = 200) {
    const response = await context.request[method](url, { headers, ...(data === undefined ? {} : { data }) });
    expect(response.status(), await response.text()).toBe(status); return (await response.json()).data;
  }
  const definition = { schema_version: 2, fields: [
    { key: 'title', label: '附件申请说明', type: 'text', required: true },
    { key: 'proof', label: '申请附件', type: 'file', required: true },
    { key: 'lines', label: '补充材料', type: 'detail', min_rows: 0, max_rows: 5,
      fields: [{ key: 'proof', label: '明细附件', type: 'file' }] },
  ] };
  let form = await api('post', `${base}forms/`, { code, name: `附件表单-${name}`, definition }, 201);
  form = await api('post', `${base}forms/${form.id}/publish/`, {});
  await page.goto(`/online-forms/${code}`);
  await page.getByRole('textbox', { name: '附件申请说明', exact: true }).fill(`提交附件-${name}`);
  const filename = `表单历史附件-${name}.txt`;
  await page.locator('input[type="file"]').setInputFiles({ name: filename, mimeType: 'text/plain', buffer: Buffer.from('online form original attachment') });
  const input = page.getByRole('combobox', { name: '申请附件', exact: true });
  await expect(input).toBeVisible();
  await expect(page.locator('.attachment-input').first()).toContainText(filename);
  const pending = page.waitForResponse(response => new URL(response.url()).pathname === records && response.request().method() === 'POST');
  await page.getByRole('button', { name: '提交', exact: true }).click();
  const submitted = await pending; expect(submitted.status(), await submitted.text()).toBe(201);
  const row = (await submitted.json()).data;
  expect(row.data.proof).toMatch(/^[a-f0-9-]{36}$/);
  expect(row.definition_snapshot.fields[1].type).toBe('file');
  const fileId = row.data.proof;
  // 同名字段在新版变成文本；旧记录仍按自己的 file 定义呈现。
  let next = await api('post', `${base}forms/${form.id}/new-version/`, { version: form.version }, 201);
  next = await api('patch', `${base}forms/${next.id}/`, { version: next.version, definition: { schema_version: 2,
    fields: [{ key: 'proof', label: '新版普通说明', type: 'text' }] } });
  await api('post', `${base}forms/${next.id}/publish/`, { version: next.version });
  await page.reload();
  await page.getByRole('region', { name: '我的表单记录', exact: true }).getByRole('button', { name: '查看记录', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '表单记录', exact: true });
  await expect(dialog).toContainText(filename);
  await expect(dialog.getByRole('textbox', { name: '新版普通说明', exact: true })).toHaveCount(0);
  await expect(dialog.locator('input[type="file"]')).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: '下载', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `online-form-attachments-${name}-frozen-history.png`), fullPage: true, animations: 'disabled' });
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  // 新版改为文本也不能绕过历史记录自己的必填附件校验。
  await api('patch', `${records}${row.id}/`, { version: row.version, data: { title: `已移除附件-${name}` } }, 400);
  // 首版必填附件，不能经新版字段定义绕过旧校验。
  const deletion = await context.request.delete(`/api/v1/files/${fileId}/`, { headers });
  expect(deletion.status(), await deletion.text()).toBe(409);
  const download = await context.request.get(`/api/v1/files/${fileId}/download/`, { headers });
  expect(download.status()).toBe(200); expect(await download.text()).toBe('online form original attachment');
  checks.push(`${name}: online form real attachment upload, frozen file schema after new release, readonly original filename, required history validation, protected deletion, retained bytes and responsive layout`);
}
