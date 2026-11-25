// 启动动画播放中按键跳过时，焦点交给谁（T24be）。
import { describe, expect, it } from 'vitest'

import { takesFocusOnKey } from '../../src/features/search-motion/launch/focus'

const body = { tagName: 'BODY' } as HTMLElement
const html = { tagName: 'HTML' } as HTMLElement
const button = { tagName: 'BUTTON' } as HTMLElement
const doc = (active: HTMLElement | null) => ({ activeElement: active, body, documentElement: html })

describe('按键跳过', () => {
  it.each([
    ['没有焦点', null],
    ['焦点在 body', body],
    ['焦点在 html', html],
  ])('%s：聚焦检索框，按下的字符进入检索框（指南 §5.3）', (_name, active) => {
    expect(takesFocusOnKey(doc(active))).toBe(true)
  })

  it('焦点在别的控件上（语言按钮、配色面板、通道开关）：不抢，这个键归那个控件', () => {
    expect(takesFocusOnKey(doc(button))).toBe(false)
  })
})
