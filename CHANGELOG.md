# Changelog

## 3.3.0-dev.3 — unreleased — KM-014 shared output routing slice 1

- Introduce explicit message IDs/parameter contracts and scoped console/English-log rendering. Integrated messages bypass the legacy tee, preserve output channels, flush progress, support non-UTF-8 consoles and never log typed answers.
- Integrate shared confirmations, progress, run status, catalog/cleanup headings and difference labels; retain English string compatibility for existing helpers. Add 58 static messages per locale (94 total); full workflow extraction and human wording review remain pending.
- Add optional ui_locale to run.json/difference.json; localize difference.txt while retaining stable category/action tokens and original paths. Old records remain readable.
- Add synthetic routing, prompt/default/token, all-mode/saved-source/restore equivalence, cancellation, interrupt and rollback tests across en/zh-Hant/zh-Hans. Device semantics and offline standalone requirements remain unchanged.
- Local validation: 154 tests (16 new shared-output/workflow cases), self-test, 3x94 locale and publication checks passed. Hosted CI and human translation/hardware acceptance remain pending.
- This is a local development slice, not a new published release or completion of KM-014/KM-015/manual hardware acceptance.

## Unreleased — maintainer tooling and documentation

- Add offline `scripts/prepare_release.py` prepare/verify commands for explicit Git commits: guarded committed files only, complete runtime/locale assets, ZIP-to-Git byte verification, temporary-extraction smoke checks and local documentation links, SHA256SUMS and local preparation records.
- Add synthetic source-package safety regressions and CI package preparation. Existing output directories are not overwritten; the helper has no upload, tag or device-operation commands.
- Reconcile published pre-release, hosted CI and scoped hardware evidence across the README, tracker and guides. This does not complete pending manual acceptance, change migration behavior or replace the already published asset.
- Maintainer follow-up validation: 138 local tests (15 package regressions), self-test, locale and publication checks passed; merged PR #5 main CI passed all six jobs.

## 3.3.0-dev.2 — 2026-10-18 — published experimental pre-release

- Explicitly close read-only statistics connections after diagnostics, including error exits. SQLite transaction context management alone does not close a connection and can leave the migration process blocking safe eject.
- Tolerate already-removed descendants during KOReader tree replacement, rollback and restore on older supported Python versions. Keep missing-root, permission and symlink errors visible. This handles disappearing macOS AppleDouble entries without suppressing other deletion errors.
- Add synthetic removal-race, permission, missing-root and symlink regressions.
- Add retained-connection regressions for successful and invalid-database diagnostics, verifying deterministic closure and unchanged fixture bytes.
- Validation: 123 local tests, self-test, locale validation and publication checks passed. Connected-device source capture, verified target recovery and saved-source KOREADER transfer completed with full manifest verification; basic KOReader operation was subsequently confirmed. The exact release commit passed all six [main CI jobs](https://github.com/gh-slee/kobo-koreader-migrate/actions/runs/39155468946). The [experimental pre-release](https://github.com/gh-slee/kobo-koreader-migrate/releases/tag/v3.3.0-dev.2) is published; broader hardware acceptance and FULL book migration remain pending.

## Publication guard follow-up — 2026-10-15 — subsequently merged

- Diagnosed PR-only CI rejection of GitHub's public merge committer address. Approved branch push CI passed all six macOS/Linux and Python 3.9/3.12/3.14 jobs.
- Permit exact `noreply@github.com` only as a merge committer; user noreply authors, all file/content/history scans and personal-email rejection remain required.
- Added real Git-history fixtures covering seven allowed/rejected identity cases. All 115 tests, self-test and locale validation passed locally. The guard follow-up was subsequently merged into main; physical acceptance remains separate from automated checks and PR merge.

## 3.3.0-dev.1 — 2026-10-15 — KM-013 foundation; ready for user testing

- Added offline JSON locale registry/catalogs for en, zh-Hant and zh-Hans, explicit/environment selection, script-aware aliases and safe English fallback.
- Added localized help descriptions, --list-locales and a read-only --preview-ui sample. Actual migration/maintenance UI and diagnostic logs remain English; full localization is pending KM-014/KM-015.
- Added bounded UTF-8/schema/duplicate-key/placeholder/control-character/plural validation, exact locale-file publication allowlist, validator CLI and CI/publish-helper checks.
- 114 tests passed locally, including existing archive/migration regressions and equivalent temporary FULL outcomes in all three locale choices. Standalone self-test passed. No real Kobo was accessed or migrated, no real backups were deleted, and no physical-device acceptance was inferred. This batch was subsequently published for review as PR #1 after explicit approval.

## 3.2.0 — 2026-10-14 — Public preparation; physical acceptance pending

- Replaced fixed model-pair direction with operator-confirmed SOURCE/TARGET roles; log model labels are hints, not hardware verification.
- Discover renamed Kobo volumes by safe .kobo directory markers; require device fingerprints and explicit runtime compatibility confirmation.
- Saved-source/target-restore workflows accept confirmed model labels without inferring an opposite model. Existing archive names/snapshots remain usable.
- Added detailed generic documentation, MIT license, privacy ignore/allowlist/index/history checks, pre-push guard, fixture CI and standalone feature-branch PR helper.
- FULL, KOREADER, LIBRARY, AUDIT and conservative cleanup/rollback behavior retained.

## 3.1.0 — 2026-10-12 — Ready for user testing

- KM-011: OS-backed project/device locks, atomic run.json status and interruption reconciliation.
- KM-005: detailed text/JSON migration differences, target-only inventory in the same supported scope and book/sidecar grouping.
- KM-001: verified saved source reuse, reference/dependency tracking and distinct exact TARGET snapshot restoration for v3.1+ runs; legacy source imports are conservative.
- KM-003: run catalog, retention/dependency/recovery protections, read-only cleanup preview and explicit typed batch deletion.
- Added tests for cross-process locks, archive integrity, source reuse, exact restore and restore rollback, cleanup protection and actual macOS ditto fixture workflow.
- Existing FULL, KOREADER, LIBRARY and AUDIT semantics retained. Physical Kobo validation and human sign-off are pending.

## 3.0.4 — Existing baseline

Normal cancellation messaging, file/byte progress, stable project-relative script and per-run output folders; 45 portable regression tests passed before this release.
