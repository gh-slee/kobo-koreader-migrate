#!/usr/bin/env python3
"""Validate a clean feature branch, push it, and create a PR. Never merges a PR."""
from __future__ import annotations
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*cmd: str, capture: bool = False) -> str:
    result = subprocess.run(list(cmd), cwd=ROOT, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ''


def repository_from_url(url: str) -> str:
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?', url)
    if not match:
        raise ValueError('origin must be a GitHub HTTPS or SSH URL without credentials.')
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, help='Expected OWNER/REPO; must match origin.')
    parser.add_argument('--title', required=True, help='PR title.')
    parser.add_argument('--body-file', type=Path, required=True, help='Reviewed PR description text file.')
    parser.add_argument('--base', default='main', help='Review target branch (default: main).')
    args = parser.parse_args()
    try:
        if not shutil.which('gh'):
            raise ValueError('Install GitHub CLI and run gh auth login first.')
        branch = run('git', 'symbolic-ref', '--quiet', '--short', 'HEAD', capture=True)
        if branch in {'main', 'master', args.base}:
            raise ValueError('Switch to a feature branch; publishing a default/base branch is refused.')
        if run('git', 'status', '--porcelain', capture=True):
            raise ValueError('Commit reviewed changes first; the working tree must be clean.')
        urls = run('git', 'remote', 'get-url', '--push', '--all', 'origin', capture=True).splitlines()
        if len(urls) != 1 or repository_from_url(urls[0]) != args.repository:
            raise ValueError('origin push URL does not match the requested repository.')
        if not args.body_file.is_file():
            raise ValueError('PR body file is missing.')
        from check_publication import inspect_blob
        if inspect_blob('README.md', args.body_file.read_bytes()) or inspect_blob('README.md', args.title.encode()):
            raise ValueError('PR title/body failed the publication content check; redact private values.')
        run(sys.executable, 'scripts/check_publication.py', '--history')
        run(sys.executable, 'scripts/check_locales.py')
        run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py')
        run(sys.executable, 'kobo-koreader-migrate.py', '--self-test')
        run('gh', 'auth', 'status')
        # No force flag, branch deletion, merge or release creation.
        run('git', 'push', '--set-upstream', 'origin', branch)
        existing = run('gh', 'pr', 'list', '--repo', args.repository, '--head', branch,
                       '--base', args.base, '--state', 'open', '--json', 'url', '--jq', '.[0].url // empty', capture=True)
        if existing:
            print('Existing PR: ' + existing)
        else:
            run('gh', 'pr', 'create', '--repo', args.repository, '--head', branch,
                '--base', args.base, '--title', args.title, '--body-file', str(args.body_file.resolve()))
        print('Await human sign-off before merging.')
        return 0
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f'Publish stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
