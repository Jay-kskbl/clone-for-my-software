# 修改记录：T24bc 中英文切换与配色（2026-11-25）

- 来源：克隆库 `feat/search-motion` 的系统配色（`91a82e1`）、界面语言（`4cadf08`）、登录页 L6 英文部分（`fcd7a15`）、L7（`5aa264c`）、联测 V3（`758ddd6`）。Barry 于 2026-11-25 批准（“批准，用建议选项”），规范例外见 `decisions.md` D60
- 任务性质：不带 🔒；只改前端；没有改后端、接口、附录 A；没有新依赖
- 修改者：Claude（Opus 5.5）

## 1. 修改

| 文件 | 修改 |
|---|---|
| `src/i18n/index.ts`、`messages.ts`（新增） | `m()` 取当前语言的文字，`translated()` 包原来的常量标签表；`en` 的类型是 `Messages`，少一条、多一条类型检查报错；选择存在 localStorage，读写失败用中文 |
| `src/features/theme/`（新增 4 个文件） | 在 `<html>` 上改写 Element Plus 的主色变量、切换 `html.dark`；默认海蓝浅色与原来相同；对比度不够时提示 |
| `src/App.vue`、`main.ts`、`element.ts` | 右下角语言、配色按钮；挂载前应用配色和语言；Element Plus 自带文字随语言切换；内容区底部 76 px，滚到底时按钮不压住分页 |
| `src/api/client.ts`、`utils/*`、`components/*`、`views/*` | 写死的中文改为 `m()` |
| `src/features/login/*`、`LoginView.vue` | 文字随语言；`notice` 保存错误对象，切换语言后提示跟着变；窄屏底部留白。`redirect.ts`、`submit.ts`、`serviceStatus.ts` 与克隆库逻辑相同，没有改 |

## 2. 与克隆库的差别

- `SearchView.vue` 用主仓库的脚本和结构，只换文字（动效在 T24be）；检索框的占位文字改为“输入关键词，或描述想找的图片”。
- `LoginBrand.vue` 保留主仓库 48 px 的静态标志；`LoginForm.vue` 保留主仓库对 `validate-on-rule-change` 的说明。
- 检索动效、任务面板用的文字没有带进来，随 T24be、T24bd 加。

## 3. 验证

- 类型检查通过；前端 19 个文件 226 项通过；生产构建通过；脚本检查没有用不到的文字键。
- 浏览器 + 真实 FastAPI + SQLite 替身：见 DEVPLAN §5。
- **未测试（Not Tested）**：见 `docs/untested.md`“T24ba–T24be”。

## 4. 局限

后端返回的文字（失败原因、`detail` 等）只有中文。登录页按错误码翻译，其余页面英文界面下仍显示中文。
