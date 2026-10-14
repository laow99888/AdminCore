import type { Component } from 'vue'
import { LayoutDashboard, Users, ShieldCheck, ListTree, FolderOpen, ClipboardCheck, Bell, ListChecks, FileText, Settings, Trash2, Clock, Info, Activity, BriefcaseBusiness, Database, Mail } from 'lucide-vue-next'

export const menuIcons: Record<string, Component> = {
  'layout-dashboard': LayoutDashboard, users: Users, 'shield-check': ShieldCheck,
  'list-tree': ListTree, 'folder-open': FolderOpen, 'clipboard-check': ClipboardCheck,
  bell: Bell, 'list-checks': ListChecks, 'file-text': FileText, settings: Settings,
  'trash-2': Trash2,
  clock: Clock,
  info: Info, activity: Activity,
  'briefcase-business': BriefcaseBusiness,
  database: Database,
  mail: Mail,
}
