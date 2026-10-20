"""Catálogo Pytest com metadados opcionais do formato legado."""
import json
from pathlib import Path

from django.conf import settings


def exercises():
    legacy_file = Path(settings.BASE_DIR) / 'tests.json'
    legacy = json.loads(legacy_file.read_text(encoding='utf-8')) if legacy_file.exists() else {}
    result = dict(legacy)
    for spec in sorted((Path(settings.BASE_DIR) / 'exercises').glob('test_*.py')):
        result.setdefault(spec.stem.removeprefix('test_'), {})
    return result
