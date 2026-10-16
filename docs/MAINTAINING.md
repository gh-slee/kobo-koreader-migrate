# Maintainer guide

[Home](../README.md) · [Usage](USAGE.md) · [Recovery](RECOVERY.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Development](DEVELOPMENT.md) · [Maintaining](MAINTAINING.md)

Repository publication and release-preparation reference. These procedures do not grant authority to upload data, merge changes or publish a release.

## Publication privacy

Backups can contain plugin API credentials, device identifiers, reading history, annotations and book filenames. Logs/manifests/reports can also reveal personal information. Keep `runs/` private, including runs stored with a custom `--backup-dir`. Do not attach raw archives, device databases, settings or reports to public issues. Share a minimal redacted reproduction using synthetic files.

`.gitignore` excludes runtime batches, copied Kobo trees, sidecars, books, fonts, databases, common credentials/private keys and local private notes. Publication additionally checks **the staged Git blobs and reachable history**, because ignoring a file does not untrack it or remove prior commits.

```bash
# Before the first Git commit, check candidate public source files.
python3 scripts/check_publication.py --worktree

# Before committing/pushing, check actual index and history.
python3 scripts/check_publication.py --history

# Install this repository's pre-push guard in this clone.
git config --local core.hooksPath .githooks
```

The guard allows only reviewed source/docs/test paths and detects common secrets/personal absolute paths without printing matching values. It is a heuristic defence, not a guarantee that all personal data can be detected. Review staged diffs and commit author identity. The history guard requires GitHub user noreply author/committer emails, with one exception: merge commits may use the exact public platform committer address `noreply@github.com` used by GitHub PR test merges. Authors still need user noreply addresses; personal and lookalike emails remain blocked. Commit messages are scanned too. New public file paths require an intentional allowlist update. CI checks after upload; the local hook is the guard before upload. Hooks can be bypassed, so maintainers must also follow [CONTRIBUTING.md](../CONTRIBUTING.md).

Use a GitHub user noreply author/committer email. The history guard also accepts the exact public platform committer noreply@github.com on merge commits; authors still require user noreply IDs. Personal emails, platform authors/non-merge committers and lookalike domains are rejected.

The privacy guard inspects actual staged blobs and every locally reachable commit. .gitignore does not untrack existing files or remove their history. Moving internal notes out of current public docs does not erase older commits. Retain allowlist entries needed to inspect historical public paths even after deleting those paths from the current tree. Handle any history remediation separately; do not bypass the guard.

Install the local pre-push hook:

```bash
git config --local core.hooksPath .githooks
```

The guard uses a public-path allowlist and secret/path heuristics. Human review remains necessary. Hooks can be bypassed, and hosted CI runs after upload. Branch protection and repository permissions are separate controls.

## PR helper

GitHub CLI is optional maintainer tooling, unnecessary for migration. Authenticate with its browser/OS credential-store flow. Never print tokens or paste credentials into source, logs, issues or an AI chat.

When authorized to publish a committed, clean feature branch, prepare a reviewed English PR body and run:

```bash
python3 scripts/publish.py --repository OWNER/REPO \
  --title "Explain the change" --body-file /tmp/pr-body.md
```

Use the exact repository identity shown by origin. The helper checks the destination, branch, clean tree, PR content, privacy, locales, tests and self-test. It performs an ordinary push and creates/reuses an open PR. It never merges, force-pushes or publishes releases. Publication helpers do not replace the operator's authorization requirements.

## Release readiness

Before a release, verify the intended commit, version/changelog, complete source distribution and required human acceptance. Include locales/ even for English; do not advertise a single downloaded Python file as a complete installation.

The complete implementation is currently under review in PR #1 on feature/public-release. Main contains bootstrap documentation only. The README clone command and CI badge intentionally point to the review branch. After an approved implementation merge, update installation instructions and badge scope to the intended default/release branch. Do not advertise nonexistent binaries, package-manager packages or hardware certification.

Confirm that user/developer links work in a clone and an extracted source archive. Keep public instructions generic, and keep personal preferences, credentials and session histories local. Existing public Git history is not erased by reorganizing current files. Release publication, merge and remote deletion are separate authorized actions; the helper does not perform them.
