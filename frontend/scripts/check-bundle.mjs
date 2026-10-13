import { readFileSync, readdirSync, statSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import assert from 'node:assert/strict'

const manifest = JSON.parse(readFileSync('dist/.vite/manifest.json', 'utf8'))
const entry = Object.keys(manifest).find(key => manifest[key].isEntry)
const login = Object.keys(manifest).find(key => key.endsWith('/LoginView.vue'))
assert(entry && login, '缺少入口或登录页 manifest')
const visited = new Set()
function visit(key) {
  if (visited.has(key)) return
  visited.add(key)
  for (const dependency of manifest[key].imports || []) visit(dependency)
}
visit(entry)
visit(login)
const initial = [...visited].map(key => manifest[key].file).filter(file => file.endsWith('.js'))
assert(initial.every(file => !file.includes('charts')), '登录首屏不可加载图表依赖')
const sizes = readdirSync('dist/assets').filter(file => file.endsWith('.js')).map(file => ({ file, bytes: statSync(`dist/assets/${file}`).size }))
const largest = sizes.reduce((previous, current) => current.bytes > previous.bytes ? current : previous)
const initialGzip = initial.reduce((sum, file) => sum + gzipSync(readFileSync(`dist/${file}`)).length, 0)
// 图表单独懒加载并保持内部执行顺序；其他块仍使用更严格预算。
for (const chunk of sizes) {
  const budget = chunk.file.startsWith('charts-') ? 600 * 1024 : 350 * 1024
  assert(chunk.bytes <= budget, `JS chunk 超出预算: ${chunk.file}, ${chunk.bytes}`)
}
assert(initialGzip <= 180 * 1024, `登录首屏 JS gzip 超出 180 KiB: ${initialGzip}`)
console.log(JSON.stringify({ jsChunks: sizes.length, largestChunk: largest, loginInitialJsChunks: initial.length, loginInitialJsGzipBytes: initialGzip, chartsExcludedFromLogin: true }, null, 2))
