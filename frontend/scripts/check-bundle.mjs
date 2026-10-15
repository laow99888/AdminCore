import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { gzipSync } from 'node:zlib'
import assert from 'node:assert/strict'

const manifest = JSON.parse(readFileSync('dist/.vite/manifest.json', 'utf8'))
const { profile } = JSON.parse(readFileSync('dist/build-profile.json', 'utf8'))
assert(['full', 'minimal'].includes(profile), '构建能力标记无效')
const minimal = profile === 'minimal'
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
assert(initial.every(file => !file.includes('localWorkbook')), '登录首屏不可加载本地导出 Worker')
const pdfRenderer = Object.keys(manifest).find(key => /pdf-preview~pdf-/.test(key))
assert(minimal ? !pdfRenderer : pdfRenderer && !visited.has(pdfRenderer), 'PDF 渲染器必须按构建能力发布并排除登录首屏')
const richTextEditor = Object.keys(manifest).find(key => key.endsWith('/RichTextEditorCore.vue'))
assert(minimal ? !richTextEditor : richTextEditor && !visited.has(richTextEditor), '富文本编辑器必须按构建能力发布并排除登录首屏')
const virtualTable = Object.keys(manifest).find(key => key.endsWith('/BaseVirtualTable.vue'))
assert(virtualTable && !visited.has(virtualTable), '虚拟表格必须独立按需加载，不进入登录首屏')
for (const [key, chunk] of Object.entries(manifest)) {
  if (key.includes('tiptap') || key.includes('prosemirror') || /richtext-editor/.test(chunk.file)) {
    assert(!visited.has(key), '登录首屏不可加载富文本编辑依赖')
  }
}
if (!minimal) {
assert(readFileSync('dist/third-party/richtext/dompurify-LICENSE.txt', 'utf8').includes('Apache License'), '富文本依赖许可证缺失')
assert(readFileSync('dist/third-party/richtext/tiptap-core-LICENSE.txt', 'utf8').includes('Tiptap GmbH'), 'Tiptap 版权说明缺失')
assert(readFileSync('dist/third-party/sheetjs/LICENSE', 'utf8').includes('Apache License'), 'SheetJS 许可证缺失')
assert(readFileSync('dist/third-party/sheetjs/README.md', 'utf8').includes('0.20.3'), 'SheetJS 来源与版本说明缺失')
const sheetPackage = createHash('sha512').update(readFileSync('vendor/xlsx-0.20.3.tgz')).digest('base64')
const sheetLock = JSON.parse(readFileSync('package-lock.json', 'utf8')).packages['node_modules/xlsx']
assert(sheetLock.version === '0.20.3' && sheetLock.resolved === 'file:vendor/xlsx-0.20.3.tgz' && sheetLock.integrity === `sha512-${sheetPackage}`, 'SheetJS 包来源、版本或摘要与锁文件不一致')
} else {
  for (const target of ['pdf-assets', 'third-party/richtext', 'third-party/sheetjs']) assert(!existsSync(`dist/${target}`), `精简构建不可发布 ${target}`)
  assert(!Object.keys(manifest).some(key => /views\/(files|approvals|notifications|tasks|example)\//.test(key) || /views\/system\/(Organization|PostManagement|SystemDiagnostics|SystemConfig|DictionaryList|CacheManagement)View/.test(key)), '精简构建不可发布可选模块页面')
}
const sizes = readdirSync('dist/assets').filter(file => file.endsWith('.js')).map(file => ({ file, bytes: statSync(`dist/assets/${file}`).size }))
assert(sizes.filter(chunk => /^localWorkbook\.worker-/.test(chunk.file)).length === (minimal ? 0 : 1), '本地导出 Worker 数量与构建能力不一致')
if (minimal) assert(sizes.every(chunk => !/pdf[.-]worker|pdf-preview|richtext-editor/.test(chunk.file)), '精简构建不得残留被裁剪的 Worker 或编辑器')
const largest = sizes.reduce((previous, current) => current.bytes > previous.bytes ? current : previous)
const initialGzip = initial.reduce((sum, file) => sum + gzipSync(readFileSync(`dist/${file}`)).length, 0)
// 图表单独懒加载并保持内部执行顺序；其他块仍使用更严格预算。
for (const chunk of sizes) {
  const budget = /^(charts-|pdf-preview~pdf-)/.test(chunk.file) ? 600 * 1024 : /^localWorkbook\.worker-/.test(chunk.file) ? 500 * 1024 : 350 * 1024
  assert(chunk.bytes <= budget, `JS chunk 超出预算: ${chunk.file}, ${chunk.bytes}`)
}
assert(initialGzip <= 180 * 1024, `登录首屏 JS gzip 超出 180 KiB: ${initialGzip}`)
console.log(JSON.stringify({ profile, jsChunks: sizes.length, largestChunk: largest, loginInitialJsChunks: initial.length, loginInitialJsGzipBytes: initialGzip, chartsExcludedFromLogin: true, pdfExcludedFromLogin: true, richTextEditorExcludedFromLogin: true, virtualTableExcludedFromLogin: true, richTextLicensesIncluded: !minimal, localExportWorkerExcludedFromLogin: true, localExportWorkerBytes: sizes.find(chunk => /^localWorkbook\.worker-/.test(chunk.file))?.bytes ?? 0, sheetJsLicenseIncluded: !minimal }, null, 2))
