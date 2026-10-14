<template>
  <div class="rich-editor" :class="{ disabled }">
    <div v-if="editor" class="rich-toolbar" role="toolbar" :aria-label="uiText('正文格式工具栏')">
      <el-button v-for="tool in tools" :key="tool.label" :aria-label="uiText(tool.label)" :title="uiText(tool.label)" :aria-pressed="tool.active ? tool.active() : undefined" :disabled="disabled || tool.unavailable?.()" @mousedown.prevent @click="tool.run()"><component :is="tool.icon" :size="18" aria-hidden="true" /></el-button>
      <el-button :aria-label="uiText('设置链接')" :title="uiText('设置链接')" :disabled="disabled" @mousedown.prevent @click="openLink"><Link :size="18" aria-hidden="true" /></el-button>
      <el-button :aria-label="uiText('移除链接')" :title="uiText('移除链接')" :disabled="disabled || !editor.isActive('link')" @mousedown.prevent @click="editor.chain().focus().unsetLink().run()"><Unlink :size="18" aria-hidden="true" /></el-button>
    </div>
    <div v-if="linkVisible" class="link-controls">
      <label :for="linkId">{{ uiText('链接地址') }}</label>
      <el-input :id="linkId" v-model="linkValue" :disabled="disabled" :aria-label="uiText('链接地址')" maxlength="2000" placeholder="https://example.com" @keydown.enter.prevent="applyLink" />
      <el-button :disabled="disabled" @click="applyLink">{{ uiText('应用链接') }}</el-button><el-button :disabled="disabled" @click="closeLink">{{ uiText('取消链接') }}</el-button>
    </div>
    <p v-if="localError" role="alert" class="editor-error">{{ localError }}</p>
    <EditorContent :editor="editor" />
    <p class="editor-hint">{{ uiText('仅支持文字排版和 HTTP/HTTPS 链接，不支持图片、附件或嵌入内容。') }} {{ modelValue.length }} / 20000</p>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Bold, Italic, Underline, Strikethrough, Heading2, Heading3, List, ListOrdered, Quote, Code, SquareCode, Minus, Link, Unlink, Undo2, Redo2 } from 'lucide-vue-next'
import { plainTextToRich, safeRichTextUrl, sanitizeRichText } from '@/utils/richText'
import { uiText } from '@/i18n/uiText'

const props = defineProps<{ modelValue: string; label: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; invalid: [value: string]; ready: [] }>()
const localError = ref(''), linkVisible = ref(false), linkValue = ref(''), linkId = useId()
let lastValid = ''
function reportLength() { localError.value = uiText('正文原文或清洗后的 HTML 超过 20000 字符，请缩短内容。'); emit('invalid', localError.value) }
function initialContent() { try { return sanitizeRichText(props.modelValue) } catch { reportLength(); return '' } }
lastValid = initialContent()
const editor = useEditor({
  content: lastValid, editable: !props.disabled,
  extensions: [StarterKit.configure({ heading: { levels: [2, 3] }, link: { autolink: false, linkOnPaste: false, openOnClick: false, enableClickSelection: false, HTMLAttributes: { target: null, rel: 'noopener noreferrer nofollow', class: null }, isAllowedUri: value => !!safeRichTextUrl(value) }, codeBlock: { languageClassPrefix: null }, trailingNode: false })],
  editorProps: {
    attributes: { role: 'textbox', 'aria-label': props.label, 'aria-multiline': 'true', 'aria-disabled': String(!!props.disabled), spellcheck: 'true' },
    transformPastedHTML: value => { try { return sanitizeRichText(value) } catch { reportLength(); return '' } },
    handlePaste: (_view, event) => {
      if (props.disabled) return true
      const html = event.clipboardData?.getData('text/html'), text = event.clipboardData?.getData('text/plain') || ''
      try { const clean = html ? sanitizeRichText(html) : plainTextToRich(text); localError.value = ''; emit('invalid', ''); editor.value?.commands.insertContent(clean) }
      catch { reportLength() }
      return true
    },
  },
  onUpdate: ({ editor: current }) => {
    try {
      const clean = sanitizeRichText(current.getHTML()); lastValid = clean; localError.value = ''; emit('invalid', ''); emit('update:modelValue', clean)
    } catch { current.commands.setContent(lastValid, { emitUpdate: false }); reportLength() }
  },
})
const tools = [
  { label: '加粗', icon: Bold, run: () => editor.value?.chain().focus().toggleBold().run(), active: () => editor.value?.isActive('bold') },
  { label: '斜体', icon: Italic, run: () => editor.value?.chain().focus().toggleItalic().run(), active: () => editor.value?.isActive('italic') },
  { label: '下划线', icon: Underline, run: () => editor.value?.chain().focus().toggleUnderline().run(), active: () => editor.value?.isActive('underline') },
  { label: '删除线', icon: Strikethrough, run: () => editor.value?.chain().focus().toggleStrike().run(), active: () => editor.value?.isActive('strike') },
  { label: '二级标题', icon: Heading2, run: () => editor.value?.chain().focus().toggleHeading({ level: 2 }).run(), active: () => editor.value?.isActive('heading', { level: 2 }) },
  { label: '三级标题', icon: Heading3, run: () => editor.value?.chain().focus().toggleHeading({ level: 3 }).run(), active: () => editor.value?.isActive('heading', { level: 3 }) },
  { label: '无序列表', icon: List, run: () => editor.value?.chain().focus().toggleBulletList().run(), active: () => editor.value?.isActive('bulletList') },
  { label: '有序列表', icon: ListOrdered, run: () => editor.value?.chain().focus().toggleOrderedList().run(), active: () => editor.value?.isActive('orderedList') },
  { label: '引用', icon: Quote, run: () => editor.value?.chain().focus().toggleBlockquote().run(), active: () => editor.value?.isActive('blockquote') },
  { label: '行内代码', icon: Code, run: () => editor.value?.chain().focus().toggleCode().run(), active: () => editor.value?.isActive('code') },
  { label: '代码块', icon: SquareCode, run: () => editor.value?.chain().focus().toggleCodeBlock().run(), active: () => editor.value?.isActive('codeBlock') },
  { label: '分隔线', icon: Minus, run: () => editor.value?.chain().focus().setHorizontalRule().run() },
  { label: '撤销', icon: Undo2, run: () => editor.value?.chain().focus().undo().run(), unavailable: () => !editor.value?.can().undo() },
  { label: '重做', icon: Redo2, run: () => editor.value?.chain().focus().redo().run(), unavailable: () => !editor.value?.can().redo() },
]
function openLink() { if (!props.disabled) { linkValue.value = editor.value?.getAttributes('link').href || ''; linkVisible.value = true; localError.value = '' } }
function closeLink() { linkVisible.value = false; linkValue.value = ''; localError.value = '' }
function applyLink() {
  if (props.disabled) return
  const url = safeRichTextUrl(linkValue.value)
  if (!url) { localError.value = uiText('链接仅允许完整的 HTTP/HTTPS 地址，不能包含凭据或空白控制字符。'); return }
  editor.value?.chain().focus().extendMarkRange('link').setLink({ href: url }).run(); closeLink()
}
watch(() => props.disabled, value => { editor.value?.setEditable(!value); editor.value?.setOptions({ editorProps: { attributes: { role: 'textbox', 'aria-label': props.label, 'aria-multiline': 'true', 'aria-disabled': String(!!value) } } }); if (value) closeLink() })
watch(() => props.modelValue, value => {
  if (!editor.value || value === lastValid) return
  try { lastValid = sanitizeRichText(value); editor.value.commands.setContent(lastValid, { emitUpdate: false }); localError.value = ''; emit('invalid', '') } catch { editor.value.commands.setContent('', { emitUpdate: false }); reportLength() }
})
onMounted(() => emit('ready'))
onBeforeUnmount(() => { closeLink(); editor.value?.destroy(); lastValid = '' })
</script>

<style scoped>
.rich-editor { border: 1px solid var(--color-border); border-radius: var(--radius-md); overflow: hidden; width: 100%; min-width: 0; }
.rich-toolbar { display: flex; gap: 4px; flex-wrap: wrap; padding: var(--spacing-sm); background: var(--color-bg-elevated); border-bottom: 1px solid var(--color-border); }
.rich-toolbar :deep(.el-button) { margin: 0; width: 44px; min-height: 44px; padding: 8px; }
.rich-toolbar :deep([aria-pressed='true']) { color: var(--color-primary); border-color: var(--color-primary); }
.rich-editor :deep(.tiptap) { min-height: 200px; max-height: 48vh; overflow: auto; padding: var(--spacing-md); line-height: 1.7; overflow-wrap: anywhere; outline-offset: -2px; }
.rich-editor :deep(pre) { white-space: pre-wrap; padding: var(--spacing-sm); background: var(--color-bg-elevated); }
.rich-editor :deep(a) { color: var(--color-primary); text-decoration: underline; }
.rich-editor :deep(blockquote) { border-left: 3px solid var(--color-border); margin-inline: 0; padding-left: var(--spacing-md); }
.editor-hint, .editor-error { margin: var(--spacing-sm); line-height: 1.6; overflow-wrap: anywhere; }
.editor-hint { color: var(--color-text-secondary); font-size: var(--font-size-sm); }
.editor-error { color: var(--color-error); }
.link-controls { display: flex; align-items: center; flex-wrap: wrap; gap: var(--spacing-sm); padding: var(--spacing-sm); }
.link-controls :deep(.el-input) { flex: 1 1 200px; }
.link-controls :deep(.el-button) { margin: 0; min-height: 44px; }
.disabled { opacity: .7; }
</style>
