import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../src/', import.meta.url))
const files = fs.readdirSync(root, { recursive: true }).filter(file => /\.(ts|vue)$/.test(file) && !file.includes('generated'))
const keys = new Set()
for (const file of files.filter(file => /messages.*\.ts$/i.test(path.basename(file)))) {
  const source = ts.createSourceFile(file, fs.readFileSync(path.join(root, file), 'utf8'), ts.ScriptTarget.Latest, true)
  function visit(node) {
    if (ts.isPropertyAssignment(node) && (ts.isStringLiteral(node.name) || ts.isIdentifier(node.name))) keys.add(node.name.text)
    ts.forEachChild(node, visit)
  }
  visit(source)
}
const missing = new Map()
let count = 0
for (const file of files) {
  const source = fs.readFileSync(path.join(root, file), 'utf8')
  for (const match of source.matchAll(/\buiText\(\s*(['"])((?:\\.|(?!\1)[^\r\n])*)\1/g)) {
    count++
    const key = match[2].replace(/\\(['"\\])/g, '$1')
    if (!keys.has(key)) missing.set(key, file)
  }
}
if (missing.size) {
  for (const [key, file] of missing) console.error(`${file}: missing translation for ${key}`)
  process.exitCode = 1
} else console.log(`UI messages: ${count} static calls checked; no missing keys.`)
