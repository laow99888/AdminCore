"""公告正文的格式契约：纯文本保持原样，HTML 只允许受控排版和绝对网页链接。"""
from html.parser import HTMLParser
import unicodedata
from urllib.parse import unquote, urlsplit

import nh3
from rest_framework.exceptions import APIException, ValidationError

MAX_CONTENT_LENGTH = 20000
ALLOWED_TAGS = {'p', 'br', 'h2', 'h3', 'strong', 'em', 'u', 's', 'ul', 'ol', 'li',
                'blockquote', 'pre', 'code', 'hr', 'a'}
DROP_CONTENT_TAGS = {'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math',
                     'template', 'noscript', 'noembed', 'noframes'}
LINK_REL = 'noopener noreferrer nofollow'


class AnnouncementContentUnavailable(APIException):
    status_code = 503
    default_detail = '公告正文暂不可用，请稍后重试'
    default_code = 'announcement_content_unavailable'


def _safe_href(tag, attribute, value):
    # nh3 对自动补充的 link_rel 也调用过滤器；只保留服务端固定值。
    if tag == 'a' and attribute == 'rel':
        return LINK_REL
    if tag != 'a' or attribute != 'href':
        return None
    # urlsplit 会忽略部分控制字符，因此须在解析前拒绝原始/百分号编码字符。
    decoded = unquote(value)
    if any(char.isspace() or unicodedata.category(char).startswith('C') or char == '\\'
           for char in value + decoded):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme.lower() not in {'http', 'https'} or not parsed.netloc or not parsed.hostname
                or parsed.username is not None or parsed.password is not None or '%' in parsed.hostname):
            return None
        parsed.port  # 非数字或越界端口也不属于有效的绝对 URL。
    except ValueError:
        return None
    return value


def sanitize_html(content):
    try:
        return nh3.clean(content, tags=ALLOWED_TAGS, clean_content_tags=DROP_CONTENT_TAGS,
                         attributes={'a': {'href'}}, attribute_filter=_safe_href,
                         strip_comments=True, link_rel=LINK_REL, url_schemes={'http', 'https'},
                         url_relative='deny')
    except Exception:
        raise AnnouncementContentUnavailable() from None


class _TextContent(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _has_visible_text(content, content_format):
    if content_format == 'html':
        parser = _TextContent()
        parser.feed(content)
        content = ''.join(parser.parts)
    return any(not char.isspace() and not unicodedata.category(char).startswith('C') for char in content)


def prepare_content(content, content_format, *, validate=True):
    """写入/发布严格校验；读取只净化以屏蔽遗留或外部直接写库的危险 HTML。"""
    if content_format not in {'plain', 'html'}:
        raise ValidationError({'content_format': '公告格式只能为 plain 或 html'})
    if not isinstance(content, str):
        raise ValidationError({'content': '公告正文必须为字符串'})
    if validate and len(content) > MAX_CONTENT_LENGTH:
        raise ValidationError({'content': '公告正文不能超过 20000 字符'})
    result = sanitize_html(content) if content_format == 'html' else content
    if validate and len(result) > MAX_CONTENT_LENGTH:
        raise ValidationError({'content': '消毒后的公告正文不能超过 20000 字符'})
    if validate and not _has_visible_text(result, content_format):
        raise ValidationError({'content': '公告正文不能为空'})
    return result
