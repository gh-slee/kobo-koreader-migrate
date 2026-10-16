#!/usr/bin/env python3
"""Check actual Git blobs before publication. No network and no third-party modules."""
from __future__ import annotations
import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
EXACT = {'kobo-koreader-migrate.py', 'README.md', 'LICENSE', 'AGENTS.md',
         'TRACKER.md', 'ACCEPTANCE.md', 'CHANGELOG.md', 'CONTRIBUTING.md',
         'SECURITY.md', '.gitignore', '.githooks/pre-push',
         '.cursor/rules/project-context.mdc', '.github/workflows/tests.yml',
         'scripts/check_publication.py', 'scripts/publish.py', 'scripts/check_locales.py',
         'locales/registry.json', 'locales/en.json', 'locales/zh-Hant.json', 'locales/zh-Hans.json',
         'docs/USAGE.md', 'docs/RECOVERY.md', 'docs/TROUBLESHOOTING.md',
         'docs/DEVELOPMENT.md', 'docs/MAINTAINING.md'}
MAX_BYTES = 1024 * 1024
# Heuristics supplement the file allowlist and human review; not a proof of privacy.
RULES = [
    ('personal absolute path', re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/')),
    ('private key', re.compile(r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----')),
    ('GitHub token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b')),
    ('service key', re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b')),
    ('AWS access key', re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('credential URL', re.compile(r'https?://[^\s/:@]+:[^\s/@]+@')),
    ('assigned secret', re.compile(r'''(?ix)(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)["']?\s*[:=]\s*["'](?!<|example|dummy|test|fixture|placeholder|changeme)[A-Za-z0-9_./+=-]{16,}["']''')),
]


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(ROOT), *args], stderr=subprocess.PIPE)


def allowed(path: str) -> bool:
    p = PurePosixPath(path)
    return path in EXACT or (len(p.parts) == 2 and p.parts[0] == 'tests'
                            and re.fullmatch(r'test_[a-z0-9_]+\.py', p.name) is not None)


def inspect_blob(path: str, data: bytes, mode: str = '100644') -> list[str]:
    issues = []
    if not allowed(path):
        return [f'{path}: file is outside the publication allowlist']
    if mode not in {'100644', '100755'}:
        return [f'{path}: symlinks and submodules are not publishable']
    if len(data) > MAX_BYTES or b'\0' in data:
        return [f'{path}: oversized or binary content is not publishable']
    try:
        source = data.decode('utf-8')
    except UnicodeDecodeError:
        return [f'{path}: content must be UTF-8 text']
    for number, line in enumerate(source.splitlines(), 1):
        for label, pattern in RULES:
            if pattern.search(line):
                # Never echo matching values or complete lines.
                issues.append(f'{path}:{number}: {label}')
    return issues


def check_index() -> list[str]:
    issues = []
    for record in git('ls-files', '--stage', '-z').split(b'\0'):
        if not record:
            continue
        header, raw_path = record.split(b'\t', 1)
        mode, oid, stage = header.decode().split()
        path = raw_path.decode('utf-8', errors='replace')
        if stage != '0':
            issues.append(f'{path}: unresolved conflict')
        else:
            issues.extend(inspect_blob(path, git('cat-file', 'blob', oid), mode))
    return issues


def check_history() -> list[str]:
    issues, seen = [], set()
    for commit in git('rev-list', '--all').decode().splitlines():
        emails = git('show', '-s', '--format=%ae%n%ce', commit).decode().splitlines()
        author, committer = emails
        author_private = author.lower().endswith('@users.noreply.github.com')
        committer_private = committer.lower().endswith('@users.noreply.github.com')
        # GitHub's PR test merge uses this public platform committer address.
        # Accept it only for merge commits; authors still need user noreply IDs.
        if committer == 'noreply@github.com':
            parents = git('rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
            committer_private = len(parents) >= 2
        if not author_private or not committer_private:
            issues.append(f'commit {commit[:12]}: author/committer email is not a GitHub noreply address')
        message = git('show', '-s', '--format=%B', commit)
        issues.extend(inspect_blob('CHANGELOG.md', message))
        for record in git('ls-tree', '-rz', commit).split(b'\0'):
            if not record:
                continue
            header, raw_path = record.split(b'\t', 1)
            mode, kind, oid = header.decode().split()
            path = raw_path.decode('utf-8', errors='replace')
            key = (path, oid, mode)
            if key in seen:
                continue
            seen.add(key)
            if kind != 'blob':
                issues.append(f'{path}: submodules are not publishable')
            else:
                issues.extend(inspect_blob(path, git('cat-file', 'blob', oid), mode))
    return issues


def check_worktree() -> list[str]:
    issues = []
    candidates = [ROOT / p for p in EXACT]
    candidates += list((ROOT / 'tests').glob('test_*.py'))
    for path in sorted(candidates):
        if path.is_symlink():
            issues.append(f'{path.relative_to(ROOT)}: symlink is not publishable')
        elif path.is_file():
            issues.extend(inspect_blob(path.relative_to(ROOT).as_posix(), path.read_bytes()))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true', help='Also check every locally reachable commit.')
    parser.add_argument('--worktree', action='store_true', help='Check candidate source files before Git initialization.')
    args = parser.parse_args()
    try:
        issues = check_worktree() if args.worktree else check_index()
        if args.history:
            issues += check_history()
    except subprocess.CalledProcessError:
        print('Publication check failed: Git inspection could not complete.', file=sys.stderr)
        return 1
    if issues:
        print('Publication blocked:', file=sys.stderr)
        for issue in sorted(set(issues)):
            print('  ' + issue, file=sys.stderr)
        return 1
    print('Publication check passed (allowlist and secret/path heuristics). Human review is still required.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
