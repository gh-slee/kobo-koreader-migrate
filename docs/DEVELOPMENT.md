# Development guide

[Home](../README.md) · [Usage](USAGE.md) · [Recovery](RECOVERY.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Development](DEVELOPMENT.md) · [Maintaining](MAINTAINING.md)

Implementation and verification reference for contributors. Read CONTRIBUTING.md for the review workflow and AGENTS.md for shared agent rules.

## Tech stack

The runtime is a Python CLI, with no third-party Python packages, hosted backend or model service.

| Layer | Technology | Role |
| --- | --- | --- |
| 🐍 CLI and orchestration | Python 3.9+ · `argparse`, `pathlib`, `dataclasses` | Modes, paths, confirmations and operation plans. |
| 📦 Archives and integrity | macOS `ditto` · `zipfile` · `hashlib` / SHA-256 | Capture/extract trees, inspect ZIP members and verify archived/copied bytes. |
| 💾 Device and process control | macOS `diskutil`, `sync` · `subprocess` · `fcntl` | Safe eject, filesystem flush, subprocess progress and OS-backed locks. |
| 🗂️ Records and diagnostics | UTF-8 JSON · Python `sqlite3` | Run state, snapshots, difference reports, manifests and read-only KOReader statistics checks. |
| 🌐 Locale foundation | UTF-8 JSON catalogs · Python `string` / `unicodedata` | Reviewed locale selection, named placeholders and safe English fallback. |
| 🧪 Tests and CI | `unittest` · temporary fixtures · GitHub Actions | Migration/recovery/privacy regressions across macOS/Linux and three Python versions. |
| 🛠️ Maintainer tooling | Git · GitHub CLI (optional) | Reviewed feature-branch publication and PR creation; unnecessary for migration. |

Reading metadata and plugins are transferred as files. Lua is not an execution dependency of this tool. GitHub and Shields.io serve README badges only; the migration CLI does not contact those services.

## Project layout

```text
kobo-koreader-migrate.py   CLI and migration/management implementation
locales/                 registry and reviewed UTF-8 catalogs
scripts/                 locale validation, publication checks and PR helper
tests/                   synthetic migration, management, locale and privacy regressions
docs/                    user, recovery, troubleshooting, development and maintainer guides
.github/workflows/       CI matrix
.githooks/               optional local pre-push guard
AGENTS.md                shared agent development rules
TRACKER.md               feature roadmap and i18n design
ACCEPTANCE.md            human verification checklist
runs/                    private generated data; ignored by Git
```

The script uses the directory containing it as the default output root. No dependency installer, package manager or hosted service is needed for migration. Keep locales/ with the script in clones and source archives. Generated data and private local instructions are outside the publication allowlist.

## Tests and validation

Run from the repository root, without a Kobo:

```bash
python3 scripts/check_locales.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 kobo-koreader-migrate.py --self-test
python3 scripts/check_publication.py --worktree --history
```

Tests use temporary synthetic devices and mock USB/eject operations. On macOS, an additional test uses real ditto for FULL migration, saved-source reuse and exact TARGET restoration on temporary directories. It never reads a physical Kobo; other test hosts skip that fixture.

Add meaningful tests for changed behavior and safety boundaries. Documentation-only work needs relative-link/anchor checks, CLI/example verification, shell syntax checks and publication privacy review. The publication helper independently runs its mandatory full checks before uploading.

Run scripts/check_locales.py after any catalog/registry change. The three initial catalogs each contain 36 foundation message entries; validation does not substitute for human translation review. Keep mode tokens, flags, JSON schemas and destructive confirmation semantics language-independent.

## Validation and release status

The development build is **3.3.0-dev.1**. Physical-Kobo testing and human sign-off remain pending; the release is experimental.

Published agent-guidance commit [48ac339](https://github.com/gh-slee/kobo-koreader-migrate/commit/48ac3399962f9c938ef0929063eb95140532eac1) passed all twelve push/PR CI checks on 2026-10-15. CI covers macOS and Ubuntu on Python 3.9, 3.12 and 3.14. Linux checks fixtures only. The local baseline for that commit was 116 tests plus self-test and locale validation.

New changes require fresh validation. Temporary fixtures and the real macOS ditto round trip do not establish hardware compatibility. KM-011/KM-005/KM-001/KM-003/KM-013 remain Ready for test; see [manual acceptance](../ACCEPTANCE.md). KM-014/KM-015 actual migration-interface localization remains queued. Follow the current [CI runs](https://github.com/gh-slee/kobo-koreader-migrate/actions) and [PR #1](https://github.com/gh-slee/kobo-koreader-migrate/pull/1) for review status.

## Coding agents

The root [AGENTS.md](../AGENTS.md) is the shared source of agent guidance using the [AGENTS.md open format](https://agents.md/). Keep it concise and link task-specific documentation rather than duplicating it in multiple vendor rule files. Contributors remain responsible for understanding, testing and reviewing AI-assisted changes.

For personal Codex defaults, use its documented user-level AGENTS.md. For private project-specific instructions, Codex supports a Git-ignored AGENTS.override.md. At one directory level, Codex selects the override instead of AGENTS.md; a local override must explicitly read the public AGENTS.md to retain this project's shared rules. This is a Codex feature, not a universal private-file standard. See [official instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Codex's local managed worktrees automatically copy an ignored AGENTS.override.md. Other ignored files require deliberate .worktreeinclude configuration; ordinary clones, manual Git worktrees and remote environments do not gain this behavior. See [official worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees). This project needs no extra private Markdown loader or worktree include file for its local override. Private instructions and credentials must never be added to a public commit.

Validate setup from a fresh session started in the repository: ask the tool which instructions it loaded and verify that shared rules remain active. Other assistants have their own discovery and subagent inheritance rules. Give delegated agents the applicable guidance and task context; do not assume automatic inheritance. Development guidance never changes the migration tool's offline runtime requirements.

## Feature and locale work

Use [TRACKER.md](../TRACKER.md) for feature criteria and the i18n design. Follow the requested ticket scope; a backlog entry is not authority to start implementation or access devices. Use [ACCEPTANCE.md](../ACCEPTANCE.md) for human feedback and [CHANGELOG.md](../CHANGELOG.md) for behavior changes. This documentation organization adds no new runtime feature or complete translation claim.
