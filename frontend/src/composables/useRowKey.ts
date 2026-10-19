/** 未保存的可编辑行使用对象身份；删除中间行时不复用其它行的输入状态。 */
export function useRowKey() {
  const keys = new WeakMap<object, number>()
  let sequence = 0
  return (row: object): number => {
    let key = keys.get(row)
    if (key === undefined) { key = ++sequence; keys.set(row, key) }
    return key
  }
}
