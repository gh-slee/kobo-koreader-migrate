"""Offline locale foundation regressions; all malformed assets are synthetic."""
from __future__ import annotations
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import test_migration as base
m = base.migration
ROOT = Path(__file__).resolve().parents[1]


class LocaleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.locales = self.root / 'locales'
        shutil.copytree(ROOT / 'locales', self.locales)

    def read(self, tag):
        return json.loads((self.locales / (tag + '.json')).read_text())

    def write(self, tag, data):
        (self.locales / (tag + '.json')).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def bundle(self, tag=None, env=None):
        return m.load_locale_bundle(tag, {} if env is None else env, self.locales)

    def cli(self, flags, expected=0):
        output, errors = io.StringIO(), io.StringIO()
        project = self.root / 'should-not-be-created'
        with mock.patch.object(m, 'LOCALE_ROOT', self.locales), \
             mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch('sys.argv', ['tool', '--backup-dir', str(project)] + flags), \
             mock.patch.object(m, 'require_macos_tools') as require, \
             mock.patch.object(m, 'wait_for_single_kobo') as devices, \
             mock.patch.object(m, 'run_catalog') as catalog, \
             mock.patch.object(m, 'FileLock') as lock, \
             mock.patch('socket.socket', side_effect=AssertionError('Network not allowed')), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                result = m.main()
            except SystemExit as error:
                result = error.code
            self.assertEqual(result, expected, errors.getvalue())
            for operation in (require, devices, catalog, lock):
                operation.assert_not_called()
        self.assertFalse(project.exists())
        return output.getvalue(), errors.getvalue()

    def test_all_shipped_catalogs_have_complete_valid_foundation_coverage(self):
        registry = m.load_locale_registry(ROOT/'locales')
        english = m.load_locale_catalog(ROOT/'locales', 'en', registry)
        self.assertEqual(set(registry['entries']), {'en','zh-Hant','zh-Hans'})
        for tag in registry['entries']:
            m.load_locale_catalog(ROOT/'locales', tag, registry, None if tag=='en' else english, complete=True)

    def test_canonical_startup_placeholders_fail_before_rendering(self):
        data = self.read('en')
        data['messages']['help.mode'] = 'Unsupported parameter {private_value}'
        self.write('en', data)
        with self.assertRaisesRegex(m.LocaleError, 'startup contract'):
            self.bundle()
        self.cli(['--help'], expected=2)

    def test_explicit_selection_aliases_and_script_priority(self):
        cases = {'en':'en','en_US.UTF-8':'en','en-CA':'en', 'EN-gb':'en',
                 'zh-Hant':'zh-Hant','zh_TW.UTF-8':'zh-Hant','zh-HK':'zh-Hant', 'zh-MO':'zh-Hant',
                 'zh-Hans':'zh-Hans','zh_CN.UTF-8':'zh-Hans','zh-SG':'zh-Hans',
                 'zh-Hant-CN':'zh-Hant','zh-Hans-TW':'zh-Hans','C.UTF-8':'en','POSIX':'en'}
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(self.bundle(name).tag, expected)

    def test_invalid_and_ambiguous_explicit_tags_do_not_select_paths(self):
        for tag in ('zh', 'fr', '../en', 'en/../../private', '/tmp/en', 'en:a', 'zh-Latn-TW', 'en\x1b[31m'):
            with self.subTest(tag=tag), mock.patch.object(m, '_locale_json', wraps=m._locale_json) as read:
                with self.assertRaises(m.LocaleError):
                    self.bundle(tag)
                self.assertEqual({call.args[1] for call in read.call_args_list}, {'registry.json', 'en.json'})

    def test_environment_precedence_and_ordered_preferences(self):
        env = {'LANG':'zh_CN.UTF-8', 'LC_MESSAGES':'zh_TW.UTF-8', 'LC_ALL':'en_US.UTF-8',
               'LANGUAGE':'fr:zh-Hans:en', 'KOBO_MIGRATE_LOCALE':'zh-Hant'}
        self.assertEqual(self.bundle('en', env).tag, 'en')
        self.assertEqual(self.bundle(env=env).tag, 'zh-Hant')
        del env['KOBO_MIGRATE_LOCALE']
        self.assertEqual(self.bundle(env=env).tag, 'zh-Hans')
        del env['LANGUAGE']
        self.assertEqual(self.bundle(env=env).tag, 'en')
        del env['LC_ALL']
        self.assertEqual(self.bundle(env=env).tag, 'zh-Hant')
        del env['LC_MESSAGES']
        self.assertEqual(self.bundle(env=env).tag, 'zh-Hans')

    def test_environment_fallback_does_not_guess_a_chinese_script(self):
        for env in ({}, {'LANG':'de_DE.UTF-8'}, {'LANG':'C'}, {'LANG':'POSIX'}):
            self.assertEqual(self.bundle(env=env).tag, 'en')
        ambiguous = self.bundle(env={'LANG':'zh'})
        self.assertEqual(ambiguous.tag, 'en')
        self.assertEqual(len(ambiguous.notices), 1)
        self.assertEqual(self.bundle(env={'LANGUAGE':'zh:zh-Hant'}).tag, 'zh-Hant')
        override = self.bundle(env={'KOBO_MIGRATE_LOCALE':'unsupported','LANG':'zh_TW.UTF-8'})
        self.assertEqual(override.tag,'en')
        self.assertEqual(len(override.notices),1)

    def test_required_english_catalog_fails_closed(self):
        data = self.read('en')
        del data['messages']['help.cleanup']
        self.write('en', data)
        with self.assertRaisesRegex(m.LocaleError, 'required'):
            self.bundle('zh-Hant')
        self.cli(['--preview-ui'], expected=2)

    def test_missing_or_invalid_translation_falls_back_without_echoing_data(self):
        path = self.locales / 'zh-Hant.json'
        path.unlink()
        bundle = self.bundle('zh-Hant')
        self.assertEqual(bundle.tag, 'en')
        self.assertEqual(len(bundle.notices), 1)
        secret = 'gh' + 'p_' + 'q' * 32
        path.write_text(secret)
        bundle = self.bundle('zh-Hant')
        self.assertEqual(bundle.tag, 'en')
        self.assertNotIn(secret, '\n'.join(bundle.notices))

    def test_missing_message_uses_complete_english_and_english_plural(self):
        data = self.read('zh-Hant')
        del data['messages']['help.mode']
        del data['messages']['preview.file_count']
        self.write('zh-Hant', data)
        bundle = self.bundle('zh-Hant')
        self.assertEqual(bundle.tag,'zh-Hant')
        self.assertEqual(bundle.render('help.mode'), bundle.english['help.mode'])
        self.assertEqual(bundle.render('preview.file_count',count=1),'Example count: 1 file.')
        registry = m.load_locale_registry(self.locales)
        english = m.load_locale_catalog(self.locales,'en',registry)
        with self.assertRaisesRegex(m.LocaleError,'coverage'):
            m.load_locale_catalog(self.locales,'zh-Hant',registry,english,complete=True)

    def test_catalog_schema_and_template_attacks_are_rejected(self):
        original = self.read('zh-Hant')
        broken = []
        for value in ('{count.__class__}', '{count[0]}', '{count!r}', '{count:{other}}', '{unexpected}',
                      '{count:999999d}', '\x1b[31m{count}', '\u202e{count}', 'unclosed {count'):
            data = copy.deepcopy(original)
            data['messages']['preview.file_count']['other'] = value
            broken.append(data)
        data = copy.deepcopy(original);data['locale']='en';broken.append(data)
        data = copy.deepcopy(original);data['schema_version']=True;broken.append(data)
        data = copy.deepcopy(original);data['messages']['unknown.message']='extra';broken.append(data)
        data = copy.deepcopy(original);data['messages']['help.mode']=42;broken.append(data)
        for data in broken:
            with self.subTest(index=broken.index(data)):
                self.write('zh-Hant',data)
                self.assertEqual(self.bundle('zh-Hant').tag,'en')

    def test_duplicate_keys_utf8_and_size_limits_fail_closed(self):
        path = self.locales/'en.json'
        for content in (b'{"schema_version":1,"schema_version":1}', b'\xff\xfe', b'x'*(m.LOCALE_MAX_BYTES+1)):
            with self.subTest(size=len(content)):
                path.write_bytes(content)
                with self.assertRaises(m.LocaleError):
                    self.bundle()

    def test_symlink_catalog_or_root_cannot_escape_assets(self):
        path = self.locales/'en.json'
        other = self.root/'outside.json'
        other.write_bytes(path.read_bytes())
        path.unlink();path.symlink_to(other)
        with self.assertRaises(m.LocaleError):
            self.bundle()
        link = self.root/'linked-locales';link.symlink_to(self.locales,target_is_directory=True)
        with self.assertRaises(m.LocaleError):
            m.load_locale_bundle('en',{},link)

    def test_registry_conflicts_unknown_rules_and_unsafe_names_fail(self):
        original=self.read('registry')
        for change in ('alias','rule','tag','control','english'):
            data=copy.deepcopy(original)
            if change=='alias': data['locales'][1]['aliases'].append('en-US')
            if change=='rule': data['locales'][1]['plural_rule']='eval(count)'
            if change=='tag': data['locales'][1]['tag']='../outside'
            if change=='control': data['locales'][1]['name']='\x1b[31munsafe'
            if change=='english': data['locales']=data['locales'][1:]
            self.write('registry',data)
            with self.subTest(change=change),self.assertRaises(m.LocaleError):
                self.bundle()

    def test_plural_rules_parameters_and_format_fallback(self):
        en=self.bundle('en');hant=self.bundle('zh-Hant')
        self.assertIn('1 file.',en.render('preview.file_count',count=1))
        self.assertIn('0 files.',en.render('preview.file_count',count=0))
        self.assertIn('2 files.',en.render('preview.file_count',count=2))
        self.assertIn('1 個檔案',hant.render('preview.file_count',count=1))
        for count in (True,-1,1.5):
            with self.assertRaises(m.LocaleError):
                en.render('preview.file_count',count=count)
        with self.assertRaises(m.LocaleError): en.render('not.a_message')
        with self.assertRaises(m.LocaleError): en.render('help.mode',unexpected='value')
        # A valid but incompatible format specifier falls back to English at render time.
        data=self.read('en');data['messages']['example.role']='Device {role}'
        self.write('en',data)
        data=self.read('zh-Hant');data['messages']['example.role']='裝置 {role:d}'
        self.write('zh-Hant',data)
        self.assertEqual(self.bundle('zh-Hant').render('example.role',role='TARGET'),'Device TARGET')

    def test_help_preview_and_list_work_offline_without_runs(self):
        for tag,title in (('en','interface preview'),('zh-Hant','介面預覽'),('zh-Hans','界面预览')):
            with self.subTest(locale=tag):
                output,_=self.cli(['--locale',tag,'--preview-ui'])
                self.assertIn(title,output)
                self.assertIn('FULL:',output)
                self.assertIn('DELETE RUN_ID',output)
                help_output,_=self.cli(['--locale',tag,'--help'])
                self.assertIn('--locale TAG',help_output)
                self.assertIn('--preview-ui',help_output)
                listing,_=self.cli(['--locale',tag,'--list-locales'])
                for supported in ('en: English','zh-Hant: 繁體中文','zh-Hans: 简体中文'):
                    self.assertIn(supported,listing)

    def test_invalid_arguments_and_assets_fail_before_device_or_run_access(self):
        for flags in (['--locale','../en','--mode','full'],['--preview-ui','--mode','full'],
                      ['--list-locales','--from-run','example'],['--preview-ui','--self-test']):
            self.cli(flags,expected=2)
        (self.locales/'en.json').unlink()
        _,errors=self.cli(['--mode','full'],expected=2)
        self.assertIn('keep the complete locales/',errors)

    def test_non_utf8_help_and_preview_output_is_safe(self):
        stream=io.TextIOWrapper(io.BytesIO(),encoding='ascii')
        with mock.patch('sys.stdout',stream), mock.patch.object(m,'LOCALE_ROOT',self.locales), \
             mock.patch('sys.argv',['tool','--locale','zh-Hant','--help']):
            with self.assertRaises(SystemExit) as result:
                m.main()
            self.assertEqual(result.exception.code,0)
            m.preview_locale_ui(self.bundle('zh-Hant'))
        stream.flush()
        self.assertIn(b'\\u',stream.buffer.getvalue())
        stream.close()

    def test_publication_allows_only_exact_reviewed_locale_files(self):
        guard=base.importlib.util.spec_from_file_location('locale_privacy_check',ROOT/'scripts/check_publication.py')
        module=base.importlib.util.module_from_spec(guard);guard.loader.exec_module(module)
        for name in ('registry.json','en.json','zh-Hant.json','zh-Hans.json'):
            self.assertTrue(module.allowed('locales/'+name))
        for name in ('locales/run.json','locales/private.json','locales/fr.json','locales/../en.json'):
            self.assertFalse(module.allowed(name))


class LocaleWorkflowTests(base.MigrationTestCase):
    prepare_devices = base.WorkflowTests.prepare_devices

    def test_locale_choice_does_not_change_full_migration_or_english_log(self):
        from test_management import ManagedWorkflowTests
        root, expected = self.root, None
        for tag in ('en','zh-Hant','zh-Hans'):
            self.root = root/tag
            self.root.mkdir()
            source,target = self.prepare_devices()
            source_before = base.tree_contents(source)
            project = self.root/'project'
            with mock.patch.dict(os.environ,{},clear=True), contextlib.redirect_stderr(io.StringIO()):
                code,calls = ManagedWorkflowTests.execute(self,project,[source,target],['--mode','full','--locale',tag])
            self.assertEqual((code,calls),(0,2))
            self.assertEqual(base.tree_contents(source),source_before)
            actual = base.tree_contents(target)
            if expected is None:
                expected = actual
            else:
                self.assertEqual(actual,expected)
            run = next((project/'runs').iterdir())
            log = next(run.glob('*.log')).read_text()
            self.assertIn('MIGRATION SUCCESSFUL',log)
            self.assertNotIn('介面預覽',log)
            self.assertNotIn('界面预览',log)
            self.assertEqual(m.read_json(run/'run.json')['status'],'success')


if __name__ == '__main__':
    unittest.main()
