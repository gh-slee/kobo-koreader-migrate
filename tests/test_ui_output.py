"""Shared UI routing and safety invariants using synthetic streams/devices only."""
from __future__ import annotations
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest import mock
import test_migration as base
import test_management as management
m = base.migration
ROOT = Path(__file__).resolve().parents[1]


class OutputRoutingTests(unittest.TestCase):
    def bundle(self, tag='en'):
        return m.load_locale_bundle(tag, {})

    def test_console_and_english_log_are_separate_without_tee_duplication(self):
        out, errors, log = io.StringIO(), io.StringIO(), io.StringIO()
        with m.ui_session(self.bundle('zh-Hant'), log, out, errors):
            with mock.patch('sys.stdout', m.LogTee(out, log)), mock.patch('sys.stderr', m.LogTee(errors, log)):
                m.ui_emit('catalog.empty')
                m.ui_emit('error.summary', detail='Synthetic checksum failure', channel='stderr', severity='error')
                print('Raw external diagnostic')
        self.assertIn('沒有已儲存的批次', out.getvalue())
        self.assertIn('錯誤：Synthetic checksum failure', errors.getvalue())
        self.assertEqual(log.getvalue().count('No saved runs.'), 1)
        self.assertEqual(log.getvalue().count('ERROR: Synthetic checksum failure'), 1)
        self.assertEqual(log.getvalue().count('Raw external diagnostic'), 1)
        self.assertNotIn('沒有已儲存', log.getvalue())

    def test_standalone_emitter_uses_its_own_bundle_and_preserves_unicode_data(self):
        out, log = io.StringIO(), io.StringIO()
        ui = m.UIOutput(self.bundle('zh-Hans'), log, out, io.StringIO())
        path = 'Books/測試.epub'
        ui.emit('run.log_path', path=path)
        self.assertEqual(out.getvalue(), '日志：' + path + '\n')
        self.assertEqual(log.getvalue(), 'Log: ' + path + '\n')

    def test_render_error_happens_before_either_stream_is_written(self):
        out, log = io.StringIO(), io.StringIO()
        ui = m.UIOutput(self.bundle('zh-Hant'), log, out, io.StringIO())
        with self.assertRaises(m.LocaleError):
            ui.emit('run.log_path', wrong='fixture')
        self.assertEqual((out.getvalue(), log.getvalue()), ('', ''))
        with self.assertRaises(ValueError):
            ui.emit('catalog.empty', channel='invalid')
        self.assertEqual((out.getvalue(), log.getvalue()), ('', ''))

    def test_incompatible_translation_format_falls_back_to_english(self):
        bundle = self.bundle('zh-Hant')
        translated = dict(bundle.messages, **{'run.log_path': '日誌：{path:d}'})
        bundle = m.LocaleBundle(bundle.tag, bundle.registry, bundle.english, translated, ())
        out, log = io.StringIO(), io.StringIO()
        ui = m.UIOutput(bundle, log, out, io.StringIO())
        ui.emit('run.log_path', path='fixture.log')
        self.assertEqual(out.getvalue(), log.getvalue())
        self.assertEqual(out.getvalue(), 'Log: fixture.log\n')

    def test_ascii_console_is_safe_but_log_preserves_utf8_values(self):
        with io.TextIOWrapper(io.BytesIO(), encoding='ascii') as out:
            log = io.StringIO()
            ui = m.UIOutput(self.bundle('zh-Hant'), log, out, io.StringIO())
            ui.emit('run.log_path', path='測試.log')
            out.flush()
            self.assertIn(b'\\u', out.buffer.getvalue())
            self.assertEqual(log.getvalue(), 'Log: 測試.log\n')

    def test_nested_session_and_exception_restore_original_context_and_streams(self):
        self.assertIsNone(m.CURRENT_UI.get())
        stdout, stderr = __import__('sys').stdout, __import__('sys').stderr
        with m.ui_session(self.bundle('zh-Hant')) as outer:
            with self.assertRaisesRegex(RuntimeError, 'fixture'):
                with m.ui_session(self.bundle('zh-Hans')):
                    raise RuntimeError('fixture')
            self.assertIs(m.current_ui(), outer)
        self.assertIsNone(m.CURRENT_UI.get())
        self.assertIs(__import__('sys').stdout, stdout)
        self.assertIs(__import__('sys').stderr, stderr)

    def test_yes_no_keeps_defaults_and_never_logs_answers(self):
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            for answers, default, expected in (([''], False, False), ([''], True, True),
                                                (['secret-response', 'yes'], False, True),
                                                (['是', 'n'], False, False)):
                with self.subTest(tag=tag, answers=answers):
                    out, log = io.StringIO(), io.StringIO()
                    with m.ui_session(self.bundle(tag), log, out, io.StringIO()), \
                         mock.patch('builtins.input', side_effect=answers):
                        self.assertIs(m.prompt_yes_no(m.message('confirm.migration'), default), expected)
                    self.assertIn('Proceed with the planned migration?', log.getvalue())
                    self.assertIn('[Y/n]' if default else '[y/N]', log.getvalue())
                    self.assertNotIn('secret-response', log.getvalue())
                    self.assertNotIn('是', log.getvalue())
                    if tag != 'en':
                        self.assertNotIn('Proceed with the planned migration?', out.getvalue())

    def test_numeric_selection_and_english_string_compatibility_remain_stable(self):
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            out, log = io.StringIO(), io.StringIO()
            with m.ui_session(self.bundle(tag), log, out, io.StringIO()), \
                 mock.patch('builtins.input', side_effect=['wrong', '']):
                choice = m.choose('Fixture menu', [('1', m.message('mode.full')), ('2', m.message('mode.audit'))], default='1')
                question = m.message('confirm.compatibility')
            self.assertEqual(choice, '1')
            self.assertIsInstance(question, str)
            self.assertIn('build is compatible', question)
            self.assertIn('(default)', log.getvalue())
            self.assertIn('Invalid selection.', log.getvalue())

    def test_progress_translates_labels_without_altering_numbers_or_english_log(self):
        out, log = io.StringIO(), io.StringIO()
        with m.ui_session(self.bundle('zh-Hant'), log, out, io.StringIO()):
            m.print_progress(m.message('progress.hash_archive'), 1, 2)
            m.print_progress(m.message('progress.hash_archive'), 2, 2)
            with mock.patch.object(m.time, 'monotonic', side_effect=[0, 3]):
                progress = m.ByteProgress(m.message('progress.hash_file', name='fixture.zip'), 100)
                progress.update(100, final=True)
        self.assertIn('計算封存檔雜湊', out.getvalue())
        self.assertIn('50.0% (1/2)', out.getvalue())
        self.assertIn('Hashing archive', log.getvalue())
        self.assertIn('ETA', log.getvalue())
        self.assertNotIn('計算', log.getvalue())
        self.assertTrue(log.getvalue().endswith('\n'))

    def test_literal_message_ids_have_explicit_parameter_contracts(self):
        tree = ast.parse((ROOT / 'kobo-koreader-migrate.py').read_text())
        ids = {node.args[0].value for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id in {'message', 'ui_emit'} and node.args
               and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)}
        self.assertFalse(ids - set(m.UI_MESSAGE_FIELDS))
        bundle = self.bundle()
        for key, fields in m.UI_MESSAGE_FIELDS.items():
            self.assertEqual(m._template_fields(bundle.english[key]), fields)
        # Mismatched canonical safety fields fail at load, not during a device write.
        data = json.loads((ROOT / 'locales/en.json').read_text())
        data['messages']['confirm.migration'] = 'Proceed {unexpected}?'
        with mock.patch.object(m, '_locale_json', return_value=data):
            with self.assertRaisesRegex(m.LocaleError, 'UI contract'):
                m.load_locale_catalog(ROOT / 'locales', 'en', bundle.registry)


class LocalizedWorkflowTests(base.MigrationTestCase):
    prepare_devices = base.WorkflowTests.prepare_devices

    def execute(self, project, devices, flags):
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            return management.ManagedWorkflowTests.execute(self, project, devices, flags)

    def test_all_modes_have_identical_device_results_across_locales(self):
        root = self.root
        for mode in ('full', 'koreader', 'library', 'audit'):
            expected = None
            for tag in ('en', 'zh-Hant', 'zh-Hans'):
                with self.subTest(mode=mode, tag=tag):
                    self.root = root / mode / tag
                    self.root.mkdir(parents=True)
                    source, target = self.prepare_devices()
                    source_before = base.tree_contents(source)
                    project = self.root / 'project'
                    self.assertEqual(self.execute(project, [source, target], ['--mode', mode, '--books' if mode != 'koreader' else '--no-books', '--no-fonts', '--locale', tag]), (0, 2))
                    self.assertEqual(base.tree_contents(source), source_before)
                    actual = base.tree_contents(target)
                    if expected is None:
                        expected = actual
                    self.assertEqual(actual, expected)
                    run = next((project / 'runs').iterdir())
                    self.assertEqual(m.read_json(run / 'run.json')['ui_locale'], tag)
                    difference = m.read_json(run / 'difference.json')
                    self.assertEqual(difference['ui_locale'], tag)
                    self.assertEqual(set(difference['files']), {'new', 'overwrite', 'identical', 'keep_target', 'metadata_skipped', 'target_only'})
                    log = next(run.glob('*.log')).read_text()
                    self.assertIn('KOReader Kobo Migration Tool', log)
                    for key in ('run.banner', 'difference.title', 'prompt.source'):
                        if tag != 'en':
                            self.assertNotIn(m.load_locale_bundle(tag, {}).messages[key].split('{')[0], log)
                    report = (run / 'difference.txt').read_text()
                    self.assertIn('OVERWRITE', report)
                    if tag != 'en':
                        self.assertIn('差異' if tag == 'zh-Hant' else '差异', report)
        self.root = root

    def test_saved_source_and_exact_restore_remain_equivalent_in_all_locales(self):
        root = self.root
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            self.root = root / tag
            self.root.mkdir()
            source, target = self.prepare_devices()
            before = base.tree_contents(target)
            project = self.root / 'project'
            self.assertEqual(self.execute(project, [source, target], ['--mode', 'full', '--locale', tag])[0], 0)
            saved = max((project / 'runs').iterdir(), key=lambda path: path.stat().st_mtime_ns)
            self.assertEqual(self.execute(project, [target], ['--from-run', saved.name, '--locale', tag]), (0, 1))
            self.assertEqual(self.execute(project, [target], ['--restore-run', saved.name, '--locale', tag]), (0, 1))
            self.assertEqual(base.tree_contents(target), before)
        self.root = root

    def test_cleanup_confirmation_token_is_exact_in_all_locales(self):
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            project = self.root / tag
            for name in ('01', '02', '03'):
                management.LockAndCatalogTests.make_run(self, project, name)
            with m.ui_session(m.load_locale_bundle(tag, {})), mock.patch('builtins.input', return_value='刪除 01'):
                self.assertEqual(m.cleanup_command(project, 2, ['01']), 0)
            self.assertTrue((project / 'runs/01').exists())
            with m.ui_session(m.load_locale_bundle(tag, {})), mock.patch('builtins.input', return_value='DELETE 01'):
                self.assertEqual(m.cleanup_command(project, 2, ['01']), 0)
            self.assertFalse((project / 'runs/01').exists())
            self.assertTrue((project / 'runs/02').exists())

    def test_cancellation_failure_and_interrupt_keep_states_and_context(self):
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            for failure, status, expected in ((m.MigrationCancelled('Fixture cancellation'), 'cancelled', 0),
                                               (m.MigrationError('Fixture failure'), 'failed', None),
                                               (KeyboardInterrupt(), 'interrupted', 130)):
                with self.subTest(tag=tag, status=status):
                    project = self.root / tag / status
                    with mock.patch.object(m, 'migrate', side_effect=failure):
                        if expected is None:
                            with self.assertRaises(m.MigrationError):
                                self.execute(project, [], ['--mode', 'full', '--locale', tag])
                        else:
                            self.assertEqual(self.execute(project, [], ['--mode', 'full', '--locale', tag])[0], expected)
                    run = next((project / 'runs').iterdir())
                    self.assertEqual(m.read_json(run / 'run.json')['status'], status)
                    self.assertIsNone(m.CURRENT_UI.get())
                    self.assertIsNone(m.CURRENT_RUN)
                    self.assertIsNone(m.CURRENT_LOCKS)
                    log = next(run.glob('*.log')).read_text()
                    self.assertIn({'cancelled': 'Fixture cancellation', 'failed': 'Run stopped:', 'interrupted': 'Interrupted by user.'}[status], log)

    def test_final_default_no_never_changes_target_in_any_locale(self):
        root = self.root
        actual_prompt = m.prompt_yes_no
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            self.root = root / tag
            self.root.mkdir()
            source, target = self.prepare_devices()
            before = base.tree_contents(target)
            project = self.root / 'project'
            def confirm(question, default=False):
                if str(question) == 'Proceed with the planned migration?':
                    return actual_prompt(question, default)
                return True
            with mock.patch('sys.argv', ['tool', '--mode', 'full', '--locale', tag,
                                         '--backup-dir', str(project), '--source-model', m.MODEL_CLARA,
                                         '--target-model', m.MODEL_LIBRA]), \
                 mock.patch.object(m, 'require_macos_tools'), \
                 mock.patch.object(m, 'wait_for_single_kobo', side_effect=[source, target]), \
                 mock.patch.object(m, 'run_with_spinner', side_effect=base.fake_ditto), \
                 mock.patch.object(m, 'safe_eject'), \
                 mock.patch.object(m, 'choose_identity_mode', return_value='preserve'), \
                 mock.patch.object(m, 'prompt_yes_no', side_effect=confirm), \
                 mock.patch('builtins.input', return_value=''), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(m.main(), 0)
            self.assertEqual(base.tree_contents(target), before)
            run = next((project / 'runs').iterdir())
            self.assertEqual(m.read_json(run / 'run.json')['status'], 'cancelled')
            self.assertFalse(m.read_json(run / 'run.json')['target_modified'])
        self.root = root

    def test_failure_after_writes_rolls_back_in_all_locales(self):
        root = self.root
        actual_restore = m.restore_payload
        for tag in ('en', 'zh-Hant', 'zh-Hans'):
            self.root = root / tag
            self.root.mkdir()
            source, target = self.prepare_devices()
            before = base.tree_contents(target)
            project = self.root / 'project'
            def restore_then_fail(mount, archive, files, journal):
                actual_restore(mount, archive, files, journal)
                if 'library-source' in archive.name:
                    raise m.MigrationError('Synthetic failure after payload writes')
            with mock.patch.object(m, 'restore_payload', side_effect=restore_then_fail):
                self.assertEqual(self.execute(project, [source, target], ['--mode', 'full', '--locale', tag])[0], 2)
            self.assertEqual(base.tree_contents(target), before)
            run = next((project / 'runs').iterdir())
            self.assertEqual(m.read_json(run / 'run.json')['status'], 'rolled-back')
            self.assertIsNone(m.CURRENT_UI.get())
        self.root = root
