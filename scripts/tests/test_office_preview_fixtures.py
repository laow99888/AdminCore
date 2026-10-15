import importlib.util
import io
from pathlib import Path
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location('office_fixtures_validation', Path(__file__).parents[1] / 'office_preview_fixtures.py')
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)


@pytest.mark.parametrize('extension', fixtures.MIMES)
def test_real_odf_family_has_content_styles_manifest_and_expected_text(extension):
    content = fixtures.odf_fixture(extension, 'UNIQUEPROOF123')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.namelist()[0] == 'mimetype'
        assert archive.read('mimetype').decode() == fixtures.MIMES[extension]
        assert b'UNIQUEPROOF123' in archive.read('content.xml')
        assert '中文内容验收' in archive.read('content.xml').decode()
        assert b'style:master-page' in archive.read('styles.xml')
        assert b'manifest:file-entry' in archive.read('META-INF/manifest.xml')
        from xml.etree import ElementTree
        for name in ('content.xml', 'styles.xml', 'META-INF/manifest.xml'):
            ElementTree.fromstring(archive.read(name))


def test_fixture_extension_cannot_be_arbitrary():
    with pytest.raises(ValueError):
        fixtures.odf_fixture('../../exe', 'proof')
