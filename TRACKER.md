# Development tracker

Last reconciled: **2026-10-15**. Tool version: **3.2.0** (experimental; physical acceptance pending).

Status vocabulary: `Queued`, `In progress`, `Ready for test`, `Blocked`, `Done`, `Deferred`. KM-011, KM-005, KM-001 and KM-003 are implemented and ready for user testing; no human sign-off has been recorded. Entries represent planned work, not permission to operate physical devices or delete backups.

## Mandatory runtime requirement (all tickets)

Every current and future feature must be implemented as ordinary executable code that users can run directly from Terminal without any LLM. Do not depend on AI inference APIs, local/remote model servers, model downloads, an agent framework, or an active Codex/ChatGPT session. LLMs may assist authoring and maintenance only.

Acceptance for every ticket must include standalone CLI operation without AI API keys/services, explicit algorithmic rules, and documented commands/ordinary user confirmations where needed. Preserve the offline core migration/maintenance workflow. Copying existing KOReader AI-plugin files does not authorize executing them.

## Current acceptance work

1. **KM-011**: execution lock and durable run status (foundation for safe cleanup/resume).
2. **KM-005**: pre-migration difference report.
3. **KM-001**: migrate/restore from verified saved archives.
4. **KM-003**: backup management and cleanup preview.

These four tickets are awaiting user testing/sign-off, not additional autonomous implementation. Read ACCEPTANCE.md. Remaining Queued tickets are not authorized by this release.

## Backlog

| ID | Priority | Status | Feature | Acceptance criteria / key constraints |
| --- | --- | --- | --- | --- |
| KM-001 | P1 | Ready for test | Restore/migrate from saved backup | Select an existing source run, verify ZIP + manifest + member paths before writes, require correct target/model confirmation, create target rollback backup, retain identity options. Separate restore of a previous target snapshot from new source migration; no source Kobo needed. |
| KM-002 | P2 | Queued | Resume interrupted transfer | Durable per-file journal; revalidate source archive and target identity; hash completed files before skipping; define recovery for interruption during FULL runtime replacement; preserve rollback capability. Depends on KM-011 and benefits from KM-001. |
| KM-003 | P1 | Ready for test | Backup management and cleanup preview | List runs, size, age, status and dependencies; preview reclaimable space; retain configurable recent successful batches; never select active/incomplete/only-recovery backups by default. Deletion needs an explicit user action. Depends on KM-011. |
| KM-004 | P3 | Queued | Exact library mirror option | Opt-in only; dry-run lists target-only books and sidecars to remove; back up removals, verify source scan completeness and capacity, support rollback. Default FULL behavior must continue retaining target-only books. |
| KM-005 | P1 | Ready for test | Detailed migration difference report | Human-readable and JSON lists/counts/bytes for new, overwritten, identical, kept and target-only files; group books with sidecars; inspect/report target-only books without silently broadening source format assumptions. Existing scan.json is a partial foundation. |
| KM-006 | P2 | Queued | Content-assisted book detection | Safe bounded signature/container checks for extensionless or mislabeled EPUB/PDF and selected formats; discovery confidence and reason in report; exclude system files; no claim of complete DRM/library discovery. |
| KM-007 | P2 | Queued | Reading-data conflict report | Read-only comparison of locations, mtimes, progress and annotation counts when safely parseable; show ambiguity/edition mismatches; no Lua execution and no silent annotation merging. Establish supported metadata schema before parsing. |
| KM-008 | P2 | Queued | Preserve target hardware settings | Optional portable policy preserving target-specific keys (buttons, rotation, lighting, calibration) while moving reading preferences. Use a tested Lua literal parser, not whole-table regex or Lua execution. Keep exact FULL clone option. |
| KM-009 | P2 | Queued | Settings-only migration | Preserve destination KOReader runtime/version, transfer compatible settings/custom plugins/resources, validate version compatibility and rollback; decide interaction with portable hardware policy KM-008. Avoid copying source core plugins blindly. |
| KM-010 | P2 | Queued | Standalone backup verification | CLI to verify existing archive SHA-256 and member content against manifest, unsafe paths/duplicates, corruption and missing pairs; read-only and usable without any Kobo. Reusable by KM-001/KM-003. |
| KM-011 | P1 | Ready for test | Execution lock and run status | Prevent concurrent runs targeting the same project/device; recover stale lock safely; durable status transitions (running, success, cancelled, failed, rolled-back, needs-recovery), distinguish interruption from success, update on every exit. Logs alone are insufficient for status. |
| KM-012 | P2 | Queued | Maintainable project structure and Git hygiene | Tracker, agent instructions, README and portable tests are now present. Git ignore policy, changelog and project-owned macOS fixture test were added with 3.1.0. Public-release privacy guard, documentation, CI and PR helper are implemented. Remote bootstrap/authentication status is recorded under public preparation below. |

## Completed baseline (verified in current code)

| ID | Status | Feature |
| --- | --- | --- |
| BASE-001 | Done | FULL, KOREADER, LIBRARY, AUDIT and dry-run; FULL automatically includes supported books + reading data and default root fonts. |
| BASE-002 | Done | Original relative paths, adjacent `.sdr`, central `docsettings/`, `hashdocsettings/`, legacy metadata and root font copying. Scoped scans conservatively skip central metadata. |
| BASE-003 | Done | Incremental size/SHA-256 comparison; library overwrite/keep-target policies with metadata protection. |
| BASE-004 | Done | Source and target backups, per-file manifests, restore verification and caught-failure rollback. |
| BASE-005 | Done | Best-effort model detection, same-device fingerprint guard, disk-space checks, safe eject and device_id options. |
| BASE-006 | Done | Plugin structural audit, read-only statistics quick_check/row counts, missing literal references, symlink/ZIP/path checks. |
| BASE-007 | Done | Detailed file/byte progress, large-file speed/ETA and subprocess heartbeat output. |
| BASE-008 | Done | Stable script filename, version in output/log/JSON; generated files under script-relative `runs/<run-id>/`. |
| BASE-009 | Done | Normal cancellation uses MigrationCancelled and a friendly message rather than MigrationError/ERROR. |

## Current constraints and historical evidence

- No successful physical-device migration has been recorded for this release. Do not infer hardware acceptance from fixture tests.
- Backup batch files are flat inside each run. Proposed `source/`, `target-backup/`, `reports/` subdivision is not implemented.
- Retention/cleanup preview, durable run status and execution locks exist in 3.1.0. Automatic resume is still queued. Legacy runs without run.json stay protected as legacy/unknown.
- FULL/KOREADER copy source runtime version. Target-specific hardware settings are not selectively preserved; only device_id has a dedicated policy.
- Standard-library tool and fixture tests target Python 3.9+. Record actual local/CI versions separately.
- Credentials can exist in archives; do not print, commit or upload them. Tests must not read physical Kobo contents.

## Session handoff

Current release: **3.2.0**, KM-011/KM-005/KM-001/KM-003 implementation complete and **Ready for test**. User explicitly requested to test and sign off. Do not mark these tickets Done without their approval. No physical Kobo was accessed and no real backups were deleted during development.

See ACCEPTANCE.md for test commands and sign-off checklist. Target snapshot restoration needs a v3.1+ run with target-snapshot.json and target-changes.json; legacy full-source snapshots can be reused when verified. FULL snapshots cannot be reused as LIBRARY because central metadata is inside the runtime archive. Libraries should use a LIBRARY-captured snapshot.

For the next authorized feature session:

1. Read this tracker, `AGENTS.md`, `README.md` and current CLI/code; reconcile facts with files.
2. Pick the requested ticket (or the next P1 when broad feature development is authorized).
3. Record scope, status, compatibility decisions and test plan before edits.
4. Implement without weakening existing FULL/KOREADER semantics; run meaningful regressions.
5. Update version, tracker evidence, documentation and unfinished-work notes together.

## Validation ledger

- 2026-10-09: v3.0.4 portable regression suite **45 passed** in development workspace; actual macOS `ditto` round trip and simulated FULL workflow passed earlier. These were fixture tests, not a physical migration.
- 2026-10-12: tracker/context installed; project-owned portable regression suite **45 passed**, and script `--self-test` **passed**. No production script behavior was changed and no physical Kobo was accessed.

- 2026-10-12: v3.1.0 — **78 tests passed**, including actual macOS ditto FULL → saved-source reuse → exact TARGET restore using temporary fixtures; --self-test passed. Added live-process lock, dependency/retention, corruption, source-mode, rollback and dry-run regressions. Human/physical Kobo tests pending.

## Public preparation (authorized)

| ID | Status | Scope / acceptance |
| --- | --- | --- |
| PUB-001 | Ready for review | Expanded Git ignore policy, source allowlist, staged/history privacy gate and local pre-push hook. Human diff review remains required; heuristics cannot prove absence of all personal data. |
| PUB-002 | Ready for test | Generic SOURCE/TARGET roles and confirmed labels, renamed-volume discovery, mandatory fingerprints, same-device rejection, explicit runtime compatibility confirmation; preserve FULL/KOREADER and legacy snapshots. |
| PUB-003 | Ready for review | Detailed English README, MIT license, contribution/security/manual acceptance docs and fixture CI. |
| PUB-004 | In progress | Clean Git history, public alias/noreply identity, authenticated remote bootstrap. No private run files may be included. |
| PUB-005 | Ready for review | Standalone feature-branch publication helper runs privacy/tests, pushes and creates/reuses a PR. Human approval before merge; no force push or automatic merge. |

Public preparation does not complete physical acceptance of KM-011/KM-005/KM-001/KM-003. Local implementation/test evidence and remote bootstrap outcome must be recorded before handoff.

- 2026-10-15: v3.2.0 public preparation — 95 local tests passed on Python 3.12.2/macOS, including the actual ditto fixture. Self-test and candidate publication check passed. Added generic-role/saved-source/restore regressions and Git blob/history/publish-helper tests. No physical Kobo was accessed, no real backups were deleted, and physical acceptance remains pending.
