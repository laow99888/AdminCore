import type { Component } from 'vue'
import { LayoutDashboard, Users, ShieldCheck, ListTree, FolderOpen, ClipboardCheck, Bell, ListChecks, FileText, Settings, Trash2 } from 'lucide-vue-next'

export const menuIcons: Record<string, Component> = {
  'layout-dashboard': LayoutDashboard, users: Users, 'shield-check': ShieldCheck,
  'list-tree': ListTree, 'folder-open': FolderOpen, 'clipboard-check': ClipboardCheck,
  bell: Bell, 'list-checks': ListChecks, 'file-text': FileText, settings: Settings,
  'trash-2': Trash2,
}
