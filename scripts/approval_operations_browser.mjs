/** 在独占数据库中验证版本发布、退回、超时去重和重新审批。 */
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

export async function validateApprovalOperations({ page, name, evidence, expect, checks, get, post }) {
  const actor = await get('auth/me/');
  const title = `运营审批-${name}`;
  const definition = { schema_version: 2, inputs: [], nodes: [
    { id: 'start', type: 'start' },
    { id: 'first', type: 'user', assignee_ids: [actor.id], timeout: { minutes: 1, escalate_after_minutes: 2, escalate_to: actor.id } },
    { id: 'second', type: 'user', assignee_ids: [actor.id] }, { id: 'end', type: 'end' },
  ], edges: [{ from: 'start', to: 'first' }, { from: 'first', to: 'second' }, { from: 'second', to: 'end' }] };
  const flow = await post('approvals/flows/', { name: title, code: `operations-${name}`, definition }, 201);
  await post(`approvals/flows/${flow.id}/publish/`, { version: flow.version });
  const app = await post('approvals/', { title, content: '验证退回和超时提醒', flow_id: flow.id }, 201);
  await post(`approvals/${app.id}/approve/`, {});
  await page.goto('/approvals/flows');
  let row = page.getByRole('row').filter({ hasText: title });
  await row.getByRole('button', { name: '编辑', exact: true }).click();
  await expect(page.getByRole('spinbutton', { name: '提醒时限分钟，0关闭', exact: true }).first()).toHaveValue('1');
  await page.getByRole('button', { name: '新建版本', exact: true }).click();
  await expect(page.getByRole('button', { name: '发布', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '发布', exact: true }).click();
  await expect(page.getByRole('button', { name: '发布', exact: true })).toHaveCount(0);
  const releases = (await get(`approvals/flows/?code=operations-${name}&ordering=-revision`)).items;
  expect(releases.map(item => item.revision)).toEqual([2, 1]);
  expect(releases[0].status).toBe('published'); expect(releases[1].status).toBe('archived');
  expect((await get(`approvals/${app.id}/`)).flow).toBe(flow.id);
  checks.push(`${name}: create and publish same-code release; in-flight application stays on old release`);

  await page.goto('/approvals');
  await page.reload();
  row = page.getByRole('row').filter({ hasText: title });
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: '详情', exact: true }).click();
  let detail = page.getByRole('dialog', { name: '申请详情', exact: true });
  await detail.getByRole('button', { name: '退回指定节点', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '退回指定节点', exact: true });
  await dialog.getByLabel('操作原因', { exact: true }).fill('浏览器退回重审');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `approval-${name}-return-dialog.png`), fullPage: true, animations: 'disabled' });
  await dialog.getByRole('button', { name: '确认', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(detail).toContainText('浏览器退回重审');
  const returned = await get(`approvals/${app.id}/`);
  expect(returned.current_node).toBe('first'); expect(returned.return_count).toBe(1);
  expect(returned.steps.map(step => step.status)).toEqual(['approved', 'cancelled', 'pending']);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(evidence, `approval-${name}-returned.png`), fullPage: true, animations: 'disabled' });
  await detail.getByRole('button', { name: '关闭', exact: true }).click();

  // 只推进本次创建的待办时钟，不更改宿主或共享数据库。
  const scan = `import django; django.setup()
from datetime import timedelta
from django.utils import timezone
from apps.approvals.models import ApprovalStep
from apps.approvals.tasks import scan_overdue
ApprovalStep.objects.filter(request_id=${JSON.stringify(app.id)}, status='pending').update(due_at=timezone.now()-timedelta(minutes=2), escalate_at=timezone.now()-timedelta(minutes=1))
assert scan_overdue()['processed'] == 2
assert scan_overdue()['processed'] == 0
`;
  execFileSync(process.env.ADMINCORE_VALIDATION_PYTHON, ['-X', 'utf8', '-c', scan], { cwd: process.env.ADMINCORE_VALIDATION_BACKEND, env: process.env, windowsHide: true, stdio: 'pipe' });
  await page.reload();
  await row.getByRole('button', { name: '详情', exact: true }).click();
  detail = page.getByRole('dialog', { name: '申请详情', exact: true });
  await expect(detail).toContainText('提醒已进入通知队列');
  await expect(detail).toContainText('升级通知已进入队列');
  await expect(detail).toContainText('已入队，送达状态请查看通知中心');
  await detail.locator('.approval-operations').scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(evidence, `approval-${name}-overdue.png`), fullPage: true, animations: 'disabled' });
  await detail.getByRole('button', { name: '关闭', exact: true }).click();
  checks.push(`${name}: return creates a new visit; overdue scan queues reminder and escalation once`);

  for (const currentNode of ['second', 'end']) {
    await row.getByRole('button', { name: '通过', exact: true }).click();
    await page.locator('.el-message-box').getByRole('button', { name: '通过', exact: true }).click();
    await expect.poll(async () => (await get(`approvals/${app.id}/`)).current_node).toBe(currentNode);
    if (currentNode === 'second') await page.reload();
  }
  expect((await get(`approvals/${app.id}/`)).status).toBe('approved');
  checks.push(`${name}: browser sends current version and completes returned workflow without overwriting history`);
}

/** 工作日配置与诊断的真实 UI 验收；仅供独占验收数据库调用。 */
export async function validateApprovalCalendarDiagnostics({ page, name, evidence, expect, checks, get, post }) {
  const actor = await get('auth/me/');
  const title = `工作日诊断-${name}`;
  const code = `calendar-${name}`;
  const definition = { schema_version: 2, inputs: [], nodes: [
    { id: 'start', type: 'start' },
    { id: 'first', type: 'user', assignee_ids: [actor.id], timeout: { minutes: 90 } },
    { id: 'end', type: 'end' },
  ], edges: [{ from: 'start', to: 'first' }, { from: 'first', to: 'end' }] };
  const flow = await post('approvals/flows/', { name: title, code, definition }, 201);
  await page.goto('/approvals/flows');
  await page.getByRole('row').filter({ hasText: title }).getByRole('button', { name: '编辑', exact: true }).click();
  const calendar = page.locator('.working-calendar');
  await calendar.locator('.el-switch').click();
  await expect(calendar.getByRole('switch', { name: '仅累计工作时段', exact: true })).toBeChecked();
  await calendar.getByRole('textbox', { name: '日历时区', exact: true }).fill('UTC');
  await calendar.getByRole('textbox', { name: '休息日期（每行一个）', exact: true }).fill('2026-02-30');
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  await expect(page.locator('.el-message--error')).toContainText('工作日历无效');
  expect((await get(`approvals/flows/${flow.id}/`)).definition.nodes[1].timeout.calendar).toBeUndefined();
  await calendar.getByRole('textbox', { name: '休息日期（每行一个）', exact: true }).fill('2026-10-01');
  await calendar.getByRole('textbox', { name: '补班日期（每行一个）', exact: true }).fill('2026-10-10');
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  const expected = { timezone: 'UTC', weekdays: [1, 2, 3, 4, 5], start: '09:00', end: '18:00', closed_dates: ['2026-10-01'], extra_dates: ['2026-10-10'] };
  await expect.poll(async () => (await get(`approvals/flows/${flow.id}/`)).definition.nodes[1].timeout.calendar).toEqual(expected);
  await page.getByRole('button', { name: '发布', exact: true }).click();
  await expect(calendar.getByRole('textbox', { name: '日历时区', exact: true })).toBeDisabled();
  await page.screenshot({ path: resolve(evidence, `approval-${name}-calendar-published.png`), fullPage: true, animations: 'disabled' });
  const app = await post('approvals/', { title, content: '工作日历和无副作用诊断', flow_id: flow.id }, 201);
  const due = new Date(app.steps[0].due_at);
  expect(due.getUTCHours() >= 9 && due.getUTCHours() <= 18).toBe(true);
  expect([1, 2, 3, 4, 5].includes(due.getUTCDay()) || expected.extra_dates.includes(due.toISOString().slice(0, 10))).toBe(true);
  expect(expected.closed_dates.includes(due.toISOString().slice(0, 10))).toBe(false);
  const before = (await get(`approvals/${app.id}/history/`)).pagination.total;
  await page.goto('/approvals');
  await page.getByRole('row').filter({ hasText: title }).getByRole('button', { name: '详情', exact: true }).click();
  const detail = page.getByRole('dialog', { name: '申请详情', exact: true });
  const diagnosis = detail.getByRole('region', { name: '审批阻塞诊断', exact: true });
  await diagnosis.getByRole('button', { name: '重新诊断', exact: true }).click();
  await expect(diagnosis).toContainText('本批未发现已检查范围内的问题');
  expect((await get(`approvals/${app.id}/history/`)).pagination.total).toBe(before);
  await detail.getByRole('button', { name: '关闭', exact: true }).click();
  checks.push(`${name}: calendar editor rejects invalid date, saves frozen release and creates business-window deadline; healthy diagnosis does not append history`);

  // 仅在独占验收库内创建一个无密码测试账号，模拟进入当前节点后离职。
  const seed = `import django; django.setup()
from django.contrib.auth import get_user_model
u = get_user_model().objects.create(username=${JSON.stringify(`calendar-blocked-${name}`)})
u.set_unusable_password(); u.save(update_fields=['password'])
print(u.pk)
`;
  const options = { cwd: process.env.ADMINCORE_VALIDATION_BACKEND, env: process.env, windowsHide: true, encoding: 'utf8', stdio: 'pipe' };
  const reviewer = execFileSync(process.env.ADMINCORE_VALIDATION_PYTHON, ['-X', 'utf8', '-c', seed], options).trim();
  const blockedDefinition = { schema_version: 2, inputs: [], nodes: [
    { id: 'start', type: 'start' }, { id: 'first', type: 'user', assignee_ids: [reviewer] },
    { id: 'second', type: 'user', assignee_ids: [reviewer] }, { id: 'end', type: 'end' },
  ], edges: [{ from: 'start', to: 'first' }, { from: 'first', to: 'second' }, { from: 'second', to: 'end' }] };
  const blockedFlow = await post('approvals/flows/', { name: `阻塞-${title}`, code: `blocked-${code}`, definition: blockedDefinition }, 201);
  await post(`approvals/flows/${blockedFlow.id}/publish/`, { version: blockedFlow.version });
  const blocked = await post('approvals/', { title: `阻塞-${title}`, content: '离职后阻塞诊断', flow_id: blockedFlow.id }, 201);
  const disable = `import django; django.setup()
from django.contrib.auth import get_user_model
get_user_model().objects.filter(pk=${JSON.stringify(reviewer)}).update(is_active=False)
`;
  execFileSync(process.env.ADMINCORE_VALIDATION_PYTHON, ['-X', 'utf8', '-c', disable], options);
  await page.reload();
  await page.getByRole('tab', { name: '我的申请', exact: true }).click();
  await page.getByRole('row').filter({ hasText: `阻塞-${title}` }).getByRole('button', { name: '详情', exact: true }).click();
  const blockedDetail = page.getByRole('dialog', { name: '申请详情', exact: true });
  const blockedDiagnosis = blockedDetail.getByRole('region', { name: '审批阻塞诊断', exact: true });
  await blockedDiagnosis.getByRole('button', { name: '重新诊断', exact: true }).click();
  await expect(blockedDiagnosis).toContainText('存在阻塞');
  await expect(blockedDiagnosis).toContainText('后续节点审批人无法解析');
  expect(await blockedDiagnosis.textContent()).not.toContain(`calendar-blocked-${name}`);
  await page.screenshot({ path: resolve(evidence, `approval-${name}-blocked-diagnosis.png`), fullPage: true, animations: 'disabled' });
  await blockedDetail.getByRole('button', { name: '关闭', exact: true }).click();
  await page.getByRole('tab', { name: '异常审批', exact: true }).click();
  const health = page.getByRole('region', { name: '审批阻塞诊断', exact: true });
  await health.getByRole('button', { name: '扫描待批申请', exact: true }).click();
  await expect(health).toContainText('检查时间');
  await expect(health.getByRole('button', { name: '扫描待批申请', exact: true })).toBeEnabled();
  const diagnosed = await get(`approvals/${blocked.id}/diagnostics/`);
  expect(diagnosed.blocked).toBe(true);
  checks.push(`${name}: departed reviewer is blocked; admin current/future diagnosis hides names and bounded health scan completes`);
}
