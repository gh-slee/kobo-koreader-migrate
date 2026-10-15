# Changelog

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
