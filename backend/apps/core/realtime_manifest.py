"""内置模块唯一静态声明；不导入模型或访问数据库。"""
from apps.core.contracts import Module

MODULE = Module('realtime', '实时通道', 'realtime', 'apps.core.realtime_urls', (), default_enabled=False)
