/** 个人文件整理：真实页面操作、API持久化及文件保留验证。 */
import { resolve } from 'node:path';

export async function validateFileLibrary({ page, context, headers, name, evidence, expect, checks }) {
  const filename = `个人整理-${name}.txt`, folderName = `采购归档-${name}`, tag = `年度-${name}`;
  const upload = await context.request.post('/api/v1/files/', {
    headers, multipart: { file: { name: filename, mimeType: 'text/plain', buffer: Buffer.from('library acceptance') } },
  });
  expect(upload.status(), await upload.text()).toBe(201);
  const uploaded = await upload.json(), file = uploaded.data ?? uploaded;
  await page.goto('/files');
  await page.getByRole('button', { name: '新建目录', exact: true }).click();
  const create = page.getByRole('dialog', { name: '新建目录', exact: true });
  await create.getByRole('textbox', { name: '目录名称', exact: true }).fill(folderName);
  await create.getByRole('button', { name: '保存', exact: true }).click();
  await expect(create).toBeHidden();
  const row = () => page.getByRole('row').filter({ hasText: filename });
  // 通过文件行内的实际操作入口进入整理弹层。
  const action = page.getByRole('button', { name: '整理文件', exact: true });
  if (await row().count()) await row().getByRole('button', { name: '整理文件', exact: true }).click();
  else await action.first().click();
  const organizer = page.getByRole('dialog', { name: '整理文件', exact: true });
  await expect(organizer).toContainText(filename);
  await organizer.locator('.el-select__wrapper').filter({ has: page.getByRole('combobox', { name: '个人目录', exact: true }) }).click();
  await page.getByRole('option', { name: folderName, exact: true }).click();
  const tagInput = organizer.getByRole('combobox', { name: '个人标签', exact: true });
  await tagInput.fill(tag);
  await page.getByRole('option', { name: tag, exact: true }).click();
  await organizer.locator('.file-title').click();
  await expect(tagInput).toHaveAttribute('aria-expanded', 'false');
  await organizer.getByRole('button', { name: '保存', exact: true }).click();
  await expect(organizer).toBeHidden();
  const library = await context.request.get('/api/v1/files/library/', { headers });
  expect(library.status()).toBe(200);
  const folder = (await library.json()).data.folders.find(item => item.name === folderName);
  const detail = await context.request.get(`/api/v1/files/${file.id}/`, { headers });
  const detailBody = await detail.json();
  expect((detailBody.data ?? detailBody).organization).toEqual({ version: 1, folder: folder.id, tags: [tag] });

  await page.reload();
  const toolbar = page.getByRole('region', { name: '我的文件整理', exact: true });
  await toolbar.locator('.el-select__wrapper').filter({ has: page.getByRole('combobox', { name: '个人目录', exact: true }) }).click();
  await page.getByRole('option', { name: folderName, exact: true }).click();
  await toolbar.getByRole('textbox', { name: '文件关键词', exact: true }).fill(filename);
  await toolbar.getByRole('button', { name: '查询文件', exact: true }).click();
  await expect(page.getByRole('button', { name: '整理文件', exact: true })).toHaveCount(1);
  await toolbar.getByRole('button', { name: '管理目录', exact: true }).click();
  const manager = page.getByRole('dialog', { name: '管理目录', exact: true });
  const managed = manager.locator('.folder-row').filter({ hasText: folderName });
  await managed.getByRole('button', { name: '编辑', exact: true }).click();
  const edit = page.getByRole('dialog', { name: '编辑目录', exact: true });
  await edit.getByRole('textbox', { name: '目录名称', exact: true }).fill(folderName + '-已验收');
  await edit.getByRole('button', { name: '保存', exact: true }).click();
  await expect(edit).toBeHidden();
  await expect(manager).toContainText(folderName + '-已验收');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.waitForFunction(() => document.getAnimations().every(animation => animation.playState !== 'running'));
  await page.screenshot({ path: resolve(evidence, `file-library-${name}-folders.png`), fullPage: true, animations: 'disabled' });
  await manager.locator('.folder-row').filter({ hasText: folderName + '-已验收' }).getByRole('button', { name: '删除', exact: true }).click();
  const confirm = page.locator('.el-message-box');
  await expect(confirm).toContainText('不删除文件');
  await confirm.getByRole('button', { name: '确定', exact: true }).click();
  await expect(manager).not.toContainText(folderName + '-已验收');
  await manager.locator('.el-dialog__headerbtn').click();
  const after = await context.request.get(`/api/v1/files/${file.id}/`, { headers });
  const afterBody = await after.json();
  expect((afterBody.data ?? afterBody).organization).toEqual({ version: 2, folder: null, tags: [tag] });
  const download = await context.request.get(`/api/v1/files/${file.id}/download/`, { headers });
  expect(download.status()).toBe(200); expect(await download.text()).toBe('library acceptance');
  await expect(page.getByRole('button', { name: '整理文件', exact: true })).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.waitForFunction(() => document.getAnimations().every(animation => animation.playState !== 'running'));
  await page.screenshot({ path: resolve(evidence, `file-library-${name}-retained.png`), fullPage: true, animations: 'disabled' });
  checks.push(`${name}: personal folder create/edit/delete, tag assignment, exact filtering, reload persistence, independent versions, retained file download and responsive layout`);
}
