"""Source distribution safety using local disposable Git repositories; no devices or network."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_release as release


class ReleasePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'repository'
        self.root.mkdir()
        self.output = Path(self.temporary.name) / 'artifacts'
        self.env = dict(os.environ, GIT_AUTHOR_NAME='Fixture', GIT_COMMITTER_NAME='Fixture',
                        GIT_AUTHOR_EMAIL='fixture@users.noreply.github.com',
                        GIT_COMMITTER_EMAIL='fixture@users.noreply.github.com')
        self.git('init', '-b', 'main')
        for path in release.REQUIRED:
            self.write(path, 'Synthetic public fixture.\n')
        self.write('kobo-koreader-migrate.py', "VERSION = '1.2.3-dev.1'\nimport sys\nprint('tool ' + VERSION if '--version' in sys.argv else 'Synthetic offline command passed.')\n")
        self.write('koreader-bridge.py', "import runpy\nfrom pathlib import Path\nrunpy.run_path(str(Path(__file__).with_name('kobo-koreader-migrate.py')), run_name='__main__')\n")
        core = self.root / 'kobo-koreader-migrate.py'
        core.write_text("PROJECT_NAME = 'KOReader Bridge'\n" + core.read_text())
        for path in ('registry', 'en', 'zh-Hant', 'zh-Hans'):
            self.write('locales/' + path + '.json', '{}\n')
        self.write('scripts/check_locales.py', "from pathlib import Path\nassert all((Path('locales') / (tag + '.json')).is_file() for tag in ('registry', 'en', 'zh-Hant', 'zh-Hans'))\n")
        self.write('README.md', '[Usage](docs/USAGE.md)\n')
        self.write('docs/USAGE.md', '[Home](../README.md)\n')
        self.write('.gitignore', '.local/\nruns/\nAGENTS.override.md\n*.epub\n')
        self.write('.githooks/pre-push', '#!/bin/sh\nexit 0\n')
        (self.root / '.githooks/pre-push').chmod(0o755)
        self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], env=self.env,
                                       stderr=subprocess.PIPE).decode().strip()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-m', 'Synthetic release fixture')
        return self.git('rev-parse', 'HEAD')

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return release.prepare(self.root, 'HEAD', self.output)

    def validate(self, directory, ref='HEAD'):
        commit, version, files = release.snapshot(self.root, ref)
        return release.validate_package(directory, commit, version, files)

    def test_package_uses_committed_bytes_and_omits_private_and_untracked_data(self):
        self.write('README.md', 'Uncommitted working content.\n')
        for path in ('AGENTS.override.md', 'runs/private/run.json', '.local/notes.md', 'private.epub', 'untracked.txt'):
            self.write(path, 'Synthetic private data.\n')
        directory = self.prepare()
        result = self.validate(directory)
        self.assertEqual(result['checks'], [label for label, _ in release.SMOKE_CHECKS])
        self.assertEqual(result['relative_doc_links_checked'], 2)
        self.assertFalse(json.loads((directory / 'PREPARATION.json').read_text())['published'])
        with zipfile.ZipFile(directory / result['asset']) as archive:
            prefix = release.names(result['version'], bridge=True)[0] + '/'
            self.assertEqual(archive.read(prefix + 'README.md'), b'[Usage](docs/USAGE.md)\n')
            self.assertEqual(archive.getinfo(prefix + '.githooks/pre-push').external_attr >> 16, 0o100755)
            self.assertFalse(any('private' in name or 'AGENTS.override.md' in name for name in archive.namelist()))
        self.assertEqual((self.root / 'README.md').read_text(), 'Uncommitted working content.\n')

    def test_branded_source_requires_canonical_entry_before_packaging(self):
        self.git('rm', 'koreader-bridge.py')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'required KOReader Bridge CLI'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_historical_package_still_verifies_from_its_old_ref(self):
        core = self.root / 'kobo-koreader-migrate.py'
        branded_core = core.read_text()
        entry = (self.root / 'koreader-bridge.py').read_text()
        core.write_text(branded_core.replace("PROJECT_NAME = 'KOReader Bridge'\n", ''))
        self.git('rm', 'koreader-bridge.py')
        old_ref = self.commit()
        directory = self.prepare()
        self.assertTrue((directory / 'kobo-koreader-migrate-1.2.3-dev.1.zip').is_file())
        self.assertEqual(self.validate(directory)['checks'],
                         [label for label, _ in release.LEGACY_SMOKE_CHECKS])
        old_bytes = {p.name: p.read_bytes() for p in directory.iterdir()}
        core.write_text(branded_core)
        self.write('koreader-bridge.py', entry)
        self.commit()
        result = self.validate(directory, old_ref)
        self.assertEqual(result['source_commit'], old_ref)
        self.assertEqual(old_bytes, {p.name: p.read_bytes() for p in directory.iterdir()})

    def test_repeated_build_matches_bytes_and_existing_output_is_not_overwritten(self):
        first = self.prepare()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepare()
        with contextlib.redirect_stdout(io.StringIO()):
            second = release.prepare(self.root, 'HEAD', self.output / 'another')
        for name in ('koreader-bridge-1.2.3-dev.1.zip', 'SHA256SUMS', 'PREPARATION.json'):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_bad_ref_and_missing_required_locale_refuse_before_output(self):
        with self.assertRaises(ValueError):
            release.prepare(self.root, '--not-a-ref', self.output)
        self.git('rm', 'locales/en.json')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'missing required'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_tracked_private_data_and_secrets_are_blocked_without_echo(self):
        self.write('AGENTS.override.md', 'Synthetic private instruction.\n')
        self.git('add', '-f', 'AGENTS.override.md')
        self.git('commit', '-m', 'Synthetic rejected candidate')
        with self.assertRaisesRegex(ValueError, 'publication'):
            self.prepare()
        self.git('rm', 'AGENTS.override.md')
        secret = 'gh' + 'p_' + 'a' * 32
        self.write('README.md', secret)
        self.commit()
        with self.assertRaises(ValueError) as caught:
            self.prepare()
        self.assertNotIn(secret, str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_tracked_symlink_is_refused(self):
        (self.root / 'README.md').unlink()
        (self.root / 'README.md').symlink_to('LICENSE')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_version_cannot_control_output_paths(self):
        self.write('kobo-koreader-migrate.py', "VERSION = '../escape'\n")
        self.commit()
        with self.assertRaisesRegex(ValueError, 'VERSION'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_failed_extracted_command_and_broken_doc_link_leave_no_package(self):
        self.write('kobo-koreader-migrate.py', "VERSION = '1.2.3-dev.1'\nraise SystemExit(2)\n")
        self.commit()
        with self.assertRaisesRegex(ValueError, 'offline check failed'):
            self.prepare()
        self.assertFalse(self.output.exists())
        self.write('README.md', '[Missing](docs/missing.md)\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'documentation'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_link_validation_stays_inside_extracted_tree(self):
        self.write('README.md', '[Outside](../outside.md)\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_wrong_expected_commit_is_rejected(self):
        directory = self.prepare()
        self.write('LICENSE', 'Different fixture revision.\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'commit/version'):
            self.validate(directory)

    def test_corrupt_zip_and_changed_checksum_are_rejected(self):
        directory = self.prepare()
        archive = directory / 'koreader-bridge-1.2.3-dev.1.zip'
        original = archive.read_bytes()
        archive.write_bytes(original[:-20])
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.validate(directory)
        archive.write_bytes(original)
        (directory / 'SHA256SUMS').write_text('Wrong checksum\n')
        with self.assertRaisesRegex(ValueError, 'SHA256SUMS'):
            self.validate(directory)

    def rewrite_zip(self, directory, change):
        archive = directory / 'koreader-bridge-1.2.3-dev.1.zip'
        with zipfile.ZipFile(archive) as current:
            entries = [(info, current.read(info)) for info in current.infolist()]
        with zipfile.ZipFile(archive, 'w') as modified:
            change(modified, entries)
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        record = json.loads((directory / 'PREPARATION.json').read_text())
        record['sha256'] = sha
        (directory / 'PREPARATION.json').write_text(json.dumps(record))
        (directory / 'SHA256SUMS').write_text(f'{sha}  {archive.name}\n')

    def test_changed_member_is_refused_even_after_checksum_and_record_are_updated(self):
        directory = self.prepare()
        def alter(archive, entries):
            for info, data in entries:
                archive.writestr(info, b'Altered public bytes.\n' if info.filename.endswith('/LICENSE') else data)
        self.rewrite_zip(directory, alter)
        with self.assertRaisesRegex(ValueError, 'source|commit'):
            self.validate(directory)

    def test_extra_traversal_member_and_duplicate_are_refused_before_extraction(self):
        for name in ('../escape', 'koreader-bridge-1.2.3-dev.1/README.md'):
            with self.subTest(name=name):
                with contextlib.redirect_stdout(io.StringIO()):
                    directory = release.prepare(self.root, 'HEAD', self.output / str(len(name)))
                def add(archive, entries):
                    for info, data in entries:
                        archive.writestr(info, data)
                    archive.writestr(name, b'Synthetic extra entry.\n')
                with self.assertWarnsRegex(UserWarning, 'Duplicate') if name.endswith('README.md') else contextlib.nullcontext():
                    self.rewrite_zip(directory, add)
                with self.assertRaisesRegex(ValueError, 'member set'):
                    self.validate(directory)
        self.assertFalse((Path(self.temporary.name) / 'escape').exists())

    def test_artifact_symlinks_and_invalid_record_are_refused(self):
        directory = self.prepare()
        record = directory / 'PREPARATION.json'
        original = record.read_bytes()
        record.write_text('[]')
        with self.assertRaisesRegex(ValueError, 'record'):
            self.validate(directory)
        record.write_bytes(original)
        checksum = directory / 'SHA256SUMS'
        checksum.unlink()
        checksum.symlink_to(record.name)
        with self.assertRaisesRegex(ValueError, 'regular'):
            self.validate(directory)

    def test_cli_reports_invalid_input_without_raw_git_output(self):
        with mock.patch.object(release, 'ROOT', self.root), \
             mock.patch('sys.argv', ['prepare_release', 'prepare', '--ref', 'missing-ref']), \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(release.main(), 1)
        self.assertIn('Release preparation stopped', errors.getvalue())
        self.assertNotIn('fatal:', errors.getvalue())

    def test_new_script_is_exactly_allowlisted_but_arbitrary_helpers_are_not(self):
        self.assertFalse(release.inspect_blob('scripts/prepare_release.py', b'Synthetic public source.\n'))
        self.assertTrue(release.inspect_blob('scripts/private_release.py', b'Synthetic private notes.\n'))


if __name__ == '__main__':
    unittest.main()
