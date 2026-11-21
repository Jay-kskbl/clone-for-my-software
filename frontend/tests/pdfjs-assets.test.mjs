// T24m：public/pdfjs/ 必须与已安装的 pdfjs-dist 逐文件一致。升级 pdfjs-dist 后忘了运行
// npm run sync:pdfjs，这里会失败；否则中文 PDF 可能又变成空白，而且没有任何报错（27b51b2 的问题）。
// 写成 .mjs 的原因见 scripts/pdfjs-assets.mjs。
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { ASSET_DIRS, diffAssets, hashFiles, pdfjsVersion } from '../scripts/pdfjs-assets.mjs'

describe('pdf.js 静态资源与 pdfjs-dist 一致（T24m）', () => {
  it('四个目录逐文件相同，没有缺少、多余或内容不同的文件', () => {
    const diff = diffAssets()
    expect(diff, `public/pdfjs 与 pdfjs-dist ${pdfjsVersion()} 不一致，运行 npm run sync:pdfjs`).toEqual({
      missing: [],
      extra: [],
      changed: [],
    })
  })

  it('每个目录都不是空的（防止两边都缺失时也“一致”）', () => {
    for (const name of ASSET_DIRS) {
      expect(hashFiles(join('public', 'pdfjs', name)).size, name).toBeGreaterThan(0)
    }
  })

  it('比较逻辑能发现缺少、多余和内容不同', () => {
    const root = mkdtempSync(join(tmpdir(), 'pdfjs-assets-'))
    const source = join(root, 'source')
    const target = join(root, 'target')
    for (const dir of [source, target]) {
      for (const name of ASSET_DIRS) mkdirSync(join(dir, name), { recursive: true })
    }
    writeFileSync(join(source, 'cmaps', 'a.bcmap'), 'a')
    writeFileSync(join(source, 'wasm', 'b.wasm'), 'new')
    writeFileSync(join(target, 'wasm', 'b.wasm'), 'old')
    writeFileSync(join(target, 'iccs', 'stale.icc'), 'x')

    expect(diffAssets(source, target)).toEqual({
      missing: ['cmaps/a.bcmap'],
      extra: ['iccs/stale.icc'],
      changed: ['wasm/b.wasm'],
    })
  })
})
