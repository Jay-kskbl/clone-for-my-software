// 启动动画播放中按键跳过时，要不要把焦点交给检索框（新功能联测 V2）。
//
// 指南 §5.3：按下的那个键要进入检索框，所以要先聚焦。但动画改成循环播放之后，用户可能正用键盘操作
// 别的控件（语言按钮、配色面板、通道开关、导航），那时抢走焦点，这个键就落空了：实测在“EN”按钮上
// 按回车，语言没有切换，焦点跳到了检索框。所以只在没有别的控件有焦点时才聚焦；动画照样立即结束。
export function takesFocusOnKey(doc: Pick<Document, 'activeElement' | 'body' | 'documentElement'>): boolean {
  const active = doc.activeElement
  return active === null || active === doc.body || active === doc.documentElement
}
