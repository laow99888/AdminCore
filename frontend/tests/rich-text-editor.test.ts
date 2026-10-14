import { describe, expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { EditorContent, type Editor } from '@tiptap/vue-3'
import RichTextEditorCore from '../src/components/common/RichTextEditorCore.vue'

describe('真实Tiptap编辑器初始化与粘贴边界', () => {
  it('初始化先消毒且只声明受限节点，disabled和卸载销毁', async () => {
    const wrapper = mount(RichTextEditorCore, { props: { modelValue: '<p style="color:red" onclick="alert(1)"><strong>allowed</strong><img src=x></p><script>discard</script>', label: '公告富文本正文' } })
    await flushPromises()
    const editor = wrapper.get('[role="textbox"]')
    expect(editor.text()).toBe('allowed'); expect(editor.find('strong').exists()).toBe(true)
    expect(editor.find('img,script,[onclick],[style]').exists()).toBe(false)
    await wrapper.setProps({ disabled: true }); expect(editor.attributes('contenteditable')).toBe('false'); expect(editor.attributes('aria-disabled')).toBe('true')
    wrapper.unmount(); expect(document.querySelector('.tiptap')).toBeNull()
  })
  it('粘贴恶意HTML先清洗；超限粘贴保持已有内容且给出错误', async () => {
    const wrapper = mount(RichTextEditorCore, { props: { modelValue: '<p>existing</p>', label: '公告富文本正文' } })
    await flushPromises()
    const element = wrapper.get('[role="textbox"]').element
    const paste = (html: string) => {
      const event = new Event('paste', { bubbles: true, cancelable: true })
      Object.defineProperty(event, 'clipboardData', { value: { getData: (format: string) => format === 'text/html' ? html : 'text' } })
      element.dispatchEvent(event)
    }
    paste('<p><em>pasted</em><img src=x onerror=alert(1)><a href="javascript:alert(1)">unsafe link</a></p>')
    await flushPromises(); expect(wrapper.text()).toContain('pasted'); expect(wrapper.find('.tiptap img,.tiptap a').exists()).toBe(false)
    const updates = wrapper.emitted('update:modelValue')!
    expect(updates.at(-1)?.[0]).not.toMatch(/<img|javascript|onerror/)
    const before = wrapper.get('.tiptap').html()
    paste('<p>' + 'a'.repeat(20_001) + '</p>'); await flushPromises()
    expect(wrapper.get('.tiptap').html()).toBe(before); expect(wrapper.get('[role="alert"]').text()).toContain('20000')
  })
  it('合法粘贴与已有内容合计超限时回滚且保留错误，合法编辑解除错误', async () => {
    const original = '<p>' + 'a'.repeat(19_970) + '</p>'
    const wrapper = mount(RichTextEditorCore, { props: { modelValue: original, label: '公告富文本正文' } })
    await flushPromises()
    const editor = wrapper.findComponent(EditorContent).props('editor') as Editor
    editor.commands.setTextSelection(19_971)
    const event = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'clipboardData', { value: { getData: (format: string) => format === 'text/html' ? '<p>' + 'b'.repeat(100) + '</p>' : 'b'.repeat(100) } })
    wrapper.get('[role="textbox"]').element.dispatchEvent(event)
    await flushPromises()
    expect(editor.getHTML()).toBe(original)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.get('[role="alert"]').text()).toContain('20000')
    expect(wrapper.emitted('invalid')?.at(-1)?.[0]).toContain('20000')
    editor.commands.setTextSelection(19_971)
    editor.commands.insertContent('z')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.emitted('invalid')?.at(-1)).toEqual([''])
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('<p>' + 'a'.repeat(19_970) + 'z</p>')
    // Typing uses the same update path: reject over-limit transactions, then recover.
    const valid = editor.getHTML()
    editor.commands.insertContent('c'.repeat(100))
    await flushPromises()
    expect(editor.getHTML()).toBe(valid)
    expect(wrapper.emitted('invalid')?.at(-1)?.[0]).toContain('20000')
    editor.commands.insertContent('d')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.emitted('invalid')?.at(-1)).toEqual([''])
  })
})
