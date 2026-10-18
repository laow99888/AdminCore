/** 独占本机夹具的在线表单验收；保留三版表单及记录，供失败复核。 */
import { resolve } from 'node:path';

// 前置：online_forms 模块开启；管理员已改初始密码，拥有 online_form 全部权限。
// page 和 headers 必须属于同一用户/租户。身份迟到响应用例只临时变更客户端状态，
// 不写角色、成员或租户数据库，不应被当作服务端越权测试（后端另有集成测试）。
export async function validateOnlineFormLifecycle({ page, context, headers, name, evidence, expect, checks }) {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:18471') throw new Error('表单生命周期验收只允许独占本机夹具');
  const code = `lifecycle-${name.toLowerCase().replace(/[^a-z0-9-]/g, '-').slice(0, 30)}`;
  const base = '/api/v1/online-forms/';
  const forms = `${base}forms/`, records = `${base}${code}/records/`;
  const oldLabel = `历史说明-${name}`, newLabel = `新版说明-${name}`;
  const schema = label => ({ schema_version: 2, sections: [], rules: [], fields: [
    { key: label === oldLabel ? 'original' : 'replacement', label, type: 'text', required: true, max_length: 120 },
  ] });
  async function api(method, url, data, status = 200) {
    const response = await context.request[method](url, { headers, ...(data === undefined ? {} : { data }) });
    expect(response.status(), await response.text()).toBe(status);
    return (await response.json()).data;
  }
  async function screenshot(suffix) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `online-form-lifecycle-${name}-${suffix}.png`), fullPage: true, animations: 'disabled' });
  }
  const waits = (url, method) => page.waitForResponse(response => new URL(response.url()).pathname === url && response.request().method() === method);
  async function uiResponse(url, method, action, status) {
    const pending = waits(url, method); await action();
    const response = await pending;
    expect(response.status(), await response.text()).toBe(status);
    return (await response.json()).data;
  }
  async function settle() {
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  }
  async function openRecords() {
    await page.goto(`/online-forms/${code}`);
    const region = page.getByRole('region', { name: '我的表单记录', exact: true });
    await expect(region.getByRole('button', { name: '查看记录', exact: true })).toHaveCount(1);
    return region;
  }
  const dialog = page.getByRole('dialog', { name: '表单记录', exact: true });
  // 先用 API 建定义，再由真实 UI 保存草稿、发布，避免给共享夹具增加固定数据。
  let first = await api('post', forms, { code, name: `生命周期-${name}`, definition: schema(oldLabel) }, 201);
  await page.goto('/online-forms');
  await page.getByRole('row').filter({ hasText: code }).click();
  const identity = page.locator('.identity input');
  await expect(identity.nth(1)).toBeDisabled();
  await identity.first().fill(`生命周期首版-${name}`);
  first = await uiResponse(`${forms}${first.id}/`, 'PUT', () => page.getByRole('button', { name: '保存草稿', exact: true }).click(), 200);
  first = await uiResponse(`${forms}${first.id}/publish/`, 'POST', () => page.getByRole('button', { name: '发布', exact: true }).click(), 200);
  expect(first.status).toBe('published'); expect(first.release_number).toBe(1);
  const originalRecord = await api('post', records, { form_id: first.id, data: { original: `首版记录-${name}` } }, 201);
  // 当前页面保持首版输入，后台发布另一个 schema；真实服务端返回 409，不能清空输入。
  await openRecords();
  const oldInput = page.getByRole('textbox', { name: oldLabel, exact: true });
  await oldInput.fill(`尚未提交-${name}`);
  let second = await api('post', `${forms}${first.id}/new-version/`, { version: first.version }, 201);
  expect(second.code).toBe(code); expect(second.release_number).toBe(2);
  second = await api('patch', `${forms}${second.id}/`, { version: second.version, definition: schema(newLabel) });
  second = await api('post', `${forms}${second.id}/publish/`, { version: second.version });
  await uiResponse(records, 'POST', () => page.getByRole('button', { name: '提交', exact: true }).click(), 409);
  await expect(oldInput).toHaveValue(`尚未提交-${name}`);
  await expect(page.locator('p[role="alert"]').filter({ hasText: /表单|版本|变化|刷新/ })).toBeVisible();
  await screenshot('stale-submit-preserved');
  // 旧记录使用自己的冻结定义；修改冲突仍保留输入，不套用新版必填字段。
  const region = page.getByRole('region', { name: '我的表单记录', exact: true });
  await region.getByRole('button', { name: '查看记录', exact: true }).click();
  await expect(dialog.getByRole('textbox', { name: oldLabel, exact: true })).toHaveValue(`首版记录-${name}`);
  await expect(dialog.getByRole('textbox', { name: newLabel, exact: true })).toHaveCount(0);
  await expect(dialog.getByRole('textbox', { name: oldLabel, exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: '修改记录', exact: true }).click();
  const historicalInput = dialog.getByRole('textbox', { name: oldLabel, exact: true });
  await historicalInput.fill(`保留历史编辑-${name}`);
  const updated = await api('patch', `${records}${originalRecord.id}/`, { version: originalRecord.version, data: { original: `另一窗口-${name}` } });
  await uiResponse(`${records}${originalRecord.id}/`, 'PATCH', () => dialog.getByRole('button', { name: '保存记录', exact: true }).click(), 409);
  await expect(historicalInput).toHaveValue(`保留历史编辑-${name}`);
  await expect(dialog.getByRole('alert')).toBeFocused();
  await screenshot('frozen-history-conflict');
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  const confirm = page.locator('.el-message-box');
  await confirm.getByRole('button', { name: '确定', exact: true }).click();
  await expect(dialog).toBeHidden();
  // 清理运行页草稿的导航确认通过 beforeunload 处理，不删除数据库记录。
  const discardNavigation = popup => popup.accept();
  page.on('dialog', discardNavigation);
  try {
    await openRecords();
  } finally { page.off('dialog', discardNavigation); }
  await expect(page.getByRole('textbox', { name: newLabel, exact: true })).toBeVisible();
  await page.getByRole('region', { name: '我的表单记录', exact: true }).getByRole('button', { name: '查看记录', exact: true }).click();
  await dialog.getByRole('button', { name: '修改记录', exact: true }).click();
  await historicalInput.fill(`旧规则保存-${name}`);
  const saved = await uiResponse(`${records}${originalRecord.id}/`, 'PATCH', () => dialog.getByRole('button', { name: '保存记录', exact: true }).click(), 200);
  expect(saved.version).toBe(updated.version + 1);
  expect(saved.definition_snapshot.fields[0].key).toBe('original');
  await expect(historicalInput).toBeDisabled();
  await expect(dialog.getByRole('status')).toContainText('记录已保存');
  await screenshot('history-saved');
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();

  // 用真实 API 响应延迟交付，验证权限撤销/租户切换后旧记录不会重新出现。
  // 只使用夹具 Pinia 实例，不导入开发模块，不读取令牌、Cookie 或 localStorage。
  const state = await page.evaluate(() => {
    const stores = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s;
    const auth = stores.get('auth'), tenants = stores.get('tenants');
    if (!auth?.user || !tenants) throw new Error('在线表单夹具缺少认证/租户 store');
    return { permissions: [...auth.user.permissions], tenantId: tenants.currentId };
  });
  async function holdDetail(change, assertAfter) {
    let release, captured;
    const ready = new Promise(resolve => { captured = resolve; });
    const gate = new Promise(resolve => { release = resolve; });
    const url = `${records}${originalRecord.id}/`;
    const route = async intercepted => {
      const response = await intercepted.fetch(); captured(); await gate;
      await intercepted.fulfill({ response });
    };
    await page.route(`**${url}`, route);
    try {
      await page.getByRole('region', { name: '我的表单记录', exact: true }).getByRole('button', { name: '查看记录', exact: true }).click();
      await ready;
      await change();
      const pending = waits(url, 'GET'); release(); await pending; await settle();
      await assertAfter();
    } finally { release(); await page.unroute(`**${url}`, route); }
  }
  try {
    await holdDetail(() => page.evaluate(() => {
      const auth = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('auth');
      auth.user = { ...auth.user, permissions: ['online_form:record_create'] };
    }), async () => {
      await expect(dialog).toBeHidden();
      await expect(page.getByRole('region', { name: '我的表单记录', exact: true })).toHaveCount(0);
    });
    await page.evaluate(permissions => {
      const auth = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('auth');
      auth.user = { ...auth.user, permissions };
    }, state.permissions);
    await expect(page.getByRole('region', { name: '我的表单记录', exact: true }).getByRole('button', { name: '查看记录', exact: true })).toHaveCount(1);
    await holdDetail(() => page.evaluate(() => {
      document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('tenants').currentId = '11111111-1111-4111-8111-111111111111';
    }), async () => {
      await expect(dialog).toBeHidden();
      await expect(dialog.getByRole('textbox', { name: oldLabel, exact: true })).toHaveCount(0);
    });
  } finally {
    await page.evaluate(state => {
      const stores = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s;
      const auth = stores.get('auth'); auth.user = { ...auth.user, permissions: state.permissions };
      stores.get('tenants').currentId = state.tenantId;
    }, state);
  }
  // 最后验证真正的“创建下一版”入口，留下第 3 版草稿；第 2 版继续对外发布。
  await page.goto('/online-forms');
  await page.getByRole('row').filter({ hasText: code }).filter({ hasText: 'published' }).click();
  const third = await uiResponse(`${forms}${second.id}/new-version/`, 'POST', () => page.getByRole('button', { name: '创建下一版', exact: true }).click(), 201);
  expect(third.code).toBe(code); expect(third.release_number).toBe(3); expect(third.status).toBe('draft');
  await expect(identity.nth(1)).toHaveValue(code); await expect(identity.nth(1)).toBeDisabled();
  await expect(page.getByRole('button', { name: '发布', exact: true })).toBeVisible();
  const published = await api('get', `${base}published/${code}/`);
  expect(published.id).toBe(second.id);
  const history = await api('get', `${records}${originalRecord.id}/`);
  expect(history.release_number).toBe(1); expect(history.definition_snapshot.fields[0].label).toBe(oldLabel);
  await screenshot('next-version-draft');
  checks.push(`${name}: online form draft/save/publish, same-code releases 1→2→3, atomic published pointer, real stale-submit 409 preserving input, frozen historical schema read/edit/conflict, late permission/tenant response discarded and responsive layout`);
}
