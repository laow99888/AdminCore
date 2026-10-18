/** 隔离数据库中验收真实版本附件、回退、容量冲突和上传失败恢复。 */
import { resolve } from 'node:path';

export async function validateFileDocuments({ page, context, headers, name, evidence, expect, checks }) {
  async function get(path) {
    const response = await context.request.get('/api/v1/' + path, { headers });
    expect(response.status(), await response.text()).toBe(200);
    return (await response.json()).data;
  }
  const original = await get('files/capacity/');
  const profile = await get('auth/me/');
  async function quota(limit, version) {
    const response = await context.request.put('/api/v1/files/capacity/', {
      headers, data: { owner_id: profile.id, limit_bytes: limit, version },
    });
    expect(response.status(), await response.text()).toBe(200);
    return (await response.json()).data;
  }
  async function openVersions(file) {
    await page.goto('/files');
    const toolbar = page.getByRole('region', { name: '我的文件整理', exact: true });
    await toolbar.getByRole('textbox', { name: '文件关键词', exact: true }).fill(file.original_name);
    await toolbar.getByRole('button', { name: '查询文件', exact: true }).click();
    const row = page.getByRole('row').filter({ hasText: file.original_name });
    await row.getByRole('button', { name: '文档版本', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '文档版本', exact: true });
    await expect(dialog).toBeVisible();
    return dialog;
  }
  async function shot(suffix) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `file-documents-${name}-${suffix}.png`), fullPage: true, animations: 'disabled' });
  }
  try {
    if (original.limit_bytes) await quota(0, original.version);
    let response = await context.request.post('/api/v1/files/', { headers, multipart: {
      file: { name: `版本验收-${name}-原稿.txt`, mimeType: 'text/plain', buffer: Buffer.from('original revision') },
    } });
    expect(response.status(), await response.text()).toBe(201);
    const file = (await response.json()).data;
    let dialog = await openVersions(file);
    await expect(dialog).toContainText('尚无版本历史');
    await dialog.getByLabel('新版本附件', { exact: true }).setInputFiles({
      name: `版本验收-${name}-新版.txt`, mimeType: 'text/plain', buffer: Buffer.from('new revision'),
    });
    await dialog.getByRole('button', { name: '上传并登记新版本', exact: true }).click();
    await expect(dialog.locator('.version-list li')).toHaveCount(2);
    let history = await get(`files/${file.id}/versions/`);
    expect(history.version).toBe(2);
    const currentId = history.current_file;
    const downloadPromise = page.waitForEvent('download');
    await dialog.locator('.version-list li').filter({ hasText: '修订 1 ·' }).getByRole('button', { name: '下载', exact: true }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(file.original_name);
    expect(await download.failure()).toBeNull();
    await dialog.locator('.version-list li').filter({ hasText: '修订 1 ·' }).getByRole('button', { name: '设为当前版本', exact: true }).click();
    await expect(dialog.locator('.version-list li')).toHaveCount(3);
    await expect(dialog).toContainText('回退自修订 1');
    history = await get(`files/${file.id}/versions/`);
    expect(history.version).toBe(3); expect(history.current_file).toBe(file.id);
    response = await context.request.post(`/api/v1/files/${file.id}/versions/`, {
      headers, data: { version: 2, restore_number: 2 },
    });
    expect(response.status()).toBe(409);
    for (const [id, contents] of [[file.id, 'original revision'], [currentId, 'new revision']]) {
      const contentsResponse = await context.request.get(`/api/v1/files/${id}/download/`, { headers });
      expect(contentsResponse.status()).toBe(200); expect(await contentsResponse.text()).toBe(contents);
      const deletion = await context.request.delete(`/api/v1/files/${id}/purge/`, { headers });
      expect(deletion.status(), await deletion.text()).toBe(409);
    }
    await shot('history');
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await page.getByRole('region', { name: '我的文件容量', exact: true }).getByRole('button', { name: '容量管理', exact: true }).click();
    const manager = page.getByRole('dialog', { name: '容量管理', exact: true });
    const limit = manager.getByRole('spinbutton', { name: '容量上限（MiB，0表示不限）', exact: true });
    await expect(limit).toBeVisible();
    await limit.fill('1');
    await manager.getByRole('button', { name: '保存容量上限', exact: true }).click();
    await expect.poll(async () => (await get('files/capacity/')).limit_bytes).toBe(1048576);
    const beforeConflict = await get('files/capacity/');
    await quota(1, beforeConflict.version);
    await limit.fill('2');
    await manager.getByRole('button', { name: '保存容量上限', exact: true }).click();
    await expect(manager).toContainText('容量配置已变更，请重新读取后再编辑。');
    await shot('capacity-conflict');
    await manager.getByRole('button', { name: '重试', exact: true }).click();
    await expect(limit).toHaveValue(String(1 / 1048576));
    await manager.getByRole('button', { name: '关闭', exact: true }).click();
    dialog = await openVersions(file);
    const input = dialog.getByLabel('新版本附件', { exact: true });
    await input.setInputFiles({ name: `容量失败-${name}.txt`, mimeType: 'text/plain', buffer: Buffer.from('quota recovery') });
    await dialog.getByRole('button', { name: '上传并登记新版本', exact: true }).click();
    await expect(dialog).toContainText('附件上传失败，请检查容量或上传限制后重试。');
    expect(await input.evaluate(element => element.files.length)).toBe(1);
    expect((await get(`files/${file.id}/versions/`)).version).toBe(3);
    await shot('quota-error');
    await quota(0, (await get('files/capacity/')).version);
    await dialog.getByRole('button', { name: '上传并登记新版本', exact: true }).click();
    await expect(dialog.locator('.version-list li')).toHaveCount(4);
    await expect(dialog.getByRole('alert')).toHaveCount(0);
    expect((await get(`files/${file.id}/versions/`)).version).toBe(4);
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    checks.push(`${name}: immutable document bytes, UI upload/download/restore, retained history and purge protection, stale versions, capacity save/conflict, real quota rejection with retained input and successful retry`);
  } finally {
    const latest = await get('files/capacity/');
    if (latest.limit_bytes !== original.limit_bytes) await quota(original.limit_bytes, latest.version);
  }
}
