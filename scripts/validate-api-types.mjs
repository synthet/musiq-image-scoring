#!/usr/bin/env node
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { generateApiTypes } from './generate-api-types.mjs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const ROOT = path.resolve(__dirname, '..')
const OUTPUT_PATH = path.join(ROOT, 'electron', 'apiTypes.ts')

async function main() {
  const before = await fs.readFile(OUTPUT_PATH, 'utf8').catch(() => null)
  await generateApiTypes()
  const after = await fs.readFile(OUTPUT_PATH, 'utf8')

  if (before !== after) {
    const tmpPath = path.join(os.tmpdir(), `apiTypes-${Date.now()}.ts`)
    if (before !== null) {
      await fs.writeFile(tmpPath, before, 'utf8')
      try {
        const diff = execFileSync('git', ['--no-pager', 'diff', '--no-index', '--', tmpPath, OUTPUT_PATH], {
          cwd: ROOT,
          encoding: 'utf8',
          stdio: ['ignore', 'pipe', 'pipe'],
        })
        process.stdout.write(diff)
      } catch (error) {
        if (typeof error.stdout === 'string') {
          process.stdout.write(error.stdout)
        }
      }
      await fs.rm(tmpPath, { force: true })
    }

    console.error('\nAPI types are out of date.')
    console.error('Changed file: electron/apiTypes.ts')
    console.error('Source of truth: openapi.json')
    console.error('Run: npm run api:types:generate')
    process.exit(1)
  }

  console.log('API types are up to date (electron/apiTypes.ts matches openapi.json).')
}

await main()
