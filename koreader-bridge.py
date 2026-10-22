#!/usr/bin/env python3
"""KOReader Bridge entry point; keep the adjacent legacy engine and locales."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def load_engine() -> ModuleType:
    """Load the shared engine beside this file without changing argv or cwd."""
    path = Path(__file__).resolve().with_name('kobo-koreader-migrate.py')
    spec = importlib.util.spec_from_file_location('_koreader_bridge_engine', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    return load_engine().cli()


if __name__ == '__main__':
    raise SystemExit(main())
