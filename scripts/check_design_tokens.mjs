#!/usr/bin/env node
/**
 * Verify @synthet/image-scoring-design is installed and synced Gradio CSS matches the package.
 */
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')

const PACKAGE_GRADIO = path.join(
  ROOT,
  'frontend',
  'node_modules',
  '@synthet',
  'image-scoring-design',
  'dist',
  'gradio-snippet.css',
)
const SIBLING_GRADIO = path.resolve(ROOT, '..', 'image-scoring-ui', 'dist', 'gradio-snippet.css')
const SYNCED_GRADIO = path.join(ROOT, 'modules', 'ui', 'gradio_design_tokens.css')

async function sha256(filePath) {
  const data = await fs.readFile(filePath)
  return crypto.createHash('sha256').update(data).digest('hex')
}

async function resolvePackageGradio() {
  try {
    await fs.access(PACKAGE_GRADIO)
    return PACKAGE_GRADIO
  } catch {
    try {
      await fs.access(SIBLING_GRADIO)
      console.warn(
        `Package not in frontend/node_modules; using sibling build: ${SIBLING_GRADIO}`,
      )
      return SIBLING_GRADIO
    } catch {
      console.error(
        'Missing @synthet/image-scoring-design: run npm install in frontend/ and ensure image-scoring-ui is built.',
      )
      process.exit(1)
    }
  }
}

async function checkDesignTokens() {
  const packageGradio = await resolvePackageGradio()

  try {
    await fs.access(SYNCED_GRADIO)
  } catch {
    console.error(`Synced file missing: ${SYNCED_GRADIO}`)
    console.error('Run: npm run design:sync (from repo root or frontend/)')
    process.exit(1)
  }

  const [packageHash, syncedHash] = await Promise.all([
    sha256(packageGradio),
    sha256(SYNCED_GRADIO),
  ])

  if (packageHash !== syncedHash) {
    console.error('gradio_design_tokens.css is out of date.')
    console.error(`  package: ${packageGradio}`)
    console.error(`  synced:  ${SYNCED_GRADIO}`)
    console.error('Run: npm run design:sync')
    process.exit(1)
  }

  console.log('Design tokens OK (gradio-snippet.css hash matches).')
}

const isMain =
  process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))

if (isMain) {
  await checkDesignTokens()
}

export { checkDesignTokens }
