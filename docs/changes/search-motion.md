# 修改记录：搜索动效（search-motion，2026-11-21 ～ 2026-11-22）

- 来源：Barry 要求按根目录 `SEARCH_MOTION_DEV_GUIDE.md`（下称“指南”）在 `frontend/` 里实现三个搜索动效：动画 1 待机转动、动画 2 启动、动画 3 扫描加载
- 任务性质：不在 DEVPLAN 里，没有任务编号；只改前端；没有改后端、数据库、索引、附录 A；没有下载或安装任何东西
- 修改者：Claude（Opus 5.5）
- 分支与提交：克隆库 `feat/search-motion`，3 个提交，未 push（克隆库已删除 origin）
  - `9ab00b7` 公共层 + 扫描加载动画（动画 3），接入检索页
  - `4658130` 启动动画（动画 2），接入演示页
  - `d53fed7` 待机转动动画（动画 1），三个动效接入检索页
- 本文件与 `frontend/src/features/search-motion/README.md` 在上述 3 个提交之后单独提交（`fed3743`）
- 之后按 Barry 的决定做了三项小修改，单独一个提交，见第 7 节

------------------------------------------------------------------------

## 1. 范围与隔离方式

- 工作目录是本地克隆 `~/Desktop/BARRY zou-search-motion`，不是主仓库。克隆后删除了 origin，不会误推。
- `frontend/node_modules` 用 APFS 克隆（`cp -c`）从主仓库复制，没有执行 `npm install`，没有下载任何东西。Node 用主仓库的 `.tools/node`。
- 主仓库 `~/Desktop/BARRY zou` 没有任何改动。
- 与 GLOBAL.md 的关系：
  - §3.1 写明前端“不做复杂动画”；§2 规定非核心功能归 P4，须在 P0–P3 完成后、经 Barry 确认才实施。
  - 这三个动效属于增强功能，没有进入 DEVPLAN，也不算毕设的验收内容。放在克隆库里做，就是为了不进入主开发。
  - 如果以后要合回主仓库，需要先按 GLOBAL.md §2 P4、§11.4 走增强功能确认流程（见第 6 节第 7 条）。

## 2. 接入前检查清单结论（指南第 1 节）

| 检查项 | 结论 |
|---|---|
| 框架与渲染方式 | Vue 3.5（3.5.45）+ Vite 8（8.3.8）+ TypeScript 6.0.3 的单页应用，Element Plus 2.14.8；没有 SSR |
| 颜色来源 | Element Plus 的 `--el-*` 和 `src/styles.css` 的 `--app-*`（`--app-*` 大多引用 `--el-*`）。动效只通过 `shared/tokens.ts` 读这两组变量，不写死色值 |
| 暗色模式 | 项目原本没有暗色模式。`tokens.ts` 同时监听系统配色（`prefers-color-scheme`）和 `<html>` 的 class / style / data-theme，以后按 Element Plus 的方式（`html.dark`）加暗色时 Canvas 会自动重新取色。演示页引入 Element Plus 自带的 `dark/css-vars.css` 并切换 `html.dark` 来测暗色 |
| 动效库 | 没有。本次也没有引入，全部用 CSS 过渡、Web Animations API 和 Canvas 2D 手写 |
| 搜索请求在哪里发 | 原本在 `SearchView.vue` 视图层直接调用 `search()`，没有取消，也没有超时；靠 `loading` 守卫和 `rerun` 标记避免结果错位。现在改由 `scan-loader/searchSession.ts` 统一负责开始 / 成功 / 失败 / 取消四个时机 |
| 搜索框在哪里 | `SearchView.vue` 里的 `el-input`。首页 `/` 是文件列表（`DocumentsView`），不是搜索页，所以启动动画改为“会话内第一次进入 `/search` 时播放”；地址栏带着检索词（`?q=`）进来时不播 |
| 埋点 | 项目没有埋点。只留了回调：待机动画 `onIdle` / `onActive`（组件事件 `idle` / `active`），扫描动画 `onDone`（组件事件 `done`），启动动画 `onFinish` |
| 多语言 | 没有 i18n 库。动效文案集中在 `messages.ts`，以后接 i18n 只替换这一个文件。扫描动画原按指南写“网页”，Barry 决定改为“文件”（第 7 节） |

## 3. Barry 确认的默认决定

1. 在本地克隆库里做；用演示页 `/motion-lab` 加模拟请求自测（不需要登录和后端）。
2. 启动动画放在 `/search`（见上表“搜索框在哪里”）。
3. 检索框改为胶囊形（启动动画的终点就是这个形状），加放大镜前缀图标；“检索”按钮同样改为圆角。
4. 待机动画放在检索页引导区右侧的空白处；屏幕宽度 ≤600px 时隐藏。
5. 接口很快返回时也完整播一轮扫描（6 张卡约 3.6 s），之后再收拢 0.4 s 显示结果，不加速。

## 4. 逐文件修改记录

以下路径都相对 `frontend/`。新增文件在 `src/features/search-motion/` 下，共 23 个文件（约 2300 行，含演示页）。

### 4.1 公共层 `src/features/search-motion/shared/`（新增，`9ab00b7`；`tokens.ts` 在 `d53fed7` 又改一次）

| 文件 | 内容 | 原因与影响 |
|---|---|---|
| `easing.ts` | `clamp01`、`lerp`、`progress`、`easeOutCubic`、`easeInOutCubic`，以及对应的 CSS 写法 `CSS_EASE_OUT`、`CSS_EASE_IN_OUT` | 指南 §3.4：聚拢、展开、淡入用缓出，样式切换和扫描线用缓入缓出；三个动效共用，不各写一份 |
| `reducedMotion.ts` | `prefersReducedMotion()`、`onReducedMotionChange()`（运行中系统设置变化也会通知）、`setReducedMotionOverride()`（演示页强制开 / 关） | 指南 §3.2：三个动效都从这里读，不各自写 `matchMedia`。强制开关只给演示页用，正式页面不调用 |
| `tokens.ts` | `readTokens()` 从 `--app-*` / `--el-*` 读 8 个颜色，读不到用 Element Plus 浅色默认值；`onThemeChange()` 监听系统配色和 `<html>` 属性变化。`d53fed7` 新增 `primaryStrong`（`--el-color-primary-dark-2`，后备 `#337ecc`） | 指南 §3.1。`primaryStrong` 的原因见第 5.3 节：浅色下主色对白底只有 2.78:1，常驻图形要求 3:1 |
| `canvas.ts` | `addFrame()`：全页面唯一的 `requestAnimationFrame` 循环，没有登记者时停帧，页面切到后台暂停，`dt` 封顶 100 ms；`activeFrameCount()` 供自测查残留；`createCanvasSurface()`：按 `devicePixelRatio` 设置画布像素、`ResizeObserver` 跟随容器尺寸、画布 `aria-hidden` | 指南 §3.3：同一时间最多一个 rAF；高清屏不模糊；侧栏展开等非窗口尺寸变化也能跟上 |
| `timers.ts` | `TimerGroup`：`after` / `cancel` / `clear` | 指南 §3.5、§6.4：取消、销毁时一次清空定时器，不留残留 |

### 4.2 文案 `src/features/search-motion/messages.ts`（新增，`9ab00b7`）

- `SCAN_TEXT`：正在打开文件… / 正在阅读第 i / n 个文件 / 正在整理答案… / 检索失败 / 重试（“文件”原为指南的“网页”，第 7 节改）。
- `SEARCH_TEXT.timeout(seconds)`：检索超时提示。

### 4.3 扫描加载动画 `src/features/search-motion/scan-loader/`（新增，`9ab00b7`）

| 文件 | 内容 | 原因与影响 |
|---|---|---|
| `machine.ts` | 纯函数状态机 `scanReducer`：`idle → scanning →（一轮结束且结果已到）summarizing → done`；`error`、`cancel`。结果到了只记 `resultReady`，等这一轮播完才进入整理 | 指南 §6.1。不碰 DOM，单元测试直接测 |
| `scanLoader.ts` | 框架无关的核心 `createScanLoader(host, options)`。卡片默认 6 张、上限 8 张；一轮 = 入场 600 ms + 每张卡 500 ms（6 张约 3.6 s），收拢 400 ms。卡片入场、对勾、收拢用 CSS 过渡 + 类名切换，扫描线用 Web Animations API。进度文字放在 `role="status"`、`aria-live="polite"` 的段落里，卡片区 `aria-hidden`。出错时卡片变淡，有 `onRetry` 时显示“重试”按钮。减少动效时去掉扫描线和收拢位移 | 指南 §6.2–§6.5 |
| `scanLoader.css` | 卡片、扫描线、对勾、收拢、出错、减少动效的样式，颜色全部引用项目变量。对勾底圆用 `--el-color-success-dark-2`，勾号用 `--app-surface` | 自测修复：暗色下底圆变成亮绿，原来的白勾对比度只有 1.91:1，改用页面底色（第 5.3 节） |
| `searchSession.ts` | `createSearchSession(loader, { timeoutMs, onError })`，返回 `run(task)`、`cancel()`、`pending`。新请求先中断旧请求（`AbortController`），旧请求晚到的返回按请求编号丢弃；默认 30 s 超时（`SearchTimeoutError`）；`onError` 把错误转成显示文字 | 指南 §6.3：四个时机放在请求这一层，一个不漏。自测修复：原来 `cancel()` 只在有进行中的请求时才停动画，请求已返回、动画还在播最后一轮时取消无效；改为 `cancel()` 总是调用 `loader.cancel()`，`run()` 内部只中断请求（`loader.start()` 自己会清旧动画，中间不出现一帧 idle） |
| `handle.ts` | `ScanLoaderHandle` 接口；`controlsFrom(() => ref)` 把组件 ref 包装成会话需要的控制对象，ref 未挂载时调用被忽略 | 页面和演示页共用 |
| `ScanLoader.vue` | Vue 适配层：挂载时创建核心、卸载时 `destroy`；props `pageCount`、`retryable`；事件 `done`、`retry`、`phase`；通过 `defineExpose` 暴露 `start` / `complete` / `error` / `cancel`。`idle` / `done` 时不占位 | 指南 §2：核心与框架分开 |

### 4.4 启动动画 `src/features/search-motion/launch/`（新增，`4658130`）

| 文件 | 内容 | 原因与影响 |
|---|---|---|
| `timeline.ts` | 纯函数时间轴 `launchFrame(t, chars)`、`launchDuration(chars)`：0–0.8 s 光标闪两次；0.8–1.7 s 60 个粒子聚拢成半径 24 px 的旋转光环；2.1–2.9 s 展开到胶囊轮廓；2.8–3.2 s 描边和图标淡入；3.1 s 起每秒打 10 字；打完停 250 ms。`pointOnOutline(box, s)` 按周长比例在胶囊轮廓上取点 | 指南 §5.1；单元测试直接测 |
| `playOnce.ts` | `hasPlayedLaunch` / `markLaunchPlayed` / `resetLaunchPlayed`，用 `sessionStorage` 记标记；读写异常（隐私模式）时一律 try/catch，按“没播过”处理 | 指南 §5.3：会话内只播一次，最坏情况是刷新后再播一次，不会报错 |
| `launchAnimation.ts` | 核心 `playLaunch(target, options)`，返回 `skip()`、`destroy()`。开始时读真实输入框的位置、宽高、圆角、背景、描边色、占位文字字体与颜色、前缀图标位置与 path，全部照它画；只打到输入框能显示的宽度为止。时间用累计 `dt`，切到后台暂停。任意按键 / 点击跳过（捕获阶段，不阻止默认行为，按下的字符进入输入框）；窗口尺寸或滚动变化直接跳到结束；减少动效打开时立即结束。结束时同一帧内显示真实输入框 → 移除 Canvas → `focus({ preventScroll: true })` | 指南 §5.2–§5.4：最容易出问题的是与真实搜索框对齐，所以不写死任何尺寸 |
| `launch.css` | `html[data-sm-launch] .sm-launch-target { visibility: hidden }`；Canvas 固定定位盖满视口、`pointer-events: none` | 随适配层同步加载：首帧就隐藏真实输入框，不闪；只是看不见、仍占位，布局不跳 |
| `useLaunchAnimation.ts` | Vue 适配层 `useLaunchAnimation(inputRef, { placeholder, hasValue, onFinish })`。在 setup 阶段（首帧前）决定播不播：减少动效、本会话播过、输入框已有内容时什么都不做；要播就给 `<html>` 打标记。挂载后才 `import('./launchAnimation')` 懒加载，找不到输入框或加载失败直接显示输入框 | 动画脚本不进首屏；el-input 上要加 `class="sm-launch-target"` |

### 4.5 待机转动动画 `src/features/search-motion/idle-spinner/`（新增，`d53fed7`）

| 文件 | 内容 | 原因与影响 |
|---|---|---|
| `idleTracker.ts` | `createIdleTracker({ idleAfter, onIdle, onActive, throttleMs, target, visibility, now })`，返回 `idle`、`poke()`、`destroy()`。五种操作（pointermove、pointerdown、keydown、wheel、touchstart，passive 监听）；200 ms 内只重置一次计时；待机中任何操作立即退出；页面切到后台停止计时（待机中直接退出），回到前台从 0 重新计时 | 指南 §4.1。事件源和时钟可注入，便于单元测试 |
| `draw.ts` | `drawIdle(ctx, size, tokens, frame)`：8 根圆头射线匀速旋转、长度和粗细按相位波动；光球呼吸缩放（4 s 周期）+ 绕圈高光弧 + 每 2.4 s 一圈涟漪；`morph` 0→1 时射线向中心回收，`morph > 0.3` 起光球从 60% 放大淡入。颜色用 `primaryStrong` | 指南 §4.3、§4.4：两种样式读同一个旋转角，切换时不重置 |
| `idleSpinner.ts` | 核心 `createIdleSpinner(canvas, { idleAfter = 8000, switchEvery = 30000, style = 'auto' / 'rays' / 'orb', onIdle, onActive })`，返回 `visible`、`show()`、`hide()`、`destroy()`。淡入淡出 0.4 s、morph 0.8 s，都从当前值补间（切换中途有操作就从当前画面直接淡出）；完全淡出后停帧；后台时直接清掉；减少动效时不轮换、不转动，只显示静止射线 | 指南 §4.2、§4.5 |
| `IdleSpinner.vue` | Vue 适配层：props `idleAfter`、`switchEvery`、`spinnerStyle`、`size`（默认 72 px）；事件 `idle`、`active`；暴露 `show` / `hide`。参数变化时重建核心，卸载时 `destroy` | — |

### 4.6 演示页 `src/features/search-motion/lab/`（新增；`MotionLabView.vue` 在三个提交里都有修改，`IdleLabPanel.vue` 在 `d53fed7` 新增）

| 文件 | 内容 |
|---|---|
| `MotionLabView.vue` | `/motion-lab` 页面，不需要登录、不调后端。模拟请求四种模式：快速 0.3 s、慢速 5 s、报错 1.5 s、不返回（演示用 8 s 超时，正式为 30 s）；“连续搜索”（慢速后 0.4 s 再发快速）；“取消”；“重播启动动画”（清标记并刷新）；浅色 / 暗色切换（引入 Element Plus `dark/css-vars.css`）；减少动效跟随系统 / 强制开 / 强制关；显示 rAF 登记数和扫描状态；事件日志。胶囊检索框与检索页写法相同 |
| `IdleLabPanel.vue` | 待机面板：自动轮换 / 固定射线 / 固定光球；“快速走查”把参数改为 2 s 待机、5 s 切换；手动 `show()` / `hide()` |

这两个文件只用于自测和设计走查，不是正式功能。

### 4.7 已有文件的修改

| 文件 | 位置 | 修改前 → 修改后 | 原因与影响 |
|---|---|---|---|
| `src/api/client.ts` | `RequestOptions`（第 45–46 行）、`requestRaw` 的 `fetch` 调用与 `catch`（第 96–100 行） | 新增可选 `signal?: AbortSignal` 并传给 `fetch`；`catch {}` 改为 `catch (error)`，`signal` 已取消时原样抛出（AbortError），否则仍转成 `ApiError(0, 'NETWORK', …)` | 主动取消不是网络故障，不能显示“无法连接服务器”；由调用方判断是被覆盖还是超时。不传 `signal` 的调用行为不变 |
| `src/api/search.ts` | `search()`（第 9–10 行） | `search(body)` → `search(body, signal?)`，并把 `signal` 传给 `request` | 只多一个可选参数，其他调用方不受影响 |
| `src/router.ts` | `/documents/:id` 之后（第 27–32 行） | 新增公开路由 `/motion-lab`（懒加载 `MotionLabView.vue`，没有 `requiresAuth`） | 演示页不需要登录。克隆库专用，合回主仓库时建议不保留 |
| `src/views/SearchView.vue` | 脚本：导入、`useLaunchAnimation`（第 51 行）、`scanPhase` / `loading`（第 57–58 行）、`session` / `onSearch` / `onScanDone` / `watch(selection)` / `onBeforeUnmount`（第 127–200 行） | 去掉 `loading` 守卫和 `rerun`：`loading` 改为由扫描状态计算（scanning 或 summarizing）；`onSearch` 先清空旧结果，再经 `session.run((signal) => search(body, signal))` 发请求；结果在扫描收拢后由 `onScanDone` 写入；检索进行中改开关直接取消旧请求、按新开关重查；卸载时 `session.cancel()`；超时用 `SEARCH_TEXT.timeout` 提示；`SEARCH_UNAVAILABLE` 仍与“没有结果”区分开 | 指南 §6.3。原来连按回车会被守卫挡住，现在新的检索直接覆盖旧的，旧返回被丢弃，不会错位 |
| 同上 | 模板：检索框（第 211–224 行）、结果区（第 272–288 行） | `el-input` 加 `ref="searchInput"`、`class="sm-launch-target search-input"`、前缀放大镜 `AppIcon`，占位文字提成常量 `PLACEHOLDER`；“检索”按钮加 `round`；结果区去掉 `v-loading`，改放 `<ScanLoader retryable>`（重试即重新检索）；引导区拆成文字 + `<IdleSpinner class="guide-idle">` | 胶囊检索框、启动动画、扫描动画、待机动画四处接入 |
| 同上 | 样式（第 360 行起、第 445–468 行、第 485–505 行、第 692–699 行） | 输入框外框 `border-radius: 999px`；引导区改为 flex，右侧留出待机动画；摘要、结果列表、空结果加 0.3 s 淡入上移（`prefers-reduced-motion` 时去掉）；≤600px 隐藏 `.guide-idle` | — |

### 4.8 测试 `tests/search-motion/`（新增）

| 文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `scan-machine.test.ts`（`9ab00b7`） | 7 | 结果到了等本轮播完、未到则下一轮、error / cancel、重新 start 清标记 |
| `search-session.test.ts`（`9ab00b7`） | 7 | 成功、失败、连续搜索丢弃旧返回、超时、cancel、请求已返回动画未播完时 cancel、成功后不再超时 |
| `launch.test.ts`（`4658130`） | 9 | 时间轴各阶段、打字速度与结束时刻、胶囊轮廓取点、会话内只播一次（含存储抛异常） |
| `idle-tracker.test.ts`（`d53fed7`） | 7 | 8 s 进入待机、五种操作、200 ms 节流、后台停止计时、destroy、poke |

## 5. 验证情况

### 5.1 命令

- `npm run typecheck`：通过。
- `npm test`：13 个文件、123 个用例全部通过（含新增 4 个文件、30 个用例）。
- `npm run build`：生产构建成功。

### 5.2 包体

- 三个动效合计约 10 KB（gzip）：共享 chunk 3.92 KB + CSS 0.88 KB + tokens 0.55 KB + 懒加载的启动动画 chunk 2.47 KB + SearchView 增量约 2.3 KB；低于指南要求的 15 KB。
- 不含演示页（单独的懒加载路由）。没有引入任何依赖。

### 5.3 浏览器自测（演示页 `/motion-lab`，由子代理执行）

- 扫描加载动画：快速、慢速、报错、超时、连续搜索、减少动效、暗色、无残留（rAF 登记数回到 0）全部通过。自测发现并已修复 2 个问题：
  1. 请求已返回、动画还没播完时 `cancel()` 不生效（`searchSession.ts`，改为总是调用 `loader.cancel()`，`run()` 内只中断请求）；
  2. 暗色下对勾的白勾对比度只有 1.91:1（`scanLoader.css`，勾号改用 `--app-surface`）。
- 启动动画：10 项中 9 项通过，第 7 项部分实测。已确认：首帧不闪；结束画面与真实输入框逐像素对比基本重合（文字墨迹重心偏差约 x +0.45 px、y −0.25 px）；结束后输入框有焦点；按键跳过且字符进入输入框；同一会话刷新不重播；尺寸变化直接跳到结束；暗色跟随。
- 待机动画：12 项中 10 项通过；1 项发现问题已修复：浅色下主色对白底 2.78:1，不到 3:1，改用 `primaryStrong`（`--el-color-primary-dark-2`），浅色 4.20:1，暗色为 `#66b1ff`，已在浏览器取像素确认；1 项仅观察：图形原创性。射线像常见的加载图标，光球是呼吸圆，不像 Claude / OpenAI 的标志，但仍需设计评审确认。

### 5.4 未测试（Not Tested）

| 项目 | 原因 | 代替做法 |
|---|---|---|
| 检索页 `SearchView` 实机运行（含第 7 节“关掉全部通道即取消”） | 需要登录和后端，本机不跑 Docker | 只做了类型检查和代码复核；动效部分与演示页用的是同一套组件和会话 |
| 真实读屏软件 | 环境里没有读屏软件 | 只核对了 `role="status"`、`aria-live="polite"` 和 Canvas / 卡片的 `aria-hidden` |
| 系统级“减少动态效果”设置 | 浏览器面板无法模拟系统设置 | 用演示页的强制开关和代码复核代替（三个动效都从 `reducedMotion.ts` 读） |
| Chrome 性能面板 60 / 30 fps、4x CPU 降速 | 当前环境做不了 | 未测 |
| 低端安卓设备 | 没有设备 | 未测 |
| SSR | 项目没有 SSR | 不适用 |

## 6. 修改建议（后续）

1. ~~文案“网页”改“文件”~~：已改，见第 7 节。
2. ~~检索进行中关掉全部通道不取消旧请求~~：已改，见第 7 节。
3. ~~启动动画占位文字太长~~：已缩短，见第 7 节。
4. 接口很快返回时是否允许加速播完（指南 §10 待确认事项）。目前按 Barry 的决定完整播一轮，结果约 4 s 后（3.6 s 一轮 + 0.4 s 收拢）才显示。
5. 浏览器帧率低于 10 fps 时启动动画会比墙钟时间慢：`dt` 封顶 100 ms 是有意为之，避免切回前台时画面一下跳到结尾。
6. 检索出错时，页面上方的 `el-alert` 和扫描区的状态行都会显示错误文字（后者带“重试”），信息重复，可以考虑只保留一处。
7. 如果要合回主仓库：先按 GLOBAL.md §2 P4、§11.4 走增强功能确认流程（说明工作量、依赖、风险、对论文主线的价值），再决定是否保留 `/motion-lab` 演示页（建议不合入，同时去掉 `router.ts` 里的公开路由）。

## 7. 跟进修改（2026-11-22，Barry 决定“三项都改”）

| 文件 | 修改 | 原因与影响 |
|---|---|---|
| `src/features/search-motion/messages.ts` | “正在打开网页…”改为“正在打开文件…”，“正在阅读第 i / n 个网页”改为“…个文件”；文件头注释同步 | 本系统检索的是文件，不是网页。只改文案，不影响状态机和测试 |
| `src/views/SearchView.vue` | `PLACEHOLDER` 由约 46 字缩短为“输入关键词，或描述想找的图片”（14 字），并注明原因 | 启动动画按每秒 10 字逐字打出，原占位文字让动画拖到约 8 s；现在约 4.75 s（3.1 s 起打 + 1.4 s + 0.25 s 停留）。各通道的说明仍在下方引导区 |
| 同上 | `onSearch`：检索词为空或没有选通道时，如果正在检索（`loading`），先 `session.cancel()` 再返回 | 原来检索进行中把通道全部关掉，旧请求返回后仍会显示结果。现在请求被中断、扫描动画回到 idle、显示引导区；之后重新勾选通道需要再点“检索”（此时没有结果和错误，自动重查的条件不成立） |
| `src/features/search-motion/lab/MotionLabView.vue` | 演示页占位文字与检索页保持一致 | 演示页用来预览启动动画，时长要与检索页相同 |

验证：`npm run typecheck` 通过；`npm test` 14 个文件 123 项通过；`npm run build` 成功；演示页实测扫描状态行依次显示“正在打开文件…”“正在阅读第 1–6 / 6 个文件”“正在整理答案…”，输入框占位文字为新文案。检索页里“关掉全部通道即取消”需要后端，**未测试（Not Tested）**，只做了代码复核：`session.cancel()` 会中断请求、让 `id` 失效，旧返回在 `run()` 里被丢弃，扫描动画回到 idle。
