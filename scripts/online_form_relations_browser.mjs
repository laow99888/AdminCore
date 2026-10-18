/** 独占本机夹具：显式业务关联资源、远程选择、冻结历史与手机布局。 */
import { resolve } from 'node:path';

export async function validateOnlineFormRelations({ page, context, headers, name, evidence, expect, checks }) {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:18471') throw new Error('业务关联验收只允许独占本机夹具');
  const suffix = name.toLowerCase().replace(/[^a-z0-9-]/g, '-').slice(0, 25);
  const code = `form-relation-${suffix}`, title = `关联供应商-${name}`;
  const base = '/api/v1/online-forms/', forms = `${base}forms/`, records = `${base}${code}/records/`;
  async function api(method, url, data, status = 200) {
    const response = await context.request[method](url, { headers, ...(data === undefined ? {} : { data }) });
    expect(response.status(), await response.text()).toBe(status); return (await response.json()).data;
  }
  async function uiResponse(url, method, action, status = 200) {
    const pending = page.waitForResponse(response => new URL(response.url()).pathname === url && response.request().method() === method);
    await action(); const response = await pending;
    expect(response.status(), await response.text()).toBe(status); return (await response.json()).data;
  }
  const supplier = await api('post', '/api/v1/cg-suppliers/records/', { code: `REL-${suffix}`, name: title, active: true, version: 0 }, 201);
  let form = await api('post', forms, { code, name: `业务关联-${name}`, definition: { schema_version: 2, fields: [
    { key: 'supplier', label: '采购供应商', type: 'relation', resource: 'cg_suppliers', required: true },
    { key: 'lines', label: '明细', type: 'detail', min_rows: 0, max_rows: 5, fields: [
      { key: 'supplier', label: '明细供应商', type: 'relation', resource: 'cg_suppliers' }] },
  ] } }, 201);
  await page.goto('/online-forms');
  await page.getByRole('row').filter({ hasText: code }).click();
  await page.locator('.el-collapse-item__header').first().click();
  const picker = page.getByRole('combobox', { name: '关联资源', exact: true }).first();
  await expect(picker).toBeVisible();
  await page.locator('.el-form-item').filter({ hasText: '关联资源' }).locator('.el-select__wrapper').first().click();
  await page.getByRole('option', { name: '供应商', exact: true }).click();
  form = await uiResponse(`${forms}${form.id}/`, 'PUT', () => page.getByRole('button', { name: '保存草稿', exact: true }).click());
  expect(form.definition.fields[0].resource).toBe('cg_suppliers');
  form = await uiResponse(`${forms}${form.id}/publish/`, 'POST', () => page.getByRole('button', { name: '发布', exact: true }).click());
  await page.goto(`/online-forms/${code}`);
  const input = page.getByRole('combobox', { name: '采购供应商', exact: true });
  await page.locator('.el-select').filter({ has: input }).locator('.el-select__wrapper').click();
  await input.fill(title);
  await page.getByRole('option', { name: title, exact: true }).click();
  const row = await uiResponse(records, 'POST', () => page.getByRole('button', { name: '提交', exact: true }).click(), 201);
  expect(row.data.supplier).toBe(supplier.id); expect(row.definition_snapshot.fields[0].type).toBe('relation');
  const next = await api('post', `${forms}${form.id}/new-version/`, { version: form.version }, 201);
  const edited = await api('patch', `${forms}${next.id}/`, { version: next.version, definition: { schema_version: 2,
    fields: [{ key: 'supplier', label: '新版普通文本', type: 'text' }] } });
  await api('post', `${forms}${next.id}/publish/`, { version: edited.version });
  await page.reload();
  await page.getByRole('region', { name: '我的表单记录', exact: true }).getByRole('button', { name: '查看记录', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '表单记录', exact: true });
  await expect(dialog).toContainText(title); await expect(dialog.getByRole('textbox', { name: '新版普通文本', exact: true })).toHaveCount(0);
  await expect(dialog.getByRole('combobox', { name: '采购供应商', exact: true })).toHaveCount(0);
  const resolved = await api('get', `${base}${code}/relations/?record_id=${row.id}&field=supplier&selected=${supplier.id}&resolve=true`);
  expect(resolved.selected).toEqual({ id: supplier.id, title });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `online-form-relations-${name}-history.png`), fullPage: true, animations: 'disabled' });
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  checks.push(`${name}: registered V2 resource picker/save/publish, authorized remote business selection, UUID-only binding, frozen historical relation type, current authorization for readonly titles and responsive layout`);
}
