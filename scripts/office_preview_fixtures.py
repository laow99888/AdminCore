"""可由 LibreOffice 实际打开的三类 ODF 内容夹具；不依赖额外办公文档库。"""
import io
import zipfile
from xml.sax.saxutils import escape

MIMES = {'odt': 'application/vnd.oasis.opendocument.text',
         'ods': 'application/vnd.oasis.opendocument.spreadsheet',
         'odp': 'application/vnd.oasis.opendocument.presentation'}
NAMESPACES = '''xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0"
xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
xmlns:xlink="http://www.w3.org/1999/xlink"'''


def odf_fixture(extension, token):
    if extension not in MIMES:
        raise ValueError('unsupported_fixture')
    paragraph = '<text:p>' + escape(token) + '</text:p><text:p>中文内容验收</text:p>'
    if extension == 'odt':
        body = '<office:text>' + paragraph + '<text:p><text:a xlink:type="simple" xlink:href="https://example.invalid/office-proof">ExternalLink</text:a></text:p></office:text>'
    elif extension == 'ods':
        body = '<office:spreadsheet><table:table table:name="Fixture"><table:table-row><table:table-cell office:value-type="string">' + paragraph + '</table:table-cell><table:table-cell office:value-type="float" office:value="42"><text:p>42</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet>'
    else:
        body = '<office:presentation><draw:page draw:name="Fixture" draw:master-page-name="Default"><draw:frame svg:x="2cm" svg:y="2cm" svg:width="20cm" svg:height="6cm"><draw:text-box>' + paragraph + '</draw:text-box></draw:frame></draw:page></office:presentation>'
    content = '<?xml version="1.0" encoding="UTF-8"?><office:document-content ' + NAMESPACES + ' office:version="1.3"><office:automatic-styles/><office:body>' + body + '</office:body></office:document-content>'
    styles = '<?xml version="1.0" encoding="UTF-8"?><office:document-styles ' + NAMESPACES + ''' office:version="1.3"><office:styles/>
<office:automatic-styles><style:page-layout style:name="pm1"><style:page-layout-properties fo:page-width="28cm" fo:page-height="21cm" style:print-orientation="landscape"/></style:page-layout></office:automatic-styles>
<office:master-styles><style:master-page style:name="Default" style:page-layout-name="pm1"/></office:master-styles></office:document-styles>'''
    manifest = '<?xml version="1.0" encoding="UTF-8"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3"><manifest:file-entry manifest:full-path="/" manifest:media-type="' + MIMES[extension] + '"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/><manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/></manifest:manifest>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('mimetype', MIMES[extension], compress_type=zipfile.ZIP_STORED)
        archive.writestr('content.xml', content)
        archive.writestr('styles.xml', styles)
        archive.writestr('META-INF/manifest.xml', manifest)
    return output.getvalue()
