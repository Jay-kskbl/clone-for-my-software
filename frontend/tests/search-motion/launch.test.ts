// 启动动画的纯逻辑：时间轴（指南 §5.1）、胶囊轮廓取点、会话内只播一次（§5.3）。
import { describe, expect, it } from 'vitest'

import { hasPlayedLaunch, markLaunchPlayed, resetLaunchPlayed } from '../../src/features/search-motion/launch/playOnce'
import {
  LAUNCH_TIMING,
  launchDuration,
  launchFrame,
  pointOnOutline,
  type Box,
} from '../../src/features/search-motion/launch/timeline'

describe('启动动画时间轴', () => {
  it('0–0.8 秒光标闪两次，之后不再出现', () => {
    const peaks = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750].map(
      (t) => launchFrame(t, 10).cursor,
    )
    // 两个波峰（约 0.2 s、0.6 s），中间回落到 0（0.4 s）
    expect(launchFrame(200, 10).cursor).toBeCloseTo(1, 5)
    expect(launchFrame(600, 10).cursor).toBeCloseTo(1, 5)
    expect(launchFrame(400, 10).cursor).toBeCloseTo(0, 5)
    expect(peaks.every((v) => v >= 0 && v <= 1)).toBe(true)
    expect(launchFrame(800, 10).cursor).toBe(0)
    expect(launchFrame(2000, 10).cursor).toBe(0)
  })

  it('各阶段在规定区间内从 0 到 1', () => {
    expect(launchFrame(799, 10).gather).toBe(0)
    expect(launchFrame(1700, 10).gather).toBe(1)
    expect(launchFrame(2100, 10).expand).toBe(0)
    expect(launchFrame(2900, 10).expand).toBe(1)
    expect(launchFrame(2800, 10).stroke).toBe(0)
    expect(launchFrame(3200, 10).stroke).toBe(1)
  })

  it('3.1 秒起每秒打 10 个字，不超过总字数', () => {
    expect(launchFrame(3099, 20).chars).toBe(0)
    expect(launchFrame(3100, 20).chars).toBe(1)
    expect(launchFrame(4099, 20).chars).toBe(10)
    expect(launchFrame(99_999, 20).chars).toBe(20)
  })

  it('打完字、描边完成后再停留一下才结束', () => {
    const end = launchDuration(20)
    expect(end).toBe(LAUNCH_TIMING.typeStart + 20 * LAUNCH_TIMING.msPerChar + LAUNCH_TIMING.hold)
    expect(launchFrame(end - 1, 20).finished).toBe(false)
    expect(launchFrame(end, 20).finished).toBe(true)
    // 没有字可打时也要等描边淡入结束
    expect(launchDuration(0)).toBe(LAUNCH_TIMING.strokeEnd + LAUNCH_TIMING.hold)
  })
})

describe('胶囊轮廓取点', () => {
  const box: Box = { x: 10, y: 20, width: 300, height: 40, radius: 999 }

  it('从右侧中点出发、顺时针，半程到左侧中点', () => {
    const start = pointOnOutline(box, 0)
    expect(start.x).toBeCloseTo(310)
    expect(start.y).toBeCloseTo(40)
    const half = pointOnOutline(box, 0.5)
    expect(half.x).toBeCloseTo(10)
    expect(half.y).toBeCloseTo(40)
    // 顺时针（y 轴向下）：四分之一处在底边
    expect(pointOnOutline(box, 0.25).y).toBeCloseTo(60)
    expect(pointOnOutline(box, 0.75).y).toBeCloseTo(20)
  })

  it('所有点都在胶囊边上（到中轴线段的距离等于半径）', () => {
    const r = 20
    for (let i = 0; i < 60; i++) {
      const p = pointOnOutline(box, i / 60)
      const cx = Math.min(Math.max(p.x, box.x + r), box.x + box.width - r)
      expect(Math.hypot(p.x - cx, p.y - (box.y + r))).toBeCloseTo(r, 6)
    }
  })

  it('圆角为 0 时是普通矩形', () => {
    const rect: Box = { x: 0, y: 0, width: 100, height: 50, radius: 0 }
    for (let i = 0; i < 40; i++) {
      const p = pointOnOutline(rect, i / 40)
      const onEdge = [p.x, p.y].some((v) => Math.abs(v) < 1e-6) || Math.abs(p.x - 100) < 1e-6 || Math.abs(p.y - 50) < 1e-6
      expect(onEdge).toBe(true)
    }
  })
})

describe('会话内只播一次', () => {
  function memoryStorage() {
    const data = new Map<string, string>()
    return {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
    }
  }

  it('记标记后不再播，清掉后可以再播', () => {
    const storage = memoryStorage()
    expect(hasPlayedLaunch(storage)).toBe(false)
    markLaunchPlayed(storage)
    expect(hasPlayedLaunch(storage)).toBe(true)
    resetLaunchPlayed(storage)
    expect(hasPlayedLaunch(storage)).toBe(false)
  })

  it('存储读写抛异常（隐私模式）时不报错，按没播过处理', () => {
    const broken = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
      removeItem: () => {
        throw new Error('SecurityError')
      },
    }
    expect(hasPlayedLaunch(broken)).toBe(false)
    expect(() => markLaunchPlayed(broken)).not.toThrow()
    expect(() => resetLaunchPlayed(broken)).not.toThrow()
    expect(hasPlayedLaunch(null)).toBe(false)
  })
})
