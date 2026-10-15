# Kobo KOReader Migration

Move KOReader, ebooks, reading data and custom fonts between two Kobo readers using a Mac. Books keep their original paths relative to the device root, so `Books/Comics/issue.cbz` on SOURCE becomes `Books/Comics/issue.cbz` on TARGET.

**Current version: 3.2.0 — experimental, awaiting physical-device testing and human sign-off.** Automated tests use temporary device fixtures. Passing those tests is not evidence that a particular Kobo pair has been validated on hardware.

The migration tool uses Python's standard library and macOS utilities. It works offline, has no telemetry, and requires no LLM, AI API key, model download or running agent. Existing plugin configurations are copied as files; plugins are not executed by the tool.

## Contents

- [Requirements and compatibility](#requirements-and-compatibility)
- [Installation and first checks](#installation-and-first-checks)
- [Choose a mode](#choose-a-mode)
- [Step-by-step migration](#step-by-step-migration)
- [Books, metadata and fonts](#books-metadata-and-fonts)
- [Conflicts and target identity](#conflicts-and-target-identity)
- [Saved source migration and target restoration](#saved-source-migration-and-target-restoration)
- [Progress, reports and project layout](#progress-reports-and-project-layout)
- [Backup cleanup](#backup-cleanup)
- [Command-line reference](#command-line-reference)
- [Troubleshooting and recovery](#troubleshooting-and-recovery)
- [Privacy and publication](#privacy-and-publication)
- [Development and contributing](#development-and-contributing)
- [Limitations and roadmap](#limitations-and-roadmap)
- [License](#license)

## Requirements and compatibility

| Requirement | Details |
| --- | --- |
| Computer | macOS with `ditto`, `diskutil` and `sync` available. |
| Python | Python 3.9 or newer. No `pip install` is needed for migration. Local validation is recorded in [TRACKER.md](TRACKER.md); CI covers additional Python versions. |
| Devices | Two Kobo readers mounted as USB storage, connected **one at a time**. A renamed volume is detected by its `.kobo/` directory. |
| Identity | Both readers must have a readable `.kobo/version` file. The fingerprint prevents using the same device as both SOURCE and TARGET and guards subsequent writes. |
| KOReader | FULL and KOREADER require an existing SOURCE installation with `reader.lua`, `frontend/` and `plugins/`. LIBRARY does not install KOReader. |
| Space | Enough Mac space for source and target backups; enough target space for the planned replacement/copies. ZIP compression savings are not assumed. |

SOURCE and TARGET are roles, not fixed model names. Each physical model must be confirmed by the operator. A model name found in KOReader logs is only a hint: a previous clone may have copied another device's log. Two different readers of the same model are allowed; identical fingerprints are refused.

FULL and KOREADER copy the SOURCE runtime version and settings. The operator must confirm that this KOReader build is compatible with the TARGET hardware. The tool does not install a fresh model-specific build or automatically preserve hardware-specific settings. Support for entering a model label is not a claim that every Kobo model has been tested.

Windows and Linux device migration are not supported. Linux CI runs fixture tests only. This tool does not migrate Kindle, Android, Nickel accounts, Kobo firmware, DRM licences or Kobo's internal database.

## Installation and first checks

Clone this repository into any directory you choose:

```bash
git clone https://github.com/gh-slee/kobo-koreader-migrate.git
cd kobo-koreader-migrate
python3 --version
python3 kobo-koreader-migrate.py --version
python3 kobo-koreader-migrate.py --self-test
python3 kobo-koreader-migrate.py --help
```

Alternatively, download the repository ZIP and extract it into a permanent project folder. Keep the script's filename as `kobo-koreader-migrate.py`; versions appear in startup output, logs and JSON records.

Start with a preview:

```bash
python3 kobo-koreader-migrate.py --mode full --dry-run
```

A dry run inspects SOURCE, ejects it, asks for TARGET and saves the plan. It changes no Kobo files and creates no ZIP backups. It still creates local logs/reports and uses execution locks. To perform that migration after reviewing the plan, run the command again without `--dry-run`; the plan is recalculated.

Do not run as `sudo`. Quit KOReader normally on both devices before USB connection so reading state and databases are saved.

## Choose a mode

Running without `--mode` opens an interactive menu; FULL is its default.

| Mode | Entire `.adds/koreader` | Books and external reading data | Root `fonts/` | Writes to Kobo |
| --- | --- | --- | --- | --- |
| FULL | Clean replacement from SOURCE | Included, original relative paths | Included by default; `--no-fonts` disables it | After backups and final confirmation |
| KOREADER | Clean replacement from SOURCE | No copying outside KOReader | No copying outside KOReader | After backups and final confirmation |
| LIBRARY | Retains installed runtime/global settings | Selected using flags or prompts | Optional | After backups and final confirmation |
| AUDIT | Plans full runtime replacement | Selected using flags or prompts | Optional | Never |

```bash
# Everything supported, including books and reading state.
python3 kobo-koreader-migrate.py --mode full

# Entire KOReader directory only.
python3 kobo-koreader-migrate.py --mode koreader

# Books + reading data, retaining TARGET's installed KOReader.
python3 kobo-koreader-migrate.py --mode library --books --no-fonts

# Only custom root fonts.
python3 kobo-koreader-migrate.py --mode library --no-books --fonts

# Detailed read-only inspection and planning.
python3 kobo-koreader-migrate.py --mode audit --books --fonts
```

FULL always includes supported books and reading data. `--no-books`, `--no-reading-data`, directory scopes and `keep-target` conflicts are rejected in FULL. Use KOREADER or LIBRARY for selective work.

**FULL retains TARGET-only books outside KOReader.** It replaces SOURCE-matching files that differ, and skips identical payload files. It replaces the entire `.adds/koreader` tree, so TARGET-only files/settings/central reading metadata **inside that tree** are removed after backup. KOREADER has the same whole-directory behavior, including any books or fonts already stored inside that tree.

## Step-by-step migration

1. Disconnect both readers. Launch the tool and select the mode.
2. Connect only **SOURCE**, choose USB connection on the Kobo and press Return when requested.
3. Inspect the displayed mount, model hint, KOReader version and masked serial hint. Enter/confirm the physical SOURCE model using the device's settings or your own verified information.
4. The tool checks paths, plugins and SQLite statistics, scans supported files, checks free space, then captures source archives with SHA-256 manifests. SOURCE files are not changed by the tool.
5. Wait for `Ejected successfully.` and `Unplug SOURCE now.` Disconnect SOURCE.
6. Connect only **TARGET**, choose USB connection and press Return when requested. Confirm the physical TARGET model. For whole-runtime copying, confirm build compatibility.
7. Review the payload plan and `difference.txt`. Select the TARGET KOReader identity policy when applicable. The tool verifies source archives and creates TARGET rollback backups.
8. At the **final** `Proceed with the planned migration? [y/N]:` prompt, type `y` and Return to allow writes. Empty input means No. Declining is a normal cancellation; TARGET is not modified.
9. Keep TARGET connected during copying and verification. On success, wait for safe eject and then disconnect it.
10. Open KOReader on TARGET and check several books, reading progress, annotations, fonts and plugins. Keep backups until your physical-device acceptance checks are complete.

Model flags provide labels in advance but do not bypass confirmations:

```bash
python3 kobo-koreader-migrate.py --mode full \
  --source-model "Kobo Clara BW" --target-model "Kobo Libra Colour" --dry-run
```

Those names are examples, not a tested hardware pair. An incorrect or stale log hint can be overridden through physical-model confirmation. Identity guards still apply.

## Books, metadata and fonts

### Book discovery

Discovery is based on case-insensitive filename extensions, not a complete content/DRM inventory. The built-in set is:

```text
epub kepub pdf cbz cbr cb7 cbt cba
mobi azw azw3 azw4 prc pdb fb2 fb3
djvu djv txt rtf doc docx html htm xhtml md
chm odt tif tiff xps oxps
```

Compound `.fb2.zip` is also recognised. `.kepub.epub` is found through its `.epub` suffix. Copying a format does not prove that KOReader on TARGET can open it. Unsupported extensions are not silently treated as books; the scan report includes unrecognised files.

Hidden/system folders are excluded from ordinary book scanning. Symlinks are skipped or rejected by the relevant safety checks. Generic ZIP archives, standalone image collections and extensionless books are not included automatically.

Use explicit extensions for other formats, and review the dry run:

```bash
python3 kobo-koreader-migrate.py --mode library --books --no-fonts \
  --extra-extension png --extra-extension zip --dry-run
```

Adding `zip` includes ordinary ZIP files within the chosen scan scope; it does not inspect them to determine whether they contain ebooks.

### Reading data

When books and reading data are enabled, adjacent sidecar directories follow their books. Examples:

```text
Books/title.epub             -> Books/title.sdr/
Books/title.kepub.epub       -> Books/title.kepub.sdr/
Comics/issue.cbz             -> Comics/issue.sdr/
```

Supported central metadata locations under `.adds/koreader` are `docsettings/`, `hashdocsettings/` and legacy `history/`. FULL/KOREADER include these through the runtime archive. Unscoped LIBRARY can copy these metadata trees without replacing the entire runtime. Lua files are copied/read as text; they are never evaluated.

Metadata is copied, **not merged**. For scoped LIBRARY scans, unfiltered central metadata is omitted to avoid overwriting unrelated reading state. Keeping a conflicting TARGET book also protects its related source sidecars and conservatively omits central metadata from that LIBRARY transfer. A different edition at the same pathname can still have incompatible reading state; review the file plan.

### Fonts

Custom root fonts live at `fonts/` relative to the Kobo root, for example `fonts/MyFont.ttf`. Root font copying recognises `.ttf`, `.otf`, `.ttc` and `.otc`. Fonts inside `.adds/koreader/fonts/` are part of the whole KOReader tree and are copied in FULL/KOREADER regardless of the external-root font option.

### Directory scopes

Use SOURCE-relative directories, without a leading slash:

```bash
python3 kobo-koreader-migrate.py --mode library --books --no-fonts \
  --include-dir Books --include-dir Comics --exclude-dir Books/Temporary --dry-run
```

Repeat flags as needed. Target-only reporting uses the same scope and extension rules. Scopes are supported in LIBRARY/AUDIT, not FULL. Saved snapshots retain their original discovery scope.

## Conflicts and target identity

Payload files are compared by size and SHA-256. Identical files are skipped. Different files at the same relative path are governed by:

| Policy | Result |
| --- | --- |
| `overwrite` | Back up existing TARGET content, then replace it with SOURCE content. Used by FULL/KOREADER; optional in LIBRARY/AUDIT. |
| `keep-target` | Keep different existing TARGET files; still copy missing files. Protect associated reading metadata. LIBRARY/AUDIT only. |

```bash
python3 kobo-koreader-migrate.py --mode library --books --no-fonts \
  --conflict keep-target --dry-run
```

For whole-runtime migration, choose one KOReader `device_id` policy:

1. Preserve TARGET's existing identity (recommended; if absent, generate a new one).
2. Generate a new TARGET identity.
3. Clone SOURCE identity exactly.

This setting concerns KOReader's ID, not the Kobo hardware serial. The copied tree is verified before deliberate identity/cache adjustments. Other hardware-specific settings are copied from SOURCE; a selective preservation feature is still on the roadmap.

## Saved source migration and target restoration

List existing runs first:

```bash
python3 kobo-koreader-migrate.py --list-runs
```

### Reuse a saved SOURCE

```bash
python3 kobo-koreader-migrate.py --from-run RUN_ID --dry-run
python3 kobo-koreader-migrate.py --from-run RUN_ID
```

Replace `RUN_ID` with an ID listed under this project's `runs/`. Only TARGET is connected. The tool verifies archive SHA-256, manifests, member paths and contents. It references the original SOURCE archives and records dependencies instead of duplicating large ZIPs.

| Captured snapshot | Permitted migration mode |
| --- | --- |
| FULL | FULL or KOREADER |
| KOREADER | KOREADER |
| LIBRARY | LIBRARY |

Default mode follows the captured mode. You cannot silently use a FULL snapshot as LIBRARY: its central metadata is inside the runtime archive. Legacy source batches need a complete scan report and valid archive/manifest pairs with an identifiable source model. Legacy run status remains unknown/protected.

Saved run selection is limited to this project's run directories; an absolute path is accepted only when it resolves to a direct run child in that same project. Use `--backup-dir` to select another project root.

### Restore the original TARGET state

```bash
python3 kobo-koreader-migrate.py --restore-run RUN_ID --dry-run
python3 kobo-koreader-migrate.py --restore-run RUN_ID
```

This uses a previous run's **TARGET pre-migration snapshot**, not its SOURCE snapshot. It restores the recorded originals and removes files that the recorded migration created. Unrelated library files are retained. If the run replaced KOReader, restoration replaces the full KOReader tree with its prior backup.

Exact restoration requires v3.1+ `target-snapshot.json`, `target-changes.json`, a run that modified its target, verified archive pairs and the same device fingerprint. Older target backups without a complete journal are not accepted by this command. The tool creates pre-restore undo backups and asks for final confirmation. Subsequent changes to the affected paths/runtime can be overwritten by restoring an older state; inspect the dry run first.

Restore cannot be combined with migration scope/model/conflict flags. Only the recorded state, `--dry-run` and `--backup-dir` control it. This is not an automatic interrupted-run resume feature.

## Progress, reports and project layout

By default all generated files stay in the project folder containing the script:

```text
kobo-koreader-migrate.py
README.md / LICENSE / CHANGELOG.md
TRACKER.md / ACCEPTANCE.md / AGENTS.md
CONTRIBUTING.md / SECURITY.md
tests/
scripts/                 publication checks and PR helper
.github/workflows/       fixture test CI
.githooks/               optional local pre-push guard
runs/                    private; ignored by Git
  <timestamp-random-id>/
    run.json
    koreader-migration-<run-id>.log
    koreader-scan-<run-id>.json
    difference.txt / difference.json
    source-snapshot.json or source-reference.json
    target-snapshot.json / target-changes.json
    *.zip / *.manifest.json
    koreader-migration-result-<run-id>.json
.project.lock             persistent lock inode; ignored by Git
.local/                   optional private notes; ignored by Git
```

Not every operation creates every artifact. A dry run creates reports but no ZIPs. Files within one batch are intentionally flat for compatibility with earlier runs. The version is recorded in logs/JSON, not in the script filename.

Choose a different output root on the Mac:

```bash
python3 kobo-koreader-migrate.py --backup-dir ~/KoboMigration --mode full --dry-run
python3 kobo-koreader-migrate.py --backup-dir ~/KoboMigration --list-runs
```

The resulting batches are `~/KoboMigration/runs/<run-id>/`. Backups under `/Volumes` or inside a Kobo mount are refused. Management commands must use the same output root to find those runs.

Progress output includes phase timestamps, file counts, bytes, large-file transfer/hash speed and estimated time, and periodic heartbeat messages for long macOS archive commands. Database diagnostics and target comparison announce their phases. Some calls, such as a SQLite check or an individual filesystem operation, can still take time without per-record progress.

`difference.txt` and `difference.json` enumerate new, overwritten, identical, kept, skipped-metadata and target-only files, with counts/bytes and book/sidecar grouping. Target-only entries are informative; default migration does not delete those books.

`run.json` tracks phases and final states:

| Status | Meaning |
| --- | --- |
| `running` | Worker has not recorded a final result. |
| `success` | Operation and verification completed. |
| `audited` | Inspection/preview completed without device writes. |
| `cancelled` | Ordinary user cancellation before target changes. |
| `failed` | Failure recorded before target modification. |
| `interrupted` | Interrupted without recorded target modification. |
| `rolled-back` | Operation failed; automatic rollback succeeded. |
| `needs-recovery` | Target may have changed and needs inspection/recovery. |
| legacy/unknown | No trustworthy modern status; conservatively protected. |

Project and device locks use OS-backed ownership. A leftover lock **filename** does not mean another worker is running: locks release when the process exits. Do not delete a live lock file to bypass ownership. Prior unfinished `running` records are reconciled conservatively at the next exclusive project startup. Older v3.0.x workers do not honour these locks; stop them before running newer versions.

## Backup cleanup

These commands do not require a connected Kobo:

```bash
# Inventory only.
python3 kobo-koreader-migrate.py --list-runs

# Preview only. This does not delete anything.
python3 kobo-koreader-migrate.py --cleanup

# Preview with a larger recent-success retention count.
python3 kobo-koreader-migrate.py --cleanup --keep-successful 5
```

The default retention count is two; the minimum is one. Cleanup protects recent successful batches, referenced dependencies, the newest known successful recovery point per target, and all non-success/legacy/unknown batches. It deletes only whole eligible batches explicitly selected by ID:

```bash
python3 kobo-koreader-migrate.py --cleanup --delete-run RUN_ID
```

You must type the exact `DELETE ...` text shown by the tool. Multiple `--delete-run` flags select multiple eligible batches. The tool locks and rechecks eligibility and rejects symlink-containing batches. Adding `--dry-run` suppresses deletion even when IDs are supplied. There is no scheduled deletion, individual-ZIP pruning or automatic removal of failed runs. Keep recovery batches until physical testing is complete.

## Command-line reference

Use `--help` for the definitive help text.

| Option | Purpose |
| --- | --- |
| `--mode full\|koreader\|library\|audit` | Select a mode; otherwise show the menu. |
| `--dry-run` | Preview with no Kobo writes or ZIP creation. |
| `--source-model NAME`, `--target-model NAME` | Provide physical model labels; confirmations remain required. |
| `--books`, `--no-books` | Include/exclude books in selective modes; FULL always includes them. |
| `--fonts`, `--no-fonts` | Include/exclude root fonts; FULL default is include. |
| `--reading-data`, `--no-reading-data` | Copy or omit reading metadata with books in LIBRARY/AUDIT. |
| `--conflict overwrite\|keep-target` | Policy for different existing payload files. |
| `--include-dir DIR` | Scan a SOURCE-relative directory; repeatable. |
| `--exclude-dir DIR` | Exclude a SOURCE-relative payload directory; repeatable. |
| `--extra-extension EXT` | Add a case-insensitive book extension; repeatable. |
| `--backup-dir PATH` | Project/output root; default is script directory. |
| `--from-run RUN_ID` | Reuse a verified saved SOURCE; connect TARGET only. |
| `--restore-run RUN_ID` | Restore the recorded original TARGET state. |
| `--list-runs` | Show saved batches/status without devices. |
| `--cleanup` | Preview eligible old batches; no deletion by itself. |
| `--keep-successful N` | Keep N newest successes during cleanup, minimum 1. |
| `--delete-run RUN_ID` | Explicit eligible deletion selection with `--cleanup`; repeatable. |
| `--self-test` | Small offline non-destructive self-test, then exit. |
| `--version`, `--help` | Show version/help, then exit. |

`--from-run`, `--restore-run`, `--list-runs` and `--cleanup` are mutually exclusive operations. The main migration workflow is interactive; there is no unattended `--yes` switch.

## Troubleshooting and recovery

| Message or symptom | Action |
| --- | --- |
| Waiting for SOURCE/TARGET | Choose USB Connect on the Kobo. Check the data cable and that macOS mounted a volume containing `.kobo/`. Connect only the requested device. Ctrl-C cancels waiting. |
| More than one Kobo mounted | Disconnect the other Kobo and restart. The tool refuses ambiguous device selection. |
| Model hint differs from the physical model | Logs may have been copied. Enter the physical label and verify the role. Do not treat the log hint as proof. |
| No device fingerprint | Check that the device's `.kobo/version` is present/readable. The tool refuses writes without an identity guard. |
| Statistics pending WAL data | Disconnect safely, open/quit KOReader cleanly, reconnect and retry. Do not delete database WAL files to silence the warning. |
| Long archive/hash/comparison | Read the latest phase/heartbeat. Large CBZ/EPUB files and slow USB storage can take time. Avoid unplugging during active writes. |
| Insufficient Mac/target space | Choose another local backup root or free space intentionally, then rerun the preview. |
| Cancelled before target modification | A No/empty response declined a confirmation. Existing backups remain; this is a normal cancellation, not a failed copy. |
| Archive/manifest verification failed | Keep originals, do not edit manifests to bypass checks. Recapture SOURCE or select a known valid batch. |
| Device changed/disconnected | Stop. Reconnect the original device and inspect the run/backups. The tool refuses rollback onto a different device. |
| `needs-recovery` | Keep all artifacts. Reconnect the original TARGET; inspect reports and try a verified `--restore-run ... --dry-run` if a complete modern snapshot exists. Otherwise recover manually from backups. |

Caught copy/restore/verification failures attempt automatic rollback while the original TARGET remains connected. Rollback cannot guarantee recovery after power loss, forced termination, hardware failure or disconnection. A checksum verifies the captured bytes, not the meaning or compatibility of settings.

Exit codes: `0` means success, completed audit/preview or ordinary cancellation; consult `run.json` to distinguish them. `1` means an error (a target may need recovery if the run says so). `2` means failed operation with successful rollback, or an argument-parser usage error before a run. `3` means failed/incomplete rollback; recovery is needed. `130` means an uncaught user interruption. Interrupted copying caught inside a transaction may instead return the rollback code.

## Privacy and publication

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

The guard allows only reviewed source/docs/test paths and detects common secrets/personal absolute paths without printing matching values. It is a heuristic defence, not a guarantee that all personal data can be detected. Review staged diffs and commit author identity. The history guard requires GitHub noreply author/committer emails and also scans commit messages. New public file paths require an intentional allowlist update. CI checks after upload; the local hook is the guard before upload. Hooks can be bypassed, so maintainers must also follow [CONTRIBUTING.md](CONTRIBUTING.md).

## Development and contributing

Run tests without a Kobo:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 kobo-koreader-migrate.py --self-test
python3 scripts/check_publication.py --worktree
```

Tests use temporary synthetic devices and mock USB/eject operations. On macOS, an additional test uses real `ditto` to exercise FULL migration, saved-source reuse and exact TARGET restoration on temporary directories. It never reads a physical Kobo. On other supported test hosts, that fixture test is skipped.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the feature-branch/PR workflow and publish helper. The helper runs tests/privacy checks, pushes a committed feature branch and creates or reuses a PR; it never merges. GitHub CLI is needed only for repository publishing, not for migration. Human approval is required before merge. [AGENTS.md](AGENTS.md) carries the same requirements for future development sessions.

[TRACKER.md](TRACKER.md) records implemented work, queued features and evidence. [ACCEPTANCE.md](ACCEPTANCE.md) contains the manual test/sign-off checklist. [CHANGELOG.md](CHANGELOG.md) describes versions. A queued ticket is not permission to access a real reader or delete backups.

## Limitations and roadmap

- Extension-based scans cannot guarantee discovery of every ebook, DRM file, image folder or extensionless document.
- Reading data is copied, not semantically merged; different editions and metadata locations can cause conflicts.
- FULL/KOREADER replace the runtime and source settings. Selective target hardware-setting preservation is not implemented.
- `.kobo/version` is fingerprinted as a whole; a firmware change can change that fingerprint and block an older exact restore. There is no unsafe bypass option.
- There is no interrupted-transfer resume, default library mirror deletion, wireless sync, scheduled cleanup or unattended migration.
- Live-device safety and usability still need physical testing and human sign-off. Current feature status is recorded rather than assumed.

Planned work includes interrupted-transfer recovery, optional exact library mirroring, content-assisted discovery, reading-data conflict reports, portable hardware settings, settings-only migration and a separate archive verifier. These remain backlog items until implemented/tested.

## License

This migration tool is released under the [MIT License](LICENSE). KOReader, Kobo software, plugins, fonts and ebooks copied from your devices retain their respective licences; this repository does not distribute those assets. This is an independent community tool, not an official Kobo or KOReader project.
