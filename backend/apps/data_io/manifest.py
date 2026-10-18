"""内置模块唯一静态声明；不导入模型或访问数据库。"""
from apps.core.contracts import Module

MODULE = Module('data_io', '数据导入导出', 'data-io', 'apps.data_io.urls', (), ('files', 'tasks'), ('data_io.run_data_import', 'data_io.run_business_export'),
    permissions=(
        ('data_io', 'import', '数据导入', 'data_io:import'),
        ('data_io', 'export', '数据导出', 'data_io:export'),
    ))
