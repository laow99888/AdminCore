/** 单表导入导出真实页面验收；后台执行仅连接隔离夹具数据库。 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export async function validateBusinessIO({ page, context, headers, name, evidence, expect, checks }) {
  await page.goto('/cg-suppliers');
  if (name === 'mobile') await page.getByRole('button', { name: '切换到深色模式', exact: true }).click();
  await page.getByRole('button', { name: '业务导入', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '业务导入', exact: true });
  await expect(dialog.getByText('选择导入文件', { exact: false })).toBeVisible();
  const code = `IO-${name}`;
  await dialog.locator('input[type=file]').setInputFiles({ name: 'suppliers.csv', mimeType: 'text/csv',
    buffer: Buffer.from(`编号,名称,启用\n${code},导入供应商,true\n${code},文件内重复,false\n${code}-2,另一个供应商,false\n`, 'utf8') });
  await dialog.getByLabel('映射列 编号', { exact: true }).selectOption('code');
  await dialog.getByLabel('映射列 名称', { exact: true }).selectOption('name');
  await dialog.getByLabel('映射列 启用', { exact: true }).selectOption('active');
  if (name === 'mobile') {
    expect(await dialog.getByLabel('映射列 编号', { exact: true }).evaluate(element => getComputedStyle(element).backgroundColor)).not.toBe('rgb(255, 255, 255)');
  }
  await dialog.getByLabel('模板名称', { exact: true }).fill(`浏览器-${name}`);
  await dialog.getByRole('button', { name: '保存个人模板', exact: true }).click();
  await expect(dialog.getByLabel('个人映射模板', { exact: true })).not.toHaveValue('');
  await dialog.getByRole('button', { name: '只校验预览', exact: true }).click();
  await expect(dialog.getByText('第 3 行', { exact: false })).toBeVisible();
  const before = await context.request.get(`/api/v1/cg-suppliers/records/?code=${code}`, { headers });
  expect((await before.json()).data.pagination.total).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await dialog.locator('.business-io-footer button').evaluateAll(buttons => buttons.every(button => {
    const box = button.getBoundingClientRect(); return box.left >= 0 && box.right <= innerWidth && box.height >= 44;
  }))).toBe(true);
  await page.screenshot({ path: resolve(evidence, `io-${name}-preview.png`), fullPage: true });
  const submitted = page.waitForResponse(response => response.url().includes('/data-io/business/plans/') && response.request().method() === 'POST');
  await dialog.getByRole('button', { name: '确认执行导入', exact: true }).click();
  const result = await (await submitted).json(); expect(result.code).toBe(200);
  const taskId = result.data.id;
  if (!/^[a-f0-9-]{36}$/.test(taskId)) throw new Error('Invalid isolated task ID');
  execFileSync(process.env.ADMINCORE_VALIDATION_PYTHON, ['-c', "import django,sys;django.setup();from apps.data_io.tasks import run_data_import;run_data_import(sys.argv[1])", taskId],
    { cwd: process.env.ADMINCORE_VALIDATION_BACKEND, env: process.env, timeout: 60000, stdio: 'pipe' });
  await dialog.getByRole('button', { name: '刷新导入结果', exact: true }).click();
  await expect(dialog.getByRole('status')).toContainText('已完成');
  let downloading = page.waitForEvent('download');
  await dialog.getByRole('button', { name: '下载错误行', exact: true }).click();
  const failed = await downloading, errorPath = resolve(evidence, `io-${name}-errors.csv`);
  await failed.saveAs(errorPath); expect(readFileSync(errorPath, 'utf8')).toContain('文件内重复');
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: code }).first()).toBeVisible();
  await page.getByRole('textbox', { name: '供应商编码', exact: true }).fill(code);
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  const submitExport = async () => {
    const response = page.waitForResponse(value => value.url().endsWith('/data-io/business/exports/') && value.request().method() === 'POST');
    await page.getByRole('button', { name: '后台导出 CSV', exact: true }).click();
    const value = await (await response).json(); expect(value.code).toBe(202);
    if (!/^[a-f0-9-]{36}$/.test(value.data.id)) throw new Error('Invalid isolated export task ID');
    await expect(page.getByRole('region', { name: '后台导出', exact: true }).getByRole('status')).toContainText('等待执行');
    return value.data.id;
  };
  const executeExport = identifier => execFileSync(process.env.ADMINCORE_VALIDATION_PYTHON,
    ['-c', "import django,sys;django.setup();from apps.data_io.business_export import run_business_export;run_business_export(sys.argv[1])", identifier],
    { cwd: process.env.ADMINCORE_VALIDATION_BACKEND, env: process.env, timeout: 60000, stdio: 'pipe' });
  const exportPanel = page.getByRole('region', { name: '后台导出', exact: true });
  const exportId = await submitExport();
  await expect(exportPanel.getByRole('button', { name: '下载导出文件', exact: true })).toHaveCount(0);
  executeExport(exportId);
  await exportPanel.getByRole('button', { name: '刷新导出结果', exact: true }).click();
  await expect(exportPanel.getByRole('status')).toContainText('已完成');
  downloading = page.waitForEvent('download');
  await exportPanel.getByRole('button', { name: '下载导出文件', exact: true }).click();
  const exported = await downloading, exportPath = resolve(evidence, `io-${name}-export.csv`);
  await exported.saveAs(exportPath);
  const content = readFileSync(exportPath, 'utf8'); expect(content).toContain(code); expect(content).not.toContain(code + '-2');
  const staleId = await submitExport();
  const existing = await context.request.get(`/api/v1/cg-suppliers/records/?code=${code}`, { headers });
  const row = (await existing.json()).data.items.find(value => value.code === code);
  expect(Boolean(row)).toBe(true);
  const changed = await context.request.patch(`/api/v1/cg-suppliers/records/${row.id}/`,
    { headers, data: { version: row.version, name: `导出后修改-${name}` } });
  expect(changed.status()).toBe(200);
  executeExport(staleId);
  await exportPanel.getByRole('button', { name: '刷新导出结果', exact: true }).click();
  await expect(exportPanel.getByRole('status')).toContainText('失败');
  await expect(exportPanel.getByRole('alert')).toContainText('导出已停止');
  await expect(exportPanel.getByRole('button', { name: '下载导出文件', exact: true })).toHaveCount(0);
  const cancelledId = await submitExport();
  const cancelled = await context.request.post(`/api/v1/tasks/${cancelledId}/cancel/`, { headers });
  expect(cancelled.status()).toBe(200);
  executeExport(cancelledId); // 真实重复投递必须保留取消状态。
  await exportPanel.getByRole('button', { name: '刷新导出结果', exact: true }).click();
  await expect(exportPanel.getByRole('status')).toContainText('已取消');
  await expect(exportPanel.getByRole('button', { name: '下载导出文件', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `io-${name}-result.png`), fullPage: true });
  if (name === 'mobile') await page.getByRole('button', { name: '切换到浅色模式', exact: true }).click();
  checks.push(`${name}: personal mapping, dry-run preview, confirmed import, mixed outcomes, error CSV, filtered async export, version failure and cancellation`);
}
