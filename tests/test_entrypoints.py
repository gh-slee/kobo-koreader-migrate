"""Canonical/legacy CLI interoperability with disposable fixtures only."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import test_migration as base

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = 'koreader-bridge.py'
LEGACY = 'kobo-koreader-migrate.py'
spec = importlib.util.spec_from_file_location('bridge_entry_under_test', ROOT / BRIDGE)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class EntryPointTests(base.MigrationTestCase):
    def setUp(self):
        super().setUp()
        self.installation = self.root / 'installation'
        self.installation.mkdir()
        for name in (BRIDGE, LEGACY):
            shutil.copyfile(ROOT / name, self.installation / name)
        shutil.copytree(ROOT / 'locales', self.installation / 'locales')
        self.cwd = self.root / 'unrelated'
        self.cwd.mkdir()
        self.env = dict(os.environ, KOBO_MIGRATE_LOCALE='en', PYTHONDONTWRITEBYTECODE='1',
                        PYTHONIOENCODING='utf-8')

    def command(self, name, *flags):
        return subprocess.run([sys.executable, str(self.installation / name), *flags],
                              cwd=self.cwd, env=self.env, capture_output=True, text=True,
                              timeout=30)

    def test_offline_commands_preserve_program_name_and_match_in_all_locales(self):
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            for flags in (('--version',), ('--help',), ('--list-locales',), ('--preview-ui',)):
                with self.subTest(tag=tag, flags=flags):
                    old = self.command(LEGACY, '--locale', tag, *flags)
                    new = self.command(BRIDGE, '--locale', tag, *flags)
                    self.assertEqual((old.returncode, new.returncode), (0, 0))
                    self.assertEqual(' '.join(old.stdout.replace(LEGACY, 'ENTRY').split()),
                                     ' '.join(new.stdout.replace(BRIDGE, 'ENTRY').split()))
                    self.assertEqual(old.stderr, new.stderr)
                    if flags in (('--version',), ('--help',)):
                        self.assertIn(LEGACY, old.stdout)
                        self.assertIn(BRIDGE, new.stdout)
        self.assertEqual(list(self.cwd.iterdir()), [])
        self.assertFalse((self.installation / 'runs').exists())
        self.assertFalse((self.installation / '.project.lock').exists())

    def test_default_output_root_is_shared_from_an_unrelated_working_directory(self):
        run = self.installation / 'runs' / 'synthetic-saved-run'
        run.mkdir(parents=True)
        (run / 'run.json').write_text(json.dumps({'status': 'success', 'operation': 'migration'}))
        before = base.tree_contents(run)
        outputs = [self.command(name, '--list-runs') for name in (LEGACY, BRIDGE)]
        for result in outputs:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('synthetic-saved-run', result.stdout)
        self.assertEqual(outputs[0].stdout, outputs[1].stdout)
        self.assertEqual(base.tree_contents(run), before)
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_both_entries_refuse_the_same_held_project_lock_before_changes(self):
        with base.migration.FileLock(self.installation / '.project.lock', 'fixture'):
            for name in (BRIDGE, LEGACY):
                result = self.command(name, '--cleanup', '--delete-run', 'synthetic-run')
                self.assertEqual(result.returncode, 1)
                self.assertIn('busy', result.stderr)
        self.assertFalse((self.installation / 'runs').exists())
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_independent_engine_imports_share_device_locks(self):
        bridge_engine = entry.load_engine()
        mount = self.root / 'device'
        mount.mkdir()
        with mock.patch.object(base.migration.tempfile, 'gettempdir', return_value=str(self.root)):
            first, second = base.migration.DeviceLocks(), bridge_engine.DeviceLocks()
            try:
                first.acquire(mount, 'synthetic-device')
                with self.assertRaises(bridge_engine.MigrationError):
                    second.acquire(mount, 'synthetic-device')
                first.close()
                second.acquire(mount, 'synthetic-device')
            finally:
                first.close()
                second.close()

    def test_shared_cli_exit_codes_and_already_reported_errors(self):
        engine = entry.load_engine()
        for reported in (False, True):
            for error, expected in ((KeyboardInterrupt(), 130),
                                    (engine.MigrationError('Synthetic error'), 1)):
                with self.subTest(reported=reported, expected=expected):
                    error.ui_reported = reported
                    output, errors = io.StringIO(), io.StringIO()
                    with mock.patch.object(engine, 'main', side_effect=error), \
                         mock.patch.object(entry, 'load_engine', return_value=engine), \
                         contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                        self.assertEqual(entry.main(), expected)
                    text = output.getvalue() + errors.getvalue()
                    self.assertEqual(bool(text), not reported)


class CrossEntryMigrationTests(base.MigrationTestCase):
    prepare_devices = base.WorkflowTests.prepare_devices

    def execute(self, canonical, engine, project, devices, flags):
        with mock.patch('sys.argv', [BRIDGE if canonical else LEGACY, '--backup-dir', str(project), *flags]), \
             mock.patch.object(engine, 'require_macos_tools'), \
             mock.patch.object(engine, 'run_with_spinner', side_effect=base.fake_ditto), \
             mock.patch.object(engine, 'wait_for_single_kobo', side_effect=devices), \
             mock.patch.object(engine, 'safe_eject'), \
             mock.patch.object(engine, 'choose', return_value='1'), \
             mock.patch.object(engine, 'choose_identity_mode', return_value='preserve'), \
             mock.patch.object(engine, 'prompt_yes_no', return_value=True), \
             mock.patch('builtins.input', return_value=''), \
             mock.patch.object(entry, 'load_engine', return_value=engine):
            return entry.main() if canonical else engine.cli()

    def test_full_transfers_match_and_opposite_entry_restores_exact_target(self):
        root = self.root
        results = []
        for canonical in (False, True):
            self.root = root / ('canonical' if canonical else 'legacy')
            self.root.mkdir()
            source, target = self.prepare_devices()
            source_before, target_before = base.tree_contents(source), base.tree_contents(target)
            engine = entry.load_engine() if canonical else base.migration
            project = self.root / 'output'
            flags = ['--mode', 'full', '--no-fonts', '--source-model', engine.MODEL_CLARA,
                     '--target-model', engine.MODEL_LIBRA]
            self.assertEqual(self.execute(canonical, engine, project, [source, target], flags), 0)
            results.append(base.tree_contents(target))
            self.assertEqual(base.tree_contents(source), source_before)
            saved = next((project / 'runs').iterdir())
            state = json.loads((saved / 'run.json').read_text())
            self.assertEqual(state['status'], 'success')
            archives = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in saved.glob('*.zip')}
            other = base.migration if canonical else entry.load_engine()
            flags = ['--restore-run', saved.name]
            self.assertEqual(self.execute(not canonical, other, project, [target], flags), 0)
            self.assertEqual(base.tree_contents(target), target_before)
            self.assertEqual(base.tree_contents(source), source_before)
            self.assertEqual(archives, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in saved.glob('*.zip')})
        self.assertEqual(results[0], results[1])
        self.root = root

    def test_legacy_manifest_brand_remains_readable_without_rewriting_bytes(self):
        source = self.root / 'source'
        self.make_koreader(source, b'fixture-runtime', 'SOURCE')
        archive, manifest = self.archive_koreader(source, 'source.zip')
        self.assertEqual(manifest['tool'], 'KOReader Bridge ' + base.migration.VERSION)
        manifest['tool'] = 'KOReader Kobo Migration Tool 3.3.0-dev.6'
        old_record = archive.with_suffix('.manifest.json')
        old_record.write_text(json.dumps(manifest))
        before = archive.read_bytes(), old_record.read_bytes()
        engine = entry.load_engine()
        engine.verify_saved_archive(archive, json.loads(old_record.read_text()), 'koreader')
        self.assertEqual((archive.read_bytes(), old_record.read_bytes()), before)
        archive.write_bytes(archive.read_bytes() + b'corrupt')
        with self.assertRaises(engine.MigrationError):
            engine.verify_saved_archive(archive, manifest, 'koreader')
