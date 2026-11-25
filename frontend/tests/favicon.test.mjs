// T24ag：index.html 声明了图标、文件存在。没有声明时浏览器会自己去请求 /favicon.ico，得到 404。
import { existsSync, readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const file = (path) => new URL(`../${path}`, import.meta.url)
const read = (path) => readFileSync(file(path), 'utf8')

describe('网页图标（T24ag）', () => {
  it('index.html 声明的图标在 public/ 里', () => {
    const href = /<link rel="icon"[^>]*href="\/([^"]+)"/.exec(read('index.html'))?.[1]
    expect(href, 'index.html 没有声明图标').toBeTruthy()
    expect(existsSync(file(`public/${href}`)), `public/${href} 不存在`).toBe(true)
  })

  it('图标的线条与 AppIcon 的 docs 图标相同', () => {
    const docs = /docs: \[(.*?)\]/.exec(read('src/components/AppIcon.vue'))?.[1] ?? ''
    const paths = [...docs.matchAll(/'([^']+)'/g)].map((match) => match[1])
    expect(paths.length).toBeGreaterThan(0)
    const icon = read('public/favicon.svg')
    for (const path of paths) expect(icon).toContain(`d="${path}"`)
  })
})
