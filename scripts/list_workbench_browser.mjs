/** 仅使用独占夹具，验收高级条件、服务端方案、跨页显式选择和逐项删除结果。 */
import { resolve } from 'node:path';

export async function validateListWorkbench({ page, context, headers, name, evidence, expect, checks }) {
  const root = '/api/v1/cg-suppliers/records/';
  const prefix = `LIST-${name}-`;
  const created = [];
  for (let index = 0; index < 12; index++) {
    const response = await context.request.post(root, { headers, data: { version: 0, code: prefix + String(index).padStart(2, '0'), name: `工作台-${name}-${index}`, active: true } });
    expect(response.status(), await response.text()).toBe(201); created.push((await response.json()).data);
  }
  await page.goto('/cg-suppliers');
  const workbench = page.getByRole('region', { name: '高级查询与方案', exact: true });
  await workbench.locator('summary').click();
  await workbench.getByRole('button', { name: '添加条件', exact: true }).click();
  await workbench.getByLabel('条件字段 1', { exact: true }).selectOption('name');
  await workbench.getByLabel('运算符 1', { exact: true }).selectOption('contains');
  await workbench.getByLabel('条件值 1', { exact: true }).fill(`工作台-${name}-`);
  await workbench.getByRole('button', { name: '应用高级条件', exact: true }).click();
  await expect(page.getByText('共 12 条', { exact: true })).toBeVisible();
  await workbench.getByLabel('方案名称', { exact: true }).fill(`本批待处理-${name}`);
  await workbench.getByRole('button', { name: '另存为新方案', exact: true }).click();
  await expect(workbench.getByText('查询方案已保存', { exact: true })).toBeVisible();
  const saved = await context.request.get(root + 'query-views/', { headers });
  expect(saved.status()).toBe(200);
  expect((await saved.json()).data.items.some(item => item.name === `本批待处理-${name}` && item.definition.advanced.conditions[0].value === `工作台-${name}-`)).toBe(true);
  await page.reload();
  await expect(page.getByText('共 12 条', { exact: true })).toBeVisible();
  await page.locator('.query-workbench summary').click();
  await expect(page.getByLabel('查询方案', { exact: true })).not.toHaveValue('');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `list-${name}-saved-query.png`), fullPage: true, animations: 'disabled' });
  checks.push(`${name}: bounded advanced conditions, server-side saved view, refresh restoration and responsive form`);

  const firstRow = page.getByRole('row').filter({ hasText: prefix + '11' });
  await firstRow.locator('.el-checkbox').click();
  await expect(page.getByText('跨页已选 1 / 100', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  const secondRow = page.getByRole('row').filter({ hasText: prefix + '00' });
  await expect(secondRow).toBeVisible();
  await secondRow.locator('.el-checkbox').click();
  await expect(page.getByText('跨页已选 2 / 100', { exact: true })).toBeVisible();
  // 第一次明确选择的版本保留；并发编辑后预检只允许另一条通过。
  const patch = await context.request.patch(root + created[11].id + '/', { headers, data: { version: created[11].version, name: `工作台-${name}-11-updated` } });
  expect(patch.status(), await patch.text()).toBe(200);
  await page.getByRole('button', { name: '批量删除预检', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '批量删除预检', exact: true });
  await expect(dialog.getByText('版本已变化', { exact: true })).toBeVisible();
  await expect(dialog.getByText('预检通过 1 / 2', { exact: true })).toBeVisible();
  await expect(dialog.getByRole('button', { name: '删除选中记录', exact: true })).toBeDisabled();
  await dialog.getByRole('textbox', { name: '输入“删除选中记录”确认', exact: true }).fill('删除选中记录');
  await page.screenshot({ path: resolve(evidence, `list-${name}-bulk-preview.png`), fullPage: true, animations: 'disabled' });
  await dialog.getByRole('button', { name: '删除选中记录', exact: true }).click();
  await expect(dialog.getByText('预检通过 1 / 2；已删除 1', { exact: true })).toBeVisible();
  expect((await context.request.get(root + created[0].id + '/', { headers })).status()).toBe(404);
  expect((await context.request.get(root + created[11].id + '/', { headers })).status()).toBe(200);
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByText('跨页已选 0 / 100', { exact: true })).toBeVisible();
  await expect(page.getByText('共 11 条', { exact: true })).toBeVisible();
  checks.push(`${name}: cross-page explicit selection, stale version preview, confirmation and only-ready deletion`);
}
