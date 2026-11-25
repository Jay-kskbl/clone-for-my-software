// 只认最后一次（新功能联测 V1）：文件列表同时有几次加载时，只有最后一次的结果、定时器算数。
import { expect, it } from 'vitest'

import { LatestRun } from '../src/utils/latestRun'

it('后一次开始后，前一次作废', () => {
  const runs = new LatestRun()
  const a = runs.begin()
  expect(runs.isCurrent(a)).toBe(true)
  const b = runs.begin()
  expect(runs.isCurrent(a)).toBe(false)
  expect(runs.isCurrent(b)).toBe(true)
})

it('停止后全部作废，之后开始的也不算数', () => {
  const runs = new LatestRun()
  const a = runs.begin()
  runs.stop()
  expect(runs.isCurrent(a)).toBe(false)
  expect(runs.stopped).toBe(true)
  expect(runs.isCurrent(runs.begin())).toBe(false)
})
