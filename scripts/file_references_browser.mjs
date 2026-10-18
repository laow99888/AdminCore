/** 隔离采购业务：真实主/明细引用、审批历史保护与响应式查询入口。 */
import { resolve } from 'node:path';

export async function validateFileReferences({ page, context, headers, name, evidence, expect, checks }) {
  async function upload(suffix) {
    const response = await context.request.post('/api/v1/files/', { headers, multipart: {
      file: { name: `引用验收-${name}-${suffix}.txt`, mimeType: 'text/plain', buffer: Buffer.from('reference acceptance') },
    } });
    expect(response.status(), await response.text()).toBe(201);
    const body = await response.json(); return body.data ?? body;
  }
  const file = await upload('protected'), free = await upload('free');
  const suppliers = await context.request.get('/api/v1/cg-suppliers/records/', { headers });
  const supplier = (await suppliers.json()).data.items[0];
  const created = await context.request.post('/api/v1/cg-orders/records/', { headers, data: {
    version: 0, code: `REF-${name}`, supplier: supplier.id, due_date: '2026-12-30',
    ordered_at: '2026-10-18T12:00:00+08:00', status: 'draft', category: 'office',
    attachment: file.id, remarks: '', lines: [{ product: '引用验收', quantity: 1, price: '1.00', evidence: file.id }], notes: [],
  } });
  expect(created.status(), await created.text()).toBe(201);
  let order = (await created.json()).data;
  async function openStatus(target, protectedFile) {
    await page.goto('/files');
    const toolbar = page.getByRole('region', { name: '我的文件整理', exact: true });
    await toolbar.getByRole('textbox', { name: '文件关键词', exact: true }).fill(target.original_name);
    await toolbar.getByRole('button', { name: '查询文件', exact: true }).click();
    const row = page.getByRole('row').filter({ hasText: target.original_name });
    await row.getByRole('button', { name: '引用保护', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '引用保护', exact: true });
    await expect(dialog).toContainText(protectedFile ? '文件受引用保护' : '当前未发现受保护引用');
    await expect(dialog).toContainText('引用不授予附件访问权限');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.waitForFunction(() => document.getAnimations().every(animation => animation.playState !== 'running'));
    await page.screenshot({ path: resolve(evidence, `file-references-${name}-${protectedFile ? 'protected' : 'free'}.png`), fullPage: true, animations: 'disabled' });
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(dialog).toBeHidden();
    return row;
  }
  let row = await openStatus(file, true);
  await row.getByRole('button', { name: '删除', exact: true }).click();
  await page.locator('.el-message-box').getByRole('button', { name: '确定', exact: true }).click();
  await expect(page.locator('.el-message--error')).toContainText('文件仍被业务记录或历史快照引用');
  const url = `/api/v1/cg-orders/records/${order.id}/`;
  let response = await context.request.post(url + 'submit/', { headers, data: { version: order.version } });
  expect(response.status(), await response.text()).toBe(200); order = (await response.json()).data;
  response = await context.request.post(url + 'withdraw/', { headers, data: { version: order.version } });
  expect(response.status(), await response.text()).toBe(200); order = (await response.json()).data;
  response = await context.request.patch(url, { headers, data: { version: order.version, attachment: null,
    lines: [{ product: '原附件已移除', quantity: 1, price: '1.00' }],
  } });
  expect(response.status(), await response.text()).toBe(200); order = (await response.json()).data;
  response = await context.request.delete(url, { headers, data: { version: order.version } });
  // 既有业务规则保留含审批历史的记录，不能为附件验收绕过它。
  expect(response.status(), await response.text()).toBe(409);
  expect(order.attachment).toBeNull();
  await openStatus(file, true);
  response = await context.request.delete(`/api/v1/files/${file.id}/purge/`, { headers });
  expect(response.status(), await response.text()).toBe(409);
  const download = await context.request.get(`/api/v1/files/${file.id}/download/`, { headers });
  expect(download.status()).toBe(200); expect(await download.text()).toBe('reference acceptance');
  await openStatus(free, false);
  checks.push(`${name}: file reference UI, live main/detail protection, rejected recycle, retained approval history after detach, business history deletion denied, protected purge, retained download and responsive layout`);
}
