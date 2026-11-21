// pdf.js 的静态资源（CMap、标准字体、WASM 解码器、ICC 配置）：PdfViewer.vue 从 public/pdfjs/ 加载，
// 内容必须与 node_modules/pdfjs-dist 里同版本的文件一致（T24m）。
// 写成 .mjs：项目没有 @types/node，vue-tsc 会检查 tests/ 下的 .ts 文件，这里用到了 node:fs。
import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

export const FRONTEND_DIR = fileURLToPath(new URL('..', import.meta.url))
export const SOURCE_DIR = join(FRONTEND_DIR, 'node_modules', 'pdfjs-dist')
export const TARGET_DIR = join(FRONTEND_DIR, 'public', 'pdfjs')
// 与 PdfViewer.vue 里 getDocument 的 cMapUrl、standardFontDataUrl、wasmUrl、iccUrl 一一对应
export const ASSET_DIRS = ['cmaps', 'standard_fonts', 'wasm', 'iccs']

/** 目录下全部文件：相对路径（用 / 分隔）→ sha256。目录不存在时返回空。 */
export function hashFiles(root) {
  const result = new Map()
  const walk = (dir) => {
    let entries
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) walk(path)
      else if (entry.isFile()) {
        const key = relative(root, path).split(sep).join('/')
        result.set(key, createHash('sha256').update(readFileSync(path)).digest('hex'))
      }
    }
  }
  walk(root)
  return result
}

/** 比较 public/pdfjs 与 pdfjs-dist：缺少的、多余的、内容不同的文件（路径形如 cmaps/xxx.bcmap）。 */
export function diffAssets(sourceDir = SOURCE_DIR, targetDir = TARGET_DIR) {
  const missing = []
  const extra = []
  const changed = []
  for (const name of ASSET_DIRS) {
    const source = hashFiles(join(sourceDir, name))
    const target = hashFiles(join(targetDir, name))
    for (const [file, hash] of source) {
      if (!target.has(file)) missing.push(`${name}/${file}`)
      else if (target.get(file) !== hash) changed.push(`${name}/${file}`)
    }
    for (const file of target.keys()) {
      if (!source.has(file)) extra.push(`${name}/${file}`)
    }
  }
  return { missing, extra, changed }
}

/** pdfjs-dist 的版本号（package.json 里的 version）。 */
export function pdfjsVersion(sourceDir = SOURCE_DIR) {
  return JSON.parse(readFileSync(join(sourceDir, 'package.json'), 'utf8')).version
}
