import { describe, expect, it } from 'vitest'

import { highlightText, sanitizeSnippet } from '../src/utils/snippet'

describe('sanitizeSnippet：只放行成对的 <em>', () => {
  it('后端的正常摘要原样保留', () => {
    expect(sanitizeSnippet('差旅<em>报销</em>标准')).toBe('差旅<em>报销</em>标准')
  })

  it('后端已转义的实体不被二次转义', () => {
    expect(sanitizeSnippet('&lt;script&gt; <em>报销</em>')).toBe('&lt;script&gt; <em>报销</em>')
  })

  it('任何其他标签都被转义，不会被浏览器执行', () => {
    const html = sanitizeSnippet('<script>alert(1)</script><img src=x onerror=alert(1)><em>报销</em>')
    expect(html).toBe(
      '&lt;script&gt;alert(1)&lt;/script&gt;&lt;img src=x onerror=alert(1)&gt;<em>报销</em>',
    )
    expect(html).not.toMatch(/<(?!\/?em>)/)
  })

  it('带属性的 em 不算 em', () => {
    expect(sanitizeSnippet('<em onclick="x">报销</em>')).toBe(
      '&lt;em onclick=&quot;x&quot;&gt;报销',
    )
  })

  it('不成对的标记被修正：多余的关闭丢弃，未关闭的补上', () => {
    expect(sanitizeSnippet('</em>前<em>中')).toBe('前<em>中</em>')
    expect(sanitizeSnippet('<em><em>中</em></em>')).toBe('<em>中</em>')
  })

  it('空值返回空字符串', () => {
    expect(sanitizeSnippet(null)).toBe('')
    expect(sanitizeSnippet(undefined)).toBe('')
    expect(sanitizeSnippet('')).toBe('')
  })
})

describe('highlightText：纯文本里标出关键词', () => {
  it('标出每个关键词', () => {
    expect(highlightText('差旅报销标准按职级执行', ['报销', '职级'])).toBe(
      '差旅<em>报销</em>标准按<em>职级</em>执行',
    )
  })

  it('原文里的标签被转义', () => {
    expect(highlightText('<b>报销</b>', ['报销'])).toBe('&lt;b&gt;<em>报销</em>&lt;/b&gt;')
  })

  it('关键词按字面匹配，不当作正则', () => {
    expect(highlightText('a.b axb', ['a.b'])).toBe('<em>a.b</em> axb')
  })

  it('关键词里的特殊字符同样被转义后匹配', () => {
    expect(highlightText('x < y', ['<'])).toBe('x <em>&lt;</em> y')
  })

  it('没有关键词时只转义', () => {
    expect(highlightText('a & <b>', [])).toBe('a &amp; &lt;b&gt;')
    expect(highlightText('文本', ['  '])).toBe('文本')
  })
})

describe('highlightText：关键词不会匹配到转义产生的实体内部', () => {
  it('搜 amp、lt、39 时，& < \' 的转义保持完整', () => {
    expect(highlightText('a & b', ['amp'])).toBe('a &amp; b')
    expect(highlightText('x < y', ['lt'])).toBe('x &lt; y')
    expect(highlightText("it's 39", ['39'])).toBe('it&#39;s <em>39</em>')
  })

  it('不区分大小写，显示时保留原文的大小写', () => {
    expect(highlightText('Python 与 python', ['PYTHON'])).toBe('<em>Python</em> 与 <em>python</em>')
  })

  it('关键词里的标签不会原样进入页面', () => {
    expect(highlightText('<img src=x>', ['<img'])).toBe('<em>&lt;img</em> src=x&gt;')
  })
})
