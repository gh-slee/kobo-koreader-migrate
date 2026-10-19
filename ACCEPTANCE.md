# Manual acceptance and sign-off

The [3.3.0-dev.2 experimental pre-release](https://github.com/gh-slee/kobo-koreader-migrate/releases/tag/v3.3.0-dev.2) was published on 2026-10-18. A connected-device KOREADER transfer, verified target recovery and basic KOReader operation have scoped confirmation; the full physical/manual checklist is not signed off. The base migration acceptance work from 3.2.0 remains pending. KM-011, KM-005, KM-001, KM-003 and KM-013 remain Ready for test. Publication is not acceptance. Automated tests use synthetic fixtures and do not replace this checklist.

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

## Statistics handles and safe eject (3.3.0-dev.2)

Current scoped evidence: connected-device KOREADER transfer and verified target recovery completed, and basic KOReader operation was confirmed. This does not sign off all controls/plugins, other modes or the remaining feature checklists.

- With a statistics database present, run KOREADER dry-run and confirm both SOURCE and TARGET safely eject without the migration process retaining the SQLite file.
- No device files or ZIPs should be created by the preview. Keep the run audited only after the entire preview succeeds.
- Success/error connection-closure regressions use synthetic databases; never corrupt a real device database for this test. A preview result does not sign off migration writes or hardware settings.

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


## KM-013: locale foundation (3.3.0-dev.1)

Status: Ready for test. This is partial i18n support, not complete migration-interface translation. No Kobo is needed for these checks. Keep locales/ beside the script.

```bash
python3 kobo-koreader-migrate.py --list-locales
python3 kobo-koreader-migrate.py --locale en --preview-ui
python3 kobo-koreader-migrate.py --locale zh-Hant --preview-ui
python3 kobo-koreader-migrate.py --locale zh-Hans --help
python3 scripts/check_locales.py
```

- Check all three options, translation wording, FULL/KOREADER distinctions, default-No examples and exact DELETE RUN_ID text. Previews must not request an answer, connect devices, inspect run data or create runs/logs/backups.
- Use a known terminal locale alias or KOBO_MIGRATE_LOCALE to confirm preference selection. Explicit --locale must win. Bare zh must not silently guess a Chinese script.
- An unsupported explicit locale must fail before device activity. Do not damage production catalogs to test fallback; malformed/missing assets are covered by synthetic automated tests.
- The published 3.3.0-dev.2 messages remain English. Development 3.3.0-dev.3 partially localizes runtime presentation; tool-owned log text remains English. Do not sign off all of KM-014/KM-015 based on a preview.
- Automated evidence: 114 fixture tests, including language-independent FULL outcomes and the actual macOS ditto fixture; this is not hardware acceptance. Record explicit human feedback before marking KM-013 Done.

## KM-018: local source package preparation (no Kobo)

Status: Ready for test on the development branch; this helper is not part of the already published 3.3.0-dev.2 ZIP. Run from a clone containing the helper after committing the reviewed changes:

```bash
python3 scripts/prepare_release.py prepare --ref HEAD
```

- The helper must create a fresh `.local/releases/VERSION-COMMIT/` with a complete source ZIP, `SHA256SUMS` and local-only `PREPARATION.json`. It must not create a tag, access a Kobo or contact GitHub.
- Use the printed directory and exact source commit with `python3 scripts/prepare_release.py verify DIRECTORY --ref COMMIT`. Verification must recheck actual ZIP bytes against that commit, not trust the preparation record or checksum alone.
- Offline commands and local documentation file links must pass from a temporary extraction. Required locale assets must be included, even for English.
- Repeating preparation into the same destination must refuse without overwriting anything. Different output parents can hold separate copies.
- Synthetic regressions cover private/untracked and modified files, bad refs, missing locales, symlinks, unsafe/duplicate ZIP members, tampering, failed extracted commands and broken links. Do not tamper with a real recovery archive for testing.
- This is source-package validation, not a new full unit-test run, privacy guarantee, hardware certification or publication approval. See [maintainer instructions](docs/MAINTAINING.md#local-package-preparation-and-verification).

## KM-014 slice 1: shared routing (3.3.0-dev.3)

Status: Ready for controlled testing of this slice; full KM-014 remains In progress and KM-015 human wording review is pending. The published pre-release ZIP does not contain this change.

- In a disposable project root, use --list-runs/--cleanup in en, zh-Hant and zh-Hans. Headings/instructions should match the selected locale; run IDs/status tokens and protection reasons retain their technical/English values. Preview creates no deletion.
- Review translated SOURCE/TARGET confirmation wording and [y/N]/[Y/n] defaults. Only y/yes/n/no are accepted; numeric choices and exact DELETE RUN_ID remain unchanged. Use synthetic disposable batches for any cleanup deletion test.
- In controlled migration tests, inspect console versus the saved log: integrated owned messages should be localized on screen and occur once in English in the log. Raw diagnostics, user/device data and unconverted messages are preserved; Unicode filenames can appear in both. Responses typed at prompts must not be recorded.
- Check localized difference.txt against stable difference.json category/path/action data. ui_locale may be present in modern records; older records without it must remain usable.
- Rendering/fallback, ascii-console safety, all-mode equivalence, saved-source/restore, final default-No, rollback after writes and context/exit-state regressions use temporary fixtures. Do not induce failures on real readers or corrupt a real recovery backup for this test.
- Record manual feedback separately. For slice 1, menu/device extraction was still pending. Slice 2 adds menus/basic inspection; detailed metadata/plugin diagnostics/errors and remaining workflow messages still need extraction; do not label this full interface translation or full hardware acceptance.

## KM-014 slice 2: menus and inspection (3.3.0-dev.4)

Status: Ready for controlled testing of this slice; full KM-014 remains In progress, with human wording and hardware acceptance pending. Use only disposable data for induced failures; no real Kobo is required for the synthetic tests.

- Review all three languages for mode/identity/conflict menus. Numeric choices/defaults must match: FULL default; preserve identity when available, new otherwise; unavailable preserve must retry; keep-target remains unsupported for FULL/KOREADER.
- Inspect a synthetic device with known and unknown values. Labels/yes/no/unknown should localize; model/version/path/serial-hint/size/count values must remain intact. English logs must not contain translated owned labels or duplicate entries.
- Review physical-model hints and mismatch warnings. A log hint never proves the hardware model; the following confirmation still defaults to No.
- Capacity reports should show the same values in all languages. Synthetic tests cover backup/target thresholds one byte below, exactly at and one byte above the requirement; replaced-runtime space is still counted. LIBRARY low space must refuse before TARGET backup/writes.
- Detailed errors/metadata/plugin diagnostics and other workflow notices are not fully translated. Existing release assets and older saved runs must remain usable; this slice is not a new public release or full translation/hardware sign-off.
