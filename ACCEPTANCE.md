# Manual acceptance and sign-off

This source snapshot is **1.0.0-rc.2**, a documentation candidate following the published [1.0.0-rc.1](https://github.com/gh-slee/kobo-koreader-migrate/releases/tag/v1.0.0-rc.1). The implementation continues the [3.3.0-dev.6 experimental package](https://github.com/gh-slee/kobo-koreader-migrate/releases/tag/v3.3.0-dev.6), published on 2026-10-19. A KOREADER transfer from that package passed full manifest verification, TARGET identity preservation and safe eject; startup and opening an existing TARGET book were explicitly confirmed. FULL preview safely refused insufficient space before writes. These are scoped results, not ticket-wide sign-off or stable acceptance. Earlier recovery evidence remains historical. Private device reports/backups stay local. See the [numbering policy](docs/MAINTAINING.md#versioning-and-first-stable-release).

Run commands from the repository root, or pass `--backup-dir` consistently if using a separate private output root. Stop any older migration worker first. Use disposable test books and retain all recovery snapshots until acceptance is complete.

## KOReader Bridge name and scope review (KM-019)

Status: Ready for human review. This is documentation work; no device connection or migration is needed.

- README identifies the project as KOReader Bridge and states that only Kobo → Kobo migration on macOS is currently implemented. General Kobo build compatibility and remaining first-stable acceptance limits are still explicit.
- Kindle and other device families are labelled future/unsupported. Non-Kobo tickets do not block the existing Kobo `1.0.0` milestone or count as implemented support.
- Existing CLI commands, filename, locale catalogs, schemas, output paths and published archive names remain unchanged. Download links still point to real existing assets.
- The proposed GitHub repository rename is tracked separately under KM-020. Current badges, clone commands and release links continue using the actual repository until that operation is approved and completed. Renaming review is not physical-device sign-off.

## First stable release gates

Target sequence: published `1.0.0-rc.1`, further candidates such as this `1.0.0-rc.2` source snapshot, then `1.0.0` after sign-off. Consult the release page for published assets rather than inferring publication from a source version. Version labels do not complete acceptance. These gates cover the existing scope, not the entire future backlog.

| Gate | Required evidence | Current state |
| --- | --- | --- |
| FULL and LIBRARY | Controlled end-to-end copying with adequate capacity; original paths, books, adjacent/central reading data, fonts, identical/overwrite handling and retained TARGET-only content checked. | Pending physical acceptance; synthetic coverage and FULL low-space refusal observed. |
| KOREADER | Whole runtime replacement, identity preservation, file hashes, safe eject and basic operation. Review the relevant controls/plugins and confirm candidate equivalence before stable sign-off. | Scoped transfer/startup/book-opening confirmed for published 3.3.0-dev.6; wider checks pending. |
| Saved-source and restoration | Human rehearsal of previews and a controlled exact restore with before/after evidence and retained undo backups; old supported snapshots remain usable. | Synthetic and historical scoped recovery evidence exists; final combined sign-off pending. |
| Locks, cancellation and cleanup | Busy/stale ownership, default-No, durable states, eligibility/protection and exact typed confirmation. Use disposable fixtures for deletion and induced faults. | Automated coverage exists; human acceptance pending. |
| Languages | Review all three catalogs, particularly destructive scope, negation, default-No and exact input tokens; verify localized console versus English diagnostics. | 371 entries per locale and automated/editorial checks complete; human wording sign-off pending. |
| Candidate and distribution | Exact candidate commit passes supported CI, locales, tests, self-test, privacy/history, documentation and independently extracted package checks. Downloaded published bytes must match reviewed assets. | RC1 passed 185 tests, six exact-main CI jobs, Git-matched 35-file package checks and downloaded-asset verification. Later candidate commits need their own validation; RC1 evidence does not certify RC2 or complete stable sign-off. |
| Public contract and release | Confirm support/compatibility limits, final changelog/package instructions, reviewed release scope and explicit publication approval. | Policy documented; stable publication pending. |

Never unplug a real reader or corrupt/delete its recovery data to induce a failure. Use synthetic disposable data for rollback/fault/deletion scenarios. A FULL capacity refusal is safety evidence, not FULL migration acceptance. Do not require all Kobo models/plugins to be tested: state the actual supported/tested scope and remaining limits precisely. Retain real backups until their recovery value is no longer needed and separate deletion is authorized.

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

Status: Ready for human test. This section describes the original locale foundation; completed owned-runtime localization is included in 3.3.0-dev.6 and the candidate source. No Kobo is needed for these foundation checks. Keep locales/ beside the script.

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

Status: Ready for human test. The helper is included in the published 3.3.0-dev.6 ZIP and the current candidate source; it was absent from the older 3.3.0-dev.2 ZIP. Run from a clone containing the helper after committing the reviewed changes:

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

Historical slice status: this describes 3.3.0-dev.3 at implementation time. The published 3.3.0-dev.6 ZIP and current candidate include completed owned-runtime extraction; human wording review remains pending. Use the combined acceptance and first-stable gates for current status.

- In a disposable project root, use --list-runs/--cleanup in en, zh-Hant and zh-Hans. Headings/instructions should match the selected locale; run IDs/status tokens and protection reasons retain their technical/English values. Preview creates no deletion.
- Review translated SOURCE/TARGET confirmation wording and [y/N]/[Y/n] defaults. Only y/yes/n/no are accepted; numeric choices and exact DELETE RUN_ID remain unchanged. Use synthetic disposable batches for any cleanup deletion test.
- In controlled migration tests, inspect console versus the saved log: integrated owned messages should be localized on screen and occur once in English in the log. Raw diagnostics, user/device data and unconverted messages are preserved; Unicode filenames can appear in both. Responses typed at prompts must not be recorded.
- Check localized difference.txt against stable difference.json category/path/action data. ui_locale may be present in modern records; older records without it must remain usable.
- Rendering/fallback, ascii-console safety, all-mode equivalence, saved-source/restore, final default-No, rollback after writes and context/exit-state regressions use temporary fixtures. Do not induce failures on real readers or corrupt a real recovery backup for this test.
- Record manual feedback separately. For slice 1, menu/device extraction was still pending. Slice 2 adds menus/basic inspection; detailed metadata/plugin diagnostics/errors and remaining workflow messages still need extraction; do not label this full interface translation or full hardware acceptance.

## KM-014 slice 2: menus and inspection (3.3.0-dev.4)

Historical slice status for 3.3.0-dev.4: extraction was still in progress at this point. The later 3.3.0-dev.6 package and candidate source include completed extraction; human wording/hardware acceptance remains pending. Use only disposable data for induced failures; no real Kobo is required for the synthetic tests.

- Review all three languages for mode/identity/conflict menus. Numeric choices/defaults must match: FULL default; preserve identity when available, new otherwise; unavailable preserve must retry; keep-target remains unsupported for FULL/KOREADER.
- Inspect a synthetic device with known and unknown values. Labels/yes/no/unknown should localize; model/version/path/serial-hint/size/count values must remain intact. English logs must not contain translated owned labels or duplicate entries.
- Confirm there is no AI Assistant configuration indicator in any console locale or the English log, whether that plugin configuration exists or not. Plugin files must still be included in FULL/KOREADER runtime archives and integrity verification; no plugin is executed. Older saved metadata remains readable.
- Review physical-model hints and mismatch warnings. A log hint never proves the hardware model; the following confirmation still defaults to No.
- Capacity reports should show the same values in all languages. Synthetic tests cover backup/target thresholds one byte below, exactly at and one byte above the requirement; replaced-runtime space is still counted. LIBRARY low space must refuse before TARGET backup/writes.
- Detailed errors/metadata/plugin diagnostics and other workflow notices are not fully translated. Existing release assets and older saved runs must remain usable; this slice is not a new public release or full translation/hardware sign-off.

## KM-014 slice 3: workflow and recovery (3.3.0-dev.5)

Historical slice status for 3.3.0-dev.5: extraction was still in progress at this point. The later 3.3.0-dev.6 package and candidate source include completed extraction. Use synthetic/disposable data for failure paths. Successful CI/merge is not human wording or hardware sign-off.

- Review en/zh-Hant/zh-Hans migration, saved-source and exact-target-restore plans, final scope, backup/verification/eject/identity notices and archive heartbeats. Original paths/numbers/category tokens and confirmation defaults must remain intact.
- Compare translated console output with the English log. Selected refusal/cancellation reasons should translate; exception string/JSON values stay English. Raw diagnostic labels should preserve the complete original detail, including Unicode paths, without duplicate tee output.
- Run the synthetic recovery tests: refusal before device access, write failure with successful rollback (exit 2), changed-device rollback refusal and secondary rollback failure (exit 3), and exact-target-restore failure with undo or identity guard. Do not induce these failures on a real reader.
- In temporary fixtures, compare status/exit codes and affected paths across all three locales. SOURCE remains unchanged; changed-device guards allow no further writes; retained snapshots must stay available.
- Pre-run interruption should print one localized message, retain exit 130 and clear the UI context. An interrupt before locale parsing can still use English.
- Low-level errors, detailed scan/comparison output, maintenance reasons/errors and startup/argparse messages are still pending extraction. Record manual wording feedback separately; this slice does not complete full translation or hardware acceptance.

## Combined localization acceptance (3.3.0-dev.6)

Status: KM-014/KM-015/KM-016 Ready for test. Complete the implementation and run automated checks first; combine human language and functional acceptance in one final round. Prior merges/CI and the editorial pass do not sign off these tickets.

- Review all 371 entries in each en/zh-Hant/zh-Hans catalog, with special attention to negation, default-No, backup-before-overwrite, retained files, snapshot restore versus rollback/manual recovery and exact DELETE RUN_ID. Keep y/yes/n/no and numeric choices unchanged.
- Exercise owned errors, per-file progress, cleanup protection reasons, warnings and custom CLI refusals. Compare console and English log, including preserved Unicode paths. Ensure no duplicate output or typed-answer logging.
- Confirm English JSON/exception/warning/reason/lock-label data and actual bool values stay equivalent across languages. A raw warning loaded from older JSON must remain raw without guessing a translation ID.
- Validate final default-No, same/changed-device guards, malformed archives, insufficient space, lock refusal and successful/blocked/failed rollback using disposable fixtures. Do not induce failures on real readers.
- Expect safe English bootstrap diagnostics when catalogs cannot load, original Python-generated argparse/traceback messages, technical tokens and raw external diagnostics. These are deliberate boundaries, not unreviewed translation gaps.
- Finish the existing mode, difference, saved-source, exact-restore, cleanup-preview and package checklists using the final reviewed build. Record human results together and retain recovery backups until sign-off.
