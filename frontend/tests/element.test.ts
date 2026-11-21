import { describe, expect, it } from 'vitest'

import { ELEMENT_COMPONENTS, componentName } from '../src/element-components'

// T24p：Element Plus 改为按需注册后，模板里用到却没注册的 <el-xxx> 不会报错，只是不显示。
// 这里扫描全部 .vue 文件，逐个核对。
const sources = import.meta.glob('../src/**/*.vue', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function pascal(tag: string): string {
  return tag
    .split('-')
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join('')
}

const registered = new Set(ELEMENT_COMPONENTS.map(componentName))

describe('Element Plus 按需注册（T24p）', () => {
  it('扫描到了页面文件', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(5)
  })

  it('模板里用到的每个 <el-xxx> 都已注册', () => {
    const used = new Set<string>()
    for (const source of Object.values(sources)) {
      for (const match of source.matchAll(/<(el-[a-z-]+)/g)) used.add(pascal(match[1]))
    }
    expect(used.size).toBeGreaterThan(10)
    const missing = [...used].filter((name) => !registered.has(name)).sort()
    expect(missing, '补上这些组件：src/element.ts 的样式，src/element-components.ts 的 import 和列表').toEqual([])
  })

  it('注册名都以 El 开头且不重复', () => {
    expect([...registered].every((name) => name.startsWith('El'))).toBe(true)
    expect(registered.size).toBe(ELEMENT_COMPONENTS.length)
  })
})
