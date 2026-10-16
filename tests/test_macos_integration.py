"""Actual ditto integration using temporary device fixtures; never calls real eject."""
from __future__ import annotations
from pathlib import Path
import shutil
import sys
from unittest import mock
import unittest
import test_migration as base
m=base.migration


@unittest.skipUnless(sys.platform=='darwin' and shutil.which('ditto'), 'Actual macOS ditto required')
class MacOSArchiveIntegration(base.MigrationTestCase):
    prepare_devices=base.WorkflowTests.prepare_devices

    def execute(self,project,devices,flags):
        labels = [] if '--restore-run' in flags else ['--source-model', m.MODEL_CLARA, '--target-model', m.MODEL_LIBRA]
        with mock.patch('sys.argv',['tool','--backup-dir',str(project)]+flags+labels), \
             mock.patch.object(m,'wait_for_single_kobo',side_effect=devices), \
             mock.patch.object(m,'safe_eject'), mock.patch.object(m,'choose',return_value='1'), \
             mock.patch.object(m,'choose_identity_mode',return_value='preserve'), \
             mock.patch.object(m,'prompt_yes_no',return_value=True), mock.patch('builtins.input',return_value=''):
            return m.main()

    def test_actual_ditto_full_saved_source_and_exact_target_restore(self):
        source,target=self.prepare_devices()
        project=self.root/'project'
        source_before=base.tree_contents(source)
        target_before=base.tree_contents(target)
        self.assertEqual(self.execute(project,[source,target],['--mode','full']),0)
        saved=max((project/'runs').iterdir(),key=lambda p:p.stat().st_mtime_ns)
        self.assertEqual(m.read_json(saved/'run.json')['status'],'success')
        self.assertEqual((target/'Books/book.epub').read_bytes(),b'new book')
        self.assertEqual(self.execute(project,[target],['--from-run',saved.name]),0)
        self.assertEqual(self.execute(project,[target],['--restore-run',saved.name]),0)
        self.assertEqual(base.tree_contents(source),source_before)
        self.assertEqual(base.tree_contents(target),target_before)


if __name__=='__main__': unittest.main(verbosity=2)
