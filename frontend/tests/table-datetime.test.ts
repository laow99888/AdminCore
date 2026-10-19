import { beforeEach, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import dayjs from 'dayjs'
import BaseTable from '../src/components/common/BaseTable.vue'

beforeEach(() => setActivePinia(createPinia()))

it('标准时间列使用本地时间，自定义 render 和普通业务文本保持原义', async () => {
  const iso = '2026-10-19T10:22:33.000Z'
  const wrapper = mount(BaseTable, { props: {
    data: [{ created_at: iso, updated_at: null, due: iso, note: iso, invalid: '2026-10-xxTinvalid', custom: iso, owner: { name: '嵌套姓名' } }],
    columns: [
      { prop: 'created_at', label: '创建' }, { prop: 'updated_at', label: '更新' },
      { prop: 'due', label: '期限', format: 'datetime' as const }, { prop: 'note', label: '文本' },
      { prop: 'invalid', label: '无效', format: 'datetime' as const },
      { prop: 'custom', label: '自定义', format: 'datetime' as const, render: () => '自定义显示' },
      { prop: 'owner.name', label: '嵌套字段' },
    ], showIndex: false, showActions: false,
  } })
  await flushPromises()
  const cells = wrapper.findAll('.el-table__body td').map(cell => cell.text())
  expect(cells).toEqual([dayjs(iso).format('YYYY-MM-DD HH:mm'), '', dayjs(iso).format('YYYY-MM-DD HH:mm'), iso, '2026-10-xxTinvalid', '自定义显示', '嵌套姓名'])
  wrapper.unmount()
})
