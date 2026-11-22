# 修改记录：登录页结构优化（2026-11-22）

- 计划：`docs/登录页结构优化计划书.md`（问题编号 A1–C5、任务编号 L1–L8 都以它为准）
- 分支：`feat/search-motion`（克隆库）。Barry 于 2026-11-22 决定全部在克隆库做，不进主仓库的 DEVPLAN
- 每个任务一个提交；提交编号在本文件和计划书第 7 节补上，单独提交
- 只改前端；没有改后端、接口、表结构；没有新下载

------------------------------------------------------------------------

## L1 抽出纯函数并补测试（行为不变）

提交：`7142770`

### 修改的文件

| 文件 | 改了什么 | 为什么 |
|---|---|---|
| `frontend/src/features/login/redirect.ts`（新增） | `safeRedirect(raw)`：只接受以单个 `/` 开头的站内路径；`//` 开头、含反斜杠或控制字符、不是字符串（null、数组）、指向登录页本身的，一律回到 `/` | 原来的判断写在 `LoginView.vue` 里，只检查“以 `/` 开头、不以 `//` 开头”，没有测试（问题 B2） |
| `frontend/src/features/login/rules.ts`（新增） | 四个检查函数（`requireUsername`、`requirePassword`、`checkNewUsername`、`checkNewPassword`）返回错误文字或 null；`LOGIN_RULES`、`REGISTER_RULES` 把它们包成 Element Plus 的 validator | 测试测到的就是页面实际用的判断（问题 B1）。提示在校验时才按当前语言取，规则不再需要 `computed` |
| `frontend/src/views/LoginView.vue` | 删掉两套内联规则和跳转判断，改为引用上面两个文件 | — |
| `frontend/tests/login/redirect.test.ts`（新增） | 23 项：站内路径保留；`//`、反斜杠、完整网址、`javascript:`、相对路径、空值、制表符、换行、DEL、登录页本身、null、数组、数字回到 `/` | — |
| `frontend/tests/login/rules.test.ts`（新增） | 26 项：用户名 2 / 3 / 32 / 33 个字符和非法字符；密码 7 / 8 / 128 / 129 个字符；登录只查是否填写；规则都带红色星号、失去焦点时检查；切到英文后提示是英文 | — |

### 与原来行为的差别

- 跳转：`/\evil.com`、带控制字符的地址、`/login` 原来会原样交给 `router.push`，现在回到 `/`。其余与原来相同
- 注册密码长度：原来由 Element Plus（async-validator）计数，现在按字符数（`[...value].length`）计数，与后端 Python 的 `len` 一致。普通字符没有差别
- 提示文字的位置、样式、触发时机（失去焦点、点提交）不变

### 与计划的差别

计划写的是 L1 同时新增 `errors.ts`，“先只放现有行为”。那样它只是把 `errorMessage` 原样转一手，是一个没有实际用途的空模块（GLOBAL §8.1），所以挪到 L6 和错误码翻译一起新增。

### 验证

- `npm run typecheck` 通过；`npm test` 18 个文件 194 项通过（新增 49 项）；`npm run build` 通过
- 浏览器（开发服务器，没有后端）：`/login` 两个输入框都有红色星号；切到注册，用户名填 `ab`、密码填 7 位后失去焦点，分别提示“3–32 个字符……”“8–128 个字符”
- 登录成功后的跳转需要后端，**未测试（Not Tested）**；跳转判断已由单元测试覆盖，`LoginView.vue` 里只剩一行调用，已做代码复核
