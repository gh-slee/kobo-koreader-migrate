"""Workflow/recovery presentation invariants using synthetic streams and files only."""
from __future__ import annotations
import contextlib
import io
import json
import os
from types import SimpleNamespace
import unittest
from unittest import mock

import test_migration as base
import test_management as management

m = base.migration
TAGS = ('en', 'zh-Hant', 'zh-Hans')


class RecoveryPresentationTests(base.MigrationTestCase):
    prepare_devices = base.WorkflowTests.prepare_devices

    def streams(self, tag):
        out, errors, log = io.StringIO(), io.StringIO(), io.StringIO()
        return out, errors, log, m.ui_session(m.load_locale_bundle(tag, {}), log, out, errors)

    def execute(self, project, devices, flags):
        self.console, self.errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(self.console), contextlib.redirect_stderr(self.errors), \
             mock.patch.dict(os.environ, {}, clear=True):
            return management.ManagedWorkflowTests.execute(self, project, devices, flags)

    def latest(self, project):
        return management.ManagedWorkflowTests.latest(self, project)

    def test_structured_capacity_error_keeps_english_args_and_machine_data(self):
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            path = self.root / 'synthetic'
            english = f'Not enough free space in {path} for a safe source combined backup.'
            with session, mock.patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
                with self.assertRaises(m.MigrationError) as caught:
                    m.ensure_backup_space(path, 1, m.message('space.source_backup'))
                exc = caught.exception
                self.assertEqual(str(exc), english)
                self.assertEqual(json.loads(json.dumps({'detail': exc.args[0]})), {'detail': english})
                m.ui_emit('error.summary', detail=m.exception_detail(exc), channel='stderr', severity='error')
            self.assertIn('ERROR: ' + english, log.getvalue())
            if tag != 'en':
                self.assertIn('可用空间不足' if tag == 'zh-Hans' else '可用空間不足', errors.getvalue())
                self.assertNotIn('Not enough free space', errors.getvalue())
                self.assertNotIn('source combined', errors.getvalue())
                self.assertNotIn('原始', errors.getvalue())

    def test_unconverted_diagnostics_are_labelled_without_log_translation_or_duplication(self):
        detail = 'Synthetic I/O error: Books/測試.epub'
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            with session, mock.patch('sys.stdout', m.LogTee(out, log)), \
                 mock.patch('sys.stderr', m.LogTee(errors, log)):
                m.ui_emit('error.summary', detail=m.exception_detail(OSError(detail)),
                          channel='stderr', severity='error')
            self.assertIn(detail, errors.getvalue())
            self.assertEqual(log.getvalue(), 'ERROR: ' + detail + '\n')
            self.assertEqual(out.getvalue(), '')
            if tag != 'en':
                self.assertIn('原始诊断（未翻译）' if tag == 'zh-Hans' else '原始診斷（未翻譯）',
                              errors.getvalue())

    def test_eject_output_and_spinner_preserve_commands_numbers_and_english_log(self):
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            mount = self.root / 'unmounted-fixture'
            proc = SimpleNamespace(poll=mock.Mock(side_effect=[None, 0]), returncode=0)
            with session, mock.patch.object(m, 'run_checked', side_effect=['', 'Synthetic diskutil 測試']) as run, \
                 mock.patch.object(m.time, 'sleep'), mock.patch.object(m.subprocess, 'Popen', return_value=proc), \
                 mock.patch.object(m.time, 'monotonic', side_effect=[0, 6, 7]):
                m.safe_eject(mount)
                m.run_with_spinner(['fixture-no-execution'], m.message('archive.creating'))
            self.assertEqual(run.call_args_list, [mock.call(['sync']), mock.call(['diskutil', 'eject', str(mount)])])
            for value in ('Synthetic diskutil 測試', str(mount)):
                self.assertIn(value, out.getvalue())
                self.assertIn(value, log.getvalue())
            self.assertIn('Creating ZIP: still running, elapsed 6s', log.getvalue())
            self.assertIn('Creating ZIP: finished after 7.0s', log.getvalue())
            self.assertEqual(log.getvalue().count('Ejected successfully.'), 1)
            if tag != 'en':
                self.assertNotIn('Ejected successfully.', out.getvalue())
                self.assertNotIn('Creating ZIP:', out.getvalue())

    def test_mode_refusal_stops_before_device_access_in_every_locale(self):
        english = 'FULL always includes ebooks and reading data. Use KOREADER for directory only, or LIBRARY for selective files.'
        for tag in TAGS:
            project = self.root / tag
            with mock.patch.object(m, 'wait_for_single_kobo') as devices:
                with self.assertRaisesRegex(m.MigrationError, 'FULL always includes ebooks'):
                    self.execute(project, [], ['--mode', 'full', '--no-books', '--locale', tag])
                devices.assert_not_called()
            run = self.latest(project)
            state = m.read_json(run / 'run.json')
            self.assertEqual((state['status'], state['exit_code'], state['target_modified']), ('failed', 1, False))
            log = next(run.glob('*.log')).read_text()
            self.assertIn('Run stopped: MigrationError: ' + english, log)
            self.assertFalse(list(run.glob('*.zip')))
            if tag != 'en':
                self.assertNotIn(english, self.console.getvalue() + self.errors.getvalue())
                self.assertIn('FULL 一律包含', self.errors.getvalue())

    def test_migration_failure_after_writes_has_localized_successful_rollback(self):
        root, actual_restore = self.root, m.restore_payload
        for tag in TAGS:
            self.root = root / tag
            self.root.mkdir()
            source, target = self.prepare_devices()
            before, source_before = base.tree_contents(target), base.tree_contents(source)
            project = self.root / 'project'
            def restore_then_fail(mount, archive, files, journal):
                actual_restore(mount, archive, files, journal)
                if 'library-source' in archive.name:
                    raise m.MigrationError(m.message('error.statistics_changed'))
            with mock.patch.object(m, 'restore_payload', side_effect=restore_then_fail):
                self.assertEqual(self.execute(project, [source, target], ['--mode', 'full', '--locale', tag])[0], 2)
            self.assertEqual(base.tree_contents(target), before)
            self.assertEqual(base.tree_contents(source), source_before)
            run = self.latest(project)
            state = m.read_json(run / 'run.json')
            self.assertEqual((state['status'], state['exit_code']), ('rolled-back', 2))
            log = next(run.glob('*.log')).read_text()
            self.assertIn('Migration failed: MigrationError: Statistics rows/check status differ after FULL migration.', log)
            self.assertIn('Automatic rollback succeeded.', log)
            if tag != 'en':
                self.assertNotIn('Statistics rows/check status differ', self.console.getvalue())
                self.assertIn('自動回復成功' if tag == 'zh-Hant' else '自动回滚成功', self.console.getvalue())
        self.root = root

    def test_changed_device_blocks_rollback_without_further_writes(self):
        root, actual_restore, actual_confirm = self.root, m.restore_payload, m.confirm_device
        for tag in TAGS:
            self.root = root / tag
            self.root.mkdir()
            source, target = self.prepare_devices()
            source_before = base.tree_contents(source)
            project = self.root / 'project'
            guard_calls, blocked_tree = [], []
            def restore_then_fail(mount, archive, files, journal):
                actual_restore(mount, archive, files, journal)
                if 'library-source' in archive.name:
                    raise OSError('Synthetic failure after writes')
            def confirm(mount, fingerprint):
                guard_calls.append(mount)
                if len(guard_calls) == 3:
                    blocked_tree.append(base.tree_contents(target))
                    raise m.MigrationError(m.message('error.device_changed'))
                return actual_confirm(mount, fingerprint)
            with mock.patch.object(m, 'restore_payload', side_effect=restore_then_fail), \
                 mock.patch.object(m, 'confirm_device', side_effect=confirm):
                self.assertEqual(self.execute(project, [source, target], ['--mode', 'full', '--locale', tag])[0], 3)
            self.assertEqual(len(guard_calls), 3)
            self.assertEqual(base.tree_contents(target), blocked_tree[0])
            self.assertEqual(base.tree_contents(source), source_before)
            run = self.latest(project)
            self.assertEqual(m.read_json(run / 'run.json')['status'], 'needs-recovery')
            log = next(run.glob('*.log')).read_text()
            self.assertIn('Automatic rollback blocked: Connected device changed; refusing to modify it.', log)
            if tag != 'en':
                self.assertNotIn('Connected device changed', self.console.getvalue())
                self.assertIn('原本的目標' if tag == 'zh-Hant' else '原本的目标', self.console.getvalue())
        self.root = root

    def test_rollback_failure_keeps_raw_detail_and_needs_recovery_status(self):
        root, actual_restore = self.root, m.restore_payload
        for tag in TAGS:
            self.root = root / tag
            self.root.mkdir()
            source, target = self.prepare_devices()
            project = self.root / 'project'
            def restore_then_fail(mount, archive, files, journal):
                actual_restore(mount, archive, files, journal)
                raise OSError('Synthetic write failure')
            with mock.patch.object(m, 'restore_payload', side_effect=restore_then_fail), \
                 mock.patch.object(m, 'rollback_payload', side_effect=PermissionError('Synthetic 測試 denied')):
                self.assertEqual(self.execute(project, [source, target], ['--mode', 'full', '--locale', tag])[0], 3)
            run = self.latest(project)
            self.assertEqual(m.read_json(run / 'run.json')['status'], 'needs-recovery')
            log = next(run.glob('*.log')).read_text()
            self.assertIn('ROLLBACK ERROR: Payload: Synthetic 測試 denied', log)
            self.assertIn('Synthetic 測試 denied', self.console.getvalue())
            self.assertNotIn('Automatic rollback succeeded.', log)
            if tag != 'en':
                self.assertIn('原始诊断（未翻译）' if tag == 'zh-Hans' else '原始診斷（未翻譯）',
                              self.console.getvalue())
        self.root = root

    def test_restore_failure_undo_and_changed_device_guard_preserve_exit_states(self):
        root, actual_restore, actual_confirm = self.root, m.restore_payload, m.confirm_device
        for tag in TAGS:
            for blocked in (False, True):
                with self.subTest(tag=tag, blocked=blocked):
                    self.root = root / tag / str(blocked)
                    self.root.mkdir(parents=True)
                    source, target = self.prepare_devices()
                    project = self.root / 'project'
                    self.assertEqual(self.execute(project, [source, target], ['--mode', 'full', '--locale', tag])[0], 0)
                    saved = self.latest(project)
                    before_restore = base.tree_contents(target)
                    calls, blocked_tree = [], []
                    def restore_then_fail(mount, archive, files, journal):
                        actual_restore(mount, archive, files, journal)
                        if 'pre-migration' in archive.name:
                            raise OSError('Synthetic restore failure')
                    def confirm(mount, fingerprint):
                        calls.append(mount)
                        if blocked and len(calls) == 3:
                            blocked_tree.append(base.tree_contents(target))
                            raise m.MigrationError(m.message('error.device_changed'))
                        return actual_confirm(mount, fingerprint)
                    with mock.patch.object(m, 'restore_payload', side_effect=restore_then_fail), \
                         mock.patch.object(m, 'confirm_device', side_effect=confirm):
                        code = self.execute(project, [target], ['--restore-run', saved.name, '--locale', tag])[0]
                    self.assertEqual(code, 3 if blocked else 2)
                    run = self.latest(project)
                    self.assertEqual(m.read_json(run / 'run.json')['status'], 'needs-recovery' if blocked else 'rolled-back')
                    self.assertEqual(base.tree_contents(target), blocked_tree[0] if blocked else before_restore)
                    log = next(run.glob('*.log')).read_text()
                    self.assertIn('Target restore failed: Synthetic restore failure', log)
                    self.assertIn('Rollback blocked:' if blocked else 'automatic rollback restored the pre-restore state.', log)
                    if tag != 'en':
                        self.assertNotIn('Target restore failed:', self.console.getvalue())
        self.root = root

    def test_pre_run_interrupt_is_reported_once_without_creating_a_run(self):
        for tag in TAGS:
            console = io.StringIO()
            project = self.root / tag
            with mock.patch('sys.argv', ['tool', '--locale', tag, '--backup-dir', str(project)]), \
                 mock.patch.object(m, 'run_main', side_effect=KeyboardInterrupt()), \
                 contextlib.redirect_stdout(console):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    m.main()
            self.assertTrue(caught.exception.ui_reported)
            self.assertEqual(len(console.getvalue().strip().splitlines()), 1)
            self.assertFalse(project.exists())
            self.assertIsNone(m.CURRENT_UI.get())
            if tag != 'en':
                self.assertNotIn('Cancelled by user.', console.getvalue())


if __name__ == '__main__':
    unittest.main()
