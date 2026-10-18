/** 独占采购夹具的真实字段诊断验收；桌面/手机共用，不读取采购业务值。 */
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';

export async function validateFieldDiagnostics({ page, context, headers, name, evidence, expect, checks }) {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:18471') throw new Error('字段诊断验收只允许独占本机夹具');
  const endpoint = '/api/v1/permissions/field-diagnostics/';
  const username = `field-diag-${name}-${randomUUID().slice(0, 8)}`;
  let role, target;
  async function request(method, path, data, status = 200) {
    const response = await context.request[method](path, { headers, ...(data === undefined ? {} : { data }) });
    // 响应可能包含用户信息，不把整个正文写入验收错误或 trace 附加文本。
    expect(response.status(), `${method} ${path} status`).toBe(status);
    return response;
  }
  async function select(dialog, label, value) {
    const combo = dialog.getByRole('combobox', { name: label, exact: true });
    await dialog.locator('.el-select__wrapper').filter({ has: page.getByRole('combobox', { name: label, exact: true }) }).click();
    await page.getByRole('option', { name: value, exact: true }).click();
    await expect(combo).toHaveAttribute('aria-expanded', 'false');
  }
  async function capture(suffix) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `field-diagnostics-${name}-${suffix}.png`), fullPage: true, animations: 'disabled' });
  }
  try {
    const permissions = (await (await request('get', '/api/v1/permissions/permissions/?search=cg_orders%3Aread')).json()).data.items;
    const permission = permissions.find(item => item.code === 'cg_orders:read');
    expect(permission?.id).toBeTruthy();
    role = (await (await request('post', '/api/v1/permissions/roles/', { name: username,
      is_active: true, permission_ids: [permission.id], field_permissions: { cg_orders: { read: ['code'], write: [] } } }, 201)).json()).data;
    await request('post', '/api/v1/users/', { username, password: `Fixture!${randomUUID()}Aa9`,
      role_ids: [role.id], is_active: true, must_change_password: false }, 201);
    const users = (await (await request('get', `/api/v1/users/?search=${encodeURIComponent(username)}`)).json()).data.items;
    target = users.find(item => item.username === username);
    expect(target?.id).toBeTruthy();
    await page.goto('/roles');
    await page.getByRole('button', { name: '字段权限诊断', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '字段权限诊断', exact: true });
    const user = dialog.getByRole('textbox', { name: '目标用户 ID', exact: true });
    const run = dialog.getByRole('button', { name: '运行诊断', exact: true });
    await user.fill('invalid-uuid');
    await expect(run).toBeDisabled();
    await user.fill(target.id);
    await select(dialog, '资源', 'cg_orders');
    await select(dialog, '字段', 'code');
    async function diagnose(status = 200) {
      const pending = page.waitForResponse(response => new URL(response.url()).pathname === endpoint && response.request().method() === 'POST');
      await run.click();
      const response = await pending;
      expect(response.status()).toBe(status);
      if (status !== 200) return;
      expect(response.headers()['cache-control']).toContain('no-store');
      const result = (await response.json()).data;
      expect(result.row_access).toBe('not_evaluated');
      expect(result.roles.some(item => item.id === role.id)).toBe(true);
      // 防止序列化器扩展把邮箱、用户名或业务值混入诊断。
      expect(Object.keys(result).sort()).toEqual(['user_id', 'resource', 'field', 'operation', 'field_action', 'field_allowed',
        'field_reason', 'permission_code', 'operation_allowed', 'user_active', 'must_change_password', 'module_enabled',
        'requires_admin', 'roles', 'data_scope', 'row_access', 'tenant_id'].sort());
      return result;
    }
    let result = await diagnose();
    expect(result.field_allowed).toBe(true); expect(result.operation_allowed).toBe(true);
    expect(result.field_reason).toBe('explicit_union');
    await expect(dialog).toContainText('已声明策略按有效角色字段并集合并');
    await expect(dialog).toContainText('本结果不是写入授权');
    await capture('read');
    await select(dialog, '操作', '修改');
    await expect(dialog.locator('.diagnostic-output')).toHaveCount(0);
    result = await diagnose();
    expect(result.field_allowed).toBe(false); expect(result.operation_allowed).toBe(false);
    await expect(dialog).toContainText('功能权限检查: 拒绝');
    await capture('denied');
    // 两个真实角色写请求：旧版本被拒绝，诊断只展示成功提交的策略。
    const staleVersion = role.version;
    role = (await (await request('patch', `/api/v1/permissions/roles/${role.id}/`, { version: staleVersion,
      field_permissions: { cg_orders: { read: ['code'], write: ['code'] } } })).json()).data;
    await request('patch', `/api/v1/permissions/roles/${role.id}/`, { version: staleVersion,
      field_permissions: { cg_orders: { read: [], write: [] } } }, 409);
    result = await diagnose();
    expect(result.field_allowed).toBe(true); expect(result.operation_allowed).toBe(false);
    expect(result.roles.find(item => item.id === role.id).version).toBe(role.version);
    await capture('live-policy-after-conflict');
    // 真实 404 保留输入；改回有效 ID 后重新运行恢复，无网络 mock。
    await user.fill(randomUUID());
    await diagnose(404);
    await expect(dialog).toContainText('无法诊断，请检查用户 ID 和当前租户后重试');
    await expect(user).not.toHaveValue(target.id);
    await capture('missing-user');
    await user.fill(target.id);
    await diagnose();
    await expect(dialog.getByText('无法诊断，请检查用户 ID 和当前租户后重试')).toHaveCount(0);
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(dialog).toBeHidden();
    await page.getByRole('button', { name: '字段权限诊断', exact: true }).click();
    await expect(dialog.locator('.diagnostic-output')).toHaveCount(0);
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    checks.push(`${name}: real field diagnostics, explicit role source, independent operation gate, fresh strategy after true 409, 404 input recovery, no business values, reopen clearing and responsive layout`);
  } finally {
    if (target) await request('delete', `/api/v1/users/${target.id}/`);
    if (role) await request('delete', `/api/v1/permissions/roles/${role.id}/`);
  }
}
