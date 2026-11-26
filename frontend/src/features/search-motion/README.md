# search-motion：搜索动效

三个搜索动效：动画 1 待机、动画 2 启动（这两个用同一个图形：星尘光球）、动画 3 扫描加载。从克隆库 `~/Desktop/BARRY zou-search-motion` 的 `feat/search-motion` 放入（T24be），作为 GLOBAL §3.1 的例外，见 `docs/decisions.md` D60。没有引入任何依赖。

代码注释里的“指南”是克隆库根目录的 `SEARCH_MOTION_DEV_GUIDE.md`，修改经过见克隆库的 `docs/changes/search-motion.md`；两者都不在本仓库。与指南不同的地方：**结果一到就收拢，不等当前一轮播完**（指南 §6.1 要求播完）；启动动画循环播放。

## 目录

| 目录 / 文件 | 作用 |
|---|---|
| `shared/` | 公共层：`easing`（缓动）、`reducedMotion`（减少动效，可订阅变化）、`tokens`（从 `--app-*` / `--el-*` 读颜色、监听主题）、`canvas`（全页唯一的 rAF 循环、高清屏画布）、`timers`（定时器集中清理）、`stardust`（星尘光球：粒子位置与画法，待机和启动共用） |
| `messages.ts` | 动效文案，从 `src/i18n` 取 |
| `scan-loader/` | 动画 3：`machine`（纯函数状态机）、`scanLoader.ts/.css`（框架无关核心）、`searchSession`（请求与动画对接：取消、丢弃旧返回、30 s 超时）、`handle`、`ScanLoader.vue` |
| `launch/` | 动画 2：`timeline`（纯函数时间轴、胶囊轮廓取点）、`loop`（没有输入时循环播放）、`launchAnimation`（Canvas 核心，懒加载）、`launch.css`、`useLaunchAnimation`（Vue 适配） |
| `idle-spinner/` | 动画 1：`idleTracker`（待机计时）、`idleSpinner`（核心）、`IdleSpinner.vue` |
| `logo/` | `StardustLogo.vue`：登录页 logo，星尘光球中间放文档图标，一直转动 |
| （不在本目录）`src/features/theme/` | 系统配色：预设主色、浅色 / 深色 / 跟随系统、自定义颜色；右下角面板 `ThemePicker.vue`。动效颜色跟着变 |
| （不在本目录）`src/i18n/` + `src/features/theme/LocaleSwitch.vue` | 界面语言切换（中文 / English），右下角与配色按钮放在一起；动效文字（`messages.ts`）从这里取 |
| `lab/` | 演示页 `/motion-lab`（`MotionLabView.vue`、`IdleLabPanel.vue`），模拟请求，自测和设计走查用 |

每个动效都分成“框架无关的核心 + 很薄的 Vue 适配层”，核心可以脱离 Vue 单独测试。单元测试在 `frontend/tests/search-motion/`。

## 对外接口

**扫描加载（`ScanLoader.vue`）**

- props：`pageCount?`（卡片数，默认 6，上限 8）、`retryable?`（出错时显示“重试”）
- 事件：`done(result)`（收拢结束，交出结果）、`retry`、`phase(phase)`（`idle` / `scanning` / `summarizing` / `done` / `error`）
- ref 方法（`ScanLoaderHandle`）：`start(pageCount?)`、`complete(result)`、`error(message?)`、`cancel()`
- 请求不要直接调这几个方法，而是交给 `createSearchSession(controlsFrom(() => ref.value), { timeoutMs?, onError? })`，用 `session.run((signal) => 请求(signal))` 发请求，离开页面时 `session.cancel()`。`onError` 返回的文字显示在扫描区

**启动动画（`useLaunchAnimation`）**

- `useLaunchAnimation(inputRef, { placeholder, hasValue?, onFinish? })`，在 `setup` 里调用（首帧前要决定是否隐藏输入框）
- `inputRef` 是 `el-input` 的组件 ref；`el-input` 上要加 `class="sm-launch-target"`，前缀图标（svg）会被照着画
- 检索框为空时循环播放：一轮播完停 3 秒（期间有点击、按键、滚轮、触摸就重新计时）再播下一轮；输入框有内容或有焦点时停止，失焦且为空后重新开始。减少动效打开时不播
- 用户按键或点击会立即结束当前这一轮并聚焦输入框（按下的字符进入输入框）；自然播完不聚焦。按键时别的控件有焦点（语言按钮、配色面板、通道开关等）则不抢焦点（`launch/focus.ts`，T24be）
- `onFinish(reason)` 每轮结束都会调用，reason 为 `end` / `skip` / `layout` / `reduced` / `destroy`

**待机动画（`IdleSpinner.vue`）**

- props：`idleAfter`（默认 8000 ms）、`size`（默认 120 px）；只有星尘光球一种样式，减少动效时显示一帧静止画面
- 事件：`idle`、`active`；ref 方法：`show()`、`hide()`

## 在页面里怎么用

参考 `src/views/SearchView.vue`（正式接入）和 `lab/MotionLabView.vue`（模拟请求）：

```vue
<el-input ref="searchInput" v-model="query" class="sm-launch-target" :placeholder="PLACEHOLDER">
  <template #prefix><AppIcon name="search" /></template>
</el-input>

<ScanLoader ref="scan" retryable @phase="(p) => (scanPhase = p)" @done="onScanDone" @retry="onSearch" />
<IdleSpinner class="guide-idle" />
```

```ts
useLaunchAnimation(searchInput, { placeholder: PLACEHOLDER, hasValue: () => query.value !== '' })
const session = createSearchSession<SearchResponse>(controlsFrom(() => scan.value), { onError })
function onSearch() { void session.run((signal) => search(body, signal)) }   // 结果在 onScanDone 里显示
onBeforeUnmount(() => session.cancel())
```

请求函数必须把 `signal` 传给 `fetch`（`api/client.ts` 已支持），取消和超时才能真正中断请求。

## 演示页

只在开发模式有（`npm run dev`），打开 `http://127.0.0.1:5173/motion-lab`，不需要登录和后端；生产构建里没有这个路由。页面上可以切换快速 / 慢速 / 报错 / 超时 / 连续搜索、暗色、减少动效（强制开关），重播启动动画，用“快速走查”参数（2 s 进入待机）看待机动画，并显示 rAF 登记数用来检查残留。
