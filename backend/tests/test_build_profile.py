import json

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.build_profile import load_profile, validate_profile


def test_source_defaults_to_full_and_valid_markers(tmp_path):
    marker = tmp_path / 'profile.json'
    assert load_profile(marker) == 'full'
    for profile in ('full', 'minimal'):
        marker.write_text(json.dumps({'profile': profile}), encoding='utf-8')
        assert load_profile(marker) == profile


@pytest.mark.parametrize('content', ['{', '[]', 'null', '{"profile":"other"}',
    '{"profile":"minimal","modules":["files"]}'])
def test_invalid_marker_rejected(tmp_path, content):
    marker = tmp_path / 'profile.json'
    marker.write_text(content, encoding='utf-8')
    with pytest.raises(ImproperlyConfigured, match='构建能力标记'):
        load_profile(marker)


@pytest.mark.parametrize('modules,storage,images', [(('files',), 'local', False),
    (('tasks',), 'local', False), ((), 's3', False), ((), 'local', True)])
def test_trimmed_image_refuses_unavailable_runtime_capabilities(modules, storage, images):
    with pytest.raises(ImproperlyConfigured, match='重新构建完整镜像'):
        validate_profile('minimal', modules, storage, images)
    validate_profile('full', modules, storage, images)


def test_minimal_profile_accepts_only_core_local_storage():
    validate_profile('minimal', (), 'local', False)
    with pytest.raises(ImproperlyConfigured):
        validate_profile('unknown', ())
