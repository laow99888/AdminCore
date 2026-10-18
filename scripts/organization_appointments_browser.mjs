/** 任职、主管流程配置与历史快照；只访问独占夹具。 */
import { resolve } from 'node:path';

export async function validateOrganizationAppointments({ page, context, name, evidence, expect, checks, get, post, password }) {
  const day = offset => { const value = new Date(); value.setUTCDate(value.getUTCDate() + offset); return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(value); };
  const actor = await get('auth/me/');
  const username = `org-worker-${name}`;
  await post('users/', { username, email: `${username}@example.invalid`, password, must_change_password: false }, 201);
  const worker = (await get(`users/?search=${username}`)).items.find(item => item.username === username);
  const parent = await post('organization/departments/', { name: `总部-${name}`, version: 0, leader: actor.id }, 201);
  const department = await post('organization/departments/', { name: `采购部-${name}`, parent: parent.id, leader: actor.id, version: 0 }, 201);
  await page.goto('/organization');
  const departmentRow = page.getByRole('row').filter({ hasText: department.name });
  await departmentRow.getByRole('button', { name: '编辑', exact: true }).click();
  let dialog = page.getByRole('dialog', { name: '编辑', exact: true });
  await expect(dialog.getByRole('button', { name: /admin \(admin\)/ })).toBeVisible();
  await dialog.getByRole('button', { name: '确认', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect((await get(`organization/departments/${department.id}/`)).leader).toBe(actor.id);
  const panel = page.locator('.appointments');
  if (name === 'mobile') await page.getByRole('button', { name: '切换到深色模式', exact: true }).click();
  async function createAppointment(kind, target, start, reason) {
    await panel.getByRole('button', { name: '新增任职', exact: true }).click();
    dialog = page.getByRole('dialog', { name: '新增任职', exact: true });
    await dialog.getByRole('button', { name: '选择人员', exact: true }).click();
    const picker = page.getByRole('dialog', { name: '选择人员', exact: true });
    await picker.getByLabel('搜索姓名或用户名', { exact: true }).fill(username);
    await picker.getByRole('button', { name: '搜索', exact: true }).click();
    const choice = picker.getByRole('radio', { name: new RegExp(username) });
    await choice.focus(); await choice.press('Space'); await expect(choice).toBeChecked();
    await picker.getByRole('button', { name: '确认', exact: true }).click();
    await dialog.getByLabel('任职部门', { exact: true }).selectOption(target.id);
    await dialog.getByLabel('任职类型', { exact: true }).selectOption(kind);
    await dialog.getByLabel('生效日期', { exact: true }).fill(start);
    await dialog.getByLabel('任职变更原因', { exact: true }).fill(reason);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(evidence, `organization-${name}-${kind}.png`), animations: 'disabled' });
    await dialog.getByRole('button', { name: '确认', exact: true }).click();
    await expect(dialog).not.toBeVisible();
  }
  await createAppointment('primary', department, day(0), '浏览器验证当前主职');
  await createAppointment('secondary', parent, day(3), '浏览器验证未来兼职');
  let row = panel.getByRole('row').filter({ hasText: username }).filter({ hasText: day(3) });
  await row.getByRole('button', { name: '取消计划', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '取消计划', exact: true });
  await dialog.getByLabel('任职变更原因', { exact: true }).fill('撤销未来兼职');
  await dialog.getByRole('button', { name: '确认', exact: true }).click(); await expect(dialog).not.toBeVisible();
  expect((await get(`organization/appointments/?user=${worker.id}`)).items.find(item => item.kind === 'secondary').cancelled).toBe(true);
  if (name === 'mobile') await page.getByRole('button', { name: '切换到浅色模式', exact: true }).click();

  const definition = { schema_version: 2, inputs: [], nodes: [{ id: 'start', type: 'start' }, { id: 'review', type: 'user', assignee: { source: 'department_leader', levels: 2 } }, { id: 'end', type: 'end' }], edges: [{ from: 'start', to: 'review' }, { from: 'review', to: 'end' }] };
  const flow = await post('approvals/flows/', { name: `部门主管流程-${name}`, code: `dept-leader-${name}`, definition }, 201);
  await page.goto('/approvals/flows');
  await page.getByRole('row').filter({ hasText: flow.name }).getByRole('button', { name: '编辑', exact: true }).click();
  await expect(page.getByRole('spinbutton', { name: '主管层级', exact: true })).toHaveValue('2');
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  await expect(page.getByText('流程草稿已保存', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '发布', exact: true }).click();
  await expect(page.getByText('已发布', { exact: true }).last()).toBeVisible();
  const login = await context.request.post('/api/v1/auth/login/', { data: { username, password } });
  expect(login.status()).toBe(200);
  const employeeHeaders = { Authorization: 'Bearer ' + (await login.json()).access };
  const created = await context.request.post('/api/v1/approvals/', { headers: employeeHeaders, data: { title: `主管链验收-${name}`, content: '当前主职部门上级负责人', flow_id: flow.id } });
  expect(created.status(), await created.text()).toBe(201);
  const application = (await created.json()).data;
  expect(application.steps[0].assignment_context.department_name).toBe(parent.name);
  await page.goto('/approvals');
  row = page.getByRole('row').filter({ hasText: `主管链验收-${name}` });
  await row.getByRole('button', { name: '详情', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '申请详情', exact: true });
  await expect(dialog).toContainText(parent.name);
  await expect(dialog).toContainText(day(0));
  await dialog.getByText(parent.name, { exact: false }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(evidence, `organization-${name}-approval.png`), animations: 'disabled' });
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  await post(`approvals/${application.id}/approve/`, {});
  expect((await get(`approvals/${application.id}/`)).status).toBe('approved');

  await page.goto('/organization');
  row = panel.getByRole('row').filter({ hasText: username }).filter({ hasText: department.name });
  await row.getByRole('button', { name: '结束任期', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '结束任期', exact: true });
  await dialog.getByLabel('结束日期（不含当天）', { exact: true }).fill(day(1));
  await dialog.getByLabel('任职变更原因', { exact: true }).fill('验证调岗交接');
  await dialog.getByRole('button', { name: '确认', exact: true }).click(); await expect(dialog).not.toBeVisible();
  await panel.getByLabel('有效日期', { exact: true }).fill(day(1));
  await panel.getByRole('button', { name: '查询', exact: true }).click();
  await expect(panel.getByRole('row').filter({ hasText: username })).toHaveCount(0);
  await panel.getByRole('button', { name: '全部历史', exact: true }).click();
  await expect(panel.getByRole('row').filter({ hasText: username })).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await panel.locator('.base-table').scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(evidence, `organization-${name}-history.png`), animations: 'disabled' });
  const cancelledStatus = panel.getByRole('row').filter({ hasText: username }).getByText('已取消', { exact: true });
  await cancelledStatus.evaluate(node => node.scrollIntoView({ block: 'nearest', inline: 'start' }));
  if (name === 'mobile') {
    const actions = await panel.getByRole('columnheader', { name: '操作', exact: true }).boundingBox();
    const status = await cancelledStatus.boundingBox();
    expect(actions.width).toBeLessThanOrEqual(101);
    expect(status.x + status.width).toBeLessThanOrEqual(actions.x + 1);
  }
  await page.screenshot({ path: resolve(evidence, `organization-${name}-history-status.png`), animations: 'disabled' });
  checks.push(`${name}: department leader editor, primary/secondary periods, future cancellation, dated history, leader flow publish and frozen assignment details`);
}
