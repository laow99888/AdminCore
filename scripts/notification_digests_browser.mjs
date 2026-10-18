/** 独占 V2 夹具通知摘要验收；由桌面/手机总 runner 注入已登录 admin。 */
import { resolve } from 'node:path';

export async function validateNotificationDigests({ page, context, headers, name, evidence, expect, checks }) {
  if (new URL(page.url()).origin !== 'http://127.0.0.1:18471') throw new Error('通知摘要验收只允许独占本机夹具');
  const root = '/api/v1/notifications/';
  async function get(url) {
    const response = await context.request.get(url, { headers });
    expect(response.status(), await response.text()).toBe(200);
    return (await response.json()).data;
  }
  const before = await get(root + 'preferences/');
  const writable = value => Object.fromEntries(['revision', 'subscriptions', 'channels', 'quiet_enabled', 'quiet_start', 'quiet_end', 'timezone', 'business_delivery_mode', 'digest_minutes'].map(key => [key, value[key]]));
  async function write(value) {
    const response = await context.request.put(root + 'preferences/', { headers, data: writable(value) });
    expect(response.status(), await response.text()).toBe(200);
  }
  async function shot(suffix) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `notification-digests-${name}-${suffix}.png`), fullPage: true, animations: 'disabled' });
  }
  async function mode(value) {
    await page.getByRole('button', { name: '通知偏好', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '通知偏好', exact: true });
    const radio = dialog.getByRole('radio', { name: value === 'digest' ? '定期摘要' : '立即入箱', exact: true });
    await radio.locator('xpath=ancestor::label[1]').click();
    await expect(radio).toBeChecked();
    const response = page.waitForResponse(response => new URL(response.url()).pathname === root + 'preferences/' && response.request().method() === 'PUT');
    await dialog.getByRole('button', { name: '保存', exact: true }).click();
    expect((await response).status()).toBe(200);
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(dialog).toBeHidden();
  }
  try {
    await write({ ...before, subscriptions: before.events.filter(event => !event.required).map(event => event.code), channels: ['inapp'], quiet_enabled: false, business_delivery_mode: 'immediate', digest_minutes: 60 });
    const suppliers = await get('/api/v1/cg-suppliers/records/');
    const code = `DIGEST-${name}-${Date.now()}`;
    const created = await context.request.post('/api/v1/cg-orders/records/', { headers, data: {
      version: 0, code, supplier: suppliers.items[0].id, due_date: '2026-12-30',
      ordered_at: '2026-10-18T12:00:00+08:00', status: 'draft', category: 'office',
      attachment: null, remarks: '', lines: [{ product: '通知摘要验收', quantity: 1, price: '1.00' }], notes: [],
    } });
    expect(created.status(), await created.text()).toBe(201);
    const order = (await created.json()).data;
    await page.goto('/notifications');
    await mode('digest');
    async function send(expected) {
      await page.getByRole('button', { name: '发送业务提醒', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: '发送业务提醒', exact: true });
      await dialog.getByRole('textbox', { name: '搜索业务记录', exact: true }).fill(code);
      await dialog.getByRole('button', { name: '搜索', exact: true }).click();
      const recordRadio = dialog.getByRole('radio', { name: new RegExp(code) });
      await recordRadio.locator('xpath=ancestor::label[1]').click();
      await expect(recordRadio).toBeChecked();
      await dialog.getByRole('button', { name: '选择人员', exact: true }).click();
      const people = page.getByRole('dialog', { name: '选择人员', exact: true });
      await people.getByRole('textbox', { name: '搜索姓名或用户名', exact: true }).fill('admin');
      await people.getByRole('button', { name: '搜索', exact: true }).click();
      const personRadio = people.getByRole('radio', { name: /\(admin\)/ });
      await personRadio.locator('xpath=ancestor::label[1]').click();
      await expect(personRadio).toBeChecked();
      await people.getByRole('button', { name: '确认', exact: true }).click();
      await expect(people).toBeHidden();
      const response = page.waitForResponse(response => new URL(response.url()).pathname === root + 'business-notices/' && response.request().method() === 'POST');
      await dialog.getByRole('button', { name: '发送业务提醒', exact: true }).click();
      const sent = await response;
      expect(sent.status(), await sent.text()).toBe(200);
      const data = (await sent.json()).data;
      expect(data[expected]).toBe(1);
      await expect(dialog.getByRole('status')).toBeVisible();
      await expect(dialog.getByRole('button', { name: '发送业务提醒', exact: true })).toBeDisabled();
      await shot(expected);
      await dialog.getByRole('button', { name: '关闭', exact: true }).click();
      await expect(dialog).toBeHidden();
    }
    await send('pending');
    await page.getByRole('button', { name: '摘要与统计', exact: true }).click();
    const status = page.getByRole('dialog', { name: '通知摘要与统计', exact: true });
    await expect(status).toContainText('等待摘要');
    await expect(status.getByRole('button', { name: '合并我的到期提醒', exact: true })).toBeDisabled();
    expect((await get(root + 'digests/status/')).due).toBe(0);
    await status.getByRole('button', { name: '读取统计', exact: true }).click();
    await expect(status).toContainText('当前不提供供应商最终送达回执');
    await expect(status).toContainText('当前租户，按创建时间统计');
    await shot('operations');
    await status.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(status).toBeHidden();
    await mode('immediate');
    await send('published');
    await page.locator('.notification-item').filter({ has: page.getByText('业务更新提醒', { exact: true }) }).first().click();
    const detail = page.getByRole('dialog', { name: '业务通知摘要', exact: true });
    await expect(detail).toContainText('打开业务详情时仍会再次鉴权');
    await shot('reference');
    await detail.getByRole('button', { name: /查看业务记录/ }).click();
    // 业务页消费一次性 record 参数并清理地址栏，验收最终打开的受权记录。
    await expect(page).toHaveURL(/\/cg-orders(?:\?.*)?$/);
    await expect(page.getByRole('dialog', { name: '采购订单', exact: true }).getByRole('textbox', { name: '订单编码', exact: true })).toHaveValue(order.code);
    checks.push(`${name}: real business search/person picker, digest preference persistence, pending summary cannot run early, immediate inbox reference and authorized record navigation, tenant operations/no supplier-delivery claim, responsive dialogs`);
  } finally {
    await write({ ...before, revision: (await get(root + 'preferences/')).revision });
  }
}
