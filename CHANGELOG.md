# Changelog

## Publication guard follow-up — 2026-10-15 — ready for review

- Diagnosed PR-only CI rejection of GitHub's public merge committer address. Approved branch push CI passed all six macOS/Linux and Python 3.9/3.12/3.14 jobs.
- Permit exact `noreply@github.com` only as a merge committer; user noreply authors, all file/content/history scans and personal-email rejection remain required.
- Added real Git-history fixtures covering seven allowed/rejected identity cases. All 115 tests, self-test and locale validation passed locally. Follow-up changes await separate push approval; physical acceptance and PR merge remain pending.

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
