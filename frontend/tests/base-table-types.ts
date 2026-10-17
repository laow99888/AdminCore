/** 由 test:typecheck 编译，确保行类型能穿过表格属性与事件边界。 */
import BaseTable from '../src/components/common/BaseTable.vue'

interface Row { id: string; title: string }
type TableProps = Parameters<typeof BaseTable<Row>>[0]

export const typedTable: TableProps = {
  data: [{ id: 'one', title: '示例' }],
  columns: [{ prop: 'title', label: '标题', render: (_value, row) => row.title }],
  onEdit: row => { const id: string = row.id; void id },
  'onSelection-change': rows => { const selected: Row[] = rows; void selected },
}

export const invalidTable: TableProps = {
  // @ts-expect-error 行必须包含约定的 title 字段
  data: [{ id: 'one' }],
  columns: [],
  // @ts-expect-error 编辑事件不能被声明为数字行
  onEdit: (row: number) => { void row },
}
