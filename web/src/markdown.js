/**
 * 极简安全的 Markdown 渲染（记忆正文预览用）。
 * 先整体 HTML 转义再套规则，杜绝注入；只支持标题/加粗/斜体/行内代码/
 * 代码块/引用/无序列表/链接/段落——预览够用，复杂排版请看原文。
 */

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function renderInline(text) {
  let out = escapeHtml(text)
  // 行内代码先提取为占位符：避免其中的 **、链接等语法被后续规则二次解析
  const codeSpans = []
  out = out.replace(/`([^`]+)`/g, (_, code) => {
    codeSpans.push(`<code>${code}</code>`)
    return `\u0000${codeSpans.length - 1}\u0000`
  })
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  out = out.replace(/\[\[([^\][|]+)(?:\|[^\][]*)?\]\]/g, '<span class="md-link-token">[[$1]]</span>')
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
  out = out.replace(/\u0000(\d+)\u0000/g, (_, index) => codeSpans[Number(index)])
  return out
}

export function renderMarkdown(source) {
  const lines = String(source || '').replace(/\r\n/g, '\n').split('\n')
  const html = []
  let inCode = false
  let listOpen = false

  const closeList = () => {
    if (listOpen) {
      html.push('</ul>')
      listOpen = false
    }
  }

  for (const line of lines) {
    if (line.trim().startsWith('```')) {
      closeList()
      html.push(inCode ? '</code></pre>' : '<pre><code>')
      inCode = !inCode
      continue
    }
    if (inCode) {
      html.push(escapeHtml(line))
      continue
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/)
    if (heading) {
      closeList()
      const level = heading[1].length
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }
    const listItem = line.match(/^\s*[-*]\s+(.*)$/)
    if (listItem) {
      if (!listOpen) {
        html.push('<ul>')
        listOpen = true
      }
      html.push(`<li>${renderInline(listItem[1])}</li>`)
      continue
    }
    closeList()
    if (line.trim().startsWith('>')) {
      html.push(`<blockquote>${renderInline(line.replace(/^\s*>\s?/, ''))}</blockquote>`)
      continue
    }
    if (!line.trim()) {
      html.push('')
      continue
    }
    if (/^(-{3,}|\*{3,})$/.test(line.trim())) {
      html.push('<hr />')
      continue
    }
    html.push(`<p>${renderInline(line)}</p>`)
  }
  closeList()
  if (inCode) html.push('</code></pre>')
  return html.join('\n')
}
