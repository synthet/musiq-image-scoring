#!/usr/bin/env node
/**
 * Copy Gradio design tokens from sibling image-scoring-ui into the backend UI bundle.
 *
 * Source: ../image-scoring-ui/dist/gradio-snippet.css
 * Target: modules/ui/gradio_design_tokens.css
 */
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')

const SOURCE = path.resolve(ROOT, '..', 'image-scoring-ui', 'dist', 'gradio-snippet.css')
const TARGET = path.join(ROOT, 'modules', 'ui', 'gradio_design_tokens.css')

async function syncDesignTokens() {
  try {
    await fs.access(SOURCE)
  } catch {
    console.error(`Source not found: ${SOURCE}`)
    console.error('Build image-scoring-ui first: cd ../image-scoring-ui && npm run build')
    process.exit(1)
  }

  const content = await fs.readFile(SOURCE, 'utf8')
  await fs.mkdir(path.dirname(TARGET), { recursive: true })
  await fs.writeFile(TARGET, content, 'utf8')
  console.log(`Synced ${SOURCE} -> ${TARGET}`)
  return { source: SOURCE, target: TARGET }
}

const isMain =
  process.argv[1] &&
  path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))

if (isMain) {
  await syncDesignTokens()
}

export { syncDesignTokens, SOURCE, TARGET }
