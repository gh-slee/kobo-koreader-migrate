"""Localized menu and inspection behavior; only synthetic streams and devices."""
from __future__ import annotations
import contextlib
from dataclasses import asdict
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import test_migration as base
import test_management as management
m = base.migration


class MenuInspectionTests(base.MigrationTestCase):
    prepare_devices = base.WorkflowTests.prepare_devices

    def streams(self, tag):
        out, log = io.StringIO(), io.StringIO()
        return out, log, m.ui_session(m.load_locale_bundle(tag, {}), log, out, io.StringIO())

    def test_identity_choices_and_defaults_are_language_independent(self):
        cases = [('TARGET-ID', [''], 'preserve'), ('TARGET-ID', ['2'], 'new'),
                 ('TARGET-ID', ['3'], 'clone'), (None, [''], 'new')]
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            for identity, answers, expected in cases:
                with self.subTest(tag=tag, expected=expected):
                    out, log, session = self.streams(tag)
                    with session, mock.patch('builtins.input', side_effect=answers):
                        self.assertEqual(m.choose_identity_mode(identity), expected)
                    self.assertIn('Target KOReader identity:', log.getvalue())
                    self.assertIn('Clone SOURCE device_id exactly', log.getvalue())
                    self.assertIn('  2)', out.getvalue())
                    self.assertIn('  3)', out.getvalue())
                    if tag != 'en':
                        self.assertNotIn('Target KOReader identity:', out.getvalue())

    def test_missing_target_identity_cannot_be_preserved_in_any_locale(self):
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            out, log, session = self.streams(tag)
            with session, mock.patch('builtins.input', side_effect=['bad', '1', '']):
                self.assertEqual(m.choose_identity_mode(None), 'new')
            self.assertIn('Invalid selection.', log.getvalue())
            self.assertIn('No target device_id was found; choose option 2 or 3.', log.getvalue())
            self.assertIn('unavailable: none found', log.getvalue())

    def test_conflict_menu_and_full_mode_restrictions_are_unchanged(self):
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            for answer, expected in (('', 'overwrite'), ('1', 'overwrite'), ('2', 'keep-target')):
                out, log, session = self.streams(tag)
                with session, mock.patch('builtins.input', return_value=answer):
                    self.assertEqual(m.select_conflict_policy('library', None), expected)
                self.assertIn('Different payload files at an existing path:', log.getvalue())
                if tag != 'en':
                    self.assertNotIn('Keep TARGET file', out.getvalue())
            _, _, session = self.streams(tag)
            with session, mock.patch.object(m, 'choose') as choose:
                for mode in ('full', 'koreader'):
                    self.assertEqual(m.select_conflict_policy(mode, None), 'overwrite')
                    with self.assertRaises(m.MigrationError):
                        m.select_conflict_policy(mode, 'keep-target')
                self.assertEqual(m.select_conflict_policy('audit', 'keep-target'), 'keep-target')
                self.assertEqual(m.select_conflict_policy('library', 'keep-target'), 'keep-target')
                choose.assert_not_called()

    def test_actual_mode_menu_numbers_and_default_reach_same_safe_cancellation(self):
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            for answer, expected in (('', 'FULL'), ('1', 'FULL'), ('2', 'KOREADER'),
                                     ('3', 'LIBRARY'), ('4', 'AUDIT')):
                with self.subTest(tag=tag, answer=answer):
                    project = self.root / tag / (answer or 'default')
                    flags = ['--no-books' if answer == '2' else '--books', '--no-fonts']
                    with mock.patch('sys.argv', ['tool', '--locale', tag, '--backup-dir', str(project),
                                                 '--conflict', 'overwrite'] + flags), \
                         mock.patch.object(m, 'require_macos_tools'), \
                         mock.patch.object(m, 'prompt_yes_no', return_value=False), \
                         mock.patch.object(m, 'wait_for_single_kobo') as devices, \
                         mock.patch('builtins.input', return_value=answer), \
                         contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(m.main(), 0)
                    devices.assert_not_called()
                    run = next((project / 'runs').iterdir())
                    state = m.read_json(run / 'run.json')
                    self.assertEqual(state['status'], 'cancelled')
                    self.assertFalse(state['target_modified'])
                    log = next(run.glob('*.log')).read_text()
                    self.assertIn('Choose migration mode:', log)
                    self.assertIn('Mode: ' + expected + ';', log)
                    self.assertIn('1) FULL:', log)
                    self.assertIn('4) AUDIT:', log)
                    self.assertFalse(list(run.glob('*.zip')))

    def test_inspection_translates_labels_and_values_but_preserves_device_data(self):
        info = m.DeviceInfo('Synthetic/測試', 'Kobo Synthetic', 'v0.0-fixture',
                            'fixture-fingerprint', '***fixture', True, False, 1234, 2048)
        original = asdict(info)
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            out, log, session = self.streams(tag)
            with session:
                m.display_device_info(info, 'SOURCE')
            self.assertEqual(asdict(info), original)
            for value in ('Synthetic/測試', 'Kobo Synthetic', 'v0.0-fixture', '***fixture', '1,234', '2.0 KiB'):
                self.assertIn(value, out.getvalue())
                self.assertIn(value, log.getvalue())
            self.assertIn('SOURCE device inspection', log.getvalue())
            self.assertIn('device_id present:  yes', log.getvalue())
            self.assertIn('AI Assistant cfg:   no', log.getvalue())
            if tag != 'en':
                self.assertNotIn('Model hint (logs)', out.getvalue())
                self.assertNotIn('device_id present', out.getvalue())

    def test_unknown_values_are_localized_and_absent_serial_is_not_invented(self):
        info = m.DeviceInfo('Synthetic', None, None, 'fixture', None, False, True, 0, 0)
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            out, log, session = self.streams(tag)
            with session:
                m.display_device_info(info, 'TARGET')
            self.assertIn('Model hint (logs):   Unknown', log.getvalue())
            self.assertIn('KOReader version:   Unknown', log.getvalue())
            self.assertNotIn('Device serial hint', log.getvalue())
            if tag != 'en':
                self.assertIn('未知', out.getvalue())

    def test_physical_model_confirmation_still_defaults_to_no_despite_log_hint(self):
        info = m.DeviceInfo('Synthetic', 'Kobo Clara 2E', None, 'fixture', None, False, False, 0, 0)
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            out, log, session = self.streams(tag)
            with session, mock.patch('builtins.input', side_effect=['Sage', '']):
                with self.assertRaises(m.MigrationCancelled):
                    m.confirm_role_model(info, None, 'TARGET')
            self.assertIn('do not prove the physical model', log.getvalue())
            self.assertIn('physical model entered is Kobo Sage', log.getvalue())
            self.assertIn('[y/N]', log.getvalue())
            self.assertNotIn('Operator confirmed', log.getvalue())
            self.assertEqual(info.detected_model, 'Kobo Clara 2E')

    def test_unknown_model_retry_and_confirmed_labels_are_generic_in_all_locales(self):
        info = m.DeviceInfo('Synthetic', None, None, 'fixture', None, False, False, 0, 0)
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            out, log, session = self.streams(tag)
            with session, mock.patch('builtins.input', side_effect=['', 'Elipsa 2E', 'y']):
                self.assertEqual(m.confirm_role_model(info, None, 'SOURCE'), 'Kobo Elipsa 2E')
            self.assertIn('Enter a model name', log.getvalue())
            self.assertIn('Operator confirmed SOURCE: Kobo Elipsa 2E', log.getvalue())
            self.assertIn('Kobo Elipsa 2E', out.getvalue())
            if tag != 'en':
                self.assertNotIn('Physical SOURCE model', out.getvalue())

    def test_backup_space_threshold_and_english_error_are_unchanged(self):
        size = 10 * 1024 * 1024
        need = int(size * 1.10) + 100 * 1024 * 1024
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            for free in (need - 1, need, need + 1):
                out, log, session = self.streams(tag)
                with session, mock.patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=free)):
                    if free < need:
                        with self.assertRaisesRegex(m.MigrationError, 'safe source combined backup'):
                            m.ensure_backup_space(Path('Synthetic'), size, m.message('space.source_backup'))
                    else:
                        m.ensure_backup_space(Path('Synthetic'), size, m.message('space.source_backup'))
                self.assertIn('source combined backup-space check:', log.getvalue())
                self.assertIn(m.human_bytes(need), log.getvalue())
                self.assertIn(m.human_bytes(free), out.getvalue())
                if tag != 'en':
                    self.assertNotIn('backup-space check', out.getvalue())

    def test_target_space_counts_replaced_runtime_and_keeps_same_boundary(self):
        size, existing = 10 * 1024 * 1024, 2 * 1024 * 1024
        need = int(size * 1.10) + 50 * 1024 * 1024
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            for effective in (need - 1, need, need + 1):
                free = effective - existing
                out, log, session = self.streams(tag)
                with session, mock.patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=free)):
                    if effective < need:
                        with self.assertRaisesRegex(m.MigrationError, 'not have enough free space'):
                            m.ensure_target_space(Path('Synthetic'), size, existing)
                    else:
                        m.ensure_target_space(Path('Synthetic'), size, existing)
                self.assertIn(m.human_bytes(effective) + ' effective', log.getvalue())
                self.assertIn(m.human_bytes(need), out.getvalue())

    def test_library_low_space_refuses_before_target_backup_or_writes_in_all_locales(self):
        root = self.root
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            self.root = root / tag
            self.root.mkdir()
            source, target = self.prepare_devices()
            before_source, before_target = base.tree_contents(source), base.tree_contents(target)
            project = self.root / 'project'
            def usage(path):
                return SimpleNamespace(free=0 if Path(path) == target else 1024**4)
            with mock.patch.object(m.shutil, 'disk_usage', side_effect=usage), \
                 mock.patch.dict(os.environ, {}, clear=True), \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(m.MigrationError, 'Not enough target space for the library copy'):
                    management.ManagedWorkflowTests.execute(self, project, [source, target],
                                                           ['--mode', 'library', '--books', '--no-fonts', '--locale', tag])
            self.assertEqual(base.tree_contents(source), before_source)
            self.assertEqual(base.tree_contents(target), before_target)
            run = next((project / 'runs').iterdir())
            self.assertFalse(m.read_json(run / 'run.json')['target_modified'])
            self.assertFalse(list(run.glob('*pre-migration*.zip')))
            self.assertIn('Library target-space check:', next(run.glob('*.log')).read_text())
        self.root = root
