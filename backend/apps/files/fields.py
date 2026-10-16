"""所有托管文件读取共享扫描入口，包括旧文件、头像、导入及 Office 源。"""
from django.conf import settings
from django.db.models.fields.files import FileField, FieldFile


class ScannedFieldFile(FieldFile):
    def _checked_file(self):
        self._require_file()
        if not settings.ADMINCORE_ANTIVIRUS.enabled or not self._committed:
            return super()._get_file()
        source = getattr(self, '_file', None)
        if source is None or source.closed:
            source = self.storage.open(self.name, 'rb')
        if source is not getattr(self, '_verified_file', None):
            from .antivirus import checked_copy
            try:
                self._file = checked_copy(source, stage='stored_read', identifier=self.instance.pk)
                self._verified_file = self._file
            finally:
                source.close()
        return self._file

    file = property(_checked_file, FieldFile._set_file, FieldFile._del_file)

    def open(self, mode='rb'):
        if not settings.ADMINCORE_ANTIVIRUS.enabled:
            return super().open(mode)
        if mode not in ('r', 'rb'):
            raise ValueError('托管文件仅支持只读打开')
        self.file.seek(0)
        return self

    def save(self, name, content, save=True):
        if not settings.ADMINCORE_ANTIVIRUS.enabled:
            return super().save(name, content, save)
        from .antivirus import checked_upload
        scanned = checked_upload(content, stage='upload')
        try:
            result = super().save(name, scanned, save)
            from .antivirus import register_artifact
            register_artifact(self)
            return result
        finally:
            scanned.close()


class ScannedFileField(FileField):
    attr_class = ScannedFieldFile
