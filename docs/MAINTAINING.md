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

Private instructions remain prohibited even if force-added: the guard checks index blobs and each locally reachable commit, including files deleted from the latest tree. Isolated Git regression fixtures cover root/nested AGENTS.override.md and local notes. Retain allowlist entries needed to inspect historical public paths after removing those paths from the current tree. History remediation requires separate review; moving or deleting a current file does not erase earlier commits.

Before each publication, review the exact staged diff, commit range, destination and public PR text, report current validation/privacy findings, and obtain the applicable operator's approval. Changed scope needs renewed approval; credentials, helper flags and earlier approvals are not consent for another push. Stage only explicit reviewed public paths. Never upload private instruction contents as evidence. The guard does not detect every secret, personal fact or sensitive semantic detail; human review remains necessary.

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

The complete development implementation is on main following the merge of PR #1. The README clone command and CI badge target main. Keep installation instructions and badge scope aligned with the actual default/release branch when release policy changes. Do not advertise nonexistent binaries, package-manager packages or hardware certification.

Confirm that user/developer links work in a clone and an extracted source archive. Keep public instructions generic, and keep personal preferences, credentials and session histories local. Existing public Git history is not erased by reorganizing current files. Release publication, merge and remote deletion are separate authorized actions; the helper does not perform them.
