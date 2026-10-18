/** 仅访问隔离夹具端口；从设计发布到业务审批与报表，桌面/手机各验收一次。 */
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { validateBusinessIO } from './business_io_browser.mjs';
import { validateReportWorkbench } from './report_workbench_browser.mjs';
import { validateOrganizationAppointments } from './organization_appointments_browser.mjs';
import { validateApprovalOperations, validateApprovalCalendarDiagnostics } from './approval_operations_browser.mjs';
import { validateListWorkbench } from './list_workbench_browser.mjs';
import { validateBusinessSearch } from './business_search_browser.mjs';
import { validateFileLibrary } from './file_library_browser.mjs';
import { validateFileReferences } from './file_references_browser.mjs';
import { validateFileDocuments } from './file_documents_browser.mjs';
import { validateNotificationPreferences } from './notification_preferences_browser.mjs';
import { validateFieldDiagnostics } from './field_diagnostics_browser.mjs';
import { validateOnlineFormLifecycle } from './online_form_lifecycle_browser.mjs';
import { validateOnlineFormAttachments } from './online_form_attachments_browser.mjs';
import { validateOnlineFormApprovals } from './online_form_approvals_browser.mjs';
import { validateOnlineFormRelations } from './online_form_relations_browser.mjs';
import { validateReportDeepening } from './report_deepening_browser.mjs';
import { validateNotificationDigests } from './notification_digests_browser.mjs';
import { validateCredentialRotation } from './credential_rotation_browser.mjs';
import { validateServiceIdentities } from './service_identities_browser.mjs';
const [workspace, evidence] = process.argv.slice(2);
const require = createRequire(resolve(workspace, 'package.json'));
const { chromium, devices, expect: baseExpect } = require('@playwright/test');
const expect = baseExpect.configure({ timeout: 20000 });
const { password } = JSON.parse(readFileSync(resolve(evidence, 'browser-access.json'), 'utf8'));
const baseURL = 'http://127.0.0.1:18471';
const checks = [], browser = await chromium.launch({ headless: true });
let passed = false;
try {
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    const context = await browser.newContext({ ...device, baseURL });
    await context.tracing.start({ screenshots: true, snapshots: true });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    try {
      await page.goto('/login');
      await page.getByPlaceholder('用户名', { exact: true }).fill('admin');
      await page.getByPlaceholder('密码', { exact: true }).fill(password);
      await page.getByRole('button', { name: '登录', exact: true }).click();
      await expect(page).toHaveURL(baseURL + '/');
      const token = await page.evaluate(() => localStorage.getItem('token'));
      const headers = { Authorization: 'Bearer ' + token };
      async function get(path) {
        const response = await context.request.get('/api/v1/' + path, { headers });
        expect(response.status()).toBe(200); const body = await response.json(); return body.data ?? body;
      }
      async function post(path, data, status = 200) {
        const response = await context.request.post('/api/v1/' + path, { headers, data });
        expect(response.status(), await response.text()).toBe(status); return (await response.json()).data;
      }
      if (process.env.ADMINCORE_BUSINESS_IO === '1') await validateBusinessIO({ page, context, headers, name, evidence, expect, checks });
      await validateListWorkbench({ page, context, headers, name, evidence, expect, checks });
      await validateBusinessSearch({ page, context, headers, name, evidence, expect, checks });
      await validateFileLibrary({ page, context, headers, name, evidence, expect, checks });
      const flow = (await get('approvals/flows/')).items.find(item => item.code === 'purchase-approval');
      await page.goto('/approvals/flows');
      await page.getByRole('row').filter({ hasText: '采购金额审批' }).getByRole('button', { name: '编辑', exact: true }).click();
      await expect(page.getByRole('switch', { name: '条件流程 V2', exact: true })).toBeChecked();
      await expect(page.getByLabel('比较值', { exact: true })).toHaveValue(name === 'desktop' ? '1000.00' : '1000.01');
      await expect(page.getByLabel('审批角色 ID', { exact: true })).toHaveCount(2);
      if (name === 'desktop') {
        await page.getByLabel('比较值', { exact: true }).fill('1000.01');
        await page.getByRole('button', { name: '发布', exact: true }).click();
        await expect(page.getByRole('button', { name: '发布', exact: true })).toHaveCount(0);
        const published = await get('approvals/flows/' + flow.id + '/');
        expect(published.definition.edges[1].when.value).toBe('1000.01');
      } else {
        await expect(page.getByLabel('比较值', { exact: true })).toBeDisabled();
      }
      await page.screenshot({ path: resolve(evidence, `v3-${name}-flow.png`), fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      checks.push(`${name}: V2 condition/role designer and immutable publish`);

      const supplier = (await get('cg-suppliers/records/')).items[0];
      async function create(price, suffix) {
        return post('cg-orders/records/', { version: 0, code: `V3-${name}-${suffix}`, supplier: supplier.id,
          due_date: '2026-12-30', ordered_at: '2026-10-18T12:00:00+08:00', status: 'draft', category: 'office',
          attachment: null, remarks: '', lines: [{ product: '浏览器采购商品', quantity: 1, price }], notes: [] }, 201);
      }
      const low = await create('0.10', 'low');
      await page.goto('/cg-orders');
      const amountHeader = page.getByRole('columnheader', { name: /^订单金额(?:\s|$)/ });
      await expect(amountHeader).toBeVisible();
      // 同一页真实配置列，验证持久化、固定、顺序、手机弹层及键盘可操作入口。
      await page.getByRole('button', { name: '列设置', exact: true }).click();
      const columnSettings = page.getByRole('group', { name: '列设置', exact: true });
      await expect(columnSettings).toBeVisible();
      await columnSettings.getByRole('button', { name: '订单编码 下移', exact: true }).click();
      await expect(columnSettings.locator('[data-column-setting]').first()).toHaveAttribute('data-column-setting', 'supplier');
      await columnSettings.locator('[data-column-setting="amount"]').getByText('订单金额', { exact: true }).click();
      await expect(columnSettings.getByRole('checkbox', { name: '订单金额', exact: true })).not.toBeChecked();
      const pinSelector = columnSettings.getByRole('combobox', { name: '订单编码 固定位置', exact: true });
      await pinSelector.focus();
      await pinSelector.press('ArrowDown');
      await page.getByRole('option', { name: '固定左侧', exact: true }).click();
      await expect(columnSettings.locator('[data-column-setting="code"]').getByText('固定左侧', { exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: resolve(evidence, `v3-${name}-column-settings.png`), fullPage: true });
      await columnSettings.getByRole('button', { name: '关闭列设置', exact: true }).click();
      await expect(amountHeader).toHaveCount(0);
      await page.reload();
      await expect(amountHeader).toHaveCount(0);
      await page.getByRole('button', { name: '列设置', exact: true }).click();
      await expect(columnSettings.locator('[data-column-setting]').first()).toHaveAttribute('data-column-setting', 'supplier');
      await expect(columnSettings.locator('[data-column-setting="code"]').getByText('固定左侧', { exact: true })).toBeVisible();
      await columnSettings.getByRole('button', { name: '恢复默认', exact: true }).click();
      await columnSettings.getByRole('button', { name: '关闭列设置', exact: true }).click();
      await expect(amountHeader).toBeVisible();
      checks.push(`${name}: column visibility, order, pinning, reload persistence, reset and responsive settings`);
      let tr = page.getByRole('row').filter({ hasText: low.code });
      await tr.getByRole('button', { name: '提交审批', exact: true }).click();
      await page.getByRole('button', { name: '确定', exact: true }).click();
      await expect(tr).toContainText('审批中');
      await expect(tr.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0);
      let record = await get(`cg-orders/records/${low.id}/`);
      expect((await get(`approvals/${record.approval_request}/`)).current_node).toBe('review');
      await tr.getByRole('button', { name: '撤回审批', exact: true }).click();
      await page.getByRole('button', { name: '确定', exact: true }).click();
      await expect(tr).toContainText('已撤回');
      await tr.getByRole('button', { name: '提交审批', exact: true }).click();
      await page.getByRole('button', { name: '确定', exact: true }).click();
      await expect(tr).toContainText('审批中');
      record = await get(`cg-orders/records/${low.id}/`);
      await page.goto('/approvals');
      let pending = page.getByRole('row').filter({ hasText: low.code });
      await pending.getByRole('button', { name: '详情', exact: true }).click();
      await expect(page.getByLabel('提交时的业务快照', { exact: true })).toContainText('浏览器采购商品');
      await expect(page.getByLabel('提交时的业务快照', { exact: true })).toContainText('0.10');
      await page.getByRole('dialog').getByRole('button', { name: '关闭', exact: true }).click();
      await pending.getByRole('button', { name: '通过', exact: true }).click();
      await page.locator('.el-message-box').getByRole('button', { name: '通过', exact: true }).click();
      await expect(pending).toHaveCount(0);
      expect((await get(`cg-orders/records/${low.id}/`)).approval_status).toBe('approved');
      checks.push(`${name}: submit, lock, withdraw, resubmit, snapshot and synchronized approval`);

      const high = await create('1000.02', 'high');
      const submitted = await post(`cg-orders/records/${high.id}/submit/`, { version: 1 });
      expect((await get(`approvals/${submitted.approval_request}/`)).current_node).toBe('finance');
      await page.goto('/approvals');
      pending = page.getByRole('row').filter({ hasText: high.code });
      await pending.getByRole('button', { name: '通过', exact: true }).click();
      await page.locator('.el-message-box').getByRole('button', { name: '通过', exact: true }).click();
      await expect.poll(async () => (await get(`approvals/${submitted.approval_request}/`)).current_node).toBe('review');
      await page.reload();
      await pending.getByRole('button', { name: '通过', exact: true }).click();
      await page.locator('.el-message-box').getByRole('button', { name: '通过', exact: true }).click();
      await expect(pending).toHaveCount(0);
      expect((await get(`cg-orders/records/${high.id}/`)).approval_status).toBe('approved');
      checks.push(`${name}: precise threshold selects finance then supervisor`);

      const design = { data_source: 'cg_orders', chart_type: 'table', dimensions: [{ field: 'approval_status' }], metric: { field: 'amount', aggregation: 'sum' }, filters: [], limit: 100 };
      const report = await post('reports/definitions/', { name: `采购汇总-${name}`, code: `purchase-${name}`, kind: 'report', definition: design }, 201);
      await post(`reports/definitions/${report.id}/publish/`, { version: report.version });
      await page.goto('/reports');
      await page.getByRole('row').filter({ hasText: report.name }).getByRole('button', { name: '运行', exact: true }).click();
      await expect(page.locator('.result')).toContainText(name === 'desktop' ? '1000.12' : '2000.24');
      const result = await get(`reports/definitions/${report.id}/run/`);
      expect(typeof result.rows[0].value).toBe('string');
      // SQLite 聚合保留不同数量的尾零；按十进制文本规范化，避免经浮点数比较。
      expect(result.rows[0].value.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')).toBe(name === 'desktop' ? '1000.12' : '2000.24');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: resolve(evidence, `v3-${name}-report.png`), fullPage: true });
      expect(errors).toEqual([]);
      checks.push(`${name}: registered report source, exact decimal totals and responsive UI`);
      await validateReportWorkbench({ page, name, evidence, expect, checks, get, post });
      await validateOrganizationAppointments({ page, context, name, evidence, expect, checks, get, post, password });
      await validateApprovalOperations({ page, name, evidence, expect, checks, get, post });
      await validateApprovalCalendarDiagnostics({ page, name, evidence, expect, checks, get, post });
      expect(errors).toEqual([]);
      await context.tracing.stop();
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, `v3-${name}-failure.png`), fullPage: true });
      await context.tracing.stop({ path: resolve(evidence, `v3-${name}-failure.zip`) });
      throw error;
    } finally { await context.close(); }
  }
  // 附件历史用例保留撤回的订单；在两端报表基线验收结束后再创建，避免污染汇总夹具。
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    const context = await browser.newContext({ ...device, baseURL });
    await context.tracing.start({ screenshots: true, snapshots: true });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    try {
      await page.goto('/login');
      await page.getByPlaceholder('用户名', { exact: true }).fill('admin');
      await page.getByPlaceholder('密码', { exact: true }).fill(password);
      await page.getByRole('button', { name: '登录', exact: true }).click();
      await expect(page).toHaveURL(baseURL + '/');
      const token = await page.evaluate(() => localStorage.getItem('token'));
      const headers = { Authorization: 'Bearer ' + token };
      await validateFileReferences({ page, context, headers, name, evidence, expect, checks });
      await validateFileDocuments({ page, context, headers, name, evidence, expect, checks });
      await validateNotificationPreferences({ page, context, headers, name, evidence, expect, checks });
      await validateNotificationDigests({ page, context, headers, name, evidence, expect, checks });
      await validateFieldDiagnostics({ page, context, headers, name, evidence, expect, checks });
      await validateOnlineFormLifecycle({ page, context, headers, name, evidence, expect, checks });
      await validateOnlineFormAttachments({ page, context, headers, name, evidence, expect, checks });
      await validateOnlineFormApprovals({ page, context, headers, name, evidence, expect, checks });
      await validateOnlineFormRelations({ page, context, headers, name, evidence, expect, checks });
      const get = async path => {
        const response = await context.request.get('/api/v1/' + path, { headers });
        expect(response.status(), await response.text()).toBe(200);
        return (await response.json()).data;
      };
      const post = async (path, data, status = 200) => {
        const response = await context.request.post('/api/v1/' + path, { headers, data });
        expect(response.status(), await response.text()).toBe(status);
        return (await response.json()).data;
      };
      await validateReportDeepening({ page, name, evidence, expect, checks, get, post });
      expect(errors).toEqual([]);
      await context.tracing.stop();
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, `file-references-${name}-failure.png`), fullPage: true });
      await context.tracing.stop({ path: resolve(evidence, `file-references-${name}-failure.zip`) });
      throw error;
    } finally { await context.close(); }
  }
  // 一次性密钥不进入 trace/HAR 或失败截图，使用单独浏览器上下文。
  for (const [name, device] of [['desktop', devices['Desktop Chrome']], ['mobile', devices['iPhone SE']]]) {
    const context = await browser.newContext({ ...device, baseURL });
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.name));
    try {
      await page.goto('/login');
      await page.getByPlaceholder('用户名', { exact: true }).fill('admin');
      await page.getByPlaceholder('密码', { exact: true }).fill(password);
      await page.getByRole('button', { name: '登录', exact: true }).click();
      await expect(page).toHaveURL(baseURL + '/');
      const token = await page.evaluate(() => localStorage.getItem('token'));
      await validateCredentialRotation({ page, context, headers: { Authorization: 'Bearer ' + token }, password, name, evidence, expect, checks });
      await validateServiceIdentities({ page, context, headers: { Authorization: 'Bearer ' + token }, password, name, evidence, expect, checks });
      expect(errors).toEqual([]);
    } finally { await context.close(); }
  }
  passed = true;
} finally {
  writeFileSync(resolve(evidence, 'browser-report.json'), JSON.stringify({ passed, checks }, null, 2));
  await browser.close();
}
