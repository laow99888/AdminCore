import { resolve } from 'node:path';

export async function validateReportWorkbench({ page, name, evidence, expect, checks, get, post }) {
  const query = { data_source: 'cg_orders', chart_type: 'bar', dimensions: [{ field: 'approval_status' }],
    metrics: [{ key: 'm_amount', label: '采购金额', field: 'amount', aggregation: 'sum' }, { key: 'm_count', label: '订单数', field: 'id', aggregation: 'count' }], filters: [], limit: 100 };
  const definition = { schema_version: 2, widgets: [
    { key: 'status', title: '审批状态分布', span: 6, definition: { ...query, metrics: [query.metrics[0]] } },
    { key: 'total', title: '采购总额', span: 6, definition: { ...query, chart_type: 'table', dimensions: [] } },
    { key: 'trend', title: '月度趋势', span: 12, definition: { ...query, metrics: [query.metrics[0]], chart_type: 'line', dimensions: [{ field: 'created_at', grain: 'month' }] } },
  ], filters: [{ key: 'category', label: '采购类别筛选', operator: 'eq', value: 'office', bindings: ['status', 'total', 'trend'].map(widget => ({ widget, field: 'category' })) }],
  links: [{ source: 'status', source_field: 'approval_status', target: 'total', target_field: 'approval_status' }] };
  const report = await post('reports/definitions/', { name: `多图采购看板-${name}`, code: `board-${name}`, kind: 'dashboard', definition }, 201);
  await page.goto('/reports');
  let row = page.getByRole('row').filter({ hasText: report.name });
  await row.click();
  const editor = page.locator('.report-dashboard-editor');
  await expect(editor.locator('details')).toHaveCount(3);
  const first = editor.locator('details').first();
  await first.getByLabel('组件宽度', { exact: true }).selectOption('12');
  await first.getByRole('button', { name: '下移', exact: true }).click();
  await expect(editor.locator('details').first().locator('summary')).toContainText('采购总额');
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  await expect(page.getByText('已保存', { exact: true })).toBeVisible();
  const saved = await get(`reports/definitions/${report.id}/`);
  expect(saved.definition.widgets[0].key).toBe('total');
  expect(saved.definition.widgets[1].span).toBe(12);
  await page.getByRole('button', { name: '发布', exact: true }).click();
  await expect(page.getByText('已发布', { exact: true })).toBeVisible();
  await expect(editor.getByLabel('组件名称', { exact: true }).first()).toBeDisabled();
  await row.getByRole('button', { name: '运行', exact: true }).click();
  const viewer = page.locator('.report-viewer');
  await expect(viewer.locator('.report-widget')).toHaveCount(3);
  const total = viewer.locator('.report-widget').filter({ has: page.getByRole('heading', { name: '采购总额', exact: true }) });
  await expect(total.locator('.result')).toContainText(name === 'desktop' ? '1000.12' : '2000.24');
  const filter = viewer.getByLabel('采购类别筛选', { exact: true });
  await filter.fill('unmatched-category');
  await viewer.getByRole('button', { name: '应用筛选并刷新', exact: true }).click();
  await expect(total.locator('.result tbody tr').first()).toContainText('0');
  const request = page.waitForResponse(response => response.url().endsWith(`/reports/definitions/${report.id}/run/`) && response.request().method() === 'POST');
  await viewer.getByRole('button', { name: '恢复默认筛选', exact: true }).click();
  expect((await request).status()).toBe(200);
  await expect(total.locator('.result')).toContainText(name === 'desktop' ? '1000.12' : '2000.24');
  const linked = page.waitForResponse(response => response.url().endsWith(`/reports/definitions/${report.id}/run/`) && response.request().method() === 'POST');
  await viewer.getByRole('button', { name: '联动筛选', exact: true }).click();
  expect((await linked).request().postDataJSON().selection).toEqual({ widget: 'status', field: 'approval_status', value: 'approved' });
  await expect(viewer.getByText('当前联动', { exact: false })).toBeVisible();
  await expect(total.locator('.result')).toContainText(name === 'desktop' ? '1000.12' : '2000.24');
  await total.getByRole('button', { name: '查看明细', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '报表明细', exact: true });
  await expect(dialog.locator('tbody tr')).toHaveCount(name === 'desktop' ? 2 : 4);
  await expect(dialog.locator('thead')).toContainText('amount');
  await expect(dialog.locator('thead')).not.toContainText('remarks');
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  await viewer.getByRole('button', { name: '清除联动', exact: true }).click();
  await expect(viewer.getByRole('button', { name: '清除联动', exact: true })).toHaveCount(0);
  await expect(viewer.locator('.report-widget')).toHaveCount(3);
  if (name === 'mobile') {
    await page.getByRole('button', { name: '切换到深色模式', exact: true }).click();
    // Every widget becomes one column; all native form controls remain within the viewport.
    const boxes = await viewer.locator('.report-widget').evaluateAll(nodes => nodes.map(node => { const box = node.getBoundingClientRect(); return { left: box.left, right: box.right, width: box.width }; }));
    expect(boxes.every(box => box.left >= 0 && box.right <= 375 && box.width > 200)).toBe(true);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  for (const key of ['total','status','trend']) {
    const title = { total: '采购总额', status: '审批状态分布', trend: '月度趋势' }[key];
    const widget = viewer.locator('.report-widget').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
    await widget.getByRole('heading', { name: title, exact: true }).evaluate(node => node.scrollIntoView({ block: 'start' }));
    await expect(widget.getByRole('heading', { name: title, exact: true })).toBeInViewport();
    await page.screenshot({ path: resolve(evidence, `reports-${name}-${key}.png`) });
    const table = widget.locator('.result');
    // Horizontal scrolling belongs to the table, never to the page or individual digits.
    expect(await table.locator('tbody td').first().evaluate(node => getComputedStyle(node).whiteSpace)).toBe('nowrap');
  }
  await viewer.getByRole('heading', { name: report.name, exact: true }).evaluate(node => node.scrollIntoView({ block: 'start' }));
  await page.screenshot({ path: resolve(evidence, `reports-${name}-workbench.png`) });
  if (name === 'mobile') await page.getByRole('button', { name: '切换到浅色模式', exact: true }).click();
  checks.push(`${name}: saved multi-widget layout, immutable publish, two metrics, month grouping, global filters, linked selection and authorized details`);
}
