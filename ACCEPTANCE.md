# Manual acceptance and sign-off

Version 3.2.0 is ready for controlled testing, not signed off on physical devices. KM-011, KM-005, KM-001 and KM-003 remain Ready for test. Public-release changes also require review. Automated tests use synthetic fixtures and do not replace this checklist.

Run commands from the repository root, or pass `--backup-dir` consistently if using a separate private output root. Stop any older migration worker first. Use disposable test books and retain all recovery snapshots until acceptance is complete.

## Offline checks (no Kobo connected)

```bash
python3 kobo-koreader-migrate.py --version
python3 -m unittest discover -s tests -p 'test_*.py'
python3 kobo-koreader-migrate.py --self-test
python3 kobo-koreader-migrate.py --list-runs
python3 kobo-koreader-migrate.py --cleanup
python3 scripts/check_publication.py --worktree
```

Confirm that these work with AI applications closed and without AI services/credentials. Cleanup alone must list eligibility without deleting anything. Legacy/non-success runs must remain protected.

## KM-011: locks and durable status

- Start a preview and attempt another run against the same output root. The second worker must report busy and refuse.
- Complete a preview; inspect `run.json` for `audited`. Decline final confirmation; expect a friendly message, status `cancelled` and no target changes.
- A stale lock filename after process exit must not block a new worker. Do not delete a live lock to test this.
- Interruption and failure records must not be marked successful. Test destructive fault scenarios only on synthetic fixtures.

## KM-005: difference report

Prepare a disposable library with one new book, one different matching-path book, one identical book and one TARGET-only book, with matching `.sdr` sidecars.

```bash
python3 kobo-koreader-migrate.py --mode full --dry-run
python3 kobo-koreader-migrate.py --mode library --books --no-fonts --conflict keep-target --dry-run
```

Check `difference.txt`/JSON categories and book/sidecar groups. Preview must not modify either Kobo or create ZIPs. TARGET-only books are retained. Keep-target must protect the different book's reading metadata.

## Generic SOURCE/TARGET workflow

- Confirm physical model labels, even when hints agree. A copied/stale log must not be reported as hardware verification.
- Renamed volumes containing `.kobo/` should be found; multiple mounted readers must be refused.
- Two distinct readers of the same model should be allowed; the same fingerprint in both roles must be refused.
- FULL/KOREADER require explicit SOURCE runtime compatibility confirmation. A missing identity file must refuse migration.
- After a controlled FULL transfer, inspect books, progress, annotations, fonts, plugins and TARGET identity. TARGET-only books outside KOReader must remain.
- KOREADER must change only the whole `.adds/koreader` tree; external books/fonts must remain untouched.

## KM-001: saved source and exact target restore

Use a successfully captured disposable test batch. Replace RUN_ID with its actual ID.

```bash
python3 kobo-koreader-migrate.py --from-run RUN_ID --dry-run
python3 kobo-koreader-migrate.py --restore-run RUN_ID --dry-run
```

Saved-source preview must need only TARGET and record a dependency on the source batch. Exact restore must require the original target and display the planned restorations/removals. A different fingerprint or missing/corrupt archive/manifest must refuse writes. Do not corrupt your only real recovery copy to test this; use fixture copies.

After reviewing the restore preview, a controlled restore should return the affected test paths/runtime to their pre-migration state. It creates pre-restore undo backups. Later changes to affected paths can be overwritten, so use disposable data.

## KM-003: backup management

- Catalog lists status and sizes. Cleanup previews protection reasons and reclaimable eligible batches.
- Recent successes, source dependencies, latest per-target recovery points and failed/interrupted/legacy batches remain protected.
- `--cleanup --delete-run RUN_ID --dry-run` must not delete.
- Wrong typed confirmation must not delete.
- Actual whole-batch deletion requires explicit eligible IDs and exact typed confirmation. Test this using disposable generated fixtures only; it is not required to delete real backups for sign-off.

## Publication review

- README explains all current modes/options and limitations using generic paths.
- Public Git content has no actual books, backups, reports, device configurations, personal paths or credentials.
- Review staged diff and public author identity, then run the index/history publication guard.
- Feature changes use PRs. Approval and passing CI precede merge; no automatic merge.

## Sign-off record

Record version, tested macOS/Python versions, hardware model pair, modes tested, ticket IDs, result and remaining problems. Keep serial numbers, book names and private reports out of public records. Leave each ticket Ready for test until explicit human acceptance is recorded.
