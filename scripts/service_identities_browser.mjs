/** 机器身份真实页面验收；仅本机独占夹具，不记录密钥的trace/HAR/截图。 */
import { resolve } from 'node:path';

export async function validateServiceIdentities({ page, context, headers, password, name, evidence, expect, checks }) {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:18471') throw new Error('机器身份验收只允许独占本机夹具');
  const root = '/api/v1/api-credentials/service-identities/';
  const title = `machine-${name}-${Date.now()}`;
  const permissionResult = await context.request.get('/api/v1/permissions/permissions/?resource=task&action=read', { headers });
  expect(permissionResult.status()).toBe(200);
  const permission = (await permissionResult.json()).data.items.find(row => row.code === 'task:read');
  expect(!!permission).toBe(true);
  const createdRole = await context.request.post('/api/v1/permissions/roles/', { headers,
    data: { name: title + '-reader', is_active: true, permission_ids: [permission.id], version: 0 } });
  expect(createdRole.status()).toBe(201);
  let oldToken = '', nextToken = '';
  const panel = page.locator('.service-identities');
  async function confirm(path, method = 'POST', status = 200) {
    const dialog = page.getByRole('dialog', { name: '密码二次确认', exact: true });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('textbox', { name: '当前密码', exact: true }).fill(password);
    const pending = page.waitForResponse(response => response.request().method() === method && new URL(response.url()).pathname === path);
    await dialog.getByRole('button', { name: '确认', exact: true }).click();
    const result = await pending;
    expect(result.status()).toBe(status);
    await expect(dialog).toBeHidden();
    return (await result.json()).data;
  }
  async function secret() {
    const dialog = page.getByRole('dialog', { name: '机器密钥仅展示一次', exact: true });
    const token = await dialog.getByRole('textbox', { name: '机器 API 密钥', exact: true }).inputValue();
    expect(/^ac_[a-f0-9]{32}\.[A-Za-z0-9_-]+$/.test(token)).toBe(true);
    await dialog.getByRole('button', { name: '已保存，关闭', exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(page.locator('#service-identity-secret')).toHaveCount(0);
    return token;
  }
  const read = token => context.request.get('/api/v1/api-credentials/tasks/', { headers: { Authorization: 'ApiToken ' + token } });
  async function shot(suffix) {
    await expect(page.locator('#service-identity-secret')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `service-identities-${name}-${suffix}.png`), fullPage: true, animations: 'disabled' });
  }
  try {
    await page.goto('/integrations/credentials');
    await panel.getByRole('button', { name: '创建机器身份', exact: true }).click();
    const editor = page.getByRole('dialog', { name: '创建机器身份', exact: true });
    await editor.getByRole('textbox', { name: '身份名称', exact: true }).fill(title);
    await editor.getByRole('textbox', { name: '用途说明', exact: true }).fill('独立ERP只读集成');
    const role = editor.getByRole('checkbox', { name: title + '-reader', exact: true });
    await role.locator('xpath=ancestor::label[1]').click();
    await expect(role).toBeChecked();
    await editor.getByRole('button', { name: '确认保存身份', exact: true }).click();
    const identity = await confirm(root, 'POST', 201);
    await expect(editor).toBeHidden();
    const row = panel.getByRole('row').filter({ hasText: title });
    await row.getByRole('button', { name: '管理机器凭证', exact: true }).click();
    const credentials = panel.getByRole('region', { name: '机器凭证', exact: true });
    await credentials.getByRole('textbox', { name: '凭证名称', exact: true }).fill(title + '-token');
    await credentials.getByRole('checkbox', { name: '读取任务摘要', exact: true }).locator('xpath=ancestor::label[1]').click();
    await credentials.getByRole('button', { name: '签发机器凭证', exact: true }).click();
    const issued = await confirm(root + identity.id + '/issue/', 'POST', 201);
    oldToken = await secret();
    expect(oldToken === issued.token).toBe(true); delete issued.token;
    expect((await read(oldToken)).status()).toBe(200);
    expect((await context.request.get('/api/v1/users/', { headers: { Authorization: 'ApiToken ' + oldToken } })).status()).toBe(401);
    await shot('issued');
    let credentialRow = credentials.getByRole('row').filter({ hasText: title + '-token' });
    await credentialRow.getByRole('button', { name: '轮换密钥', exact: true }).click();
    const rotated = await confirm(root + identity.id + '/rotate/');
    nextToken = await secret();
    expect(nextToken === rotated.token && nextToken !== oldToken).toBe(true); delete rotated.token;
    expect((await read(oldToken)).status()).toBe(401);
    expect((await read(nextToken)).status()).toBe(200);
    const stale = await context.request.post(root + identity.id + '/rotate/', { headers,
      data: { credential_id: issued.id, version: 1, current_password: password } });
    expect(stale.status()).toBe(409);
    expect((await read(nextToken)).status()).toBe(200);
    await row.getByRole('button', { name: '停用身份', exact: true }).click();
    await confirm(root + identity.id + '/', 'PATCH');
    expect((await read(nextToken)).status()).toBe(401);
    await expect(credentials.getByRole('button', { name: '签发机器凭证', exact: true })).toBeDisabled();
    await row.getByRole('button', { name: '启用身份', exact: true }).click();
    await confirm(root + identity.id + '/', 'PATCH');
    expect((await read(nextToken)).status()).toBe(401);
    credentialRow = credentials.getByRole('row').filter({ hasText: title + '-token' });
    await credentialRow.getByRole('button', { name: '撤销凭证', exact: true }).click();
    await confirm(root + identity.id + '/revoke/');
    await expect(credentialRow.getByRole('button', { name: '撤销凭证', exact: true })).toBeDisabled();
    await shot('disabled-reenabled-revoked');
    checks.push(`${name}: independent machine identity UI create/password confirmation/readonly role, issue/one-time secret cleared, API200 and interactive401, rotate/old401/current200/stale409, disable401 and reenable never revives key, revoke, responsive UI; no trace/HAR/secret screenshots`);
  } finally { oldToken = ''; nextToken = ''; }
}
