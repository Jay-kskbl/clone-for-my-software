// 扫描加载动画（动画 3）核心，框架无关。
// 卡片入场、变淡、对勾、收拢用 CSS transition + 类名切换；扫描线用 Web Animations API；
// 所有定时器集中在 TimerGroup，cancel / destroy 时一次清空（指南 §6.4）。
import { SCAN_TEXT } from '../messages'
import { CSS_EASE_IN_OUT } from '../shared/easing'
import { onReducedMotionChange, prefersReducedMotion } from '../shared/reducedMotion'
import { TimerGroup } from '../shared/timers'
import { INITIAL_SCAN_STATE, scanReducer, type ScanEvent, type ScanPhase, type ScanState } from './machine'
import './scanLoader.css'

export const DEFAULT_PAGE_COUNT = 6
export const MAX_PAGE_COUNT = 8

// 一轮 = 入场 600 ms + 每张卡 500 ms；6 张卡约 3.6 秒（指南 §6.3）
const STAGGER_MS = 60
const CARD_IN_MS = 300
const SCAN_MS = 500
const RESET_MS = 250
const SUMMARY_MS = 400

export interface ScanLoaderOptions<T> {
  pageCount?: number
  /** 收拢结束、结果交给结果区渲染时调用 */
  onDone?: (result: T) => void
  onPhaseChange?: (phase: ScanPhase) => void
  /** 提供时，出错状态下显示“重试”按钮 */
  onRetry?: () => void
}

export interface ScanLoader<T> {
  readonly phase: ScanPhase
  /** 提交搜索时调用；有真实来源数时传进来（上限 8） */
  start(pageCount?: number): void
  complete(result: T): void
  error(message?: string): void
  cancel(): void
  destroy(): void
}

function clampCount(value: number): number {
  return Math.min(MAX_PAGE_COUNT, Math.max(1, Math.round(value)))
}

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag)
  node.className = className
  return node
}

const CHECK_SVG =
  '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" ' +
  'stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3l6-7"/></svg>'

export function createScanLoader<T>(host: HTMLElement, options: ScanLoaderOptions<T> = {}): ScanLoader<T> {
  let state: ScanState = INITIAL_SCAN_STATE
  let result: { value: T } | null = null
  let count = clampCount(options.pageCount ?? DEFAULT_PAGE_COUNT)
  let beam: Animation | null = null
  let reduced = prefersReducedMotion()
  const timers = new TimerGroup()

  const root = element('div', 'sm-scan')
  root.dataset.phase = state.phase
  root.classList.toggle('is-reduced', reduced)
  // 读屏软件通过这一行得知进度（Canvas / 卡片本身对读屏隐藏）
  const status = element('p', 'sm-scan-status')
  status.setAttribute('role', 'status')
  status.setAttribute('aria-live', 'polite')
  const list = element('ol', 'sm-scan-cards')
  list.setAttribute('aria-hidden', 'true')
  const errorBox = element('div', 'sm-scan-error')
  errorBox.hidden = true
  const retry = element('button', 'sm-scan-retry')
  retry.type = 'button'
  retry.textContent = SCAN_TEXT.retry
  const onRetryClick = () => options.onRetry?.()
  retry.addEventListener('click', onRetryClick)
  errorBox.append(retry)
  root.append(status, list, errorBox)
  host.append(root)

  const offReduced = onReducedMotionChange((value) => {
    reduced = value
    root.classList.toggle('is-reduced', value)
    if (value) stopBeam()
  })

  function dispatch(event: ScanEvent): void {
    const before = state.phase
    state = scanReducer(state, event)
    root.dataset.phase = state.phase
    if (state.phase !== before) options.onPhaseChange?.(state.phase)
  }

  function setStatus(text: string): void {
    if (status.textContent !== text) status.textContent = text
  }

  function cards(): HTMLElement[] {
    return Array.from(list.children) as HTMLElement[]
  }

  function buildCards(): void {
    const items: HTMLElement[] = []
    for (let i = 0; i < count; i++) {
      const card = element('li', 'sm-scan-card')
      for (let j = 0; j < 3; j++) card.append(element('span', 'sm-scan-line'))
      const check = element('span', 'sm-scan-check')
      check.innerHTML = CHECK_SVG
      card.append(check, element('span', 'sm-scan-beam'))
      items.push(card)
    }
    list.replaceChildren(...items)
  }

  function stopBeam(): void {
    beam?.cancel()
    beam = null
  }

  function resetView(): void {
    timers.clear()
    stopBeam()
    list.classList.remove('is-gathered', 'is-dim')
    for (const card of cards()) card.classList.remove('is-in', 'is-active', 'is-read')
    errorBox.hidden = true
  }

  function scanCard(card: HTMLElement, index: number): void {
    setStatus(SCAN_TEXT.reading(index + 1, count))
    card.classList.add('is-active')
    if (!reduced) {
      const line = card.querySelector<HTMLElement>('.sm-scan-beam')
      const distance = Math.max(0, card.clientHeight - 2)
      beam = line?.animate([{ transform: 'translateY(0)' }, { transform: `translateY(${distance}px)` }], {
        duration: SCAN_MS - 60,
        easing: CSS_EASE_IN_OUT,
      }) ?? null
    }
    timers.after(SCAN_MS - 60, () => {
      card.classList.remove('is-active')
      card.classList.add('is-read')
      beam = null
    })
  }

  function runRound(): void {
    const items = cards()
    let t = 0
    if (state.round > 1) {
      // 下一轮：已读卡片先淡出，再重新入场
      for (const card of items) card.classList.remove('is-in', 'is-read', 'is-active')
      t = RESET_MS
    }
    setStatus(SCAN_TEXT.opening)
    items.forEach((card, i) =>
      timers.after(t + i * STAGGER_MS, () => {
        // 容器刚从 display: none 变为显示时，先强制算一次样式，入场过渡才有起点
        void card.offsetWidth
        card.classList.add('is-in')
      }),
    )
    t += Math.max(600, (items.length - 1) * STAGGER_MS + CARD_IN_MS)
    items.forEach((card, i) => timers.after(t + i * SCAN_MS, () => scanCard(card, i)))
    timers.after(t + items.length * SCAN_MS, () => {
      dispatch({ type: 'roundEnd' })
      runRound()
    })
  }

  function summarize(): void {
    setStatus(SCAN_TEXT.summarizing)
    if (!reduced) {
      // 每张卡朝卡片区中心收拢
      const box = list.getBoundingClientRect()
      const cx = box.left + box.width / 2
      const cy = box.top + box.height / 2
      for (const card of cards()) {
        const r = card.getBoundingClientRect()
        card.style.setProperty('--sm-dx', `${cx - (r.left + r.width / 2)}px`)
        card.style.setProperty('--sm-dy', `${cy - (r.top + r.height / 2)}px`)
      }
    }
    list.classList.add('is-gathered')
    timers.after(SUMMARY_MS, () => {
      dispatch({ type: 'summarized' })
      const done = result
      result = null
      if (done) options.onDone?.(done.value)
    })
  }

  return {
    get phase() {
      return state.phase
    },
    start(pageCount) {
      resetView()
      result = null
      if (pageCount !== undefined) count = clampCount(pageCount)
      if (list.children.length !== count) buildCards()
      dispatch({ type: 'start' })
      runRound()
    },
    complete(value) {
      if (state.phase !== 'scanning') return
      result = { value }
      // 不等这一轮播完：停下扫描，马上收拢（D60）
      timers.clear()
      stopBeam()
      for (const card of cards()) card.classList.remove('is-active')
      dispatch({ type: 'complete' })
      summarize()
    },
    error(message) {
      if (state.phase !== 'scanning') return
      timers.clear()
      stopBeam()
      for (const card of cards()) card.classList.remove('is-active')
      list.classList.add('is-dim')
      dispatch({ type: 'error' })
      setStatus(message ?? SCAN_TEXT.failed)
      // 每次出错时重新取文字：界面语言可能在创建之后切换过
      retry.textContent = SCAN_TEXT.retry
      errorBox.hidden = !options.onRetry
    },
    cancel() {
      resetView()
      result = null
      setStatus('')
      dispatch({ type: 'cancel' })
    },
    destroy() {
      resetView()
      result = null
      offReduced()
      retry.removeEventListener('click', onRetryClick)
      root.remove()
    },
  }
}
