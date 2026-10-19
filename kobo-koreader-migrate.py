#!/usr/bin/env python3
"""
KOReader Kobo Migration Tool v3.3.0-dev.4
macOS, standard library only.

Supported workflow:
  SOURCE Kobo -> TARGET Kobo; both roles confirmed by the operator

Safety model:
  - Source is read-only from the script's perspective.
  - Source KOReader is archived to the project run directory and fully hashed.
  - Target KOReader is archived before any destructive operation.
  - Target .adds/koreader is then cleanly replaced (never Finder-merged).
  - Restored files are verified against a per-file SHA-256 manifest.
  - On restore/verification failure, the target backup is automatically restored.
  - Target KOReader device_id can be preserved (recommended), regenerated, or cloned.
  - Optional ebooks are staged on the Mac and copied to matching relative paths.
  - Overwritten ebooks are backed up; copied files are hashed and rolled back on failure.

This tool intentionally clones the whole .adds/koreader tree.
Backups may contain API keys or other credentials; treat them as sensitive.
"""

from __future__ import annotations

import argparse
import fcntl
from contextlib import ExitStack, closing, contextmanager
from contextvars import ContextVar
from functools import lru_cache
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
import sqlite3
import stat
import string
import tempfile
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

VERSION = "3.3.0-dev.4"
DEFAULT_BACKUP_DIR = Path(__file__).resolve().parent
VOLUME_ROOT = Path("/Volumes")

MODEL_CLARA = "Kobo Clara 2E"
MODEL_LIBRA = "Kobo Libra 2"

# We intentionally do not verify files that are deliberately removed after restore.
VERIFY_EXCLUDES = {
    "cache/fontlist/fontinfo.dat",
    "cache/fontinfo.dat",
}

APPLEDOUBLE_PREFIX = "._"
DEVICE_ID_RE = re.compile(
    r'(\["device_id"\]\s*=\s*)"([^"]*)"',
    flags=re.MULTILINE,
)
DETECTED_KOBO_RE = re.compile(
    r"Detected a Kobo\s+(.+?)\s+\(",
    flags=re.IGNORECASE,
)


class MigrationError(RuntimeError):
    pass


class MigrationCancelled(RuntimeError):
    """An intentional cancellation before any target modification."""
    pass


@dataclass
class DeviceInfo:
    mount: str
    detected_model: Optional[str]
    koreader_version: Optional[str]
    fingerprint_sha256: Optional[str]
    serial_hint: Optional[str]
    device_id_present: bool
    ai_assistant_config: bool  # Legacy snapshot metadata; not a dedicated UI check.
    file_count: int
    total_bytes: int


# Locale assets are reviewed data. Locale names never select arbitrary files.
LOCALE_ROOT = Path(__file__).resolve().parent / 'locales'
LOCALE_MAX_BYTES = 256 * 1024
LOCALE_TAG_RE = re.compile(r'[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?\Z')
MESSAGE_ID_RE = re.compile(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z')
LOCALE_REQUIRED_IDS = frozenset({
    'cli.description',
    'cli.foundation_notice',
    'cli.locales_heading',
    'help.backup_dir',
    'help.books',
    'help.cleanup',
    'help.conflict',
    'help.delete_run',
    'help.dry_run',
    'help.exclude_dir',
    'help.extra_extension',
    'help.fonts',
    'help.from_run',
    'help.help',
    'help.include_dir',
    'help.keep_successful',
    'help.list_locales',
    'help.list_runs',
    'help.locale',
    'help.mode',
    'help.preview_ui',
    'help.reading_data',
    'help.restore_run',
    'help.self_test',
    'help.source_model',
    'help.target_model',
    'help.version',
    'mode.audit',
    'mode.full',
    'mode.koreader',
    'mode.library',
    'preview.default_no',
    'preview.delete',
    'preview.file_count',
    'preview.notice',
    'preview.title',
})
PLURAL_RULES = {'one-other': {'one', 'other'}, 'other-only': {'other'}}


class LocaleError(ValueError):
    """English startup diagnostic that never includes catalog contents."""


def _locale_text(value, limit=8192, multiline=True):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise LocaleError('Locale text must be a nonempty bounded string.')
    if any(unicodedata.category(ch) in {'Cc', 'Cf', 'Cs'} and
           not (multiline and ch in '\n\t') for ch in value):
        raise LocaleError('Locale text contains forbidden control characters.')
    return value


def _unique_locale_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LocaleError('Duplicate key in locale JSON.')
        result[key] = value
    return result


def _locale_json(root: Path, name: str) -> dict:
    path = root / name
    try:
        if root.is_symlink() or not root.is_dir() or path.is_symlink() or not path.is_file():
            raise LocaleError('Locale assets must be regular files in locales/.')
        with path.open('rb') as stream:
            raw = stream.read(LOCALE_MAX_BYTES + 1)
        if len(raw) > LOCALE_MAX_BYTES:
            raise LocaleError('Locale asset exceeds the size limit.')
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_locale_object)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, LocaleError):
            raise
        raise LocaleError('Cannot read a valid UTF-8 locale asset.') from None
    if not isinstance(result, dict) or type(result.get('schema_version')) is not int or result['schema_version'] != 1:
        raise LocaleError('Unsupported locale asset schema.')
    return result


def _normalize_locale(value: str) -> Optional[str]:
    if not isinstance(value, str) or len(value) > 80 or not re.fullmatch(r'[A-Za-z0-9_.@-]+', value.strip()):
        return None
    tag = value.strip().split('.', 1)[0].split('@', 1)[0].replace('_', '-')
    if tag.casefold() in {'c', 'posix'}:
        return 'en'
    pieces = tag.split('-')
    normalized = [pieces[0].lower()]
    for piece in pieces[1:]:
        normalized.append(piece.title() if len(piece) == 4 else piece.upper())
    tag = '-'.join(normalized)
    return tag if LOCALE_TAG_RE.fullmatch(tag) else None


def load_locale_registry(root: Path) -> dict:
    data = _locale_json(root, 'registry.json')
    if set(data) != {'schema_version', 'locales'} or not isinstance(data['locales'], list) or not 1 <= len(data['locales']) <= 100:
        raise LocaleError('Invalid locale registry.')
    entries, aliases = {}, {}
    for item in data['locales']:
        if not isinstance(item, dict) or set(item) != {'tag', 'name', 'plural_rule', 'aliases'}:
            raise LocaleError('Invalid locale registry entry.')
        tag = item['tag']
        if not isinstance(tag, str) or not LOCALE_TAG_RE.fullmatch(tag) or tag in entries:
            raise LocaleError('Invalid or duplicate registered locale.')
        _locale_text(item['name'], 80, multiline=False)
        if not isinstance(item['plural_rule'], str) or item['plural_rule'] not in PLURAL_RULES:
            raise LocaleError('Unsupported locale plural rule.')
        if not isinstance(item['aliases'], list) or len(item['aliases']) > 100:
            raise LocaleError('Invalid locale aliases.')
        entries[tag] = dict(item)
    if 'en' not in entries or entries['en']['plural_rule'] != 'one-other':
        raise LocaleError('Registry must include English with the one-other rule.')
    for tag, item in entries.items():
        for alias in [tag] + item['aliases']:
            normalized = _normalize_locale(alias)
            if normalized is None or (normalized in aliases and aliases[normalized] != tag):
                raise LocaleError('Invalid or conflicting locale alias.')
            aliases[normalized] = tag
    return {'entries': entries, 'aliases': aliases}


def resolve_locale_tag(value: str, registry: dict) -> Optional[str]:
    tag = _normalize_locale(value)
    if tag is None or tag == 'zh':
        return None
    parts = tag.split('-')
    # An explicit script must win over any region alias.
    if len(parts) >= 2 and len(parts[1]) == 4:
        return registry['entries'].get('-'.join(parts[:2]), {}).get('tag')
    if tag in registry['aliases']:
        return registry['aliases'][tag]
    return parts[0] if parts[0] in registry['entries'] else None


def select_locale(requested: Optional[str], environ: dict, registry: dict):
    if requested is not None:
        tag = resolve_locale_tag(requested, registry)
        if tag is None:
            raise LocaleError('Unsupported --locale. Use --list-locales to see supported tags.')
        return tag, []
    override = environ.get('KOBO_MIGRATE_LOCALE', '').strip()
    if override:
        tag = resolve_locale_tag(override, registry)
        return (tag, []) if tag else ('en', ['Unsupported environment locale; using English.'])
    preferences = next((environ.get(key, '').strip() for key in
                        ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG') if environ.get(key, '').strip()), '')
    for preference in preferences.split(':'):
        tag = resolve_locale_tag(preference, registry)
        if tag:
            return tag, []
    notices = ['Chinese script is unspecified; use --locale zh-Hant or zh-Hans. Using English.'] if any(
        _normalize_locale(p) == 'zh' for p in preferences.split(':')) else []
    return 'en', notices


def _template_fields(template: str) -> set:
    _locale_text(template)
    fields = set()
    try:
        for literal, field, spec, conversion in string.Formatter().parse(template):
            if field is None:
                continue
            if not re.fullmatch(r'[a-z][a-z0-9_]*', field) or conversion is not None or spec not in {'', 'd', ',d', '.1f'}:
                raise LocaleError('Unsafe or unsupported locale placeholder.')
            fields.add(field)
    except ValueError as exc:
        if isinstance(exc, LocaleError):
            raise
        raise LocaleError('Malformed locale format string.') from None
    return fields


def load_locale_catalog(root: Path, tag: str, registry: dict, english: Optional[dict] = None, complete=False) -> dict:
    if tag not in registry['entries']:
        raise LocaleError('Unregistered locale catalog.')
    data = _locale_json(root, tag + '.json')
    if set(data) != {'schema_version', 'locale', 'messages'} or data['locale'] != tag or not isinstance(data['messages'], dict):
        raise LocaleError('Invalid locale catalog schema or tag.')
    messages = data['messages']
    if not messages or len(messages) > 2000:
        raise LocaleError('Locale catalog must contain a bounded message map.')
    if tag == 'en' and not (LOCALE_REQUIRED_IDS | UI_MESSAGE_FIELDS.keys()) <= set(messages):
        raise LocaleError('Canonical English catalog is missing required messages.')
    if english is not None and (set(messages) - set(english) or (complete and set(messages) != set(english))):
        raise LocaleError('Locale catalog message coverage does not match English.')
    forms = PLURAL_RULES[registry['entries'][tag]['plural_rule']]
    for key, value in messages.items():
        if not MESSAGE_ID_RE.fullmatch(key):
            raise LocaleError('Invalid locale message identifier.')
        if isinstance(value, str):
            fields = _template_fields(value)
        elif isinstance(value, dict) and set(value) == forms:
            variants = [_template_fields(text) for text in value.values()]
            if 'count' not in variants[0] or any(fields != variants[0] for fields in variants):
                raise LocaleError('Plural variants must use identical placeholders including count.')
            fields = variants[0]
        else:
            raise LocaleError('Invalid locale message or plural variants.')
        if tag == 'en' and key in LOCALE_REQUIRED_IDS:
            plural = key == 'preview.file_count'
            if fields != ({'count'} if plural else set()) or isinstance(value, dict) != plural:
                raise LocaleError('Canonical message placeholders do not match the startup contract.')
        if tag == 'en' and key in UI_MESSAGE_FIELDS:
            if not isinstance(value, str) or fields != UI_MESSAGE_FIELDS[key]:
                raise LocaleError('Canonical message placeholders do not match the UI contract.')
        if english is not None:
            original = english[key]
            reference = original if isinstance(original, str) else original['other']
            if isinstance(value, str) != isinstance(original, str) or fields != _template_fields(reference):
                raise LocaleError('Locale placeholders or message types do not match English.')
    return messages


@dataclass(frozen=True)
class LocaleBundle:
    tag: str
    registry: dict
    english: dict
    messages: dict
    notices: tuple

    def render(self, key: str, **values) -> str:
        if key not in self.english:
            raise LocaleError('Unknown locale message identifier.')
        original = self.english[key]
        translated = self.messages.get(key, original)
        if isinstance(original, dict):
            count = values.get('count')
            if type(count) is not int or count < 0:
                raise LocaleError('Plural messages require a nonnegative integer count.')
            rule = self.registry['entries'][self.tag]['plural_rule'] if key in self.messages else 'one-other'
            form = 'one' if rule == 'one-other' and count == 1 else 'other'
            translated = translated.get(form, original['one' if count == 1 else 'other'])
            original = original['one' if count == 1 else 'other']
        # The English field set is authoritative; mismatched callers are programmer errors.
        if set(values) != _template_fields(original):
            raise LocaleError('Message parameters do not match the English template.')
        try:
            return translated.format(**values)
        except (ValueError, TypeError, KeyError, OverflowError):
            try:
                return original.format(**values)
            except (ValueError, TypeError, KeyError, OverflowError):
                raise LocaleError('Cannot format the English locale message.') from None


def load_locale_bundle(requested=None, environ=None, root=None) -> LocaleBundle:
    root = LOCALE_ROOT if root is None else Path(root)
    registry = load_locale_registry(root)
    english = load_locale_catalog(root, 'en', registry)
    tag, notices = select_locale(requested, os.environ if environ is None else environ, registry)
    messages = english
    if tag != 'en':
        try:
            messages = load_locale_catalog(root, tag, registry, english)
        except LocaleError:
            tag, messages = 'en', english
            notices.append('Requested translation is invalid or unavailable; using English.')
    return LocaleBundle(tag, registry, english, messages, tuple(notices))


def locale_console_write(text: str, stream=None) -> None:
    """Write read-only startup output without triggering Unicode failures."""
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, 'encoding', None) or 'utf-8'
    stream.write(text.encode(encoding, errors='backslashreplace').decode(encoding))
    stream.flush()


class LocaleArgumentParser(argparse.ArgumentParser):
    """Use public parser methods to handle non-UTF-8 help/error streams safely."""
    def print_help(self, file=None):
        locale_console_write(self.format_help(), sys.stdout if file is None else file)

    def print_usage(self, file=None):
        locale_console_write(self.format_usage(), sys.stdout if file is None else file)

    def exit(self, status=0, message=None):
        if message:
            locale_console_write(message, sys.stderr)
        raise SystemExit(status)


def preview_locale_ui(bundle: LocaleBundle) -> None:
    lines = [bundle.render('preview.title'), bundle.render('preview.notice'), '']
    for number, token in enumerate(('full', 'koreader', 'library', 'audit'), 1):
        lines.append(f"  {number}) {token.upper()}: {bundle.render('mode.' + token)}")
    lines += ['', bundle.render('preview.default_no'), bundle.render('preview.delete'),
              bundle.render('preview.file_count', count=2)]
    locale_console_write('\n'.join(lines) + '\n')



# This slice migrates shared presentation; remaining owned messages stay English.
UI_MESSAGE_FIELDS = {
    'ui.partial_notice': set(),
    'prompt.retry_yes_no': set(), 'prompt.default': set(), 'prompt.selection': set(),
    'prompt.invalid_selection': set(), 'prompt.confirmation': set(),
    'run.banner': {'version', 'run_id'}, 'run.log_path': {'path'},
    'run.cancelled': {'detail'}, 'run.interrupted': set(),
    'run.stopped': {'kind', 'detail'}, 'error.summary': {'detail'},
    'progress.files': {'label', 'bar', 'percent', 'done', 'total'},
    'progress.start': {'label', 'size'},
    'progress.bytes': {'label', 'percent', 'done', 'total', 'rate', 'elapsed', 'eta'},
    'progress.hash_file': {'name'}, 'progress.hash_archive': set(),
    'progress.verify_target': set(), 'progress.hash_payload': set(),
    'progress.archive_payload': set(), 'progress.copy_payload': set(),
    'progress.verify_members': set(), 'progress.verify_file': {'name'},
    'catalog.heading': set(), 'catalog.empty': set(),
    'cleanup.heading': set(), 'cleanup.empty': set(), 'cleanup.reclaimable': {'size'},
    'cleanup.protected': {'run_id', 'reason'}, 'cleanup.confirm': {'expected'},
    'cleanup.cancelled': set(), 'cleanup.deleted': {'run_id'},
    'difference.title': set(), 'difference.retain': set(),
    'difference.section': {'label', 'count', 'size'}, 'difference.paths': {'path'},
    'difference.new': set(), 'difference.overwrite': set(), 'difference.identical': set(),
    'difference.keep_target': set(), 'difference.metadata_skipped': set(), 'difference.target_only': set(),
    'confirm.continue': set(), 'confirm.saved_source': set(), 'confirm.restore_target': set(),
    'confirm.compatibility': set(), 'confirm.migration': set(),
    'confirm.books': set(), 'confirm.fonts': set(), 'confirm.device': {'role', 'model'},
    'prompt.source': set(), 'prompt.target': set(),
    'prompt.restore_target': {'model'}, 'device.waiting': {'role'},
    'device.connect_one': set(), 'device.detected': {'path'},
    'migration.success': {'path'}, 'migration.done': set(),
    'menu.mode': set(),
    'menu.full': set(),
    'menu.koreader': set(),
    'menu.library': set(),
    'menu.audit': set(),
    'menu.identity': set(),
    'menu.identity_preserve': set(),
    'menu.identity_unavailable': set(),
    'menu.identity_new': set(),
    'menu.identity_clone': set(),
    'menu.identity_retry': set(),
    'menu.conflict': set(),
    'menu.overwrite': set(),
    'menu.keep_target': set(),
    'inspection.title': {'role'},
    'inspection.mount': {'path'},
    'inspection.model': {'model'},
    'inspection.version': {'version'},
    'inspection.files': {'count'},
    'inspection.size': {'size'},
    'inspection.identity': {'present'},
    'inspection.serial': {'hint'},
    'value.yes': set(),
    'value.no': set(),
    'value.unknown': set(),
    'prompt.physical_model': {'role', 'suffix'},
    'device.model_retry': set(),
    'device.log_hint': set(),
    'device.model_mismatch': {'hint', 'model'},
    'device.model_confirmed': {'model', 'role'},
    'space.backup': {'free', 'label', 'need'},
    'space.target': {'effective', 'free', 'need'},
    'space.library': {'free', 'need'},
    'space.source_backup': set(),
    'space.target_backup': set(),
    'space.pre_restore': set(),
    'migration.options': {'books', 'conflict', 'fonts', 'mode'},
}
CURRENT_UI = ContextVar('kobo_migration_ui', default=None)


@lru_cache(maxsize=8)
def _english_output_bundle(root: Path):
    return load_locale_bundle('en', {}, root)


def current_ui():
    ui = CURRENT_UI.get()
    return ui if ui is not None else UIOutput(_english_output_bundle(LOCALE_ROOT), preflight=False)


class UIMessage(str):
    """A stable message ID with English string compatibility for existing helpers."""
    def __new__(cls, key, **values):
        ui = current_ui()
        english, _ = ui.render(key, values)
        result = str.__new__(cls, english)
        result.key, result.values = key, dict(values)
        return result


def message(key, **values):
    return UIMessage(key, **values)


class UIOutput:
    """Render console and English diagnostics separately, before writing either."""
    def __init__(self, bundle, log=None, stdout=None, stderr=None, preflight=True):
        self.bundle = bundle
        self.english = LocaleBundle('en', bundle.registry, bundle.english, bundle.english, ())
        self.log = log
        self.stdout = sys.stdout if stdout is None else stdout
        self.stderr = sys.stderr if stderr is None else stderr
        # Format every integrated message before creating runs or accessing devices.
        if preflight:
            for key, fields in UI_MESSAGE_FIELDS.items():
                self.render(key, {field: 0 for field in fields})

    def text(self, value, english=False):
        if isinstance(value, UIMessage):
            pair = self.render(value.key, value.values)
            return pair[0 if english else 1]
        return str(value)

    def render(self, key, values):
        english_values = {key: self.text(value, True) if isinstance(value, UIMessage) else value
                          for key, value in values.items()}
        console_values = {key: self.text(value) if isinstance(value, UIMessage) else value
                          for key, value in values.items()}
        english = self.english.render(key, **english_values)
        console = self.bundle.render(key, **console_values)
        return english, console

    def deliver(self, english, console, *, channel='stdout', severity='info', prefix='', end='\n'):
        if channel not in {'stdout', 'stderr'} or severity not in {'info', 'warning', 'error'}:
            raise ValueError('Invalid UI event channel or severity.')
        stream = self.stderr if channel == 'stderr' else self.stdout
        locale_console_write(prefix + console + end, stream)
        if self.log is not None:
            self.log.write(prefix + english + end)
            self.log.flush()

    def write(self, value, **presentation):
        self.deliver(self.text(value, True), self.text(value), **presentation)

    def emit(self, key, *, channel='stdout', severity='info', prefix='', end='\n', **values):
        english, console = self.render(key, values)
        self.deliver(english, console, channel=channel, severity=severity, prefix=prefix, end=end)

    def read(self, prompt, suffix=''):
        self.write(prompt, end=suffix)
        try:
            # Never log user responses or patch builtins.input/print.
            return input()
        finally:
            if self.log is not None:
                self.log.write('\n')
                self.log.flush()


@contextmanager
def ui_session(bundle, log=None, stdout=None, stderr=None):
    ui = UIOutput(bundle, log, stdout, stderr)
    token = CURRENT_UI.set(ui)
    try:
        yield ui
    finally:
        CURRENT_UI.reset(token)


def ui_emit(key, **values):
    current_ui().emit(key, **values)


def ui_input(prompt):
    return current_ui().read(prompt)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def human_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    n = float(value)
    for unit in units:
        if n < 1024.0 or unit == units[-1]:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{value} B"


def prompt_yes_no(question: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        ans = current_ui().read(question, suffix=suffix).strip().lower()
        if not ans:
            return default
        if ans in {"y", "yes"}:
            return True
        if ans in {"n", "no"}:
            return False
        ui_emit('prompt.retry_yes_no')


def choose(question: str, options: List[Tuple[str, str]], default: Optional[str] = None) -> str:
    current_ui().write(question)
    for key, label in options:
        ui = current_ui()
        marker = ' ' + ui.text(message('prompt.default')) if key == default else ''
        log_marker = ' ' + ui.text(message('prompt.default'), True) if key == default else ''
        # Numeric choices and model/path values are never translated.
        ui.deliver(f'  {key}) {ui.text(label, True)}{log_marker}',
                   f'  {key}) {ui.text(label)}{marker}')
    while True:
        ans = ui_input(message('prompt.selection')).strip()
        if not ans and default is not None:
            return default
        if any(ans == key for key, _ in options):
            return ans
        ui_emit('prompt.invalid_selection')


def require_macos_tools() -> None:
    if sys.platform != "darwin":
        raise MigrationError("This migration tool is designed for macOS.")
    for cmd in ("ditto", "diskutil", "sync"):
        if shutil.which(cmd) is None:
            raise MigrationError(f"Required macOS command not found: {cmd}")


def kobo_mounts() -> List[Path]:
    mounts: List[Path] = []
    if not VOLUME_ROOT.exists():
        return mounts
    for path in sorted(VOLUME_ROOT.iterdir()):
        if path.is_symlink() or not path.is_dir():
            continue
        if (path / ".kobo").is_dir() and not (path / ".kobo").is_symlink():
            mounts.append(path)
    return mounts


def wait_for_single_kobo(role: str) -> Path:
    print()
    ui_emit('device.waiting', role=role)
    ui_emit('device.connect_one')
    while True:
        mounts = kobo_mounts()
        if len(mounts) > 1:
            raise MigrationError(
                "More than one Kobo is mounted. Disconnect all but the requested device."
            )
        if len(mounts) == 1:
            ui_emit('device.detected', path=mounts[0])
            return mounts[0]
        time.sleep(2)


def run_with_spinner(cmd: List[str], label: str, env: Optional[dict] = None) -> None:
    with tempfile.TemporaryFile(mode='w+t') as stdout, tempfile.TemporaryFile(mode='w+t') as stderr:
        proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, text=True, env=env)
        started = last = time.monotonic()
        log_status(f'{label}: started')
        try:
            while proc.poll() is None:
                now = time.monotonic()
                if now - last >= 5:
                    log_status(f'{label}: still running, elapsed {now - started:.0f}s')
                    last = now
                time.sleep(0.12)
        except BaseException:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise
        log_status(f'{label}: finished after {time.monotonic() - started:.1f}s')
        if proc.returncode != 0:
            stderr.seek(0)
            stdout.seek(0)
            detail = (stderr.read() or stdout.read()).strip()
            raise MigrationError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{detail}")


def run_checked(cmd: List[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MigrationError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    return proc.stdout.strip()


def safe_eject(mount: Path) -> None:
    print("Flushing filesystem writes...")
    run_checked(["sync"])
    time.sleep(2)
    print(f"Safely ejecting {mount} ...")
    out = run_checked(["diskutil", "eject", str(mount)])
    if out:
        print(out)
    for _ in range(20):
        if not mount.exists():
            break
        time.sleep(0.5)
    print("Ejected successfully.")


def canonical_model(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    name = " ".join(name.strip().split())
    low = name.lower()
    if low in {"clara 2e", "kobo clara 2e"}:
        return MODEL_CLARA
    if low in {"libra 2", "kobo libra 2"}:
        return MODEL_LIBRA
    return name if low.startswith("kobo ") else "Kobo " + name


def tail_text(path: Path, max_bytes: int = 2_000_000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        data = f.read()
    return data.decode("utf-8", errors="replace")


def detect_model(mount: Path) -> Optional[str]:
    kr = mount / ".adds" / "koreader"

    # A copied KOReader log may describe a different device. This is a hint,
    # never hardware verification; the operator must confirm each role.
    for candidate in (kr / "crash.log", kr / "version.log"):
        text = tail_text(candidate)
        matches = DETECTED_KOBO_RE.findall(text)
        if matches:
            return canonical_model(matches[-1])

        # Best-effort fallback for version logs containing a friendly model name.
        for known in (MODEL_CLARA, MODEL_LIBRA):
            if known.lower() in text.lower():
                return known
    return None


def read_koreader_version(mount: Path) -> Optional[str]:
    git_rev = mount / ".adds" / "koreader" / "git-rev"
    if git_rev.is_file():
        value = git_rev.read_text(encoding="utf-8", errors="replace").strip()
        return value or None

    crash = tail_text(mount / ".adds" / "koreader" / "crash.log")
    matches = re.findall(r"\[\*\]\s+Version:\s+([^\r\n]+)", crash)
    return matches[-1].strip() if matches else None


def device_fingerprint(mount: Path) -> Tuple[Optional[str], Optional[str]]:
    version_file = mount / ".kobo" / "version"
    if not version_file.is_file():
        return None, None
    if mount.is_symlink() or (mount / '.kobo').is_symlink() or version_file.is_symlink():
        raise MigrationError('Device identity paths must not be symlinks.')
    if version_file.stat().st_size > 65536:
        raise MigrationError('Device identity file is unexpectedly large.')
    raw = version_file.read_bytes()
    if not raw.strip():
        return None, None
    fp = hashlib.sha256(raw).hexdigest()

    text = raw.decode("utf-8", errors="replace").strip()
    first = text.split(",", 1)[0].strip() if text else ""
    if first:
        hint = ("*" * max(0, len(first) - 4)) + first[-4:]
    else:
        hint = None
    return fp, hint


def read_device_id(settings_file: Path) -> Optional[str]:
    if not settings_file.is_file():
        return None
    text = settings_file.read_text(encoding="utf-8", errors="replace")
    match = DEVICE_ID_RE.search(text)
    if not match:
        return None
    value = match.group(2)
    return value if value else None


def set_device_id(settings_file: Path, new_id: str) -> None:
    if not settings_file.is_file():
        raise MigrationError(f"Cannot set device_id; file not found: {settings_file}")

    text = settings_file.read_text(encoding="utf-8", errors="strict")
    match = DEVICE_ID_RE.search(text)

    if match:
        replacement = match.group(1) + f'"{new_id}"'
        updated = text[:match.start()] + replacement + text[match.end():]
    else:
        # KOReader's settings file is a Lua table. If device_id is absent,
        # add it immediately after "return {".
        marker = re.search(r"return\s*\{", text)
        if not marker:
            raise MigrationError(
                "settings.reader.lua does not look like a KOReader Lua settings table."
            )
        insert_at = marker.end()
        updated = (
            text[:insert_at]
            + f'\n    ["device_id"] = "{new_id}",'
            + text[insert_at:]
        )

    tmp = settings_file.with_suffix(settings_file.suffix + ".tmp-migration")
    tmp.write_text(updated, encoding="utf-8")
    os.replace(tmp, settings_file)


def should_exclude_rel(rel: str) -> bool:
    rel = rel.replace("\\", "/").lstrip("/")
    if rel in VERIFY_EXCLUDES:
        return True
    parts = rel.split("/")
    if any(part == ".DS_Store" or part.startswith(APPLEDOUBLE_PREFIX) for part in parts):
        return True
    return False


def walk_tree_stats(root: Path) -> Tuple[int, int]:
    count = 0
    total = 0
    if not root.exists():
        return 0, 0
    for base, _, files in os.walk(root):
        for name in files:
            p = Path(base) / name
            try:
                st = p.stat()
            except FileNotFoundError:
                continue
            count += 1
            total += st.st_size
    return count, total


def basic_plugin_audit(koreader: Path) -> Tuple[List[str], List[str]]:
    plugins_dir = koreader / "plugins"
    plugins: List[str] = []
    warnings: List[str] = []
    if not plugins_dir.is_dir():
        warnings.append("plugins/ directory is missing")
        return plugins, warnings

    for p in sorted(plugins_dir.glob("*.koplugin")):
        if not p.is_dir():
            continue
        plugins.append(p.name)
        # Structural audit only; not a dependency/compatibility guarantee.
        if not (p / "main.lua").is_file():
            warnings.append(f"{p.name}: main.lua missing")
        if not (p / "_meta.lua").is_file():
            warnings.append(f"{p.name}: _meta.lua missing")
    return plugins, warnings


def inspect_device(mount: Path) -> DeviceInfo:
    koreader = mount / ".adds" / "koreader"
    count, total = walk_tree_stats(koreader)
    fingerprint, serial_hint = device_fingerprint(mount)
    settings = koreader / "settings.reader.lua"
    ai_cfg = koreader / "plugins" / "assistant.koplugin" / "configuration.lua"
    return DeviceInfo(
        mount=str(mount),
        detected_model=detect_model(mount),
        koreader_version=read_koreader_version(mount),
        fingerprint_sha256=fingerprint,
        serial_hint=serial_hint,
        device_id_present=read_device_id(settings) is not None,
        ai_assistant_config=ai_cfg.is_file(),
        file_count=count,
        total_bytes=total,
    )


def display_device_info(info: DeviceInfo, label: str) -> None:
    print()
    ui_emit('inspection.title', role=label)
    print('-' * 60)
    ui_emit('inspection.mount', path=info.mount)
    ui_emit('inspection.model', model=info.detected_model or message('value.unknown'))
    ui_emit('inspection.version', version=info.koreader_version or message('value.unknown'))
    ui_emit('inspection.files', count=info.file_count)
    ui_emit('inspection.size', size=human_bytes(info.total_bytes))
    ui_emit('inspection.identity', present=message('value.yes' if info.device_id_present else 'value.no'))
    if info.serial_hint:
        ui_emit('inspection.serial', hint=info.serial_hint)


def confirm_role_model(info: DeviceInfo, requested: Optional[str], role: str) -> str:
    """Confirm the physical model independently from possibly cloned logs."""
    expected = canonical_model(requested)
    if expected is None:
        hint = canonical_model(info.detected_model)
        suffix = f" [{hint}]" if hint else ""
        while not expected:
            value = ui_input(message('prompt.physical_model', role=role, suffix=suffix)).strip()
            expected = canonical_model(value) if value else hint
            if not expected:
                ui_emit('device.model_retry')
    if len(expected) > 80 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()+-]*", expected):
        raise MigrationError('Model names must be short plain ASCII labels, e.g. Kobo Clara BW.')
    verify_expected_model(info, expected, role)
    return expected


def verify_expected_model(info: DeviceInfo, expected: str, role: str) -> None:
    detected = canonical_model(info.detected_model)
    ui_emit('device.log_hint')
    if detected and detected.casefold() != expected.casefold():
        ui_emit('device.model_mismatch', hint=detected, model=expected, severity='warning')
    if not prompt_yes_no(message('confirm.device', role=role, model=expected)):
        raise MigrationCancelled('Migration cancelled during device confirmation. No target files were modified.')
    ui_emit('device.model_confirmed', role=role, model=expected)


def require_device_fingerprint(info: DeviceInfo) -> None:
    if not info.fingerprint_sha256:
        raise MigrationError('Cannot establish device identity from .kobo/version; refusing migration.')


def ensure_source_structure(mount: Path) -> None:
    kr = mount / ".adds" / "koreader"
    required = [
        kr,
        kr / "reader.lua",
        kr / "frontend",
        kr / "plugins",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise MigrationError(
            "Source KOReader failed pre-flight; missing:\n  " + "\n  ".join(missing)
        )


def ensure_backup_space(backup_dir: Path, required_bytes: int, label: str) -> None:
    free = shutil.disk_usage(backup_dir).free
    # Conservative because ZIP may not compress much.
    need = int(required_bytes * 1.10) + 100 * 1024 * 1024
    ui_emit('space.backup', label=label, free=human_bytes(free), need=human_bytes(need))
    if free < need:
        raise MigrationError(
            f"Not enough free space in {backup_dir} for a safe {label} backup."
        )


def ensure_target_space(target_mount: Path, source_size: int, existing_target_size: int) -> None:
    free = shutil.disk_usage(target_mount).free
    # Existing target will be removed before restore, so its size becomes reusable.
    effective = free + existing_target_size
    need = int(source_size * 1.10) + 50 * 1024 * 1024
    ui_emit('space.target', free=human_bytes(free), effective=human_bytes(effective), need=human_bytes(need))
    if effective < need:
        raise MigrationError("Target Kobo does not have enough free space.")


def log_status(message: str) -> None:
    current_ui().write(message, prefix=f"[{datetime.now().strftime('%H:%M:%S')}] ")


class ByteProgress:
    def __init__(self, label: str, total: int):
        self.label, self.total, self.done = label, total, 0
        self.started = self.last = time.monotonic()
        log_status(message('progress.start', label=label, size=human_bytes(total)))

    def update(self, count: int, final: bool = False) -> None:
        self.done += count
        now = time.monotonic()
        if not final and now - self.last < 2:
            return
        elapsed = max(now - self.started, 0.001)
        rate = self.done / elapsed
        percent = self.done / self.total * 100 if self.total else 100
        remaining = max(self.total - self.done, 0) / rate if rate > 0 else None
        eta = f'{remaining:.0f}s' if remaining is not None else 'unknown'
        log_status(message('progress.bytes', label=self.label, percent=f'{percent:.1f}',
                           done=human_bytes(self.done), total=human_bytes(self.total),
                           rate=human_bytes(int(rate)), elapsed=f'{elapsed:.0f}', eta=eta))
        self.last = now


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    size = path.stat().st_size
    progress = ByteProgress(message('progress.hash_file', name=path.name), size) if size >= 32 * 1024 * 1024 else None
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
            if progress:
                progress.update(len(chunk))
    if progress:
        progress.update(0, final=True)
    return h.hexdigest()


def copy_with_progress(src, dst, label: str, size: int) -> None:
    progress = ByteProgress(label, size) if size >= 32 * 1024 * 1024 else None
    for chunk in iter(lambda: src.read(1024 * 1024), b''):
        dst.write(chunk)
        if progress:
            progress.update(len(chunk))
    if progress:
        progress.update(0, final=True)


def print_progress(label: str, done: int, total: int) -> None:
    width = 28
    if total <= 0:
        pct = 1.0
    else:
        pct = min(1.0, done / total)
    filled = int(width * pct)
    bar = "#" * filled + "-" * (width - filled)
    ui_emit('progress.files', label=label, bar=bar, percent=f'{pct * 100:5.1f}',
            done=done, total=total, prefix='\r', end='\n' if done >= total else '')


def validate_tree_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise MigrationError(f'Symlink tree root is not allowed: {root}')
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            if (Path(base) / name).is_symlink():
                raise MigrationError(f'Symlink in KOReader tree: {Path(base) / name}')


def validate_koreader_zip(archive: Path) -> None:
    seen = set()
    paths = []
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename
            parts = name.rstrip('/').split('/')
            if (not name or name.startswith('/') or '\\' in name
                    or parts[0] not in {'koreader', '__MACOSX'}
                    or any(part in {'', '.', '..'} for part in parts)
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise MigrationError(f'Unsafe KOReader ZIP member: {name}')
            if name in seen:
                raise MigrationError(f'Duplicate KOReader ZIP member: {name}')
            seen.add(name)
            if not info.is_dir():
                paths.append(name)
    assert_unique_paths(paths)


def archive_entries(zf: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    entries: List[zipfile.ZipInfo] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        if not name.startswith("koreader/"):
            continue
        rel = name[len("koreader/"):]
        if not rel or should_exclude_rel(rel):
            continue
        entries.append(info)
    return entries


def build_manifest(
    zip_path: Path,
    manifest_path: Path,
    source_info: DeviceInfo,
    plugins: List[str],
    plugin_warnings: List[str],
    strict_source: bool = True,
) -> dict:
    validate_koreader_zip(zip_path)
    print("Building SHA-256 manifest from archive...")
    files: Dict[str, dict] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        if strict_source and "koreader/reader.lua" not in names:
            raise MigrationError("Archive is missing koreader/reader.lua.")

        entries = archive_entries(zf)
        seen = set()
        for idx, info in enumerate(entries, 1):
            rel = info.filename.replace("\\", "/")[len("koreader/"):]
            if rel in seen:
                raise MigrationError(f"Duplicate path in ZIP: {rel}")
            seen.add(rel)

            h = hashlib.sha256()
            try:
                with zf.open(info, "r") as src:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        h.update(chunk)
            except Exception as exc:
                raise MigrationError(f"Failed reading ZIP member {rel}: {exc}") from exc

            files[rel] = {
                "sha256": h.hexdigest(),
                "size": info.file_size,
            }
            print_progress(message('progress.hash_archive'), idx, len(entries))

    manifest = {
        "strict_source": strict_source,
        "schema_version": 1,
        "tool": f"KOReader Kobo Migration Tool {VERSION}",
        "created_at": iso_now(),
        "source": {
            "detected_model": source_info.detected_model,
            "koreader_version": source_info.koreader_version,
            "device_fingerprint_sha256": source_info.fingerprint_sha256,
            "serial_hint": source_info.serial_hint,
            "device_id_present": source_info.device_id_present,
            "ai_assistant_config": source_info.ai_assistant_config,
        },
        "archive": {
            "filename": zip_path.name,
            "sha256": sha256_file(zip_path),
            "size": zip_path.stat().st_size,
        },
        "plugins": plugins,
        "plugin_structural_warnings": plugin_warnings,
        "excluded_from_full_hash_verification": sorted(VERIFY_EXCLUDES),
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def create_archive(
    source_koreader: Path,
    zip_path: Path,
    manifest_path: Path,
    source_info: DeviceInfo,
    plugins: List[str],
    plugin_warnings: List[str],
    strict_source: bool = True,
) -> dict:
    if zip_path.exists() or manifest_path.exists():
        raise MigrationError(f"Refusing to overwrite an existing backup: {zip_path}")
    validate_tree_symlinks(source_koreader)

    env = os.environ.copy()
    env["COPYFILE_DISABLE"] = "1"
    run_with_spinner(
        ["ditto", "-c", "-k", "--keepParent", str(source_koreader), str(zip_path)],
        "Creating ZIP",
        env=env,
    )

    try:
        return build_manifest(
            zip_path,
            manifest_path,
            source_info,
            plugins,
            plugin_warnings,
            strict_source=strict_source,
        )
    except Exception:
        # Do not leave a backup that failed validation looking like a good backup.
        try:
            manifest_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def remove_tree(root: Path) -> None:
    """Remove a tree while tolerating descendants already removed by the filesystem."""
    root_path = os.path.abspath(root)
    def handle_error(function, path, exc_info):
        error = exc_info[1]
        # Match Python 3.13 behavior on older supported interpreters. FAT/macOS
        # may remove an AppleDouble companion while its listed entry remains.
        if isinstance(error, FileNotFoundError) and os.path.abspath(path) != root_path:
            return
        raise error.with_traceback(exc_info[2])
    shutil.rmtree(root, onerror=handle_error)


def remove_macos_metadata(root: Path) -> int:
    removed = 0
    if not root.exists():
        return removed
    for base, dirs, files in os.walk(root, topdown=False):
        base_p = Path(base)
        for name in files:
            if name == ".DS_Store" or name.startswith("._"):
                try:
                    (base_p / name).unlink()
                    removed += 1
                except FileNotFoundError:
                    pass
        for name in dirs:
            if name.startswith("._"):
                try:
                    remove_tree(base_p / name)
                    removed += 1
                except FileNotFoundError:
                    pass
    return removed


def remove_stale_caches(koreader: Path) -> None:
    for rel in VERIFY_EXCLUDES:
        p = koreader / rel
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def verify_restored_tree(target_koreader: Path, manifest: dict) -> None:
    required = [
        target_koreader / "reader.lua",
        target_koreader / "frontend",
        target_koreader / "plugins",
    ]
    for p in (required if manifest.get("strict_source", True) else []):
        if not p.exists():
            raise MigrationError(f"Restore verification failed; missing: {p}")

    files = manifest["files"]
    items = list(files.items())
    print(f"Full target verification: {len(items):,} files")

    for idx, (rel, meta) in enumerate(items, 1):
        p = target_koreader / rel
        if not p.is_file():
            raise MigrationError(f"Restore verification failed; file missing: {rel}")
        if p.stat().st_size != meta["size"]:
            raise MigrationError(f"Restore verification failed; size mismatch: {rel}")
        actual = sha256_file(p)
        if actual != meta["sha256"]:
            raise MigrationError(f"Restore verification failed; checksum mismatch: {rel}")
        print_progress(message('progress.verify_target'), idx, len(items))

    print("Full SHA-256 target verification: OK")


def restore_zip(zip_path: Path, target_adds: Path) -> None:
    validate_koreader_zip(zip_path)
    env = os.environ.copy()
    env["COPYFILE_DISABLE"] = "1"
    run_with_spinner(
        ["ditto", "-x", "-k", str(zip_path), str(target_adds)],
        "Restoring ZIP",
        env=env,
    )


def rollback_target(
    target_koreader: Path,
    target_adds: Path,
    target_backup_zip: Optional[Path],
    target_backup_manifest: Optional[dict],
) -> None:
    print()
    print("!!! Migration failed after target modification.")
    print("Starting automatic rollback...")

    if target_backup_zip is not None:
        validate_koreader_zip(target_backup_zip)
        if target_backup_manifest and sha256_file(target_backup_zip) != target_backup_manifest['archive']['sha256']:
            raise MigrationError('Rollback archive checksum changed.')
    if target_koreader.exists():
        remove_tree(target_koreader)
    if target_backup_zip is None:
        print('Target had no original KOReader tree; incomplete restore was removed.')
        return
    restore_zip(target_backup_zip, target_adds)
    if target_backup_manifest is not None:
        verify_restored_tree(target_koreader, target_backup_manifest)
    print("Automatic rollback: SUCCESS")
    print("The target has been restored to its pre-migration KOReader backup.")


def choose_identity_mode(target_device_id: Optional[str]) -> str:
    default = "1" if target_device_id else "2"
    options = []
    if target_device_id:
        options.append(("1", message('menu.identity_preserve')))
    else:
        options.append(("1", message('menu.identity_unavailable')))
    options += [
        ("2", message('menu.identity_new')),
        ("3", message('menu.identity_clone')),
    ]
    while True:
        choice = choose(message('menu.identity'), options, default=default)
        if choice == "1" and not target_device_id:
            ui_emit('menu.identity_retry', severity='warning')
            continue
        return {"1": "preserve", "2": "new", "3": "clone"}[choice]


def apply_identity_mode(target_koreader: Path, mode: str, target_device_id: Optional[str]) -> Optional[str]:
    settings = target_koreader / "settings.reader.lua"

    if mode == "clone":
        print("KOReader device_id: cloned from source.")
        return read_device_id(settings)

    if mode == "preserve":
        if not target_device_id:
            raise MigrationError("Target device_id was not available to preserve.")
        new_id = target_device_id
        label = "preserved target device_id"
    elif mode == "new":
        new_id = uuid.uuid4().hex.upper()
        label = "new device_id"
    else:
        raise MigrationError(f"Unknown identity mode: {mode}")

    set_device_id(settings, new_id)
    check = read_device_id(settings)
    if check != new_id:
        raise MigrationError("Failed to verify updated device_id.")
    print(f"KOReader identity: {label} applied successfully.")
    return new_id



# Electronic reading formats; generic image folders/ZIPs are opt-in.
EBOOK_EXTENSIONS = {
    '.epub', '.kepub', '.pdf', '.cbz', '.cbr', '.cb7', '.cbt', '.cba',
    '.mobi', '.azw', '.azw3', '.azw4', '.prc', '.pdb', '.fb2', '.fb3',
    '.djvu', '.djv', '.txt', '.rtf', '.doc', '.docx', '.html', '.htm',
    '.xhtml', '.md', '.chm', '.odt', '.tif', '.tiff', '.xps', '.oxps',
}
METADATA_DIRS = ('docsettings', 'hashdocsettings', 'history')


def checked_path(mount: Path, rel: str, allow_metadata: bool = False) -> Path:
    parts = rel.split('/')
    allowed_hidden = allow_metadata and len(parts) >= 2 and parts[:2] == ['.adds', 'koreader']
    if not rel or any(part in {'', '.', '..'} for part in parts):
        raise MigrationError(f'Unsafe relative path: {rel}')
    if any(part.startswith('.') for part in parts) and not allowed_hidden:
        raise MigrationError(f'Hidden/system path is not allowed: {rel}')
    current = mount
    if mount.is_symlink() or not mount.is_dir():
        raise MigrationError(f'Invalid device root: {mount}')
    for idx, part in enumerate(parts):
        current = current / part
        if current.is_symlink():
            raise MigrationError(f'Symlink is not allowed: {rel}')
        if current.exists() and idx < len(parts) - 1 and not current.is_dir():
            raise MigrationError(f'Parent is not a directory: {rel}')
    return current


def payload_path(mount: Path, rel: str) -> Path:
    central = any(rel.startswith(f'.adds/koreader/{name}/') for name in METADATA_DIRS)
    path = checked_path(mount, rel, allow_metadata=central)
    if path.exists() and not path.is_file():
        raise MigrationError(f'Payload destination is not a regular file: {rel}')
    return path


def path_key(rel: str) -> str:
    return unicodedata.normalize('NFC', rel).casefold()


def assert_unique_paths(paths) -> None:
    seen = {}
    spellings = {}
    for rel in paths:
        parts = rel.split('/')
        for idx in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:idx])
            key = path_key(prefix)
            if key in spellings and spellings[key] != prefix:
                raise MigrationError(f'Case/Unicode path collision: {spellings[key]} and {prefix}')
            spellings[key] = prefix
        seen[path_key(rel)] = rel
    for rel in paths:
        parts = rel.split('/')
        for idx in range(1, len(parts)):
            key = path_key('/'.join(parts[:idx]))
            if key in seen:
                raise MigrationError(f'File/directory path collision: {seen[key]} and {rel}')


def scan_payload(mount: Path, include_books: bool, include_fonts: bool,
                 include_metadata: bool = True, include_dirs=None,
                 exclude_dirs=None, extra_extensions=None, missing_roots_ok: bool = False, include_central_metadata: bool = True) -> Tuple[dict, dict]:
    files = {}
    report = {'books': [], 'sidecars': [], 'central_metadata': [], 'fonts': [],
              'unrecognized': [], 'skipped_symlinks': [], 'warnings': []}
    extensions = set(EBOOK_EXTENSIONS)
    for ext in extra_extensions or []:
        extensions.add('.' + ext.lower().lstrip('.'))
    excluded = []
    for rel in exclude_dirs or []:
        checked_path(mount, rel)
        excluded.append(rel.rstrip('/'))

    def excluded_path(rel):
        return any(rel == prefix or rel.startswith(prefix + '/') for prefix in excluded)

    def add(path, category):
        rel = path.relative_to(mount).as_posix()
        if excluded_path(rel) or rel in files:
            return
        if path.is_symlink():
            report['skipped_symlinks'].append(rel)
            return
        payload_path(mount, rel)
        if not path.is_file():
            return
        files[rel] = {'size': path.stat().st_size, 'category': category}
        report[category].append(rel)

    def walk_regular(root, category):
        if root.is_symlink():
            report['skipped_symlinks'].append(root.relative_to(mount).as_posix())
            return
        if not root.exists():
            return
        for base, dirs, names in os.walk(root, followlinks=False):
            for name in list(dirs):
                path = Path(base) / name
                rel = path.relative_to(mount).as_posix()
                if path.is_symlink():
                    report['skipped_symlinks'].append(rel)
                if name.startswith('.') or path.is_symlink() or excluded_path(rel):
                    dirs.remove(name)
            for name in names:
                if not name.startswith('.'):
                    add(Path(base) / name, category)

    if include_books:
        roots = [mount]
        if include_dirs:
            roots = [checked_path(mount, rel) for rel in include_dirs]
            for root in roots:
                if not root.is_dir() and not missing_roots_ok:
                    raise MigrationError(f'Book directory not found: {root}')
            roots = [root for root in roots if root.is_dir()]
        for root in roots:
            for base, dirs, names in os.walk(root, followlinks=False):
                for name in list(dirs):
                    path = Path(base) / name
                    rel = path.relative_to(mount).as_posix()
                    if path.is_symlink():
                        report['skipped_symlinks'].append(rel)
                    if (name.startswith('.') or name.endswith('.sdr') or path.is_symlink()
                            or excluded_path(rel) or rel == 'fonts'):
                        dirs.remove(name)
                for name in sorted(names):
                    path = Path(base) / name
                    rel = path.relative_to(mount).as_posix()
                    if name.startswith('.') or excluded_path(rel):
                        continue
                    if path.is_symlink():
                        report['skipped_symlinks'].append(rel)
                    elif path.suffix.lower() in extensions or name.lower().endswith('.fb2.zip'):
                        add(path, 'books')
                        if include_metadata:
                            walk_regular(path.with_suffix('.sdr'), 'sidecars')
                    elif path.is_file():
                        report['unrecognized'].append(rel)
        if include_metadata and include_central_metadata and not include_dirs and not exclude_dirs:
            for name in METADATA_DIRS:
                root = checked_path(mount, f'.adds/koreader/{name}', allow_metadata=True)
                walk_regular(root, 'central_metadata')
            report['warnings'].append('Central metadata is copied as complete trees; no Lua data is merged.')
    if include_metadata and include_books and (include_dirs or exclude_dirs):
        report['warnings'].append('Scoped scan: central metadata excluded to avoid overwriting data for unrelated books; adjacent sidecars still included.')
    if include_fonts:
        root = checked_path(mount, 'fonts')
        if root.is_dir():
            for base, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith('.') and not (Path(base) / d).is_symlink()]
                for name in names:
                    if not name.startswith('.') and Path(name).suffix.lower() in {'.ttf', '.otf', '.ttc', '.otc'}:
                        add(Path(base) / name, 'fonts')
    assert_unique_paths(files)
    files = dict(sorted(files.items()))
    for category in ('books', 'sidecars', 'central_metadata', 'fonts', 'unrecognized', 'skipped_symlinks'):
        report[category] = sorted(set(report[category]))
    report['file_count'] = len(files)
    report['total_bytes'] = sum(meta['size'] for meta in files.values())
    report['extensions'] = sorted(extensions)
    log_status(f'Scan complete: {len(files):,} payload files found.')
    return files, report


def hash_payload(mount: Path, files: dict) -> dict:
    result = {}
    for idx, (rel, meta) in enumerate(files.items(), 1):
        path = payload_path(mount, rel)
        if path.stat().st_size != meta['size']:
            raise MigrationError(f'Source changed during scan: {rel}')
        result[rel] = {**meta, 'sha256': sha256_file(path)}
        print_progress(message('progress.hash_payload'), idx, len(files))
    return {'files': result}


def create_payload_archive(mount: Path, files: dict, archive: Path) -> dict:
    manifest = hash_payload(mount, files)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for idx, (rel, meta) in enumerate(manifest['files'].items(), 1):
            path = payload_path(mount, rel)
            log_status(f'Archiving payload [{idx}/{len(files)}]: {rel}')
            with path.open('rb') as src, zf.open(rel, 'w', force_zip64=True) as dst:
                copy_with_progress(src, dst, f'Archiving {rel}', meta['size'])
            digest = hashlib.sha256()
            progress = ByteProgress(message('progress.verify_file', name=rel), meta['size']) if meta['size'] >= 32 * 1024 * 1024 else None
            with zf.open(rel) as member:
                for chunk in iter(lambda: member.read(1024 * 1024), b''):
                    digest.update(chunk)
                    if progress:
                        progress.update(len(chunk))
            if progress:
                progress.update(0, final=True)
            if digest.hexdigest() != meta['sha256']:
                raise MigrationError(f'Source changed during archive: {rel}')
            print_progress(message('progress.archive_payload'), idx, len(files))
    manifest.update({'tool_version': VERSION, 'created_at': iso_now(),
                     'archive_sha256': sha256_file(archive)})
    archive.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def plan_payload(target: Path, manifest: dict, conflict: str = 'overwrite') -> dict:
    files = manifest['files']
    assert_unique_paths(files)
    plan = {'copy': {}, 'skip': [], 'existing': {}, 'conflicts_kept': []}
    directory_names = {}
    log_status(f'Comparing TARGET payload: {len(files):,} files; this phase only reads the device.')
    # Check the spelling of each existing component even on case-sensitive hosts.
    for index, (rel, meta) in enumerate(files.items(), 1):
        log_status(f'Comparing TARGET [{index}/{len(files)}]: {rel} ({human_bytes(meta["size"])})')
        path = payload_path(target, rel)
        current = target
        for part in rel.split('/'):
            if current.is_dir():
                if current not in directory_names:
                    directory_names[current] = {path_key(p.name): p.name for p in current.iterdir()}
                existing_name = directory_names[current].get(path_key(part))
                if existing_name is not None and existing_name != part:
                    raise MigrationError(f'Destination name collision: {rel} vs {existing_name}')
            current = current / part
        if path.exists():
            if path.stat().st_size == meta['size'] and sha256_file(path) == meta['sha256']:
                plan['skip'].append(rel)
                log_status('  Identical: skipped.')
                continue
            if conflict == 'keep-target':
                plan['conflicts_kept'].append(rel)
                log_status('  Different: keeping TARGET.')
                continue
            plan['existing'][rel] = {'size': path.stat().st_size, 'category': meta.get('category', 'backup')}
        plan['copy'][rel] = meta
        log_status('  Different: backup then overwrite.' if rel in plan['existing'] else '  New: will copy.')
    kept_books = [rel for rel in plan['conflicts_kept'] if files[rel].get('category') == 'books']
    protected_sidecars = [str(Path(rel).with_suffix('.sdr')).replace(os.sep, '/') + '/' for rel in kept_books]
    plan['metadata_skipped'] = []
    if kept_books:
        for rel in list(plan['copy']):
            category = files[rel].get('category')
            if category == 'central_metadata' or any(rel.startswith(prefix) for prefix in protected_sidecars):
                del plan['copy'][rel]
                plan['existing'].pop(rel, None)
                plan['metadata_skipped'].append(rel)
    return plan


def restore_payload(target: Path, archive: Path, files: dict, journal: dict) -> None:
    with zipfile.ZipFile(archive) as zf:
        all_names = zf.namelist()
        if len(all_names) != len(set(all_names)):
            raise MigrationError('Duplicate payload ZIP members.')
        assert_unique_paths(files)
        for rel, meta in files.items():
            payload_path(target, rel)
            try:
                member = zf.getinfo(rel)
            except KeyError as exc:
                raise MigrationError(f'Payload ZIP member is missing: {rel}') from exc
            if member.is_dir() or stat.S_ISLNK(member.external_attr >> 16) or member.file_size != meta['size']:
                raise MigrationError(f'Unsafe/incorrect payload ZIP member: {rel}')
        for idx, (rel, meta) in enumerate(files.items(), 1):
            path = payload_path(target, rel)
            missing = []
            parent = path.parent
            while parent != target and not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                journal['created_dirs'].append(directory)
            journal['touched'].append(rel)
            persist_target_changes(journal)
            with zf.open(rel) as src, path.open('wb') as dst:
                log_status(f'Copying payload [{idx}/{len(files)}]: {rel}')
                copy_with_progress(src, dst, f'Copying {rel}', meta['size'])
            if path.stat().st_size != meta['size'] or sha256_file(path) != meta['sha256']:
                raise MigrationError(f'Payload verification failed: {rel}')
            print_progress(message('progress.copy_payload'), idx, len(files))


def rollback_payload(target: Path, backup: Optional[Path], previous: dict, journal: dict) -> None:
    # Validate backup before deleting any currently restored payload files.
    if backup is not None:
        with zipfile.ZipFile(backup) as zf:
            for rel in journal['touched']:
                if rel in previous:
                    meta = previous[rel]
                    digest = hashlib.sha256()
                    with zf.open(rel) as member:
                        for chunk in iter(lambda: member.read(1024 * 1024), b''):
                            digest.update(chunk)
                    if digest.hexdigest() != meta['sha256']:
                        raise MigrationError(f'Rollback payload checksum changed: {rel}')
    # Only restore overwritten files that were actually touched.
    for rel in reversed(journal['touched']):
        payload_path(target, rel).unlink(missing_ok=True)
    restore = {rel: meta for rel, meta in previous.items() if rel in journal['touched']}
    if restore:
        if backup is None:
            raise MigrationError('Payload rollback backup is missing.')
        restore_payload(target, backup, restore, {'touched': [], 'created_dirs': []})
    for directory in reversed(journal['created_dirs']):
        if directory.exists() and not any(directory.iterdir()):
            directory.rmdir()
    print('Payload rollback: SUCCESS')


def device_diagnostics(mount: Path) -> dict:
    log_status('Checking metadata configuration and reading statistics...')
    kr = checked_path(mount, '.adds/koreader', allow_metadata=True)
    result = {'metadata_mode': 'unknown', 'statistics': None, 'missing_references': []}
    settings = checked_path(mount, '.adds/koreader/settings.reader.lua', allow_metadata=True)
    if settings.is_file() and not settings.is_symlink():
        text = settings.read_text(encoding='utf-8', errors='replace')
        match = re.search(r'\["document_metadata_folder"\]\s*=\s*"([^"]+)"', text)
        result['metadata_mode'] = match.group(1) if match else 'doc (default)'
    db = checked_path(mount, '.adds/koreader/settings/statistics.sqlite3', allow_metadata=True)
    if db.is_symlink():
        raise MigrationError('Statistics database must not be a symlink.')
    if db.is_file():
        if db.with_name(db.name + '-wal').exists() and db.with_name(db.name + '-wal').stat().st_size:
            raise MigrationError('Statistics has pending WAL data. Exit KOReader cleanly before connecting USB.')
        try:
            with closing(sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True)) as conn:
                log_status(f'Statistics quick_check: {human_bytes(db.stat().st_size)} database')
                checks = [row[0] for row in conn.execute('PRAGMA quick_check')]
                if checks != ['ok']:
                    raise MigrationError('Statistics database quick_check failed: ' + '; '.join(checks))
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                counts = {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                          for table in ('book', 'page_stat_data', 'page_stat') if table in tables}
                result['statistics'] = {'quick_check': 'ok', 'rows': counts}
        except sqlite3.Error as exc:
            raise MigrationError(f'Statistics database could not be read: {exc}') from exc
    log_status('Checking history, collections and folder references...')
    for rel in ('history.lua', 'settings/collection.lua', 'settings.reader.lua'):
        path = checked_path(mount, '.adds/koreader/' + rel, allow_metadata=True)
        if path.is_file() and not path.is_symlink():
            text = path.read_text(encoding='utf-8', errors='replace')
            for device_path in set(re.findall(r'"(/mnt/onboard/[^"\n]+)"', text)):
                # Report literal references only; do not evaluate Lua or rewrite paths.
                if '\\' not in device_path:
                    relative = device_path[len('/mnt/onboard/'):]
                    if not (mount / relative).exists():
                        result['missing_references'].append({'file': rel, 'path': device_path})
    return result


class LogTee:
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, value):
        self.stream.write(value)
        self.log.write(value)
        return len(value)

    def flush(self):
        self.stream.flush()
        self.log.flush()


def ensure_local_backup(backup_dir: Path, mount: Path) -> None:
    if backup_dir == mount or mount in backup_dir.parents:
        raise MigrationError('Backup directory must be on the Mac, not the Kobo.')


def confirm_device(mount: Path, fingerprint: Optional[str]) -> None:
    if not mount.is_dir() or not (mount / '.kobo').is_dir():
        raise MigrationError('Device disconnected; reconnect the same target before manual recovery.')
    if fingerprint and device_fingerprint(mount)[0] != fingerprint:
        raise MigrationError('Connected device changed; refusing to modify it.')



def self_test() -> None:
    import tempfile

    print("Running self-tests...")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        settings = root / "settings.reader.lua"
        settings.write_text(
            'return {\n    ["device_id"] = "ABC123",\n    ["language"] = "en",\n}\n',
            encoding="utf-8",
        )

        assert read_device_id(settings) == "ABC123"
        set_device_id(settings, "XYZ789")
        assert read_device_id(settings) == "XYZ789"

        settings2 = root / "settings2.reader.lua"
        settings2.write_text('return {\n    ["language"] = "en",\n}\n', encoding="utf-8")
        set_device_id(settings2, "NEWID")
        assert read_device_id(settings2) == "NEWID"

        assert should_exclude_rel("cache/fontlist/fontinfo.dat")
        assert should_exclude_rel("foo/._bar")
        assert should_exclude_rel("foo/.DS_Store")
        assert not should_exclude_rel("fonts/noto/NotoSans-Regular.ttf")

        assert canonical_model("Kobo Clara 2E") == MODEL_CLARA
        assert canonical_model("Kobo Libra 2") == MODEL_LIBRA

        source = root / "source"
        target = root / "target"
        (source / "Books").mkdir(parents=True)
        target.mkdir()
        (source / "Books/book.epub").write_bytes(b"new book")
        (source / "Books/book.sdr").mkdir()
        (source / "Books/book.sdr/metadata.epub.lua").write_bytes(b"return {}")
        scanned, report = scan_payload(source, True, False)
        assert len(scanned) == 2 and len(report['sidecars']) == 1
        archive = root / 'payload.zip'
        manifest = create_payload_archive(source, scanned, archive)
        plan = plan_payload(target, manifest)
        journal = {'touched': [], 'created_dirs': []}
        restore_payload(target, archive, plan['copy'], journal)
        assert len(plan_payload(target, manifest)['skip']) == 2
        rollback_payload(target, None, {}, journal)
        assert not (target / 'Books').exists()

    print("Self-tests: OK")


def parse_args() -> argparse.Namespace:
    bootstrap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    bootstrap.add_argument('--locale')
    initial, _ = bootstrap.parse_known_args()
    try:
        bundle = load_locale_bundle(initial.locale)
    except LocaleError as exc:
        bootstrap.error('Locale initialization failed; keep the complete locales/ folder beside the script. ' + str(exc))
    for notice in bundle.notices:
        locale_console_write('WARNING: ' + notice + '\n', sys.stderr)
    parser = LocaleArgumentParser(description=bundle.render('cli.description'),
        epilog=bundle.render('cli.foundation_notice'), allow_abbrev=False, add_help=False)
    parser.add_argument('-h', '--help', action='help', help=bundle.render('help.help'))
    parser.add_argument('--locale', metavar='TAG', help=bundle.render('help.locale'))
    parser.add_argument('--mode', choices=('full', 'koreader', 'library', 'audit'), help=bundle.render('help.mode'))
    parser.add_argument('--source-model', help=bundle.render('help.source_model'))
    parser.add_argument('--target-model', help=bundle.render('help.target_model'))
    parser.add_argument('--dry-run', action='store_true', help=bundle.render('help.dry_run'))
    parser.add_argument('--books', action=argparse.BooleanOptionalAction, default=None, help=bundle.render('help.books'))
    parser.add_argument('--fonts', action=argparse.BooleanOptionalAction, default=None, help=bundle.render('help.fonts'))
    parser.add_argument('--reading-data', action=argparse.BooleanOptionalAction, default=True, help=bundle.render('help.reading_data'))
    parser.add_argument('--conflict', choices=('overwrite', 'keep-target'), help=bundle.render('help.conflict'))
    parser.add_argument('--include-dir', action='append', default=[], help=bundle.render('help.include_dir'))
    parser.add_argument('--exclude-dir', action='append', default=[], help=bundle.render('help.exclude_dir'))
    parser.add_argument('--extra-extension', action='append', default=[], help=bundle.render('help.extra_extension'))
    parser.add_argument('--backup-dir', type=Path, default=DEFAULT_BACKUP_DIR, help=bundle.render('help.backup_dir'))
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument('--preview-ui', action='store_true', help=bundle.render('help.preview_ui'))
    operations.add_argument('--list-locales', action='store_true', help=bundle.render('help.list_locales'))
    operations.add_argument('--from-run', metavar='RUN_ID', help=bundle.render('help.from_run'))
    operations.add_argument('--restore-run', metavar='RUN_ID', help=bundle.render('help.restore_run'))
    operations.add_argument('--list-runs', action='store_true', help=bundle.render('help.list_runs'))
    operations.add_argument('--cleanup', action='store_true', help=bundle.render('help.cleanup'))
    parser.add_argument('--keep-successful', type=int, default=2, help=bundle.render('help.keep_successful'))
    parser.add_argument('--delete-run', action='append', default=[], metavar='RUN_ID', help=bundle.render('help.delete_run'))
    parser.add_argument('--self-test', action='store_true', help=bundle.render('help.self_test'))
    parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}', help=bundle.render('help.version'))
    args = parser.parse_args()
    if args.delete_run and not args.cleanup:
        parser.error('--delete-run requires --cleanup')
    if args.keep_successful < 1:
        parser.error('--keep-successful must be at least 1')
    if args.restore_run and (args.source_model or args.target_model or args.mode or args.books is not None or args.fonts is not None or args.conflict
                            or args.include_dir or args.exclude_dir or args.extra_extension or not args.reading_data):
        parser.error('--restore-run restores the recorded TARGET snapshot; only --dry-run and --backup-dir may customize it')
    args.locale = bundle.tag
    args.locale_bundle = bundle
    if (args.preview_ui or args.list_locales) and (args.mode or args.self_test or args.books is not None or args.fonts is not None
            or args.source_model or args.target_model or args.conflict or args.include_dir or args.exclude_dir
            or args.extra_extension or not args.reading_data):
        parser.error('Locale preview/list commands cannot be combined with migration settings')
    return args


# Run management deliberately uses OS locks, not stale PID-file ownership.
CURRENT_RUN = None
CURRENT_LOCKS = None


def atomic_json(path: Path, data: dict) -> None:
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp.unlink(missing_ok=True)


class FileLock:
    def __init__(self, path: Path, label: str):
        self.path, self.label, self.fd = path, label, None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise MigrationError(f'Lock path must not be a symlink: {self.path}')
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise MigrationError('Lock must be a regular file.')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise MigrationError(f'{self.label} is busy in another process. Wait for it to finish; do not remove the lock file.') from exc
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps({'pid': os.getpid(), 'started_at': iso_now(), 'label': self.label}).encode())
            self.fd = fd
            return self
        except BaseException:
            os.close(fd)
            raise

    def __exit__(self, *exc):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None
        # Keep the inode: deleting it could let a second lock bypass a waiting holder.


class DeviceLocks:
    def __init__(self):
        self.stack, self.keys = ExitStack(), set()

    def acquire(self, mount: Path, fingerprint: Optional[str]):
        identities = ['mount:' + str(mount.resolve())]
        if fingerprint:
            identities.append('device:' + fingerprint)
        base = Path(tempfile.gettempdir()) / f'koreader-migration-locks-{os.getuid()}'
        if base.is_symlink():
            raise MigrationError('Device lock directory must not be a symlink.')
        for identity in identities:
            key = hashlib.sha256(identity.encode()).hexdigest()
            if key not in self.keys:
                self.stack.enter_context(FileLock(base / (key + '.lock'), 'Kobo device'))
                self.keys.add(key)

    def close(self):
        self.stack.close()


class RunState:
    def __init__(self, directory: Path, run_id: str, operation: str):
        self.directory = directory
        self.data = {'schema_version': 1, 'tool_version': VERSION, 'run_id': run_id,
                     'operation': operation, 'status': 'running', 'phase': 'starting',
                     'ui_locale': current_ui().bundle.tag,
                     'pid': os.getpid(), 'started_at': iso_now(), 'updated_at': iso_now(),
                     'target_modified': False, 'dependencies': []}
        self.update()

    def update(self, **fields):
        self.data.update(fields)
        self.data['updated_at'] = iso_now()
        atomic_json(self.directory / 'run.json', self.data)

    def finish(self, status: str, **fields):
        self.update(status=status, ended_at=iso_now(), **fields)


def run_phase(phase: str, **fields):
    if CURRENT_RUN is not None:
        CURRENT_RUN.update(phase=phase, **fields)


def acquire_device(mount: Path, fingerprint: Optional[str]):
    if CURRENT_LOCKS is not None:
        CURRENT_LOCKS.acquire(mount, fingerprint)


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise MigrationError(f'Missing or unsafe JSON file: {path.name}')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise MigrationError(f'Cannot read JSON file: {path.name}') from exc
    if not isinstance(data, dict):
        raise MigrationError(f'JSON must contain an object: {path.name}')
    return data


def resolve_saved_run(project: Path, reference: str) -> Path:
    root = project / 'runs'
    candidate = Path(reference).expanduser()
    if not candidate.is_absolute():
        if len(candidate.parts) != 1:
            raise MigrationError('Use a run ID or an absolute run path inside this project.')
        candidate = root / reference
    if candidate.is_symlink() or root.is_symlink():
        raise MigrationError('Saved run directories must not be symlinks.')
    if not candidate.is_dir() or candidate.resolve().parent != root.resolve():
        raise MigrationError('Saved run must be a direct child of this project\'s runs/ directory.')
    return candidate.resolve()


def saved_file(run: Path, name: str) -> Path:
    if not isinstance(name, str) or Path(name).name != name or name in {'', '.', '..'}:
        raise MigrationError('Invalid saved artifact filename.')
    path = run / name
    if path.is_symlink() or not path.is_file():
        raise MigrationError(f'Saved artifact is missing/unsafe: {name}')
    return path


def validate_file_manifest(files: dict, payload: bool):
    if not isinstance(files, dict):
        raise MigrationError('Invalid file manifest.')
    assert_unique_paths(files)
    for rel, meta in files.items():
        if not isinstance(rel, str) or '\\' in rel or rel.startswith('/'):
            raise MigrationError('Unsafe manifest path.')
        parts = rel.split('/')
        if any(part in {'', '.', '..'} for part in parts):
            raise MigrationError('Unsafe manifest path.')
        if payload:
            central = any(rel.startswith(f'.adds/koreader/{name}/') for name in METADATA_DIRS)
            if any(part.startswith('.') for part in parts) and not central:
                raise MigrationError('System path is not allowed in payload manifest.')
        if (not isinstance(meta, dict) or not isinstance(meta.get('size'), int)
                or meta['size'] < 0 or not re.fullmatch(r'[0-9a-f]{64}', str(meta.get('sha256', '')))):
            raise MigrationError(f'Invalid manifest entry: {rel}')


def verify_saved_archive(archive: Path, manifest: dict, kind: str) -> None:
    payload = kind == 'payload'
    files = manifest.get('files')
    validate_file_manifest(files, payload)
    expected = manifest.get('archive_sha256') if payload else manifest.get('archive', {}).get('sha256')
    if not isinstance(expected, str) or sha256_file(archive) != expected:
        raise MigrationError(f'Saved archive checksum mismatch: {archive.name}')
    if not payload:
        validate_koreader_zip(archive)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise MigrationError('Duplicate saved ZIP members.')
        if payload:
            actual = {info.filename for info in zf.infolist() if not info.is_dir()}
            if actual != set(files):
                raise MigrationError('Payload archive members do not match manifest.')
            for info in zf.infolist():
                if info.is_dir():
                    raise MigrationError('Unexpected directory entry in saved payload archive.')
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise MigrationError('Symlink in saved payload archive.')
                validate_file_manifest({info.filename: files.get(info.filename, {})}, True) if not info.is_dir() else None
        else:
            actual = {info.filename[len('koreader/'):] for info in archive_entries(zf)}
            if actual != set(files):
                raise MigrationError('KOReader archive members do not match manifest.')
            if manifest.get('strict_source', True) and 'reader.lua' not in files:
                raise MigrationError('Source archive has no reader.lua.')
        for index, (rel, meta) in enumerate(files.items(), 1):
            member_name = rel if payload else 'koreader/' + rel
            info = zf.getinfo(member_name)
            if info.file_size != meta['size']:
                raise MigrationError(f'Saved ZIP size mismatch: {rel}')
            digest = hashlib.sha256()
            progress = ByteProgress(message('progress.verify_file', name=rel), meta['size']) if meta['size'] >= 32 * 1024 * 1024 else None
            with zf.open(member_name) as member:
                for chunk in iter(lambda: member.read(1024 * 1024), b''):
                    digest.update(chunk)
                    if progress:
                        progress.update(len(chunk))
            if progress:
                progress.update(0, final=True)
            if digest.hexdigest() != meta['sha256']:
                raise MigrationError(f'Saved ZIP checksum mismatch: {rel}')
            print_progress(message('progress.verify_members'), index, len(files))
    log_status(f'Saved archive verified: {archive.name}')


def load_artifact(run: Path, entry: Optional[dict], kind: str):
    if entry is None:
        return None, None
    archive = saved_file(run, entry['archive'])
    manifest = read_json(saved_file(run, entry['manifest']))
    verify_saved_archive(archive, manifest, kind)
    return archive, manifest


def artifact_entry(archive: Optional[Path]) -> Optional[dict]:
    return {'archive': archive.name, 'manifest': archive.with_suffix('.manifest.json').name} if archive else None


def save_source_snapshot(run: Path, info: DeviceInfo, mode: str, books: bool, fonts: bool,
                         scan_report: dict, kr_archive: Optional[Path], payload_archive: Optional[Path], confirmed_model: Optional[str] = None):
    descriptor = {'schema_version': 1, 'role': 'source', 'mode': mode,
                  'device': asdict(info), 'confirmed_model': confirmed_model, 'books': books, 'fonts': fonts,
                  'source_diagnostics': scan_report['source_diagnostics'],
                  'scan_report': scan_report, 'koreader': artifact_entry(kr_archive),
                  'payload': artifact_entry(payload_archive)}
    atomic_json(run / 'source-snapshot.json', descriptor)


def source_descriptor(run: Path) -> dict:
    if (run / 'source-snapshot.json').exists():
        return read_json(run / 'source-snapshot.json')
    # Import old flat runs conservatively. Require finished manifests and scan metadata.
    reports = list(run.glob('koreader-scan-*.json'))
    if len(reports) != 1:
        raise MigrationError('Legacy source run requires exactly one scan report.')
    report = read_json(reports[0])
    mode = report.get('mode')
    if mode not in {'full', 'koreader', 'library'}:
        raise MigrationError('Legacy run mode is missing or not reusable.')
    kr = [p for p in run.glob('koreader-*.manifest.json') if '-pre-migration-' not in p.name]
    library = [p for p in run.glob('library-*.manifest.json') if '-pre-migration-' not in p.name]
    if (mode in {'full', 'koreader'} and len(kr) != 1) or len(library) > 1:
        raise MigrationError('Legacy source archive pair is missing or ambiguous.')
    if report.get('dry_run'):
        raise MigrationError('A dry-run has no reusable source snapshot.')
    book_count = len(report.get('books', []))
    payload_count = book_count + len(report.get('sidecars', [])) + len(report.get('fonts', []))
    if mode == 'library':
        payload_count += len(report.get('central_metadata', []))
    if payload_count and not library:
        raise MigrationError('Legacy source payload archive is missing; source snapshot is incomplete.')
    kr_manifest = read_json(kr[0]) if kr else None
    source = kr_manifest.get('source', {}) if kr_manifest else {}
    model = source.get('detected_model')
    if not model:
        raise MigrationError('Legacy source device model cannot be established.')
    info = DeviceInfo('', model, source.get('koreader_version'), source.get('device_fingerprint_sha256'),
                      source.get('serial_hint'), bool(source.get('device_id_present')),
                      bool(source.get('ai_assistant_config')), len(kr_manifest.get('files', {})),
                      sum(m['size'] for m in kr_manifest.get('files', {}).values()))
    return {'schema_version': 1, 'role': 'source', 'mode': mode, 'device': asdict(info),
            'books': bool(book_count), 'fonts': bool(report.get('fonts')),
            'source_diagnostics': report.get('source_diagnostics', {}), 'scan_report': report,
            'koreader': artifact_entry(kr[0].with_suffix('').with_suffix('.zip')) if kr else None,
            'payload': artifact_entry(library[0].with_suffix('').with_suffix('.zip')) if library else None}


def build_difference_report(target: Path, source_files: dict, plan: dict, books: bool, fonts: bool,
                            scan_options: dict) -> dict:
    categories = {'new': [], 'overwrite': [], 'identical': [], 'keep_target': [],
                  'metadata_skipped': [], 'target_only': []}
    for rel, meta in plan['copy'].items():
        category = 'overwrite' if rel in plan['existing'] else 'new'
        categories[category].append({'path': rel, **meta,
            'target_size': plan['existing'].get(rel, {}).get('size')})
    for label, key in (('identical', 'skip'), ('keep_target', 'conflicts_kept'), ('metadata_skipped', 'metadata_skipped')):
        categories[label] = [{'path': rel, **source_files[rel]} for rel in plan[key]]
    log_status('Scanning TARGET-only books/fonts within the same discovery scope...')
    target_files, target_scan = scan_payload(target, books, fonts, include_metadata=books, include_central_metadata=False,
        include_dirs=scan_options.get('include_dirs') or None,
        exclude_dirs=scan_options.get('exclude_dirs') or None,
        extra_extensions=scan_options.get('extra_extensions') or None,
        missing_roots_ok=True)
    for rel, meta in target_files.items():
        if rel not in source_files:
            categories['target_only'].append({'path': rel, **meta, 'action': 'retain'})
    groups = {}
    for label, entries in categories.items():
        for entry in entries:
            rel = entry['path']
            if entry.get('category') == 'books':
                groups[rel] = {'book': rel, 'action': label, 'sidecars': []}
    for label, entries in categories.items():
        for entry in entries:
            if entry.get('category') == 'sidecars':
                owners = [rel for rel in groups if entry['path'].startswith(Path(rel).with_suffix('.sdr').as_posix() + '/')]
                for owner in owners:
                    groups[owner]['sidecars'].append({'path': entry['path'], 'action': label})
    summary = {label: {'count': len(entries), 'bytes': sum(e.get('size', 0) for e in entries),
                      'source_bytes': 0 if label == 'target_only' else sum(e.get('size', 0) for e in entries),
                      'target_bytes': sum((e.get('target_size') or e.get('size', 0)) for e in entries)}
               for label, entries in categories.items()}
    return {'schema_version': 1, 'created_at': iso_now(), 'ui_locale': current_ui().bundle.tag, 'summary': summary,
            'files': categories, 'book_groups': list(groups.values()),
            'scope': scan_options, 'notes': ['Target-only files are retained; mirror deletion is not enabled.',
            'Discovery uses the same supported extensions and selected roots; this is not a complete disk inventory.']}


def write_difference(run: Path, difference: dict):
    atomic_json(run / 'difference.json', difference)
    ui = current_ui()
    lines = [ui.text(message('difference.title')), ui.text(message('difference.retain')), '']
    for label, entries in difference['files'].items():
        summary = difference['summary'][label]
        category = message('difference.' + label)
        lines.append(ui.text(message('difference.section', label=category, count=summary['count'],
                                     size=human_bytes(summary['bytes']))))
        lines.extend('  ' + entry['path'] for entry in entries)
        lines.append('')
        ui_emit('difference.section', label=category, count=summary['count'], size=human_bytes(summary['bytes']))
    (run / 'difference.txt').write_text('\n'.join(lines), encoding='utf-8')
    ui_emit('difference.paths', path=run / 'difference.txt')


def run_catalog(project: Path) -> List[dict]:
    root = project / 'runs'
    if not root.is_dir() or root.is_symlink():
        return []
    records = []
    for run in sorted(root.iterdir()):
        if not run.is_dir() or run.is_symlink():
            continue
        try:
            state = read_json(run / 'run.json') if (run / 'run.json').is_file() else {}
        except MigrationError:
            state = {'status': 'unreadable'}
        if not isinstance(state.get('dependencies', []), list) or any(not isinstance(d, str) for d in state.get('dependencies', [])):
            state = {'status': 'unreadable'}
        total = sum(p.stat().st_size for p in run.rglob('*') if p.is_file() and not p.is_symlink())
        records.append({'run_id': run.name, 'path': str(run), 'bytes': total,
                        'status': state.get('status', 'legacy/unknown'),
                        'ended_at': state.get('ended_at'), 'operation': state.get('operation', 'unknown'),
                        'dependencies': state.get('dependencies', []), 'target_modified': state.get('target_modified', False),
                        'target_fingerprint': state.get('target_fingerprint')})
    return records


def cleanup_plan(project: Path, keep_successful: int = 2) -> dict:
    if keep_successful < 1:
        raise MigrationError('Keep at least one successful run.')
    records = run_catalog(project)
    successes = sorted([r for r in records if r['status'] == 'success'],
                       key=lambda r: (r['ended_at'] or '', r['run_id']), reverse=True)
    keep = {r['run_id'] for r in successes[:keep_successful]}
    # Conservatively protect all dependency targets, including references from old runs.
    dependencies = {dep for record in records for dep in record['dependencies']}
    latest_recovery = {}
    for record in successes:
        if record.get('target_fingerprint'):
            latest_recovery.setdefault(record['target_fingerprint'], record['run_id'])
    recovery_ids = set(latest_recovery.values())
    candidates, protected = [], []
    for record in records:
        reason = None
        if record['run_id'] in keep:
            reason = 'recent successful run'
        elif record['run_id'] in dependencies:
            reason = 'referenced by another run'
        elif record['run_id'] in recovery_ids:
            reason = 'newest successful recovery snapshot for this target device'
        elif record['status'] != 'success':
            reason = 'not a confirmed successful run; may be the only recovery backup'
        if reason:
            protected.append({**record, 'reason': reason})
        else:
            candidates.append(record)
    return {'keep_successful': keep_successful, 'candidates': candidates, 'protected': protected,
            'reclaimable_bytes': sum(r['bytes'] for r in candidates)}


def print_catalog(records: List[dict]):
    ui_emit('catalog.heading')
    for record in records:
        print(f'{record["run_id"]} | {record["status"]} | {record["operation"]} | {human_bytes(record["bytes"])}')
    if not records:
        ui_emit('catalog.empty')


def cleanup_command(project: Path, keep: int, selected: List[str]) -> int:
    def show(plan):
        ui_emit('cleanup.heading')
        if plan['candidates']:
            print_catalog(plan['candidates'])
        else:
            ui_emit('cleanup.empty')
        ui_emit('cleanup.reclaimable', size=human_bytes(plan['reclaimable_bytes']))
        for record in plan['protected']:
            ui_emit('cleanup.protected', run_id=record['run_id'], reason=record['reason'])
    if not selected:
        show(cleanup_plan(project, keep))
        return 0
    with FileLock(project / '.project.lock', 'Project'):
        plan = cleanup_plan(project, keep)
        show(plan)
        allowed = {r['run_id'] for r in plan['candidates']}
        if len(set(selected)) != len(selected) or not set(selected) <= allowed:
            raise MigrationError('Requested runs are not eligible for cleanup; nothing deleted.')
        expected = 'DELETE ' + ','.join(sorted(selected))
        ui_emit('cleanup.confirm', expected=expected, severity='warning')
        if ui_input(message('prompt.confirmation')).strip() != expected:
            ui_emit('cleanup.cancelled')
            return 0
        # Recompute protection at the final step; the project lock blocks new dependents.
        allowed = {r['run_id'] for r in cleanup_plan(project, keep)['candidates']}
        if not set(selected) <= allowed:
            raise MigrationError('Cleanup eligibility changed; nothing deleted.')
        for run_id in selected:
            run = resolve_saved_run(project, run_id)
            if any(p.is_symlink() for p in run.rglob('*')):
                raise MigrationError('Refusing cleanup of a batch containing symlinks.')
        for run_id in selected:
            shutil.rmtree(resolve_saved_run(project, run_id))
            ui_emit('cleanup.deleted', run_id=run_id)
    return 0


def reconcile_interrupted_runs(project: Path):
    # Called only with the exclusive project lock. Prior live workers cannot coexist.
    for record in run_catalog(project):
        if record['status'] == 'running':
            path = Path(record['path']) / 'run.json'
            state = read_json(path)
            state.update(status='needs-recovery' if state.get('target_modified') else 'interrupted',
                         updated_at=iso_now(), note='Previous process ended without a final status; inspect before reuse/cleanup.')
            atomic_json(path, state)



def main() -> int:
    args = parse_args()
    with ui_session(args.locale_bundle):
        try:
            return run_main(args)
        except MigrationError as exc:
            ui_emit('error.summary', detail=str(exc), channel='stderr', severity='error')
            exc.ui_reported = True
            raise


def run_main(args) -> int:
    global CURRENT_RUN, CURRENT_LOCKS
    if getattr(args, 'list_locales', False):
        bundle = args.locale_bundle
        lines = [bundle.render('cli.locales_heading')]
        lines += [f"  {tag}: {entry['name']}" for tag, entry in bundle.registry['entries'].items()]
        locale_console_write('\n'.join(lines) + '\n')
        return 0
    if getattr(args, 'preview_ui', False):
        preview_locale_ui(args.locale_bundle)
        return 0
    if getattr(args, 'locale', 'en') != 'en':
        ui_emit('ui.partial_notice', channel='stderr')
    if args.self_test:
        self_test()
        return 0
    project = args.backup_dir.expanduser().resolve()
    if VOLUME_ROOT.resolve() == project or VOLUME_ROOT.resolve() in project.parents:
        raise MigrationError('Project/backups must be on the Mac, outside /Volumes.')
    if (project / 'runs').is_symlink():
        raise MigrationError('runs/ must not be a symlink.')
    if getattr(args, 'list_runs', False):
        print_catalog(run_catalog(project))
        return 0
    if getattr(args, 'cleanup', False):
        return cleanup_command(project, args.keep_successful, [] if args.dry_run else args.delete_run)
    require_macos_tools()
    with FileLock(project / '.project.lock', 'Project'):
        reconcile_interrupted_runs(project)
        run_id = now_stamp() + '-' + uuid.uuid4().hex[:8]
        directory = project / 'runs' / run_id
        directory.mkdir(parents=True, exist_ok=False)
        operation = 'restore-target' if getattr(args, 'restore_run', None) else 'saved-source' if getattr(args, 'from_run', None) else 'migration'
        state = RunState(directory, run_id, operation)
        CURRENT_RUN, CURRENT_LOCKS = state, DeviceLocks()
        log_path = directory / f'koreader-migration-{run_id}.log'
        try:
            with log_path.open('x', encoding='utf-8', buffering=1) as log:
                stdout, stderr = sys.stdout, sys.stderr
                with ui_session(args.locale_bundle, log, stdout, stderr):
                    sys.stdout, sys.stderr = LogTee(stdout, log), LogTee(stderr, log)
                    try:
                        ui_emit('run.banner', version=VERSION, run_id=run_id)
                        ui_emit('run.log_path', path=log_path)
                        if operation == 'restore-target':
                            code = restore_saved_target(args, project, directory, run_id, log_path)
                        elif operation == 'saved-source':
                            code = migrate_saved_source(args, project, directory, run_id, log_path)
                        else:
                            code = migrate(args, directory, run_id, log_path)
                        status = {2: 'rolled-back', 3: 'needs-recovery'}.get(code)
                        if status is None:
                            status = 'audited' if args.dry_run or state.data.get('dry_run') else 'success'
                        state.finish(status, exit_code=code)
                        return code
                    except MigrationCancelled as exc:
                        ui_emit('run.cancelled', detail=str(exc))
                        state.finish('cancelled', exit_code=0)
                        return 0
                    except KeyboardInterrupt:
                        ui_emit('run.interrupted', severity='warning')
                        state.finish('needs-recovery' if state.data['target_modified'] else 'interrupted', exit_code=130)
                        return 130
                    except BaseException as exc:
                        ui_emit('run.stopped', kind=type(exc).__name__, detail=str(exc), severity='error')
                        state.finish('needs-recovery' if state.data['target_modified'] else 'failed', exit_code=1)
                        raise
                    finally:
                        sys.stdout, sys.stderr = stdout, stderr
        finally:
            CURRENT_LOCKS.close()
            CURRENT_RUN, CURRENT_LOCKS = None, None


def migrate_saved_source(args, project: Path, run: Path, run_id: str, log_path: Path) -> int:
    selected = saved = resolve_saved_run(project, args.from_run)
    seen = set()
    selected_mode = None
    while (saved / 'source-reference.json').exists():
        if saved.name in seen or len(seen) >= 20:
            raise MigrationError('Saved source reference cycle or excessive depth.')
        seen.add(saved.name)
        reference = read_json(saved / 'source-reference.json')
        selected_mode = selected_mode or reference.get('mode')
        saved = resolve_saved_run(project, reference['run_id'])
    dependencies = sorted({selected.name, saved.name})
    run_phase('verifying-saved-source', dependencies=dependencies)
    descriptor = source_descriptor(saved)
    if descriptor.get('role') != 'source' or descriptor.get('mode') not in {'full', 'koreader', 'library'}:
        raise MigrationError('Invalid saved source descriptor.')
    original_mode = descriptor['mode']
    if selected_mode not in {None, 'full', 'koreader', 'library'}:
        raise MigrationError('Invalid saved source reference mode.')
    mode = args.mode or selected_mode or original_mode
    if mode == 'audit':
        mode = original_mode
        dry_run = True
    else:
        dry_run = args.dry_run
    if mode == 'library' and original_mode != 'library':
        raise MigrationError('LIBRARY reuse requires a LIBRARY-captured snapshot; FULL central metadata is stored in the runtime archive.')
    if mode == 'full' and original_mode != 'full':
        raise MigrationError('FULL requires a source snapshot captured in FULL mode.')
    if mode in {'full', 'koreader'} and not descriptor.get('koreader'):
        raise MigrationError('Saved run has no full KOReader archive.')
    if args.include_dir or args.exclude_dir or args.extra_extension:
        raise MigrationError('Saved snapshots use their captured discovery scope; recapture to change it.')
    if mode == 'full' and (args.books is False or not args.reading_data):
        raise MigrationError('FULL always includes captured books and reading data.')
    if mode == 'koreader' and (args.books is True or args.fonts is True):
        raise MigrationError('KOREADER copies only the entire KOReader directory.')
    source_zip, source_manifest = load_artifact(saved, descriptor.get('koreader'), 'koreader') if mode != 'library' else (None, None)
    payload_zip, payload_manifest = load_artifact(saved, descriptor.get('payload'), 'payload') if mode != 'koreader' else (None, None)
    payload_manifest = payload_manifest or {'files': {}}
    if any(meta.get('category') not in {'books', 'sidecars', 'central_metadata', 'fonts'} for meta in payload_manifest['files'].values()):
        raise MigrationError('Source payload categories are missing or invalid; recapture the source.')
    if mode == 'full' and args.fonts is False:
        payload_manifest = {**payload_manifest, 'files': {p: m for p, m in payload_manifest['files'].items() if m.get('category') != 'fonts'}}
    if mode == 'library':
        books = descriptor.get('books', True) if args.books is None else args.books
        fonts = descriptor.get('fonts', False) if args.fonts is None else args.fonts
        allowed = ({'books', 'sidecars', 'central_metadata'} if books else set()) | ({'fonts'} if fonts else set())
        if not args.reading_data:
            allowed -= {'sidecars', 'central_metadata'}
        payload_manifest = {**payload_manifest, 'files': {p: m for p, m in payload_manifest['files'].items() if m.get('category') in allowed}}
        if not books and not fonts:
            raise MigrationError('LIBRARY requires books and/or fonts.')
    else:
        books, fonts = mode == 'full', mode == 'full' and args.fonts is not False
    conflict = select_conflict_policy(mode, args.conflict)
    info = DeviceInfo(**descriptor['device'])
    source_expected = canonical_model(descriptor.get('confirmed_model') or info.detected_model)
    if not source_expected:
        raise MigrationError('Saved source must have a confirmed or detected model label.')
    require_device_fingerprint(info)
    if args.source_model and canonical_model(args.source_model).casefold() != source_expected.casefold():
        raise MigrationError('--source-model does not match the saved SOURCE label.')
    target_expected = args.target_model
    target_slug = 'target'
    source_diag = descriptor.get('source_diagnostics', {})
    report = dict(descriptor.get('scan_report', {}))
    report.update(tool_version=VERSION, mode=mode, saved_source_run=saved.name, source_diagnostics=source_diag)
    scanned = payload_manifest['files']
    source_manifest_path = saved_file(saved, descriptor['koreader']['manifest']) if source_zip else None
    report_path = run / f'koreader-scan-{run_id}.json'
    atomic_json(report_path, report)
    # Reference verified originals; no multi-GiB duplication of source archives.
    atomic_json(run / 'source-reference.json', {'run_id': saved.name, 'mode': mode})
    run_phase('waiting-for-target', mode=mode, dry_run=dry_run)
    print(f'Using verified saved SOURCE {saved.name}: {source_expected} -> TARGET')
    print('Only connect TARGET. Original source device is not required.')
    if not prompt_yes_no(message('confirm.saved_source')):
        raise MigrationCancelled('Migration cancelled. No target files were modified.')
    return migrate_target(args, run, run_id, log_path, mode, dry_run, mode in {'full', 'koreader'},
                          books, fonts, conflict, info, source_expected, target_expected, target_slug,
                          source_zip, source_manifest_path, source_manifest, payload_zip,
                          payload_manifest, scanned, source_diag, report, report_path)


def persist_target_changes(journal: dict):
    if CURRENT_RUN is not None and journal.get('_mount') is not None:
        mount = journal['_mount']
        atomic_json(CURRENT_RUN.directory / 'target-changes.json', {
            'schema_version': 1, 'touched': journal['touched'],
            'created_dirs': [p.relative_to(mount).as_posix() for p in journal['created_dirs']]})


def restore_saved_target(args, project: Path, run: Path, run_id: str, log_path: Path) -> int:
    saved = resolve_saved_run(project, args.restore_run)
    run_phase('verifying-target-snapshot', dependencies=[saved.name], dry_run=args.dry_run)
    descriptor = read_json(saved / 'target-snapshot.json')
    if descriptor.get('role') != 'target':
        raise MigrationError('Saved snapshot must be a TARGET pre-migration snapshot.')
    if descriptor.get('replaced_koreader') and descriptor.get('had_koreader') and not descriptor.get('koreader'):
        raise MigrationError('Original KOReader backup is missing.')
    changes = read_json(saved / 'target-changes.json')
    prior_state = read_json(saved / 'run.json')
    if not prior_state.get('target_modified'):
        raise MigrationError('That run did not modify its target; no target restore is needed.')
    original = DeviceInfo(**descriptor['device'])
    kr_archive, kr_manifest = load_artifact(saved, descriptor.get('koreader'), 'koreader')
    payload_archive, payload_manifest = load_artifact(saved, descriptor.get('payload'), 'payload')
    previous = payload_manifest['files'] if payload_manifest else {}
    touched = changes.get('touched', [])
    if not isinstance(touched, list) or any(not isinstance(p, str) for p in touched):
        raise MigrationError('Invalid saved change journal.')
    allowed_paths = set(descriptor.get('planned_paths', []))
    if not set(touched) <= allowed_paths:
        raise MigrationError('Change journal includes paths not in the saved target plan.')
    removed = [p for p in touched if p not in previous]
    restored = {p: m for p, m in previous.items() if p in touched}
    expected = canonical_model(descriptor.get('confirmed_model') or original.detected_model)
    if not expected or not original.fingerprint_sha256:
        raise MigrationError('Exact target restore requires a known model and original device fingerprint.')
    print(f'RESTORE TARGET SNAPSHOT from {saved.name}: {expected}')
    print('This restores the old TARGET state, not the SOURCE migration snapshot.')
    ui_input(message('prompt.restore_target', model=expected))
    mount = wait_for_single_kobo('RESTORE TARGET')
    acquire_device(mount, device_fingerprint(mount)[0])
    confirm_device(mount, original.fingerprint_sha256)
    ensure_local_backup(run, mount.resolve())
    info = inspect_device(mount)
    verify_expected_model(info, expected, 'RESTORE TARGET')
    kr = checked_path(mount, '.adds/koreader', allow_metadata=True)
    if kr.exists() and not kr.is_dir():
        raise MigrationError('KOReader must be a directory.')
    if kr.is_dir():
        validate_tree_symlinks(kr)
    current_files = {}
    for rel in changes.get('created_dirs', []):
        checked_path(mount, rel, allow_metadata=rel.startswith('.adds/koreader/'))
    for rel in set(touched) | set(restored):
        path = payload_path(mount, rel)
        if path.exists():
            current_files[rel] = {'size': path.stat().st_size, 'category': previous.get(rel, {}).get('category', 'backup')}
    replacing_kr = bool(descriptor.get('replaced_koreader'))
    print(f'Restore runtime: {replacing_kr}; payload restore: {len(restored)}; remove prior-created files: {len(removed)}')
    for rel in sorted(restored):
        print(f'  Restore original: {rel}')
    for rel in sorted(removed):
        print(f'  Remove file created by that migration: {rel}')
    restore_plan = {'operation': 'restore-target', 'from_run': saved.name,
                    'restore_paths': sorted(restored), 'remove_created_paths': removed}
    atomic_json(run / 'restore-plan.json', restore_plan)
    if args.dry_run:
        print('DRY RUN: snapshot verified; no TARGET files changed.')
        safe_eject(mount)
        return 0
    ensure_backup_space(run, (info.total_bytes if replacing_kr else 0) + sum(m['size'] for m in current_files.values()), message('space.pre_restore'))
    ensure_target_space(mount, (sum(m['size'] for m in kr_manifest['files'].values()) if kr_manifest else 0)
                        + sum(m['size'] for m in restored.values()), info.total_bytes if replacing_kr else 0)
    undo_kr, undo_manifest = None, None
    if replacing_kr and kr.is_dir():
        undo_kr = run / 'koreader-before-restore.zip'
        plugins, warnings = basic_plugin_audit(kr)
        undo_manifest = create_archive(kr, undo_kr, undo_kr.with_suffix('.manifest.json'), info, plugins, warnings, strict_source=False)
    undo_payload, undo_files = None, {}
    if current_files:
        undo_payload = run / 'library-before-restore.zip'
        undo_files = create_payload_archive(mount, current_files, undo_payload)['files']
    atomic_json(run / 'target-snapshot.json', {'schema_version': 1, 'role': 'target', 'device': asdict(info),
        'confirmed_model': expected, 'replaced_koreader': replacing_kr, 'had_koreader': kr.is_dir(), 'had_adds': kr.parent.exists(), 'koreader': artifact_entry(undo_kr),
        'payload': artifact_entry(undo_payload), 'planned_paths': sorted(set(touched) | set(restored))})
    if not prompt_yes_no(message('confirm.restore_target')):
        safe_eject(mount)
        raise MigrationCancelled('Target restore cancelled. No target files were modified.')
    journal = {'touched': [], 'created_dirs': [], '_mount': mount}
    kr_modified = False
    try:
        confirm_device(mount, original.fingerprint_sha256)
        run_phase('restoring-target', target_modified=True)
        if replacing_kr:
            kr_modified = True
            if kr.exists():
                remove_tree(kr)
            if descriptor.get('had_koreader'):
                if kr_archive is None:
                    raise MigrationError('Original KOReader backup is missing.')
                kr.parent.mkdir(parents=True, exist_ok=True)
                restore_zip(kr_archive, kr.parent)
                verify_restored_tree(kr, kr_manifest)
        for rel in removed:
            path = payload_path(mount, rel)
            journal['touched'].append(rel)
            persist_target_changes(journal)
            path.unlink(missing_ok=True)
        if restored:
            restore_payload(mount, payload_archive, restored, journal)
        for rel in reversed(changes.get('created_dirs', [])):
            directory = checked_path(mount, rel, allow_metadata=rel.startswith('.adds/koreader/'))
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        if replacing_kr and not descriptor.get('had_adds', True) and kr.parent.is_dir() and not any(kr.parent.iterdir()):
            kr.parent.rmdir()
        atomic_json(run / 'restore-result.json', {**restore_plan, 'completed_at': iso_now(), 'tool_version': VERSION})
    except (Exception, KeyboardInterrupt) as exc:
        print(f'Target restore failed: {exc}')
        errors = []
        try:
            confirm_device(mount, original.fingerprint_sha256)
        except Exception as error:
            print(f'Rollback blocked: {error}')
            return 3
        try:
            rollback_payload(mount, undo_payload, undo_files, journal)
        except Exception as error:
            errors.append(str(error))
        if kr_modified:
            try:
                rollback_target(kr, kr.parent, undo_kr, undo_manifest)
            except Exception as error:
                errors.append(str(error))
        if errors:
            print('Rollback errors: ' + '; '.join(errors))
            return 3
        print('Restore failed; automatic rollback restored the pre-restore state.')
        return 2
    safe_eject(mount)
    print('TARGET SNAPSHOT RESTORE SUCCESSFUL.')
    return 0


def select_conflict_policy(mode: str, requested: Optional[str]) -> str:
    if mode in {'full', 'koreader'}:
        if requested == 'keep-target':
            raise MigrationError('--conflict keep-target is only supported by LIBRARY or AUDIT. FULL backs up and overwrites source-matching paths.')
        return 'overwrite'
    if mode == 'audit':
        return requested or 'overwrite'
    return requested or {'1': 'overwrite', '2': 'keep-target'}[choose(
        message('menu.conflict'),
        [('1', message('menu.overwrite')), ('2', message('menu.keep_target'))], default='1')]


def migrate(args, backup_dir: Path, run_id: str, log_path: Path) -> int:
    mode = args.mode or {'1': 'full', '2': 'koreader', '3': 'library', '4': 'audit'}[choose(
        message('menu.mode'),
        [('1', message('menu.full')),
         ('2', message('menu.koreader')),
         ('3', message('menu.library')),
         ('4', message('menu.audit'))], default='1')]
    dry_run = args.dry_run or mode == 'audit'
    full = mode in {'full', 'koreader', 'audit'}
    if mode == 'full':
        if args.books is False or not args.reading_data:
            raise MigrationError('FULL always includes ebooks and reading data. Use KOREADER for directory only, or LIBRARY for selective files.')
        if args.include_dir or args.exclude_dir:
            raise MigrationError('FULL scans the complete supported library. Use LIBRARY or AUDIT for scoped scans.')
        books = True
        fonts = args.fonts if args.fonts is not None else True
    elif mode == 'koreader':
        if args.books is True or args.fonts is True:
            raise MigrationError('KOREADER only migrates the entire KOReader directory. Use FULL or LIBRARY to copy books/fonts.')
        books, fonts = False, False
    else:
        books = args.books if args.books is not None else prompt_yes_no(message('confirm.books'), default=True)
        fonts = args.fonts if args.fonts is not None else prompt_yes_no(message('confirm.fonts'), default=False)
    if not full and not books and not fonts:
        raise MigrationError('LIBRARY requires books and/or fonts.')
    conflict = select_conflict_policy(mode, args.conflict)
    source_expected, target_expected = getattr(args, 'source_model', None), getattr(args, 'target_model', None)
    source_slug, target_slug = 'source', 'target'
    ui_emit('migration.options', mode=mode.upper(), books=books, fonts=fonts, conflict=conflict)
    if dry_run:
        print('DRY RUN / AUDIT: no Kobo files or backup archives will be created, replaced or deleted.')
        print('Local scan reports and execution logs will be saved.')
    print('Disconnect both Kobos. Connect only the requested device.')
    print('Archives may contain credentials; keep them private.')
    if not prompt_yes_no(message('confirm.continue')):
        raise MigrationCancelled('Migration cancelled. No target files were modified.')
    ui_input(message('prompt.source'))
    source_mount = wait_for_single_kobo('SOURCE')
    ensure_local_backup(backup_dir, source_mount.resolve())
    source_kr = checked_path(source_mount, '.adds/koreader', allow_metadata=True)
    if full:
        ensure_source_structure(source_mount)
    if source_kr.is_dir():
        validate_tree_symlinks(source_kr)
    acquire_device(source_mount, device_fingerprint(source_mount)[0])
    source_info = inspect_device(source_mount)
    run_phase('capturing-source', mode=mode, dry_run=dry_run)
    display_device_info(source_info, 'SOURCE')
    require_device_fingerprint(source_info)
    source_expected = confirm_role_model(source_info, source_expected, 'SOURCE')
    source_diag = device_diagnostics(source_mount)
    print(f'Source metadata mode: {source_diag["metadata_mode"]}')
    print(f'Source statistics: {source_diag["statistics"]}')
    print(f'Source missing literal references: {len(source_diag["missing_references"])}')
    scanned, scan_report = scan_payload(source_mount, books, fonts,
        include_metadata=args.reading_data, include_dirs=args.include_dir,
        exclude_dirs=args.exclude_dir, extra_extensions=args.extra_extension)
    # In FULL, the KOReader ZIP already includes all central metadata.
    if full:
        scanned = {rel: meta for rel, meta in scanned.items() if not rel.startswith('.adds/koreader/')}
    print(f'Payload: {len(scanned):,} files, {human_bytes(sum(m["size"] for m in scanned.values()))}')
    for category in ('books', 'sidecars', 'central_metadata', 'fonts', 'unrecognized', 'skipped_symlinks'):
        print(f'  {category}: {len(scan_report[category]):,}')
    for warning in scan_report['warnings']:
        print(f'WARNING: {warning}')
    report_path = backup_dir / f'koreader-scan-{run_id}.json'
    scan_report.update({'tool_version': VERSION, 'mode': mode, 'source_diagnostics': source_diag,
                        'scan_options': {'include_dirs': args.include_dir, 'exclude_dirs': args.exclude_dir, 'extra_extensions': args.extra_extension}})
    report_path.write_text(json.dumps(scan_report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Scan report: {report_path}')
    source_zip = backup_dir / f'koreader-{source_slug}-{run_id}.zip'
    source_manifest_path = source_zip.with_suffix('.manifest.json')
    payload_zip = backup_dir / f'library-{source_slug}-{run_id}.zip'
    source_manifest = None
    payload_manifest = {'files': {}}
    required = (source_info.total_bytes if full else 0) + sum(m['size'] for m in scanned.values())
    ensure_backup_space(backup_dir, required, message('space.source_backup'))
    if full:
        plugins, warnings = basic_plugin_audit(source_kr)
        print(f'Plugin structural audit: {len(plugins)} plugins; {len(warnings)} warnings.')
        for warning in warnings:
            print(f'  {warning}')
        if dry_run:
            print(f'Would archive full KOReader: {source_zip}')
        else:
            source_manifest = create_archive(source_kr, source_zip, source_manifest_path,
                source_info, plugins, warnings)
    if scanned:
        if dry_run:
            payload_manifest = hash_payload(source_mount, scanned)
            print(f'Would archive payload: {payload_zip}')
        else:
            payload_manifest = create_payload_archive(source_mount, scanned, payload_zip)
    if not dry_run:
        save_source_snapshot(backup_dir, source_info, mode, books, fonts, scan_report,
                             source_zip if full else None, payload_zip if scanned else None, confirmed_model=source_expected)
    run_phase('waiting-for-target')
    safe_eject(source_mount)
    print('Unplug SOURCE now.')
    return migrate_target(args, backup_dir, run_id, log_path, mode, dry_run, full, books, fonts,
                          conflict, source_info, source_expected, target_expected, target_slug,
                          source_zip if full else None, source_manifest_path if full else None,
                          source_manifest, payload_zip if scanned else None, payload_manifest,
                          scanned, source_diag, scan_report, report_path)


def migrate_target(args, backup_dir, run_id, log_path, mode, dry_run, full, books, fonts,
                   conflict, source_info, source_expected, target_expected, target_slug,
                   source_zip, source_manifest_path, source_manifest, payload_zip,
                   payload_manifest, scanned, source_diag, scan_report, report_path):
    ui_input(message('prompt.target'))
    target_mount = wait_for_single_kobo('TARGET')
    ensure_local_backup(backup_dir, target_mount.resolve())
    target_kr = checked_path(target_mount, '.adds/koreader', allow_metadata=True)
    target_adds = target_mount / '.adds'
    if target_kr.exists() and not target_kr.is_dir():
        raise MigrationError('Target KOReader path is not a directory.')
    if target_kr.is_dir():
        validate_tree_symlinks(target_kr)
    acquire_device(target_mount, device_fingerprint(target_mount)[0])
    target_info = inspect_device(target_mount)
    run_phase('planning-target', target_fingerprint=target_info.fingerprint_sha256, target_model=target_info.detected_model)
    display_device_info(target_info, 'TARGET')
    require_device_fingerprint(target_info)
    target_expected = confirm_role_model(target_info, target_expected, 'TARGET')
    run_phase('planning-target', target_model=target_expected)
    if full and not prompt_yes_no(message('confirm.compatibility'), default=False):
        raise MigrationCancelled('Runtime compatibility not confirmed. No target files were modified.')
    if (source_info.fingerprint_sha256 and target_info.fingerprint_sha256
            and source_info.fingerprint_sha256 == target_info.fingerprint_sha256):
        raise MigrationError('SOURCE and TARGET have the same Kobo fingerprint.')
    log_status('TARGET preflight: no target files have been modified.')
    target_diag = device_diagnostics(target_mount)
    log_status('TARGET diagnostics complete; starting library comparison.')
    plan = plan_payload(target_mount, payload_manifest, conflict)
    print(f'Payload plan: {len(plan["copy"])} copy, {len(plan["skip"])} identical skipped, '
          f'{len(plan["existing"])} overwritten, {len(plan["conflicts_kept"])} kept on target.')
    kept_books = [rel for rel in plan['conflicts_kept']
                  if payload_manifest['files'][rel].get('category') == 'books']
    if full and kept_books:
        raise MigrationError('FULL cannot keep conflicting target ebooks while cloning source metadata. Use LIBRARY with keep-target, or FULL with overwrite.')
    if plan['metadata_skipped']:
        print(f'WARNING: {len(plan["metadata_skipped"])} metadata files skipped to protect retained target books.')
    difference = build_difference_report(target_mount, payload_manifest['files'], plan, books, fonts, scan_report.get('scan_options', {}))
    write_difference(backup_dir, difference)
    copy_size = sum(m['size'] for m in plan['copy'].values())
    if full:
        ensure_target_space(target_mount, source_info.total_bytes + copy_size, target_info.total_bytes)
    else:
        free = shutil.disk_usage(target_mount).free
        need = int(copy_size * 1.1) + 50 * 1024 * 1024
        ui_emit('space.library', free=human_bytes(free), need=human_bytes(need))
        if free < need:
            raise MigrationError('Not enough target space for the library copy.')
    ensure_backup_space(backup_dir, (target_info.total_bytes if full else 0)
                        + sum(m['size'] for m in plan['existing'].values()), message('space.target_backup'))
    identity_mode = choose_identity_mode(read_device_id(target_kr / 'settings.reader.lua')) if full else None
    target_id = read_device_id(target_kr / 'settings.reader.lua') if full else None
    target_zip = backup_dir / f'koreader-{target_slug}-pre-migration-{run_id}.zip'
    target_manifest_path = target_zip.with_suffix('.manifest.json')
    payload_backup = backup_dir / f'library-{target_slug}-pre-migration-{run_id}.zip'
    scan_report.update({'target_diagnostics_before': target_diag, 'plan': plan,
                        'identity_mode': identity_mode, 'dry_run': dry_run})
    report_path.write_text(json.dumps(scan_report, indent=2, ensure_ascii=False), encoding='utf-8')
    if dry_run:
        if full:
            print(f'Would cleanly replace: {target_kr}')
            print(f'Would back up current KOReader: {target_zip}')
        for rel in plan['copy']:
            print(f'Would {"overwrite (backup first)" if rel in plan["existing"] else "create"}: {rel}')
        print(f'No Kobo files were modified. Detailed plan: {report_path}')
        safe_eject(target_mount)
        return 0
    confirm_device(target_mount, target_info.fingerprint_sha256)
    # Validate saved archives before any target writes.
    log_status('Verifying local source archive checksums before target writes...')
    if full:
        if sha256_file(source_zip) != source_manifest['archive']['sha256']:
            raise MigrationError('Source KOReader archive checksum changed.')
        validate_koreader_zip(source_zip)
    if scanned and sha256_file(payload_zip) != payload_manifest['archive_sha256']:
        raise MigrationError('Source payload archive checksum changed.')
    target_manifest, actual_target_zip = None, None
    if full and target_kr.is_dir():
        plugins, warnings = basic_plugin_audit(target_kr)
        log_status('Backing up the existing TARGET KOReader tree...')
        target_manifest = create_archive(target_kr, target_zip, target_manifest_path,
                                        target_info, plugins, warnings, strict_source=False)
        actual_target_zip = target_zip
    previous, actual_payload_backup = {}, None
    if plan['existing']:
        log_status('Backing up TARGET payload files that will be overwritten...')
        previous = create_payload_archive(target_mount, plan['existing'], payload_backup)['files']
        actual_payload_backup = payload_backup
    atomic_json(backup_dir / 'target-snapshot.json', {'schema_version': 1, 'role': 'target',
        'device': asdict(target_info), 'confirmed_model': target_expected, 'replaced_koreader': full, 'had_koreader': target_kr.is_dir(), 'had_adds': target_adds.exists(),
        'koreader': artifact_entry(actual_target_zip), 'payload': artifact_entry(actual_payload_backup),
        'planned_paths': list(plan['copy'])})
    run_phase('awaiting-final-confirmation')
    print(f'Target FULL replacement: {full}; payload writes: {len(plan["copy"])}')
    print('Only planned paths are affected; unrelated library files are retained.')
    if not prompt_yes_no(message('confirm.migration')):
        safe_eject(target_mount)
        raise MigrationCancelled('Migration cancelled. No target files were modified. Target safely ejected; backups retained.')
    journal = {'touched': [], 'created_dirs': [], '_mount': target_mount}
    persist_target_changes(journal)
    kr_modified = False
    adds_created = False
    try:
        confirm_device(target_mount, target_info.fingerprint_sha256)
        if full:
            run_phase('replacing-koreader', target_modified=True)
            checked_path(target_mount, '.adds/koreader', allow_metadata=True)
            if not target_adds.exists():
                target_adds.mkdir()
                adds_created = True
            kr_modified = True
            if target_kr.exists():
                if not target_kr.is_dir():
                    raise MigrationError('Target KOReader path is not a directory.')
                remove_tree(target_kr)
            restore_zip(source_zip, target_adds)
            remove_stale_caches(target_kr)
            remove_macos_metadata(target_kr)
            verify_restored_tree(target_kr, source_manifest)
            apply_identity_mode(target_kr, identity_mode, target_id)
            ensure_source_structure(target_mount)
        if plan['copy']:
            run_phase('copying-library', target_modified=True)
            restore_payload(target_mount, payload_zip, plan['copy'], journal)
        after = device_diagnostics(target_mount)
        if full and 'statistics' in source_diag and after['statistics'] != source_diag['statistics']:
            raise MigrationError('Statistics rows/check status differ after FULL migration.')
        result = {'tool_version': VERSION, 'mode': mode, 'completed_at': iso_now(),
            'source_model': source_expected, 'target_model': target_expected,
            'source_archive': str(source_zip) if full else None,
            'source_payload': str(payload_zip) if scanned else None,
            'target_backup': str(actual_target_zip) if actual_target_zip else None,
            'target_payload_backup': str(actual_payload_backup) if actual_payload_backup else None,
            'payload_copied': len(plan['copy']), 'identical_skipped': len(plan['skip']),
            'conflicts_kept': len(plan['conflicts_kept']), 'metadata_skipped': len(plan['metadata_skipped']),
            'identity_mode': identity_mode,
            'diagnostics_after': after, 'scan_report': str(report_path), 'log': str(log_path)}
        run_phase('writing-result')
        result_path = backup_dir / f'koreader-migration-result-{run_id}.json'
        result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    except (Exception, KeyboardInterrupt) as exc:
        try:
            run_phase('rolling-back')
        except OSError as status_error:
            log_status(f'Could not update status before rollback: {status_error}')
        print(f'Migration failed: {type(exc).__name__}: {exc}')
        errors = []
        try:
            confirm_device(target_mount, target_info.fingerprint_sha256)
        except Exception as guard_exc:
            print(f'Automatic rollback blocked: {guard_exc}')
            print('Reconnect the original target and recover using the saved backups.')
            return 3
        try:
            rollback_payload(target_mount, actual_payload_backup, previous, journal)
        except Exception as error:
            errors.append(f'Payload: {error}')
        if kr_modified:
            try:
                checked_path(target_mount, '.adds/koreader', allow_metadata=True)
                rollback_target(target_kr, target_adds, actual_target_zip, target_manifest)
                if adds_created and target_adds.exists() and not any(target_adds.iterdir()):
                    target_adds.rmdir()
            except Exception as error:
                errors.append(f'KOReader: {error}')
        if errors:
            for error in errors:
                print(f'ROLLBACK ERROR: {error}')
            print('Keep the target connected for inspection/manual recovery.')
            return 3
        print('Automatic rollback succeeded. Target left connected for inspection.')
        return 2
    ui_emit('migration.success', path=result_path)
    print(f'Missing literal references after migration: {len(after["missing_references"])}')
    run_phase('ejecting-target')
    safe_eject(target_mount)
    ui_emit('migration.done')
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        raise SystemExit(130)
    except MigrationError as exc:
        if not getattr(exc, "ui_reported", False):
            print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
