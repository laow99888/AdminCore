/** 仅访问隔离夹具端口；从设计发布到业务审批与报表，桌面/手机各验收一次。 */
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
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
      const flow = (await get('approvals/flows/')).items[0];
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
      await context.tracing.stop();
    } catch (error) {
      await page.screenshot({ path: resolve(evidence, `v3-${name}-failure.png`), fullPage: true });
      await context.tracing.stop({ path: resolve(evidence, `v3-${name}-failure.zip`) });
      throw error;
    } finally { await context.close(); }
  }
  passed = true;
} finally {
  writeFileSync(resolve(evidence, 'browser-report.json'), JSON.stringify({ passed, checks }, null, 2));
  await browser.close();
}
