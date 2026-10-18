import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import { browserSessionAPI } from './browser_session_api.mjs';

const token = (sid = 'one', revision = 1) => 'fixture.' + Buffer.from(JSON.stringify({ sid, user_id: 'admin', session_version: 1, revision })).toString('base64url') + '.fixture';
function fixture(onRequest = () => 200, onRefresh = state => { state.access = token('one', 2); }) {
  const state = { access: token(), refreshes: 0, calls: [], tenant: '', user: { id: 'admin', permissions: ['*'] } };
  const auth = { get user() { return state.user; }, async fetchUser(force) { assert.equal(force, true); state.refreshes++; await onRefresh(state); return state.user; } };
  const page = {
    url: () => 'http://127.0.0.1:18471/approvals',
    evaluate: (fn, refresh) => runInNewContext(`(${fn})(refresh)`, {
      refresh, localStorage: { getItem: key => key === 'token' ? state.access : state.tenant },
      document: { querySelector: () => ({ __vue_app__: { config: { globalProperties: { $pinia: { _s: new Map([['auth', auth], ['tenants', { get currentId() { return state.tenant; } }]]) } } } } }) },
    }),
  };
  const request = {};
  for (const method of ['get', 'post', 'patch']) request[method] = async function (url, options) {
    assert.equal(this, request);
    state.calls.push({ method, url, options });
    const status = await onRequest(state, url, options);
    return { status: () => status };
  };
  return { state, page, context: { request, isClosed() { return this.request === request; } } };
}

test('uses the current page access token after a normal rotation', async () => {
  const f = fixture(), session = await browserSessionAPI(f.page, f.context);
  f.state.access = token('one', 2);
  assert.equal((await session.context.request.get('/api/v1/auth/me/', { headers: session.headers })).status(), 200);
  assert.equal(f.state.calls[0].options.headers.Authorization, 'Bearer ' + f.state.access);
  assert.equal(f.state.refreshes, 0);
  assert.equal(session.context.isClosed(), true);
});

test('401 refreshes through the real page auth store and replays the exact request once', async () => {
  const f = fixture(state => state.calls.length === 1 ? 401 : 201), session = await browserSessionAPI(f.page, f.context);
  const data = { version: 1 }, multipart = { file: Buffer.from('fixture') };
  assert.equal((await session.context.request.post('/api/v1/files/', { headers: session.headers, data, multipart })).status(), 201);
  assert.equal(f.state.refreshes, 1); assert.equal(f.state.calls.length, 2);
  assert.equal(f.state.calls[1].options.data, data); assert.equal(f.state.calls[1].options.multipart, multipart);
  assert.notEqual(f.state.calls[0].options.headers.Authorization, f.state.calls[1].options.headers.Authorization);
});

test('reuses rotation completed while the first API request was in flight', async () => {
  const f = fixture(state => {
    if (state.calls.length === 1) { state.access = token('one', 2); return 401; }
    return 200;
  }), session = await browserSessionAPI(f.page, f.context);
  assert.equal((await session.context.request.get('/api/v1/auth/me/', { headers: session.headers })).status(), 200);
  assert.equal(f.state.refreshes, 0); assert.equal(f.state.calls.length, 2);
});

test('does not replace or refresh explicit employee and API-key credentials', async () => {
  const f = fixture(() => 401), session = await browserSessionAPI(f.page, f.context);
  for (const authorization of ['Bearer employee-fixture', 'ApiToken revoked-fixture']) {
    const headers = { Authorization: authorization };
    assert.equal((await session.context.request.get('/api/v1/tasks/', { headers })).status(), 401);
    assert.equal(f.state.calls.at(-1).options.headers, headers);
  }
  assert.equal(f.state.refreshes, 0);
});

test('preserves a genuine 401 when page authentication did not rotate', async () => {
  const f = fixture(() => 401, () => {}), session = await browserSessionAPI(f.page, f.context);
  assert.equal((await session.context.request.get('/api/v1/tasks/', { headers: session.headers })).status(), 401);
  assert.equal(f.state.calls.length, 1); assert.equal(f.state.refreshes, 1);
});

test('does not loop when the replay still returns 401', async () => {
  const f = fixture(() => 401), session = await browserSessionAPI(f.page, f.context);
  assert.equal((await session.context.request.get('/api/v1/tasks/', { headers: session.headers })).status(), 401);
  assert.equal(f.state.calls.length, 2); assert.equal(f.state.refreshes, 1);
});

test('rejects a new login before sending and after a refresh', async () => {
  const f = fixture(), session = await browserSessionAPI(f.page, f.context);
  f.state.access = token('different-login');
  await assert.rejects(session.context.request.get('/api/v1/tasks/', { headers: session.headers }), /login changed/);
  assert.equal(f.state.calls.length, 0);
  const g = fixture(() => 401, state => { state.access = token('different-login'); });
  const other = await browserSessionAPI(g.page, g.context);
  await assert.rejects(other.context.request.get('/api/v1/tasks/', { headers: other.headers }), /login changed/);
  assert.equal(g.state.calls.length, 1);
});

test('two contexts stay isolated and managed credentials cannot leave the API origin', async () => {
  const f = fixture(), g = fixture(); g.state.access = token('second-context');
  const first = await browserSessionAPI(f.page, f.context), second = await browserSessionAPI(g.page, g.context);
  await second.context.request.get('/api/v1/tasks/', { headers: second.headers });
  assert.equal(g.state.calls[0].options.headers.Authorization, 'Bearer ' + g.state.access);
  assert.equal(f.state.calls.length, 0);
  await assert.rejects(first.context.request.get('https://elsewhere.invalid/api/v1/tasks/', { headers: first.headers }), /left its origin/);
  assert.equal(f.state.calls.length, 0);
});

test('sends the selected tenant and rejects tenant or permission changes', async () => {
  const f = fixture(); f.state.tenant = 'tenant-one';
  const session = await browserSessionAPI(f.page, f.context);
  await session.context.request.get('/api/v1/tasks/', { headers: session.headers });
  assert.equal(f.state.calls[0].options.headers['X-AdminCore-Tenant'], 'tenant-one');
  f.state.tenant = 'tenant-two';
  await assert.rejects(session.context.request.get('/api/v1/tasks/', { headers: session.headers }), /security context changed/);
  f.state.tenant = 'tenant-one'; f.state.user.permissions = [];
  await assert.rejects(session.context.request.get('/api/v1/tasks/', { headers: session.headers }), /security context changed/);
  assert.equal(f.state.calls.length, 1);
});

for (const replay of [false, true]) {
  for (const change of ['login', 'version', 'permission', 'tenant']) {
    test(`rejects in-flight ${change} changes after ${replay ? 'replayed' : 'initial'} 200`, async () => {
      const f = fixture(state => {
        if (replay && state.calls.length === 1) return 401;
        if (change === 'login') state.access = token('other-login');
        if (change === 'version') state.access = 'fixture.' + Buffer.from(JSON.stringify({ sid: 'one', user_id: 'admin', session_version: 2 })).toString('base64url') + '.fixture';
        if (change === 'permission') state.user.permissions = [];
        if (change === 'tenant') state.tenant = 'other-tenant';
        return 200;
      }), session = await browserSessionAPI(f.page, f.context);
      await assert.rejects(session.context.request.get('/api/v1/tasks/', { headers: session.headers }), /changed during API validation/);
      assert.equal(f.state.calls.length, replay ? 2 : 1);
    });
  }
}
