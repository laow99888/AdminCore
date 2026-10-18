/** Keep fixture API setup/assertions in the page's current login, including normal access rotation. */
export async function browserSessionAPI(page, context) {
  const origin = new URL(page.url()).origin;
  const readSession = refresh => page.evaluate(async refresh => {
    const stores = document.querySelector('#app')?.__vue_app__?.config.globalProperties.$pinia?._s;
    const auth = stores?.get('auth');
    if (refresh) {
      if (!auth || !await auth.fetchUser(true)) throw new Error('Browser fixture session could not refresh');
    }
    const tenant = stores?.get('tenants')?.currentId || '';
    const storedTenant = localStorage.getItem('admincore.tenant') || '';
    if (tenant !== storedTenant) throw new Error('Browser fixture tenant selection is inconsistent');
    const user = auth?.user;
    return { access: localStorage.getItem('token'), tenant,
      scope: JSON.stringify([user?.id, [...(user?.permissions || [])].sort(), user?.is_staff,
        user?.is_superuser, user?.must_change_password, tenant]) };
  }, refresh);
  const identity = token => {
    try {
      const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
      if (typeof claims.sid !== 'string' || typeof claims.user_id !== 'string' || typeof claims.session_version !== 'number') return null;
      return JSON.stringify([claims.sid, claims.user_id, claims.session_version]);
    } catch { return null; }
  };
  const initial = await readSession(false), owner = identity(initial.access);
  if (!owner) throw new Error('Browser fixture requires an authenticated bearer session');
  const headers = { Authorization: 'Bearer ' + initial.access,
    ...(initial.tenant ? { 'X-AdminCore-Tenant': initial.tenant } : {}) };
  async function current(refresh = false) {
    const session = await readSession(refresh);
    if (identity(session.access) !== owner) throw new Error('Browser fixture login changed during API validation');
    if (session.scope !== initial.scope) throw new Error('Browser fixture security context changed during API validation');
    return session.access;
  }
  const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'fetch']);
  const request = new Proxy(context.request, {
    get(target, property) {
      const method = Reflect.get(target, property);
      if (!methods.has(property)) return typeof method === 'function' ? method.bind(target) : method;
      return async (url, options = {}) => {
        // Explicit employee/API-key requests must retain their own identity and status checks.
        if (options.headers !== headers) return method.call(target, url, options);
        const destination = new URL(url, origin);
        if (destination.origin !== origin || !destination.pathname.startsWith('/api/v1/')) throw new Error('Browser fixture API request left its origin');
        let access = await current();
        const send = () => method.call(target, url, { ...options, headers: { ...headers, Authorization: 'Bearer ' + access } });
        const response = await send();
        await current();
        if (response.status() !== 401) return response;
        // Let the application's axios/refresh lock perform rotation; never rotate independently.
        const latest = await current();
        const refreshed = latest === access ? await current(true) : latest;
        if (refreshed === access) return response;
        access = refreshed;
        const replay = await send();
        await current();
        return replay;
      };
    },
  });
  return {
    headers,
    context: new Proxy(context, { get(target, property) {
      if (property === 'request') return request;
      const value = Reflect.get(target, property);
      return typeof value === 'function' ? value.bind(target) : value;
    } }),
  };
}
