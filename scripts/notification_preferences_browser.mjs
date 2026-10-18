/** 仅用于独占浏览器夹具；普通已登录用户即可，无外部渠道发送。 */
import { resolve } from 'node:path';

// 与 file_references_browser.mjs 相同，由主验收的桌面/手机循环调用。
// 前置：notifications 模块开启、已完成初始改密；page 与 headers 必须属于同一用户/租户。
// 无需预置通知、模板或渠道凭据；恢复测试前的个人设置，不影响后续业务用例。
export async function validateNotificationPreferences({ page, context, headers, name, evidence, expect, checks }) {
  const endpoint = '/api/v1/notifications/preferences/';
  const origin = new URL(page.url());
  if (origin.origin !== 'http://127.0.0.1:18471') throw new Error('通知偏好浏览器验收只允许独占本机夹具');
  const writable = ({ revision, subscriptions, channels, quiet_enabled, quiet_start, quiet_end, timezone }) =>
    ({ revision, subscriptions, channels, quiet_enabled, quiet_start, quiet_end, timezone });
  async function read() {
    const response = await context.request.get(endpoint, { headers });
    expect(response.status(), await response.text()).toBe(200);
    return (await response.json()).data;
  }
  async function write(values) {
    const response = await context.request.put(endpoint, { headers, data: writable(values) });
    expect(response.status(), await response.text()).toBe(200);
    return (await response.json()).data;
  }
  async function screenshot(suffix) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `notification-preferences-${name}-${suffix}.png`), fullPage: true, animations: 'disabled' });
  }
  const before = await read();
  try {
    await write({ ...before, subscriptions: before.events.filter(event => !event.required).map(event => event.code),
      channels: ['inapp', 'email', 'webhook', 'sms'], quiet_enabled: false,
      quiet_start: '22:00', quiet_end: '08:00', timezone: 'Asia/Shanghai' });
    await page.goto('/notifications');
    await page.getByRole('button', { name: '通知偏好', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '通知偏好', exact: true });
    const timezone = dialog.getByRole('textbox', { name: '时区', exact: true });
    await expect(timezone).toHaveValue('Asia/Shanghai');
    await expect(dialog).toContainText('必须通知的站内副本始终保留');
    const required = dialog.getByRole('checkbox', { name: /必须接收/ });
    await expect(required).toHaveCount(3);
    for (const checkbox of await required.all()) {
      await expect(checkbox).toBeChecked();
      await expect(checkbox).toBeDisabled();
    }
    // Element Plus 将原生 input 隐藏；点击可见 label，随后检查真实 input 状态。
    for (const label of ['业务更新提醒', '站内通知']) {
      const checkbox = dialog.getByRole('checkbox', { name: label, exact: true });
      await checkbox.locator('xpath=ancestor::label[1]').click();
      await expect(checkbox).not.toBeChecked();
    }
    for (const checkbox of await required.all()) await expect(checkbox).toBeChecked();
    await dialog.getByRole('switch').locator('..').click();
    await expect(dialog.getByRole('switch')).toBeChecked();
    async function selectTime(label, value) {
      const combo = dialog.getByRole('combobox', { name: label, exact: true });
      await combo.locator('xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " el-select__wrapper ")][1]').click();
      await page.getByRole('listbox', { name: label, exact: true }).getByRole('option', { name: value, exact: true }).click();
      await expect(combo).toHaveAttribute('aria-expanded', 'false');
    }
    async function expectTime(label, value) {
      const combo = dialog.getByRole('combobox', { name: label, exact: true });
      await expect(combo.locator('xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " el-select__wrapper ")][1]')).toContainText(value);
    }
    await selectTime('开始时间', '23:15');
    await selectTime('结束时间', '07:45');
    async function save(status) {
      const pending = page.waitForResponse(response => new URL(response.url()).pathname === endpoint && response.request().method() === 'PUT');
      await dialog.getByRole('button', { name: '保存', exact: true }).click();
      const response = await pending;
      expect(response.status(), await response.text()).toBe(status);
    }
    // 使用真实后端校验，避免把模拟错误响应当作集成验收。
    await timezone.fill('Invalid/NotificationBrowserFixture');
    await save(400);
    await expect(dialog).toContainText('保存未确认，输入已保留');
    await expect(timezone).toHaveValue('Invalid/NotificationBrowserFixture');
    await expect(dialog.getByRole('switch')).toBeChecked();
    await expectTime('开始时间', '23:15');
    await expectTime('结束时间', '07:45');
    await screenshot('invalid-preserved');
    await timezone.fill('America/New_York');
    await save(200);
    await expect(page.getByText('偏好已保存', { exact: true }).last()).toBeVisible();
    await expect(dialog.getByText('保存未确认，输入已保留', { exact: false })).toHaveCount(0);
    let persisted = await read();
    expect(persisted.timezone).toBe('America/New_York');
    expect(persisted.quiet_enabled).toBe(true);
    expect([persisted.quiet_start, persisted.quiet_end]).toEqual(['23:15', '07:45']);
    expect(persisted.subscriptions).not.toContain('business.update');
    expect(persisted.channels).not.toContain('inapp');
    expect(persisted.events.filter(event => event.required).map(event => event.code)).toEqual(['system.notice', 'approval.action', 'task.result']);
    await screenshot('saved');

    // 另一窗口真实更新版本，旧草稿必须收到 409 并保留输入。
    await timezone.fill('UTC');
    persisted = await write({ ...persisted, timezone: 'Asia/Tokyo' });
    await save(409);
    await expect(dialog).toContainText('保存未确认，输入已保留');
    await expect(timezone).toHaveValue('UTC');
    await screenshot('conflict-preserved');
    await dialog.getByRole('button', { name: '重新读取', exact: true }).click();
    await expect(timezone).toHaveValue('Asia/Tokyo');
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(dialog).toBeHidden();
    await page.reload();
    await page.getByRole('button', { name: '通知偏好', exact: true }).click();
    await expect(timezone).toHaveValue('Asia/Tokyo');
    await expectTime('开始时间', '23:15');
    await expectTime('结束时间', '07:45');
    await expect(dialog.getByRole('checkbox', { name: '业务更新提醒', exact: true })).not.toBeChecked();
    for (const checkbox of await required.all()) { await expect(checkbox).toBeChecked(); await expect(checkbox).toBeDisabled(); }
    await screenshot('reloaded');
    await dialog.getByRole('button', { name: '关闭', exact: true }).click();
    await expect(dialog).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    checks.push(`${name}: personal notification preferences, mandatory inbox, IANA/cross-midnight quiet hours, real 400/409 preserving input, saved revision/reload persistence and responsive layout`);
  } finally {
    const current = await read();
    await write({ ...before, revision: current.revision });
  }
}
