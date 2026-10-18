#!/usr/bin/env python3
"""Prepare or verify a local source package from a reviewed Git commit. Never publishes."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile

from check_publication import inspect_blob, MAX_BYTES

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    'kobo-koreader-migrate.py', 'README.md', 'LICENSE', 'AGENTS.md',
    'locales/registry.json', 'locales/en.json', 'locales/zh-Hant.json', 'locales/zh-Hans.json',
    'scripts/check_locales.py', 'docs/USAGE.md', 'docs/RECOVERY.md',
    'docs/TROUBLESHOOTING.md', 'docs/DEVELOPMENT.md', 'docs/MAINTAINING.md',
}
SMOKE_CHECKS = (
    ('locales', ('scripts/check_locales.py',)),
    ('version', ('kobo-koreader-migrate.py', '--version')),
    ('help', ('kobo-koreader-migrate.py', '--help')),
    ('locale list', ('kobo-koreader-migrate.py', '--list-locales')),
    ('Traditional Chinese preview', ('kobo-koreader-migrate.py', '--locale', 'zh-Hant', '--preview-ui')),
    ('self-test', ('kobo-koreader-migrate.py', '--self-test')),
)


def git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        raise ValueError('Git inspection failed; use a valid local commit reference.') from error


def snapshot(root: Path, ref: str) -> tuple[str, str, dict]:
    """Read only Git objects, never private/untracked/modified working files."""
    commit = git(root, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()
    files = {}
    total = 0
    for record in git(root, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not record:
            continue
        header, raw_path = record.split(b'\t', 1)
        mode, kind, oid = header.decode().split()
        path = raw_path.decode('utf-8')
        if kind != 'blob' or mode not in {'100644', '100755'}:
            raise ValueError('Source contains a symlink, submodule or unsupported file mode.')
        size = int(git(root, 'cat-file', '-s', oid))
        total += size
        if size > MAX_BYTES or total > 32 * MAX_BYTES or len(files) >= 2048:
            raise ValueError('Source exceeds package size/file limits.')
        data = git(root, 'cat-file', 'blob', oid)
        if inspect_blob(path, data, mode):
            raise ValueError('Source failed the publication allowlist/content check; no content was printed.')
        files[path] = (mode, data)
    if not REQUIRED <= files.keys():
        raise ValueError('Source is missing required runtime, locale or documentation files.')
    tree = ast.parse(files['kobo-koreader-migrate.py'][1].decode('utf-8'))
    versions = [node.value.value for node in tree.body
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION'
                                                       for t in node.targets)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
    if len(versions) != 1 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?', versions[0]):
        raise ValueError('Source must declare one safe literal VERSION string.')
    return commit, versions[0], files


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def names(version: str) -> tuple[str, str]:
    prefix = 'kobo-koreader-migrate-' + version
    return prefix, prefix + '.zip'


def write_archive(path: Path, version: str, files: dict) -> None:
    prefix, _ = names(version)
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, (mode, data) in sorted(files.items()):
            info = zipfile.ZipInfo(prefix + '/' + relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = int(mode, 8) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def check_archive(path: Path, version: str, files: dict, extracted: Path) -> None:
    """Compare every member to Git before writing any extracted file."""
    prefix, _ = names(version)
    expected = {prefix + '/' + name: (name, mode, data) for name, (mode, data) in files.items()}
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) != len(expected) or {entry.filename for entry in entries} != set(expected):
            raise ValueError('ZIP member set differs from the commit (extra, duplicate, missing or unsafe path).')
        for entry in entries:
            relative, mode, data = expected[entry.filename]
            actual_mode = entry.external_attr >> 16
            if actual_mode != int(mode, 8) or entry.file_size != len(data) or entry.flag_bits & 1:
                raise ValueError('ZIP member mode, size or encryption differs from the source.')
            if archive.read(entry) != data:
                raise ValueError('ZIP member content differs from the specified commit.')
        # The extraction root is new and private; paths came from the guarded Git tree.
        for entry in entries:
            relative, mode, _ = expected[entry.filename]
            target = extracted / prefix / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
            target.chmod(0o755 if mode == '100755' else 0o644)


def check_links(root: Path) -> int:
    """Validate local Markdown/HTML file targets without contacting any website."""
    count = 0
    for doc in root.rglob('*.md'):
        source = doc.read_text(encoding='utf-8')
        targets = [a or b for a, b in re.findall(r'\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))\)', source)]
        targets += re.findall(r'href=["\']([^"\']+)["\']', source)
        for target in targets:
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            path = (doc.parent / unquote(url.path)).resolve()
            if (path != root.resolve() and root.resolve() not in path.parents) or not path.exists():
                raise ValueError('An extracted documentation file link is missing or escapes the package.')
            count += 1
    return count


def run_smoke_checks(root: Path, version: str) -> list[str]:
    """Run only offline entry points in the fully checked, disposable extraction."""
    env = dict(os.environ, KOBO_MIGRATE_LOCALE='en', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    passed = []
    for label, arguments in SMOKE_CHECKS:
        print('  Offline check: ' + label, flush=True)
        result = subprocess.run([sys.executable, *arguments], cwd=root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        if result.returncode or (label == 'version' and result.stdout.decode('utf-8').split()[-1:] != [version]):
            raise ValueError('Extracted offline check failed: ' + label + '. Output was withheld.')
        passed.append(label)
    return passed


def validate_package(directory: Path, commit: str, version: str, files: dict) -> dict:
    _, asset = names(version)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Package directory must be an existing regular directory.')
    for name in (asset, 'SHA256SUMS', 'PREPARATION.json'):
        if (directory / name).is_symlink() or not (directory / name).is_file():
            raise ValueError('Package is missing a regular required artifact.')
    if (directory / 'PREPARATION.json').stat().st_size > MAX_BYTES:
        raise ValueError('Preparation record exceeds the size limit.')
    record = json.loads((directory / 'PREPARATION.json').read_text(encoding='utf-8'))
    if not isinstance(record, dict) or record.get('schema_version') != 1 or record.get('source_commit') != commit or record.get('version') != version:
        raise ValueError('Preparation record does not match the specified source commit/version.')
    archive = directory / asset
    # The package cannot legitimately exceed its bounded Git source by more than ZIP overhead.
    if archive.stat().st_size > sum(len(data) for _, data in files.values()) + len(files) * 1024 + MAX_BYTES:
        raise ValueError('ZIP exceeds the expected size limit.')
    sha = digest(archive.read_bytes())
    expected_members = {path: {'sha256': digest(data), 'mode': mode, 'bytes': len(data)}
                        for path, (mode, data) in sorted(files.items())}
    if (record.get('asset') != asset or record.get('sha256') != sha
            or record.get('tracked_file_count') != len(files) or record.get('files') != expected_members):
        raise ValueError('Package digest or member record differs from the source.')
    checksum = f'{sha}  {asset}\n'.encode()
    if ((directory / 'SHA256SUMS').stat().st_size != len(checksum)
            or (directory / 'SHA256SUMS').read_bytes() != checksum):
        raise ValueError('SHA256SUMS does not match the ZIP.')
    with tempfile.TemporaryDirectory(prefix='kobo-release-verify-') as temporary:
        extraction = Path(temporary)
        check_archive(archive, version, files, extraction)
        package = extraction / names(version)[0]
        links = check_links(package)
        checks = run_smoke_checks(package, version)
    return {'source_commit': commit, 'version': version, 'asset': asset, 'sha256': sha,
            'tracked_file_count': len(files), 'relative_doc_links_checked': links, 'checks': checks}


def prepare(root: Path, ref: str, output_dir: Path) -> Path:
    commit, version, files = snapshot(root, ref)
    destination = output_dir / (version + '-' + commit[:12])
    if destination.exists() or destination.is_symlink():
        raise ValueError('Output already exists; verify it or select a different output directory. Nothing was overwritten.')
    _, asset = names(version)
    with tempfile.TemporaryDirectory(prefix='kobo-release-prepare-') as temporary:
        staging = Path(temporary)
        write_archive(staging / asset, version, files)
        sha = digest((staging / asset).read_bytes())
        (staging / 'SHA256SUMS').write_text(f'{sha}  {asset}\n', encoding='utf-8')
        record = {'schema_version': 1, 'source_commit': commit, 'version': version, 'asset': asset,
                  'sha256': sha, 'tracked_file_count': len(files), 'published': False,
                  'files': {path: {'sha256': digest(data), 'mode': mode, 'bytes': len(data)}
                            for path, (mode, data) in sorted(files.items())}}
        (staging / 'PREPARATION.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print('Checking extracted package (locales, help, preview, self-test and file links)...', flush=True)
        results = validate_package(staging, commit, version, files)
        record['verification'] = results
        (staging / 'PREPARATION.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        output_dir.mkdir(parents=True, exist_ok=True)
        destination.mkdir()  # Exclusive creation: never reuse or erase an existing output.
        for name in (asset, 'SHA256SUMS', 'PREPARATION.json'):
            with (staging / name).open('rb') as source, (destination / name).open('xb') as target:
                shutil.copyfileobj(source, target)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    build = commands.add_parser('prepare', help='Create and verify a new local source ZIP; no upload/tag.')
    build.add_argument('--ref', required=True, help='Reviewed local Git commit/tag/ref, e.g. HEAD.')
    build.add_argument('--output-dir', type=Path, default=ROOT / '.local' / 'releases', help='Parent of a new VERSION-COMMIT directory (default: .local/releases).')
    verify = commands.add_parser('verify', help='Recheck package bytes against an independently specified Git ref.')
    verify.add_argument('directory', type=Path, help='Previously generated package directory.')
    verify.add_argument('--ref', required=True, help='Expected reviewed Git commit/tag/ref; not inferred from the package.')
    args = parser.parse_args()
    try:
        if args.operation == 'prepare':
            directory = prepare(ROOT, args.ref, args.output_dir)
            print('Prepared locally: ' + str(directory))
        else:
            commit, version, files = snapshot(ROOT, args.ref)
            result = validate_package(args.directory, commit, version, files)
            print(f'Package verified: {result["tracked_file_count"]} committed files; {result["sha256"]}')
        print('No network, Kobo access, Git tag, push or release publication was performed. Human publication review is still required.')
        return 0
    except (ValueError, OSError, UnicodeError, SyntaxError, EOFError, zipfile.BadZipFile, RuntimeError,
            subprocess.SubprocessError) as error:
        # Do not echo raw Git/Python output, file contents or private paths.
        print('Release preparation stopped: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__) + '.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
