// 按需引入 Element Plus（T24p）。原来 main.ts 整包引入（app.use(ElementPlus) + dist/index.css），
// 主包约 874 KB，大部分是用不到的组件。现在只注册页面里实际用到的组件和样式。
//
// 新页面用到这里没有的 <el-xxx> 时，必须两处都补上：本文件的样式 import，
// element-components.ts 的 import 和 ELEMENT_COMPONENTS。
// 漏了的话 Vue 只在控制台警告、页面上那个元素不显示；tests/element.test.ts 会扫描全部 .vue 文件，
// 发现没注册的组件就失败。
//
// 每个组件的 style/css 会连带引入它依赖的样式（例如 table 引入 checkbox、tooltip、scrollbar）。
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/checkbox-group/style/css'
import 'element-plus/es/components/container/style/css'
import 'element-plus/es/components/header/style/css'
import 'element-plus/es/components/main/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/link/style/css'
import 'element-plus/es/components/pagination/style/css'
import 'element-plus/es/components/radio-group/style/css'
import 'element-plus/es/components/radio-button/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tab-pane/style/css'
import 'element-plus/es/components/tag/style/css'
// 不是模板里的标签：v-loading 指令，以及在脚本里调用的 ElMessage、ElMessageBox
import 'element-plus/es/components/loading/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'

import { ElLoading, ElMessage, ElMessageBox, provideGlobalConfig } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import type { App } from 'vue'

import { ELEMENT_COMPONENTS, componentName } from './element-components'

export function installElementPlus(app: App): void {
  for (const component of ELEMENT_COMPONENTS) app.component(componentName(component), component)
  app.use(ElLoading) // v-loading 指令
  // 让在脚本里调用的 ElMessage、ElMessageBox 拿到应用的上下文（中文语言包等）
  app.use(ElMessage)
  app.use(ElMessageBox)
  // 等同于原来 app.use(ElementPlus, { locale: zhCn }) 里的全局配置
  provideGlobalConfig({ locale: zhCn }, app, true)
}
