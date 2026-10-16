import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'
import openapiTS, { astToString } from 'openapi-typescript'
import ts from 'typescript'

const root = fileURLToPath(new URL('../../', import.meta.url))
const { values } = parseArgs({ options: { check: { type: 'boolean' }, profile: { type: 'string', default: 'full' }, modules: { type: 'string' }, 'output-dir': { type: 'string' } } })
if (!['full', 'standard', 'minimal'].includes(values.profile)) throw new Error('profile must be full, standard or minimal')
if ((values.profile !== 'full' || values.modules !== undefined) && !values['output-dir']) throw new Error('Custom module contracts require an explicit --output-dir')
const destination = values['output-dir'] ? path.resolve(values['output-dir']) : path.join(root, 'frontend/src/api/generated')
const localPython = path.join(root, 'backend/venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const python = process.env.ADMINCORE_PYTHON || (existsSync(localPython) ? localPython : process.platform === 'win32' ? 'python' : 'python3')
const temporary = mkdtempSync(path.join(tmpdir(), 'admincore-sdk-'))
try {
  const schemaFile = path.join(temporary, 'schema.json')
  const args = [path.join(root, 'scripts/export_openapi.py'), '--profile', values.profile, '--output', schemaFile]
  if (values.modules !== undefined) args.push('--modules', values.modules)
  const exported = spawnSync(python, args, { cwd: root, encoding: 'utf8', timeout: 120000, windowsHide: true })
  if (exported.status !== 0) throw new Error(`OpenAPI export failed.\n${exported.stderr || exported.error?.message || 'Unknown export error'}`)
  const schemaText = readFileSync(schemaFile, 'utf8')
  const schema = JSON.parse(schemaText)
  function localReferences(value) {
    if (!value || typeof value !== 'object') return
    if ('$ref' in value && (typeof value.$ref !== 'string' || !value.$ref.startsWith('#/'))) throw new Error('SDK export requires local references')
    for (const item of Object.values(value)) localReferences(item)
  }
  localReferences(schema)
  const ast = await openapiTS(schema, { alphabetize: true, immutable: false,
    transform(value) { if (value.format === 'binary') return ts.factory.createTypeReferenceNode('Blob') },
  })
  const types = '// 自动生成，请运行 npm run sdk:generate，勿手工修改。\n' + astToString(ast)
  const routes = {}
  for (const [url, item] of Object.entries(schema.paths)) {
    if (!url.startsWith('/api/v1/')) throw new Error('SDK export requires API v1 paths')
    for (const [method, operation] of Object.entries(item)) {
      if (!['get', 'post', 'put', 'patch', 'delete', 'head', 'options'].includes(method)) continue
      if (!operation.operationId || routes[operation.operationId]) throw new Error('SDK operations require unique operationId')
      routes[operation.operationId] = [method, url]
    }
  }
  const routeSource = '// 自动生成，请运行 npm run sdk:generate，勿手工修改。\nimport type { operations } from \'./schema\'\n\nexport const sdkRoutes = '
    + JSON.stringify(routes, null, 2) + ' as const satisfies Record<keyof operations, readonly [string, string]>\n'
  const outputs = { 'openapi.json': schemaText, 'schema.ts': types, 'routes.ts': routeSource }
  for (const [name, content] of Object.entries(outputs)) {
    const target = path.join(destination, name)
    if (values.check) {
      if (!existsSync(target) || readFileSync(target, 'utf8').replace(/\r\n/g, '\n') !== content) {
        throw new Error(`SDK contract drift: ${name}. Run npm run sdk:generate and commit the result.`)
      }
    } else {
      mkdirSync(destination, { recursive: true })
      writeFileSync(target, content, 'utf8')
    }
  }
  console.log(JSON.stringify({ checked: !!values.check, profile: values.profile, paths: Object.keys(schema.paths).length, modules: schema.info['x-admincore-modules'] }))
} finally {
  rmSync(temporary, { recursive: true, force: true })
}
