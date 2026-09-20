import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const webRoot = resolve(scriptDir, '..')
const source = resolve(webRoot, 'dist')
const destination = resolve(webRoot, '..', 'src', 'mshub', 'web')

if (!existsSync(source)) {
  throw new Error(`Frontend build output is missing: ${source}`)
}

rmSync(destination, { recursive: true, force: true })
mkdirSync(destination, { recursive: true })
cpSync(source, destination, { recursive: true })
console.log(`Copied production UI to ${destination}`)
