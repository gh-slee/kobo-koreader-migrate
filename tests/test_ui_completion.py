"""Owned CLI coverage and localization safety; temporary fixtures only."""
from __future__ import annotations
import ast
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

import test_migration as base
m = base.migration
TAGS = ('en','zh-Hant','zh-Hans')
ROOT = Path(__file__).resolve().parents[1]


class CompletionTests(base.MigrationTestCase):
    def streams(self, tag):
        out, errors, log = io.StringIO(), io.StringIO(), io.StringIO()
        return out, errors, log, m.ui_session(m.load_locale_bundle(tag,{}),log,out,errors)

    def test_owned_error_status_and_parser_sites_cannot_silently_bypass_catalogs(self):
        tree = ast.parse((ROOT/'kobo-koreader-migrate.py').read_text())
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call):
                continue
            if isinstance(node.func,ast.Name) and node.func.id in {'MigrationError','MigrationCancelled','log_status'}:
                self.assertTrue(node.args, node.lineno)
                arg = node.args[0]
                self.assertIsInstance(arg,ast.Call,node.lineno)
                self.assertIsInstance(arg.func,ast.Name,node.lineno)
                self.assertEqual(arg.func.id,'message',node.lineno)
            if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) \
                    and node.func.value.id == 'parser' and node.func.attr == 'error':
                self.assertEqual(ast.unparse(node.args[0].func),'bundle.render',node.lineno)
        # Only blank/decorative print calls are allowed inside runtime functions.
        # The module wrapper keeps minimal English output when no UI can be used.
        for function in (node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))):
            for node in ast.walk(function):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id == 'print' and node.args:
                    self.assertEqual(ast.unparse(node.args[0]), "'-' * 60", node.lineno)

    def test_cleanup_reason_translation_keeps_protection_and_serialized_values(self):
        records = [
            dict(run_id='recent',status='success',ended_at='5',bytes=1,dependencies=[]),
            dict(run_id='recovery',status='success',ended_at='4',bytes=2,dependencies=[],target_fingerprint='fixture'),
            dict(run_id='dependency',status='success',ended_at='3',bytes=3,dependencies=[]),
            dict(run_id='failed',status='failed',ended_at='2',bytes=4,dependencies=['dependency']),
            dict(run_id='eligible',status='success',ended_at='1',bytes=5,dependencies=[]),
        ]
        records = [dict(operation='migration',**record) for record in records]
        expected = None
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            with session, mock.patch.object(m,'run_catalog',return_value=records):
                plan = m.cleanup_plan(self.root,1)
                m.cleanup_command(self.root,1,[])
            encoded = json.dumps(plan,sort_keys=True)
            if expected is None:
                expected = encoded
            self.assertEqual(encoded,expected)
            self.assertEqual([record['run_id'] for record in plan['candidates']],['eligible'])
            self.assertEqual(plan['reclaimable_bytes'],5)
            self.assertEqual({record['run_id'] for record in plan['protected']},
                             {'recent','recovery','dependency','failed'})
            self.assertIn('recent successful run',log.getvalue())
            self.assertIn('not a confirmed successful run',log.getvalue())
            if tag != 'en':
                self.assertNotIn('recent successful run',out.getvalue())
                self.assertNotIn('not a confirmed successful run',out.getvalue())
                self.assertIn('近期成功批次',out.getvalue())

    def test_scan_warnings_remain_english_json_and_render_as_owned_messages(self):
        source = self.root/'source'
        base.write_file(source/'Books/example.epub',b'synthetic')
        before = base.tree_contents(source)
        expected = None
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            with session:
                files, report = m.scan_payload(source,True,False)
                for warning in report['warnings']:
                    m.ui_emit('diagnostic.warning',detail=m.diagnostic_detail(warning))
                _, scoped = m.scan_payload(source,True,False,include_dirs=['Books'])
                for warning in scoped['warnings']:
                    m.ui_emit('diagnostic.warning',detail=m.diagnostic_detail(warning))
            encoded = json.dumps(report,sort_keys=True)
            if expected is None:
                expected = encoded
            self.assertEqual(encoded,expected)
            self.assertIn('Central metadata is copied as complete trees; no Lua data is merged.',encoded)
            self.assertIn('Scoped scan:',log.getvalue())
            self.assertEqual(base.tree_contents(source),before)
            if tag != 'en':
                self.assertNotIn('Central metadata is copied',out.getvalue())
                self.assertNotIn('Scoped scan:',out.getvalue())
                self.assertNotIn('原始診斷',out.getvalue())
                self.assertNotIn('原始诊断',out.getvalue())

    def test_plugin_audit_warnings_have_structured_display_and_english_manifest_values(self):
        kr = self.root/'koreader'
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            with session:
                _, missing = m.basic_plugin_audit(kr/'absent')
                plugin = kr/'plugins/example.koplugin'
                plugin.mkdir(parents=True,exist_ok=True)
                plugins, warnings = m.basic_plugin_audit(kr)
                for warning in missing + warnings:
                    m.ui_emit('diagnostic.plugin_warning',detail=m.diagnostic_detail(warning))
            self.assertEqual(plugins,['example.koplugin'])
            self.assertEqual(json.loads(json.dumps(warnings)),
                             ['example.koplugin: main.lua missing','example.koplugin: _meta.lua missing'])
            self.assertIn('plugins/ directory is missing',log.getvalue())
            if tag != 'en':
                self.assertNotIn('main.lua missing',out.getvalue())
                self.assertIn('缺少 main.lua',out.getvalue())
                self.assertNotIn('未翻譯',out.getvalue())
                self.assertNotIn('未翻译',out.getvalue())

    def test_comparison_output_keeps_plan_and_device_bytes_language_independent(self):
        source, target = self.root/'source',self.root/'target'
        base.write_file(source/'same.epub',b'same')
        base.write_file(source/'changed.epub',b'source')
        base.write_file(source/'測試.epub',b'new')
        base.write_file(target/'same.epub',b'same')
        base.write_file(target/'changed.epub',b'target')
        before_source, before_target = base.tree_contents(source), base.tree_contents(target)
        expected = None
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            with session:
                files,_ = m.scan_payload(source,True,False)
                manifest = m.hash_payload(source,files)
                plan = m.plan_payload(target,manifest,'keep-target')
            encoded = json.dumps(plan,sort_keys=True)
            if expected is None:
                expected = encoded
            self.assertEqual(encoded,expected)
            self.assertEqual(base.tree_contents(source),before_source)
            self.assertEqual(base.tree_contents(target),before_target)
            for text in ('Comparing TARGET payload:', 'Different: keeping TARGET.', 'Identical: skipped.','New: will copy.','測試.epub'):
                self.assertIn(text,log.getvalue())
            if tag != 'en':
                self.assertNotIn('Comparing TARGET payload:',out.getvalue())
                self.assertIn('測試.epub',out.getvalue())

    def test_unsafe_archive_refusal_translates_without_extraction_or_arg_changes(self):
        archive = self.root/'unsafe.zip'
        with zipfile.ZipFile(archive,'w') as zf:
            zf.writestr('koreader/../outside.lua',b'synthetic')
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            with session:
                with self.assertRaises(m.MigrationError) as caught:
                    m.validate_koreader_zip(archive)
                self.assertEqual(str(caught.exception),'Unsafe KOReader ZIP member: koreader/../outside.lua')
                m.ui_emit('error.summary',detail=m.exception_detail(caught.exception),channel='stderr',severity='error')
            self.assertFalse((self.root/'outside.lua').exists())
            self.assertIn('Unsafe KOReader ZIP member:',log.getvalue())
            if tag != 'en':
                self.assertIn('不安全的 KOReader ZIP',errors.getvalue())
                self.assertNotIn('Unsafe KOReader ZIP',errors.getvalue())

    def test_custom_cli_refusals_are_localized_before_run_or_device_access(self):
        cases = [
            ['--delete-run','fixture'],
            ['--cleanup','--keep-successful','0'],
            ['--restore-run','fixture','--mode','full'],
            ['--preview-ui','--books'],
        ]
        for tag in TAGS:
            for flags in cases:
                with self.subTest(tag=tag,flags=flags):
                    project = self.root/tag
                    errors = io.StringIO()
                    with mock.patch('sys.argv',['tool','--locale',tag,'--backup-dir',str(project)]+flags), \
                         mock.patch.dict(os.environ,{},clear=True), mock.patch.object(m,'run_main') as run, \
                         mock.patch.object(m,'wait_for_single_kobo') as device, contextlib.redirect_stderr(errors):
                        with self.assertRaises(SystemExit) as caught:
                            m.main()
                    self.assertEqual(caught.exception.code,2)
                    run.assert_not_called()
                    device.assert_not_called()
                    self.assertFalse(project.exists())
                    if tag != 'en':
                        self.assertTrue(any('\u3400' <= char <= '\u9fff' for char in errors.getvalue()))

    def test_command_and_nested_recovery_details_keep_original_english_logs(self):
        detail = 'Synthetic external detail 測試'
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            with session, mock.patch.object(m.subprocess,'run',return_value=SimpleNamespace(
                    returncode=7,stderr=detail,stdout='')) as command:
                with self.assertRaises(m.MigrationError) as caught:
                    m.run_checked(['fixture','--value'])
                self.assertEqual(str(caught.exception),'Command failed (7): fixture --value\n'+detail)
                first = m.exception_detail(caught.exception)
                second = m.exception_detail(m.MigrationError(m.message('error.manifest_path')))
                m.ui_emit('restore.rollback_errors',detail=m.join_diagnostics([first,second]))
            command.assert_called_once_with(['fixture','--value'],capture_output=True,text=True)
            self.assertEqual(log.getvalue(),'Rollback errors: Command failed (7): fixture --value\n'+detail+'; Unsafe manifest path.\n')
            if tag != 'en':
                self.assertNotIn('Unsafe manifest path.',out.getvalue())
                self.assertNotIn('Command failed (7)',out.getvalue())
                self.assertIn(detail,out.getvalue())

    def test_busy_lock_still_refuses_and_records_english_label(self):
        for tag in TAGS:
            out, errors, log, session = self.streams(tag)
            path = self.root/(tag+'.lock')
            with session, m.FileLock(path,m.message('lock.project')):
                with self.assertRaises(m.MigrationError) as caught:
                    with m.FileLock(path,m.message('lock.project')):
                        self.fail('A second lock must never succeed.')
                self.assertEqual(str(caught.exception),
                    'Project is busy in another process. Wait for it to finish; do not remove the lock file.')
                m.ui_emit('error.summary',detail=m.exception_detail(caught.exception),channel='stderr')
                self.assertEqual(json.loads(path.read_text())['label'],'Project')
            if tag != 'en':
                self.assertNotIn('is busy in another process',errors.getvalue())


if __name__ == '__main__':
    unittest.main()
