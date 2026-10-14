import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { plainTextToRich, richTextHasContent, richTextToPlain, safeRichTextUrl, sanitizeRichText } from '../src/utils/richText'
import SafeRichText from '../src/components/common/SafeRichText.vue'

describe('富文本安全白名单与长度', () => {
  it('移除脚本、媒体、表单、命名与展示属性，只保留排版', () => {
    const result = sanitizeRichText('<p id="x" name="x" style="color:red" class="x" onclick="alert(1)" data-x="1" aria-label="x">文字<strong>粗体</strong></p><script>discard-script</script><style>discard-style</style><iframe>discard-frame</iframe><svg><text>discard-svg</text></svg><math><mtext>discard-math</mtext></math><img src="https://attacker.invalid/x"><form><input value="discard-input"></form>')
    expect(result).toBe('<p>文字<strong>粗体</strong></p>')
  })
  it.each(['javascript:alert(1)', 'mailto:a@example.test', '/path', '//example.test/', 'https://user:pass@example.test/', 'https://example.test/white space', 'https://example.test/\npath', 'https://example.test/a%0ab', 'https://example.test/a%7fb', 'https://example.test\\x', 'https://example.test/a%20b', 'https://example.test/a%5cb', 'https://example.test/a%c2%85b', 'https://example.test/a%e2%80%8bb', 'https://example.test/a%zz'])('拒绝不安全链接 %s 且保留可读文字', value => {
    expect(safeRichTextUrl(value)).toBeNull()
    const a = document.createElement('a'); a.setAttribute('href', value); a.textContent = 'readable'
    expect(sanitizeRichText(a.outerHTML)).toBe('readable')
  })
  it('绝对安全链接固定rel且不保留target/ping等其他属性', () => {
    expect(safeRichTextUrl('https://@example.test/')).toBeNull()
    expect(sanitizeRichText('<a href="https://example.test/guide" rel="opener" target="_blank" ping="https://example.test/ping">指南</a>')).toBe('<a href="https://example.test/guide" rel="noopener noreferrer nofollow">指南</a>')
  })
  it('纯文本转换转义HTML与换行；反向转换明确丢弃格式', () => {
    const text = '<img src=x onerror=alert(1)> literal\nsecond & line'
    const html = plainTextToRich(text)
    expect(html).toContain('&lt;img'); expect(html).toContain('<br>'); expect(richTextToPlain(html)).toBe(text)
    expect(richTextToPlain('<h2>heading</h2><p>body<br>next</p>')).toBe('heading\nbody\nnext')
  })
  it.each(['<p><br></p>', '<hr>', '<p>&nbsp; \u200b\u200e</p>', '<img src=x>', '<script>discard</script>'])('拒绝语义空白 %s', value => { expect(richTextHasContent(value)).toBe(false) })
  it('分别限制原文与rel补全后的清洗长度', () => {
    expect(() => sanitizeRichText('a'.repeat(20_001))).toThrow('rich-text-length')
    expect(() => sanitizeRichText('<a href="https://example.test">' + 'a'.repeat(19_960) + '</a>')).toThrow('rich-text-length')
    expect(sanitizeRichText('a'.repeat(20_000))).toHaveLength(20_000)
  })
  it('SafeRichText默认纯文本显示旧HTML字面值，html防御过长不进入DOM', () => {
    const literal = '<strong>literal</strong><img src=x>'
    const wrapper = mount(SafeRichText, { props: { content: literal, label: '内容' } })
    expect(wrapper.text()).toBe(literal); expect(wrapper.find('strong,img').exists()).toBe(false)
    const html = mount(SafeRichText, { props: { content: '<strong>allowed</strong><img src=x>', format: 'html' } })
    expect(html.find('strong').text()).toBe('allowed'); expect(html.find('img').exists()).toBe(false)
    const long = mount(SafeRichText, { props: { content: 'a'.repeat(20_001), format: 'html' } })
    expect(long.find('[role="alert"]').exists()).toBe(true); expect(long.text()).not.toContain('a'.repeat(20_001))
  })
})
