/** 独占夹具验收；调用方必须禁用 tracing/HAR，密钥仅在内存中使用。 */
import { resolve } from 'node:path';

export async function validateCredentialRotation({ page, context, headers, password, name, evidence, expect, checks }) {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:18471') throw new Error('凭证验收只允许独占本机夹具');
  const root = '/api/v1/api-credentials/';
  let oldToken = '', newToken = '';
  const title = `rotation-${name}-${Date.now()}`;
  async function authenticated(token, path = 'tasks/') {
    return context.request.get(root + path, { headers: { Authorization: 'ApiToken ' + token } });
  }
  async function confirm(action) {
    const dialog = page.getByRole('dialog', { name: '密码二次确认', exact: true });
    await expect(dialog).toBeVisible();
    await dialog.getByRole('textbox', { name: '当前密码', exact: true }).fill(password);
    const pending = page.waitForResponse(response => response.request().method() === 'POST'
      && new URL(response.url()).pathname === root + action);
    await dialog.getByRole('button', { name: '确认', exact: true }).click();
    const response = await pending;
    // 创建和轮换响应含密钥，禁止作为断言消息或日志输出。
    expect(response.status()).toBe(action === 'credentials/' ? 201 : 200);
    await expect(dialog).toBeHidden();
    return (await response.json()).data;
  }
  async function closeSecret() {
    const dialog = page.getByRole('dialog', { name: '密钥仅展示一次', exact: true });
    const value = await dialog.getByRole('textbox', { name: '开放 API 密钥', exact: true }).inputValue();
    // 只断言格式，避免断言失败输出密钥。
    expect(/^ac_[a-f0-9]{32}\.[A-Za-z0-9_-]+$/.test(value)).toBe(true);
    await dialog.getByRole('button', { name: '已保存，关闭', exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(page.locator('#issued-api-secret')).toHaveCount(0);
    return value;
  }
  async function shot(suffix) {
    await expect(page.locator('#issued-api-secret')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `credential-rotation-${name}-${suffix}.png`), fullPage: true, animations: 'disabled' });
  }
  async function activateRowButton(row, name) {
    const button = row.getByRole('button', { name, exact: true });
    await button.focus();
    await button.press('Enter');
  }
  try {
    await page.goto('/integrations/credentials');
    await page.getByRole('textbox', { name: '名称', exact: true }).fill(title);
    const scope = page.getByRole('checkbox', { name: '读取任务摘要', exact: true });
    await scope.locator('xpath=ancestor::label[1]').click();
    await expect(scope).toBeChecked();
    await page.getByRole('button', { name: '确认创建', exact: true }).click();
    const created = await confirm('credentials/');
    oldToken = await closeSecret();
    expect(oldToken === created.token).toBe(true);
    delete created.token;
    expect((await authenticated(oldToken)).status()).toBe(200);
    // 业务参数错误也属于已认证请求；不能把调用次数解释为业务成功次数。
    expect((await authenticated(oldToken, 'tasks/?ordering=password')).status()).toBe(400);
    let row = page.getByRole('row').filter({ hasText: title });
    await activateRowButton(row, '调用统计');
    const stats = page.getByRole('dialog', { name: '调用统计', exact: true });
    await expect(stats).toContainText('累计已授权请求：2');
    await expect(stats).toContainText('所选期间请求：2');
    await expect(stats).toContainText('不代表操作成功');
    await shot('before-rotation');
    await stats.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(stats).toBeHidden();
    await activateRowButton(row, '轮换密钥');
    const rotated = await confirm(`credentials/${created.id}/rotate/`);
    newToken = await closeSecret();
    expect(newToken === rotated.token && newToken !== oldToken).toBe(true);
    delete rotated.token;
    expect(rotated.version).toBe(2);
    expect(rotated.expires_at).toBe(created.expires_at);
    expect(rotated.scopes).toEqual(created.scopes);
    expect((await authenticated(oldToken)).status()).toBe(401);
    expect((await authenticated(newToken)).status()).toBe(200);
    const stale = await context.request.post(root + `credentials/${created.id}/rotate/`, {
      headers, data: { version: 1, current_password: password },
    });
    expect(stale.status()).toBe(409);
    expect((await authenticated(newToken)).status()).toBe(200);
    await page.reload();
    row = page.getByRole('row').filter({ hasText: title });
    await activateRowButton(row, '调用统计');
    await expect(stats).toContainText('累计已授权请求：4');
    await expect(stats).toContainText('所选期间请求：4');
    await shot('after-rotation');
    await stats.getByRole('button', { name: '关闭', exact: true }).click();
    await activateRowButton(row, '撤销凭证');
    await confirm(`credentials/${created.id}/revoke/`);
    expect((await authenticated(newToken)).status()).toBe(401);
    await expect(row.getByRole('button', { name: '轮换密钥', exact: true })).toBeDisabled();
    await expect(row.getByRole('button', { name: '撤销凭证', exact: true })).toBeDisabled();
    await shot('revoked');
    checks.push(`${name}: credential creation/password confirmation, one-time secret cleared, UTC accepted-request statistics including business 400, rotation invalidates old key, stale version409 preserves new key, revoke401, responsive UI; no trace/HAR/secret screenshots`);
  } finally { oldToken = ''; newToken = ''; }
}
