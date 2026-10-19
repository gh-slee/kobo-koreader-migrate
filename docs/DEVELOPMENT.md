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
scripts/                 locale/privacy checks, source-package preparation and PR helper
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

Run scripts/check_locales.py after any catalog/registry change. The development catalogs each contain 94 extracted message entries (36 in the published 3.3.0-dev.2 foundation); validation does not substitute for human translation review. Keep mode tokens, flags, JSON schemas and destructive confirmation semantics language-independent.

## Validation and release status

The [**3.3.0-dev.2 experimental pre-release**](https://github.com/gh-slee/kobo-koreader-migrate/releases/tag/v3.3.0-dev.2) was published on 2026-10-18 from commit `721e2cad01c7c2811baeb9bd3fff424bba87f275`. Its [main CI](https://github.com/gh-slee/kobo-koreader-migrate/actions/runs/39155468946) passed all six macOS/Ubuntu Python 3.9, 3.12 and 3.14 jobs. The release baseline passed 123 local tests, self-test, locale and privacy checks. Connected-device target recovery and saved-source KOREADER transfer passed full manifest verification; basic KOReader operation was confirmed. Broader hardware acceptance, FULL book migration and the remaining manual checklists are still pending. This is not a stable release.

The development branch adds an offline [source-package helper](MAINTAINING.md#local-package-preparation-and-verification) and synthetic package-safety regressions. CI prepares and checks a source ZIP for its checked-out commit without uploading it. This helper is not included in the already published 3.3.0-dev.2 ZIP. Local follow-up validation passed 138 tests (including 15 package tests), self-test, locale and worktree/history privacy checks. The helper was merged as PR #5; its [merged-main CI](https://github.com/gh-slee/kobo-koreader-migrate/actions/runs/39165980479) passed all six jobs. Its extracted smoke checks do not rerun the full unit suite or establish hardware acceptance; new changes need their own test results.

[PR #1](https://github.com/gh-slee/kobo-koreader-migrate/pull/1) merged into main on 2026-10-16 as [564234e](https://github.com/gh-slee/kobo-koreader-migrate/commit/564234e2256bb6a64085cc10a4d3c5535322313e). Its [main-branch CI run](https://github.com/gh-slee/kobo-koreader-migrate/actions/runs/38918881111) passed all six macOS/Ubuntu Python 3.9, 3.12 and 3.14 jobs. Linux checks fixtures only. The pre-merge documentation commit dedc884 passed 117 local tests plus self-test and locale validation, and all twelve push/PR CI jobs.

New changes require fresh validation. Temporary fixtures and the real macOS ditto round trip do not establish hardware compatibility. KM-011/KM-005/KM-001/KM-003/KM-013 remain Ready for test; see [manual acceptance](../ACCEPTANCE.md). KM-014 shared output routing is in progress with slice 1 ready for controlled testing; full extraction and KM-015 catalog review remain pending. Follow the current [CI runs](https://github.com/gh-slee/kobo-koreader-migrate/actions) and [open pull requests](https://github.com/gh-slee/kobo-koreader-migrate/pulls) for subsequent changes.

## Coding agents

The root [AGENTS.md](../AGENTS.md) is the shared source of agent guidance using the [AGENTS.md open format](https://agents.md/). Keep it concise and link task-specific documentation rather than duplicating it in multiple vendor rule files. Contributors remain responsible for understanding, testing and reviewing AI-assisted changes.

For personal Codex defaults, use its documented user-level AGENTS.md. For private project-specific instructions, Codex supports a Git-ignored AGENTS.override.md. At one directory level, Codex selects the override instead of AGENTS.md; a local override must explicitly read the public AGENTS.md to retain this project's shared rules. This is a Codex feature, not a universal private-file standard. See [official instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Codex's local managed worktrees automatically copy an ignored AGENTS.override.md. Other ignored files require deliberate .worktreeinclude configuration; ordinary clones, manual Git worktrees and remote environments do not gain this behavior. See [official worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees). This project needs no extra private Markdown loader or worktree include file for its local override. Private instructions and credentials must never be added to a public commit.

Create private guidance only after confirming that both root and nested AGENTS.override.md paths are ignored and untracked. The local override must begin with this exact line:

```text
Before working, explicitly read ./AGENTS.md.
```

Keep personal preferences, operator authorization boundaries and concise current state in that private file. Replace stale branch/check/pending-work facts rather than appending transcripts. Never store credentials there or copy its contents into public guidance. Do not create custom OWNER.md/HANDOFF.md memory files. Keep shared rules in AGENTS.md; consolidate duplicate vendor instructions into references while preserving useful tool-specific activation and settings. No global Codex configuration change is required.

Other assistants have their own discovery and subagent inheritance rules. Delegate only when requested, and give each agent a bounded task and the applicable guidance; do not assume conversation inheritance. Development guidance never changes the migration tool's offline runtime requirements.

### Fresh-session verification

Start a new session with this repository as its working directory. Paste the following verification prompt; it does not authorize edits, device operations or publication:

```text
Verify this repository's agent setup without modifying files or publishing anything.
1. Identify instruction files supplied through startup discovery, separating them
   from files you explicitly read during this verification. If discovery provenance
   is unavailable, say so; do not infer discovery merely from a file's existence.
2. Follow any local override's instruction to read ./AGENTS.md explicitly.
   Summarize the shared stack, relevant validation commands and safety boundaries.
3. If private guidance is active, report only its effective response-language and
   publication-approval requirements. Do not quote private text, session notes,
   credentials or personal paths. Report missing guidance without inventing it.
4. Report the current branch, HEAD commit and working-tree status. Identify pending
   work without treating old approvals or checks as permission or fresh evidence.
5. State whether this is an actual fresh-session check or only a static file audit.
   If this is a worktree, verify destination guidance and branch/state separately.
```

After creating a local managed worktree, verify its ignored guidance and current branch/state at the destination. Ordinary clones, remote environments and manual worktrees need deliberate local setup; do not assume private files transferred. A successful file/ignore test does not prove startup discovery, precedence, agent compliance or worktree copying. Record a fresh-session or managed-worktree result only after actually performing that check.

### Public language policy

Canonical documentation, owned public code, comments and docstrings use English. Preserve original license terms, attribution and quoted source/user text. Locale catalogs, multilingual regression fixtures and necessary compatibility strings are intentional exceptions. Do not change stored application data or remove supported languages to eliminate non-English characters. Review translated heading anchors and executable examples when translating documentation.

There is no automated English-language guard. A CJK search can help review canonical prose, but cannot prove English grammar or translation accuracy; blanket non-ASCII bans would also reject valid names, symbols and localization fixtures.

## Feature and locale work

Use [TRACKER.md](../TRACKER.md) for feature criteria and the i18n design. Follow the requested ticket scope; a backlog entry is not authority to start implementation or access devices. Use [ACCEPTANCE.md](../ACCEPTANCE.md) for human feedback and [CHANGELOG.md](../CHANGELOG.md) for behavior changes. This documentation organization adds no new runtime feature or complete translation claim.

## Shared output routing (KM-014 slice 1)

Development 3.3.0-dev.3 adds a ContextVar-scoped UIOutput adapter. Explicit message IDs and named values render separately for the selected console locale and English diagnostic log. UIMessage retains its English string representation so existing helper contracts and technical comparisons do not depend on the selected language. Do not translate already-formatted output or monkeypatch print/input. A nested ui_session binds the original stdout/stderr plus the run log; it resets in finally on every exit. Emitters bypass LogTee to avoid duplicate/localized log entries. Legacy print/external diagnostics still pass through the tee unchanged until extracted.

UI_MESSAGE_FIELDS inventories the integrated IDs and exact named parameters. Canonical missing/mismatched fields fail at catalog load. Both renderings are computed before either stream is written; all integrated templates are pre-rendered before run creation/device access. A translation formatting failure falls back to English. Filenames, model labels, statuses and other technical data are never translated; original Unicode data can legitimately occur in an English log. Severity and output channel are explicit and preserve stdout/stderr routing. Typed responses are never logged. Shared yes/no defaults, numeric choices and exact cleanup tokens remain unchanged.

| Integrated IDs / surface | Remaining extraction |
| --- | --- |
| prompt.*, confirm.* | Physical model free-text prompt; mode/identity/conflict menu questions and option descriptions |
| progress.* | Spinner/scan/comparison phase sentences and per-file diagnostic lines |
| run.*, error.summary | Detailed MigrationError text, caught-failure/rollback explanations and pre-run interrupt output |
| catalog.*, cleanup.* | Cleanup protection reasons and detailed maintenance errors |
| difference.* | Machine JSON notes remain English; paths/action tokens unchanged |
| device.waiting/connect_one/detected, migration.success/done | Device inspection, space/metadata/plugin diagnostics, restore completion and remaining workflow notices |

run.json and difference.json gain optional ui_locale metadata. No status/category/phase tokens or recovery schemas are renamed; old runs remain accepted. difference.txt is localized human presentation. Full message extraction, consistent raw-diagnostic labelling and full human catalog review are later KM-014/KM-015 work, not completed by this slice. All text is static UTF-8 JSON and ordinary offline Python code; there is no runtime translator or AI dependency.

Synthetic regressions compare all four modes, saved-source reuse, exact target restore, final default-No, rollback after writes, cleanup tokens and exit states across the three locales. Stream tests cover English logs, Unicode/ascii output, no duplicate tee entries, fallback, parameter contracts and context cleanup. These do not establish physical-device acceptance or human translation sign-off. New hosted CI results require publication of this branch.

Local slice evidence: 154 tests passed (16 new shared-output/workflow tests), self-test, all 94 messages in each of three catalogs and publication worktree/history checks. The existing main CI applies to the merged baseline; hosted CI for this local slice remains pending.
