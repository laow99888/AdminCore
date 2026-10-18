"""内置模块唯一静态声明；不导入模型或访问数据库。"""
from apps.core.contracts import Module, MenuDeclaration, Parameter

MODULE = Module('files', '文件管理', 'files', 'apps.files.urls', ('/files',),
    data_resources=(('file', '文件'),),
    permissions=(
        ('file', 'upload', '上传文件', 'file:upload'),
        ('file', 'download', '下载文件', 'file:download'),
        ('file', 'process', '处理图片并下载派生结果', 'file:process'),
        ('file', 'recycle', '查看文件回收站', 'file:recycle'),
        ('file', 'restore', '恢复文件', 'file:restore'),
        ('file', 'purge', '彻底删除文件', 'file:purge'),
    ),
    audit_fields=(
        ('file_document', ('id', 'version', 'current_file_id', 'restored_from')),
        ('file_capacity', ('owner_id', 'limit_bytes', 'version')),
        ('file_folder', ('id', 'owner_id', 'version', 'operation', 'content_sha256')),
        ('file_organization', ('id', 'owner_id', 'version', 'operation', 'content_sha256')),
        ('file_scan', ('outcome', 'stage', 'sha256', 'bytes', 'engine', 'signature_sha256')),
        ('file', ('id', 'purpose', 'size', 'file_type', 'is_deleted', 'deleted_at', 'deleted_by', 'lifecycle_version')),
        ('file_transform', ('id', 'lifecycle_version', 'source_sha256', 'width', 'height', 'format', 'quality', 'watermark_sha256', 'opacity', 'position', 'output_sha256', 'size')),
        ('file_office_preview', ('job_id', 'lifecycle_version', 'source_sha256', 'output_sha256', 'status', 'engine')),
    ),
    menus=(
        MenuDeclaration('文件管理', '/files', 'folder-open', None, 5),
        MenuDeclaration('文件回收站', '/files/recycle', 'trash-2', 'file:recycle', 15),
    ),
    parameters=(
        Parameter(key='files.retention_days', label='软删除文件保留天数', kind='integer', default=30, setting='FILE_SOFT_DELETE_RETENTION_DAYS', minimum=1, maximum=3650),
    ))
