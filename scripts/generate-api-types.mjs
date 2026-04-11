#!/usr/bin/env node
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const ROOT = path.resolve(__dirname, '..')

const OPENAPI_PATH = path.join(ROOT, 'openapi.json')
const OUTPUT_PATH = path.join(ROOT, 'electron', 'apiTypes.ts')

const HEADER = `/**\n * AUTO-GENERATED FILE - DO NOT EDIT.\n *\n * Source of truth: ./openapi.json\n * Regenerate with: npm run api:types:generate\n */\n\n`

function stableStringify(value, indent = 2) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item, indent)).join(', ')}]`
  }
  if (value && typeof value === 'object') {
    const keys = Object.keys(value).sort((a, b) => a.localeCompare(b))
    const entries = keys.map((key) => `${JSON.stringify(key)}: ${stableStringify(value[key], indent)}`)
    return `{${entries.join(', ')}}`
  }
  return JSON.stringify(value)
}

export async function generateApiTypes() {
  const schema = JSON.parse(await fs.readFile(OPENAPI_PATH, 'utf8'))
  const schemaLiteral = stableStringify(schema)

  const generated = `${HEADER}export const OPENAPI_SCHEMA = ${schemaLiteral} as const;\n\nexport type OpenApiSchema = typeof OPENAPI_SCHEMA;\nexport type OpenApiPaths = OpenApiSchema['paths'];\nexport type OpenApiComponents = OpenApiSchema['components'];\n`

  await fs.mkdir(path.dirname(OUTPUT_PATH), { recursive: true })
  await fs.writeFile(OUTPUT_PATH, generated, 'utf8')

  return { openapiPath: OPENAPI_PATH, outputPath: OUTPUT_PATH }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { openapiPath, outputPath } = await generateApiTypes()
  console.log(`Generated API types from ${path.relative(ROOT, openapiPath)} -> ${path.relative(ROOT, outputPath)}`)
}
