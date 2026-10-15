"""底座版本的唯一源码；不接受部署环境任意覆盖。"""
import json
from pathlib import Path
import re

_VERSION = json.loads((Path(__file__).resolve().parents[2] / 'config/base-version.json').read_text(encoding='utf-8'))
if (set(_VERSION) != {'version', 'module_contract_version'}
        or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?', _VERSION['version'])
        or type(_VERSION['module_contract_version']) is not int or _VERSION['module_contract_version'] < 1):
    raise ValueError('底座版本元数据无效')

BASE_VERSION = _VERSION['version']
MODULE_CONTRACT_VERSION = _VERSION['module_contract_version']
