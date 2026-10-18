/** Real generated-procurement API/UI checks. Run after the original report baseline checks. */
import { resolve } from 'node:path';

function localDate(value) {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value));
  return ['year', 'month', 'day'].map(type => parts.find(part => part.type === type).value).join('-');
}
function nextDate(value) { return new Date(Date.parse(value) + 86400000).toISOString().slice(0, 10); }
function decimal(value) { return String(value).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, ''); }

export async function validateReportDeepening({ page, name, evidence, expect, checks, get, post }) {
  // Each device has different totals, so its fixed filter excludes every other fixture order.
  const offset = name === 'desktop' ? 1 : 3;
  const supplier = (await get('cg-suppliers/records/')).items[0];
  const records = [];
  for (const [suffix, lines] of [
    ['one', [{ product: '比较商品甲', quantity: 2, price: `${10000 + offset}.00` }, { product: '比较商品乙', quantity: 3, price: `${10000 + offset}.00` }]],
    ['two', [{ product: '比较商品丙', quantity: 4, price: `${25000 + offset}.00` }]],
  ]) {
    records.push(await post('cg-orders/records/', { version: 0, code: `DEEP-${name}-${suffix}`, supplier: supplier.id,
      due_date: null, ordered_at: null, status: 'draft', category: 'office', attachment: null, remarks: '', lines, notes: [] }, 201));
  }
  expect(records.map(record => decimal(record.amount))).toEqual([String(50000 + offset * 5), String(100000 + offset * 4)]);
  const days = records.map(record => localDate(record.created_at)).sort();
  const start = days[0], end = nextDate(days.at(-1));
  const definition = { data_source: 'cg_orders', chart_type: 'bar', dimensions: [{ field: 'category' }],
    metrics: [
      { key: 'm_orders', label: '订单数', field: 'id', aggregation: 'count' },
      { key: 'm_total', label: '主表金额', field: 'amount', aggregation: 'sum' },
      { key: 'm_quantity', label: '明细数量', field: 'lines.quantity', aggregation: 'sum' },
      { key: 'm_price', label: '明细均价', field: 'lines.price', aggregation: 'avg' },
    ], filters: [{ field: 'amount', operator: 'in', value: records.map(record => record.amount) }], limit: 100 };
  const report = await post('reports/definitions/', { name: `时间与明细聚合-${name}`, code: `deep-${name}`, kind: 'report', definition }, 201);
  await page.goto('/reports');
  const row = page.getByRole('row').filter({ hasText: report.name });
  await row.click();
  const editor = page.locator('.report-design-card');
  const compare = editor.getByLabel('时间比较', { exact: true });
  const save = page.getByRole('button', { name: '保存草稿', exact: true });
  await expect(editor.getByLabel('指标字段', { exact: true }).nth(2)).toHaveValue('lines.quantity');
  await expect(editor.getByLabel('指标字段', { exact: true }).nth(3)).toHaveValue('lines.price');
  await compare.selectOption('previous_period');
  await expect(editor.getByRole('alert')).toContainText('请填写有效比较区间');
  await expect(save).toBeDisabled();
  await editor.getByLabel('比较日期字段', { exact: true }).selectOption('created_at');
  await editor.getByLabel('开始日期（含）', { exact: true }).fill(start);
  await editor.getByLabel('结束日期（不含）', { exact: true }).fill(start);
  await expect(save).toBeDisabled();
  await editor.getByLabel('结束日期（不含）', { exact: true }).fill(end);
  await expect(save).toBeEnabled();
  const saveDefinition = async mode => {
    const response = page.waitForResponse(value => value.url().endsWith(`/reports/definitions/${report.id}/`) && value.request().method() === 'PATCH');
    await save.click();
    expect((await response).status()).toBe(200);
    await expect(compare).toBeEnabled();
    expect((await get(`reports/definitions/${report.id}/`)).definition.comparison).toEqual({ field: 'created_at', mode, start, end });
  };
  await saveDefinition('previous_period');
  await compare.selectOption('previous_year');
  await saveDefinition('previous_year');
  // Reload confirms the server round trip and the editor's comparison migration path.
  await page.reload();
  await row.click();
  await expect(compare).toHaveValue('previous_year');
  await expect(editor.getByLabel('开始日期（含）', { exact: true })).toHaveValue(start);
  await compare.selectOption('previous_period');
  await saveDefinition('previous_period');
  await page.getByRole('button', { name: '发布', exact: true }).click();
  await expect(compare).toBeDisabled();
  await row.getByRole('button', { name: '运行', exact: true }).click();
  const viewer = page.locator('.report-viewer');
  await expect(viewer.getByRole('status')).toContainText(`本期 ${start} 至 ${end}`);
  const result = await get(`reports/definitions/${report.id}/run/`);
  expect(result.rows).toHaveLength(1);
  const aggregate = result.rows[0];
  expect(aggregate.category).toBe('office');
  expect(aggregate.m_orders).toBe(2);
  expect(decimal(aggregate.m_total)).toBe(String(150000 + offset * 9));
  expect(aggregate.m_quantity).toBe(9);
  expect(decimal(aggregate.m_price)).toBe(String(15000 + offset));
  expect(aggregate.m_orders_previous).toBe(0);
  expect(decimal(aggregate.m_orders_delta)).toBe('2');
  for (const metric of definition.metrics) expect(aggregate[metric.key + '_rate']).toBeNull();
  expect(aggregate.m_total_previous).toBeNull();
  expect(aggregate.m_total_delta).toBeNull();
  expect(result.chart_columns).toEqual(definition.metrics.flatMap(metric => [metric.key, metric.key + '_previous']));
  const table = viewer.locator('table.result');
  await expect(table.locator('tbody tr')).toHaveCount(1);
  const cells = table.locator('tbody tr').locator('td');
  for (const [index, column] of result.columns.entries()) {
    const actual = await cells.nth(index).innerText();
    expect(decimal(actual)).toBe(aggregate[column] == null ? '' : decimal(aggregate[column]));
  }
  await expect(table.locator('thead')).toContainText('主表金额·差额');
  await expect(table.locator('thead')).toContainText('明细数量·变化率(%)');
  expect(await cells.first().evaluate(node => getComputedStyle(node).whiteSpace)).toBe('nowrap');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await viewer.getByRole('heading', { name: report.name, exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(evidence, `reports-${name}-comparison.png`) });
  await viewer.getByRole('button', { name: '查看明细', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '报表明细', exact: true });
  await expect(dialog).toContainText('时间比较仅下钻本期');
  await expect(dialog.locator('tbody tr')).toHaveCount(2);
  await expect(dialog.locator('thead')).toContainText('明细数量·本单明细汇总');
  await expect(dialog.locator('thead')).not.toContainText('remarks');
  const details = await post(`reports/definitions/${report.id}/details/`, { widget: 'single', group: { category: 'office' }, page: 1, page_size: 20 });
  expect(details.rows.map(record => record.id).sort()).toEqual(records.map(record => record.id).sort());
  expect(details.rows.map(record => record.m_quantity).sort()).toEqual([4, 5]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `reports-${name}-detail-aggregation.png`) });
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  // Malformed relation traversal and unsupported date-bucket comparison fail at the real API boundary.
  const comparison = { field: 'created_at', mode: 'previous_period', start, end };
  await post('reports/definitions/', { name: '不可注册关联', code: `deep-invalid-${name}`, kind: 'report',
    definition: { ...definition, metrics: [{ key: 'm_bad', label: '错误字段', field: 'supplier.amount', aggregation: 'sum' }] } }, 400);
  await post('reports/definitions/', { name: '比较配置冲突', code: `deep-conflict-${name}`, kind: 'report',
    definition: { ...definition, comparison, dimensions: [{ field: 'created_at', grain: 'day' }] } }, 400);
  checks.push(`${name}: real API/UI persisted period/year comparison, invalid-range blocking, fan-out-safe parent totals, weighted detail average, null baseline, chart columns, current-period parent drill-down and responsive tables`);
}
