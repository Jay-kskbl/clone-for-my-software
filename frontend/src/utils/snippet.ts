// 检索结果的命中摘要要用 v-html 显示（关键词用 <em> 标出），所以显示前必须清洗。
//
// 后端已经把原文做了 HTML 转义、只插入了 <em> 和 </em>（decisions.md D28）。
// 这里不依赖这一点，再做一次白名单处理：除了成对的 <em>…</em>，任何 < 和 > 都转义掉，
// 引号也转义。这样即使后端或检索服务出了问题，页面也不会执行文档里的脚本。

const EM_TAG = /(<em>|<\/em>)/

function neutralize(text: string): string {
  return text.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

/** 把后端给的摘要变成可以安全放进 v-html 的字符串：只保留成对的 <em>。 */
export function sanitizeSnippet(snippet: string | null | undefined): string {
  if (!snippet) return ''
  let open = false
  let html = ''
  for (const part of snippet.split(EM_TAG)) {
    if (part === '<em>') {
      if (!open) {
        html += '<em>'
        open = true
      }
    } else if (part === '</em>') {
      if (open) {
        html += '</em>'
        open = false
      }
    } else {
      html += neutralize(part)
    }
  }
  if (open) html += '</em>'
  return html
}

/** 在纯文本里把关键词标出来，返回可以放进 v-html 的字符串（预览页里用）。 */
export function highlightText(text: string, terms: string[]): string {
  const escape = (part: string) => neutralize(part.replace(/&/g, '&amp;'))
  const words = terms.map((t) => t.trim()).filter((t) => t.length > 0)
  if (words.length === 0) return escape(text)
  // 在原文上匹配，匹配完再逐段转义。不能先转义再匹配：那样关键词会匹配到转义产生的
  // 实体内部（例如搜 “amp” 或 “39” 会把 &amp;、&#39; 拆坏）。
  // 关键词按字面匹配（不当作正则），不区分大小写（检索本身也不区分）
  const pattern = words
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .sort((a, b) => b.length - a.length)
    .join('|')
  // 带捕获组的 split：奇数位置是匹配到的关键词，偶数位置是其余文字
  return text
    .split(new RegExp(`(${pattern})`, 'gi'))
    .map((part, index) => (index % 2 === 1 ? `<em>${escape(part)}</em>` : escape(part)))
    .join('')
}
