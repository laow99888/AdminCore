/** 显式登记的业务搜索：真实登录、结果定位、草稿保护与手机布局。 */
import { resolve } from 'node:path';

export async function validateBusinessSearch({ page, context, headers, name, evidence, expect, checks }) {
  const title = `全局检索-${name}`;
  const created = await context.request.post('/api/v1/cg-suppliers/records/', {
    headers, data: { version: 0, code: `SEARCH-${name}`, name: title, active: true },
  });
  expect(created.status(), await created.text()).toBe(201);
  const record = (await created.json()).data;
  await page.goto('/');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: '业务搜索', exact: true }).click();
  const search = page.getByRole('dialog', { name: '业务搜索', exact: true });
  await search.getByRole('textbox', { name: '业务关键词', exact: true }).fill(title);
  const hit = search.getByRole('button').filter({ hasText: title });
  await expect(hit).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `search-${name}-results.png`), fullPage: true });
  await hit.click();
  await expect(page).toHaveURL(/\/cg-suppliers$/);
  const detail = page.getByRole('dialog', { name: '供应商', exact: true });
  await expect(detail.getByRole('textbox', { name: '供应商名称', exact: true })).toHaveValue(title);
  await expect(detail.getByRole('textbox', { name: '供应商名称', exact: true })).toBeDisabled();
  await detail.getByRole('button', { name: '取消', exact: true }).click();
  checks.push(`${name}: registered global search, bounded summaries and authorized readonly detail navigation`);

  // 同一路由的搜索定位不能越过编辑草稿保护。
  await page.getByRole('button', { name: '新增', exact: true }).click();
  const editor = page.getByRole('dialog', { name: '供应商', exact: true });
  await editor.getByRole('textbox', { name: '供应商名称', exact: true }).fill('保留未保存草稿');
  await page.evaluate(id => { history.pushState({}, '', '/cg-suppliers?record=' + id); window.dispatchEvent(new PopStateEvent('popstate')); }, record.id);
  const confirm = page.locator('.el-message-box');
  await expect(confirm).toContainText('尚有未保存的修改');
  await confirm.getByRole('button', { name: '取消', exact: true }).click();
  await expect(confirm).toBeHidden();
  await expect(editor.getByRole('textbox', { name: '供应商名称', exact: true })).toHaveValue('保留未保存草稿');
  await editor.getByRole('button', { name: '取消', exact: true }).click();
  await confirm.getByRole('button', { name: '确定', exact: true }).click();
  await expect(editor).toBeHidden();
  await page.getByRole('button', { name: '业务搜索', exact: true }).click();
  await search.getByRole('textbox', { name: '业务关键词', exact: true }).fill('不存在的全局关键词');
  await expect(search.getByRole('status')).toContainText('没有匹配的授权业务记录');
  await page.screenshot({ path: resolve(evidence, `search-${name}-empty.png`), fullPage: true });
  await search.press('Escape');
  await expect(search).toBeHidden();
  checks.push(`${name}: same-page unsaved draft cancellation, empty state and responsive search dialog`);
}
