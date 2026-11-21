// 把 node_modules/pdfjs-dist 的 cmaps、standard_fonts、wasm、iccs 复制到 public/pdfjs/（T24m）。
// 升级 pdfjs-dist 之后运行：npm run sync:pdfjs，再跑 npm test 确认一致。
// 只动这四个目录：先整个删掉再复制，旧版本多出来的文件不会残留。
import { cpSync, existsSync, rmSync } from 'node:fs'
import { join } from 'node:path'

import { ASSET_DIRS, SOURCE_DIR, TARGET_DIR, diffAssets, pdfjsVersion } from './pdfjs-assets.mjs'

for (const name of ASSET_DIRS) {
  if (!existsSync(join(SOURCE_DIR, name))) {
    console.error(`找不到 ${join(SOURCE_DIR, name)}：先在 frontend/ 下运行 npm install`)
    process.exit(1)
  }
}
for (const name of ASSET_DIRS) {
  rmSync(join(TARGET_DIR, name), { recursive: true, force: true })
  cpSync(join(SOURCE_DIR, name), join(TARGET_DIR, name), { recursive: true })
}
const { missing, extra, changed } = diffAssets()
if (missing.length || extra.length || changed.length) {
  console.error('复制后仍不一致：', { missing, extra, changed })
  process.exit(1)
}
console.log(`已把 pdfjs-dist ${pdfjsVersion()} 的 ${ASSET_DIRS.join('、')} 复制到 public/pdfjs/`)
