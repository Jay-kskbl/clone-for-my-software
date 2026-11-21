// Element Plus 按需注册的组件清单（T24p）。单独成一个文件、不引入样式，
// 是为了让 tests/element.test.ts 在 Node 里直接导入（Node 不认识 .css）。样式在 element.ts。
import {
  ElAlert,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElLink,
  ElPagination,
  ElRadioButton,
  ElRadioGroup,
  ElTable,
  ElTableColumn,
  ElTabPane,
  ElTabs,
  ElTag,
} from 'element-plus'
import type { Component } from 'vue'

// 逐个按名字注册（app.component），不用 app.use：子组件（ElRadioGroup、ElTableColumn、
// ElFormItem 等）自己的 install 什么都不做，要靠父组件的 install 才注册上，漏了父组件就
// 静默不显示（T24p 浏览器检查时 ElRadioGroup 就是这样）。按名字注册，tests/element.test.ts
// 核对的名字就是实际注册的名字
export const ELEMENT_COMPONENTS: Component[] = [
  ElAlert,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  // T24s 起页面骨架改用自己的侧栏布局，不再用 ElContainer、ElHeader、ElMain
  ElDialog,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElLink,
  ElPagination,
  ElRadioGroup,
  ElRadioButton,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTabPane,
  ElTag,
]

/** 组件在模板里对应的注册名，例如 ElTableColumn（<el-table-column>）。 */
export function componentName(component: Component): string {
  const name = (component as { name?: string }).name
  if (!name) throw new Error('Element Plus 组件缺少 name，无法按名字注册')
  return name
}
