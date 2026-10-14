import DOMPurify from 'dompurify'

export const RICH_TEXT_LIMIT = 20_000
const tags = ['p', 'br', 'h2', 'h3', 'strong', 'em', 'u', 's', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'hr', 'a']

export function safeRichTextUrl(value: string): string | null {
  if (!/^https?:\/\//i.test(value) || /[\s\p{C}\\]/u.test(value)) return null
  try {
    if (/[\s\p{C}\\]/u.test(decodeURIComponent(value))) return null
    if (/^https?:\/\/[^/?#]*@/i.test(value)) return null
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && url.hostname && !url.hostname.includes('%') && !url.username && !url.password && !/[\s\p{C}\\]/u.test(url.href) ? url.href : null
  } catch { return null }
}

/** Only this result may reach the rich text renderer. No inline styles or embedded media. */
export function sanitizeRichText(value: string): string {
  if (value.length > RICH_TEXT_LIMIT) throw new Error('rich-text-length')
  const clean = DOMPurify.sanitize(value, {
    ALLOWED_TAGS: tags, ALLOWED_ATTR: ['href', 'rel'], ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false,
    FORBID_TAGS: ['svg', 'math', 'style', 'script', 'template', 'iframe', 'object', 'embed', 'form', 'input'],
  })
  const template = document.createElement('template')
  template.innerHTML = clean
  for (const element of template.content.querySelectorAll('*')) {
    for (const attribute of [...element.attributes]) if (element.tagName !== 'A' || !['href', 'rel'].includes(attribute.name)) element.removeAttribute(attribute.name)
    if (element.tagName === 'A') {
      const url = safeRichTextUrl(element.getAttribute('href') || '')
      if (!url) element.replaceWith(...element.childNodes)
      else { element.setAttribute('href', url); element.setAttribute('rel', 'noopener noreferrer nofollow') }
    }
  }
  const result = template.innerHTML
  if (result.length > RICH_TEXT_LIMIT) throw new Error('rich-text-length')
  return result
}

export function richTextToPlain(value: string): string {
  const template = document.createElement('template')
  template.innerHTML = sanitizeRichText(value)
  for (const br of template.content.querySelectorAll('br')) br.replaceWith('\n')
  for (const block of template.content.querySelectorAll('p,h2,h3,li,blockquote,pre,hr')) block.append('\n')
  return (template.content.textContent || '').replace(/\n{3,}/g, '\n\n').trim()
}

export function richTextHasContent(value: string): boolean {
  return richTextToPlain(value).replace(/[\s\p{C}]/gu, '').length > 0
}

export function plainTextToRich(value: string): string {
  const paragraph = document.createElement('p')
  value.split(/\r?\n/).forEach((line, index) => { if (index) paragraph.append(document.createElement('br')); paragraph.append(document.createTextNode(line)) })
  return sanitizeRichText(paragraph.outerHTML)
}
