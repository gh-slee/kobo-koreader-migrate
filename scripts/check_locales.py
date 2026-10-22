#!/usr/bin/env python3
"""Validate registered locale assets without devices, runs, network or AI services."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    spec = importlib.util.spec_from_file_location('migration_locale_check', ROOT / 'koreader-bridge.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module = module.load_engine()
    try:
        registry = module.load_locale_registry(ROOT / 'locales')
        english = module.load_locale_catalog(ROOT / 'locales', 'en', registry)
        for tag in registry['entries']:
            module.load_locale_catalog(ROOT / 'locales', tag, registry,
                                       None if tag == 'en' else english, complete=True)
        print(f'Locale validation passed: {len(registry["entries"])} locales; {len(english)} messages each.')
        return 0
    except module.LocaleError as error:
        print(f'Locale validation failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
