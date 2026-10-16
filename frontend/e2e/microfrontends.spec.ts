import { test, expect, type Page } from '@playwright/test'

const envelope = (data: unknown) => ({ code: 200, message: 'success', data })

async function setup(page: Page) {
  await page.addInitScript(() => localStorage.setItem('token', 'micro-browser-fixture'))
  await page.route('**/subapps/example/**', route => route.fulfill({
    contentType: 'text/html',
    body: '<!doctype html><script src="/subapps/example/entry.js"></script>',
  }))
  await page.route('**/subapps/example/entry.js', route => route.fulfill({
    contentType: 'application/javascript',
    body: `window['example-subapp'] = {
      bootstrap: async function () {},
      mount: async function (props) {
        props.container.innerHTML = '<div role="status">子应用已挂载</div>';
        props.container.host?.setAttribute('data-identity-present', String(Boolean(props.identity)));
        props.container.host?.setAttribute('data-token-prop', String('token' in props));
      },
      unmount: async function (props) { props.container.innerHTML = ''; props.container.host?.setAttribute('data-unmounted', 'true'); }
    };`,
  }))
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/modules/')) return route.fulfill({ json: envelope({ contract_version: 1, preset: 'standard', modules: [] }) })
    if (path.endsWith('/auth/me/')) return route.fulfill({ json: envelope({ id: 'micro-user', username: 'micro-user', permissions: ['example:read'], must_change_password: false }) })
    if (path.endsWith('/menus/my_menu/')) return route.fulfill({ json: envelope([]) })
    return route.fulfill({ json: envelope({}) })
  })
}

test('可信子应用实际挂载并在离开路由时卸载', async ({ page }) => {
  await setup(page)
  await page.goto('/micro/example-subapp/orders')
  const wrapper = page.locator('#__qiankun_microapp_wrapper_for_example_subapp__')
  await expect.poll(() => wrapper.evaluate(el => el.shadowRoot?.querySelector('[role="status"]')?.textContent ?? '')).toBe('子应用已挂载')
  await expect(wrapper).toHaveAttribute('data-identity-present', 'true')
  await expect(wrapper).toHaveAttribute('data-token-prop', 'false')
  await page.goto('/login')
  await expect(page.locator('#__qiankun_microapp_wrapper_for_example_subapp__')).toHaveCount(0)
})
