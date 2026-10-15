# Development tracker

Last reconciled: **2026-10-15**. Tool version: **3.3.0-dev.1** (experimental; physical acceptance pending).

Status vocabulary: `Queued`, `In progress`, `Ready for test`, `Blocked`, `Done`, `Deferred`. KM-011, KM-005, KM-001 and KM-003 are implemented and ready for user testing; no human sign-off has been recorded. Entries represent planned work, not permission to operate physical devices or delete backups.

## Mandatory runtime requirement (all tickets)

Every current and future feature must be implemented as ordinary executable code that users can run directly from Terminal without any LLM. Do not depend on AI inference APIs, local/remote model servers, model downloads, an agent framework, or an active Codex/ChatGPT session. LLMs may assist authoring and maintenance only.

Acceptance for every ticket must include standalone CLI operation without AI API keys/services, explicit algorithmic rules, and documented commands/ordinary user confirmations where needed. Preserve the offline core migration/maintenance workflow. Copying existing KOReader AI-plugin files does not authorize executing them.

## Current acceptance work

1. **KM-011**: execution lock and durable run status (foundation for safe cleanup/resume).
2. **KM-005**: pre-migration difference report.
3. **KM-001**: migrate/restore from verified saved archives.
4. **KM-003**: backup management and cleanup preview.

These four tickets are awaiting user testing/sign-off, not additional autonomous implementation. Read ACCEPTANCE.md. KM-013 is implemented and Ready for test for locale selection, localized help and read-only UI samples. KM-014 through KM-017 remain Queued; actual migration/maintenance localization has not started. Other Queued work is not authorized by this release.

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

| KM-013 | P1 | Ready for test | i18n locale foundation | en, zh-Hant, zh-Hans; explicit/env locale resolution, reviewed aliases, JSON catalogs, safe named placeholders/plurals and English fallback; no runtime LLM or network. |
| KM-014 | P1 | Queued | Localized CLI and English diagnostic output | Separate console/log rendering, localize owned help/prompts/progress/errors and human report labels, stable English machine schemas and additive ui_locale metadata; preserve all migration safety. |
| KM-015 | P1 | Queued | Initial three reviewed translations | Complete English, Traditional Chinese and Simplified Chinese catalogs; consistent terminology, exact destructive confirmation tokens and human-reviewed safety prompts. |
| KM-016 | P1 | Queued | Locale validation and multilingual regression | Schema/duplicate-key/coverage/placeholder/control-character checks, exact publication allowlist extensions and CI; equivalent migration/device outcomes in all three locales. |
| KM-017 | P2 | Queued | Translation contribution and expansion guide | Document CLI selection, packaging, aliases, fallback, supported plural rules and acceptance; new languages require reviewed registry/catalog changes and privacy checks. |

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

Current release: **3.3.0-dev.1**, KM-011/KM-005/KM-001/KM-003 implementation complete and **Ready for test**. User explicitly requested to test and sign off. Do not mark these tickets Done without their approval. No physical Kobo was accessed and no real backups were deleted during development.

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
| PUB-004 | In progress | Public origin/minimal main bootstrap exist. GitHub CLI subsequently confirmed OAuth refresh completion; verify effective scope before approved publication rather than requesting another device code automatically. Complete implementation remains local with additional uncommitted changes; no feature PR exists. Explicit change/privacy review and push approval are pending. |
| PUB-005 | Ready for review | Standalone feature-branch publication helper runs privacy/tests, pushes and creates/reuses a PR. Human approval before merge; no force push or automatic merge. |

Public preparation does not complete physical acceptance of KM-011/KM-005/KM-001/KM-003. Local implementation/test evidence and remote bootstrap outcome must be recorded before handoff.

- 2026-10-15: v3.2.0 public preparation — 95 local tests passed on Python 3.12.2/macOS, including the actual ditto fixture. Self-test and candidate publication check passed. Added generic-role/saved-source/restore regressions and Git blob/history/publish-helper tests. No physical Kobo was accessed, no real backups were deleted, and physical acceptance remains pending.

- 2026-10-15: Public remote initialized. Git identity uses the authenticated GitHub alias/noreply address. Only README, MIT license and ignore policy were bootstrapped on main; the complete tool and detailed README are committed on feature/public-release. Index/history privacy checks passed. Hosted CI and PR review are pending.

- Publication history: GitHub refused feature/public-release because its CI workflow needed OAuth workflow scope. A subsequent `gh auth refresh --hostname github.com --scopes workflow` reported Authentication complete. This is not push approval. Verify effective credentials only when needed; retain CI and all checks. No feature PR has been created or merged.

- Publication approval override: the owner now requires a concrete change/privacy review and explicit approval before every remote push, in addition to approval before merge. Do not resume publication after OAuth workflow consent alone. Current feature branch publication is on hold pending that review; no new remote writes are authorized. This supersedes earlier automatic-push instructions.


## Internationalization design and implementation status

Status: KM-013 locale foundation is implemented in 3.3.0-dev.1 and Ready for test. Help descriptions and static UI samples support en/zh-Hant/zh-Hans; actual migration/maintenance output remains English. The rest of this design describes the target full i18n scope, not completed runtime behavior. Remote publication remains subject to separate explicit approval.

### Initial language scope

| Language | Canonical locale | Purpose |
| --- | --- | --- |
| English | en | Default, canonical source catalog and fallback. |
| Traditional Chinese | zh-Hant | Initial Traditional Chinese interface, shared across supported regional aliases. |
| Simplified Chinese | zh-Hans | Separately reviewed Simplified Chinese interface. |

This is a proposed initial product scope, not a claim about market popularity. Use script tags rather than equating a script with a single country. Traditional and Simplified Chinese require independent wording review; do not publish an automatic character-conversion output as an accepted translation.

Code, comments, identifiers and canonical developer documentation stay English. The latest i18n request authorizes translated user-facing terminal text; it supersedes the earlier English-only CLI policy. Tool-owned diagnostic log messages stay English. The conversation language remains the user's preference.

### First-release behavior

Translate owned menus, prompts, help descriptions, progress labels, safety warnings, cancellation/error guidance, run-catalog headings and difference.txt labels. Preserve raw macOS/Python/subprocess diagnostics as received, with a translated explanatory wrapper when useful. Do not claim arbitrary operating-system output is translated.

Keep these stable and untranslated:

- CLI flag names, mode tokens FULL/KOREADER/LIBRARY/AUDIT and numeric menu selections.
- JSON keys/status/phase values, report and archive filenames, run IDs, checksums and device fingerprints.
- Book/font paths, metadata contents and technical identifiers such as device_id.
- Exact destructive confirmation syntax such as DELETE RUN_ID. Translate the instruction, not the required command.
- ISO timestamps and existing byte units/number representations in this first release; full cultural date/number formatting is deferred.

SOURCE and TARGET must remain visibly identifiable in translated text, e.g. a translated role name followed by (SOURCE) or (TARGET). Never translate user/device data or change migration decisions based on language.

### Proposed CLI and locale resolution

Locale selection/help/list commands now work in 3.3.0-dev.1. Migration commands accept the preference but still use English output; localized migration presentation is deferred:

```bash
python3 kobo-koreader-migrate.py --locale en --help
python3 kobo-koreader-migrate.py --locale zh-Hant --mode full --dry-run
python3 kobo-koreader-migrate.py --locale zh-Hans --list-runs
python3 kobo-koreader-migrate.py --list-locales
python3 kobo-koreader-migrate.py --locale zh-Hant --preview-ui
```

Resolution order: explicit --locale; KOBO_MIGRATE_LOCALE environment preference; terminal language environment (LANGUAGE, LC_ALL, LC_MESSAGES, LANG); English fallback. Respect ordered LANGUAGE preferences. Do not execute macOS settings commands or read a Kobo's copied language setting to infer the operator's preference.

Normalize common case/encoding/separator variations. Alias examples:

| Input | Result |
| --- | --- |
| en, en_US.UTF-8, en-CA | en |
| zh-Hant, zh_TW.UTF-8, zh-HK, zh-MO | zh-Hant |
| zh-Hans, zh_CN.UTF-8, zh-SG | zh-Hans |
| zh without an explicit script/region | en with a concise notice; ask users to select an explicit script |
| C, POSIX, unsupported environment locale | en |
| Unsupported explicit --locale | Usage error before creating run folders or accessing devices |

An explicit script takes precedence over a conflicting region. Region aliases share one reviewed script catalog initially; regional vocabulary variants can be introduced later. Set locale once at startup. Do not mutate process-wide locale settings or switch language mid-transfer.

A small bootstrap parse must resolve --locale before building translated help/error descriptions and before run/device setup. --list-locales must work without a Kobo, creating runs, or loading private runtime artifacts. Raw argparse diagnostics may retain their original text; owned guidance and descriptions are translated.

### Architecture and files

Use Python's standard library and UTF-8 JSON catalogs. No runtime translation service, AI API, downloaded model, third-party package or translator compilation tool is required.

Proposed layout:

```text
kobo-koreader-migrate.py       # message rendering/output adapter; stable entry point
locales/
  registry.json              # reviewed tags, native names, aliases and plural-rule IDs
  en.json                    # canonical English messages
  zh-Hant.json
  zh-Hans.json
scripts/check_locales.py      # deterministic schema/coverage/placeholder checks
tests/test_i18n.py
docs/TRANSLATING.md
```

Initially keep the small runtime adapter in the main script rather than coupling i18n to a broad migration-code refactor. Distribute the whole repository with locales/. If the English catalog is absent or invalid, fail with a short built-in English explanation before accessing devices. Update installation docs so a lone copied script is not presented as the complete multilingual distribution.

Use stable English message IDs with named placeholders, for example migration.wait_for_device with {role}, rather than translating concatenated fragments or already-formatted f-strings. Keep comments/context for translators in schema-supported metadata. English catalog text is the canonical message source; avoid maintaining duplicate English dictionaries that drift.

Allow declarative plural variants, initially one/other for English and other-only for Chinese. Select variants through vetted code rule IDs, never eval or executable catalog expressions. Future languages with additional plural rules require a reviewed rule implementation and tests, not an unsupported promise that every language needs only a new file.

Catalog validation must reject duplicate JSON keys, wrong schema/value types, invalid IDs, mismatched placeholders, attribute/index placeholder traversal, unexpected nested formatting and terminal control/ANSI injection. Permit only explicitly supported formatting syntax. Load only registered catalog paths beside the script; locale input must never become an arbitrary file path or execute code.

Missing noncritical translations fall back to the complete English message. An unreadable/invalid selected translation falls back to the English catalog with one warning. Invalid canonical English messages stop startup safely. Supported release catalogs must have complete message coverage, especially all safety prompts; runtime fallback is a recovery feature, not a substitute for completed translations.

### Console and log separation

The current LogTee copies the same bytes to screen and log. Refactor owned messages through an event emitter before translating them; do not translate text after LogTee has duplicated it.

An event carries an English message ID, severity and named parameters. Render the selected locale for the console and English for the log. Preserve original stdout/stderr routing and progress flushing. Keep raw external-tool diagnostics separate and explicitly labelled; they may be in the operating system's language.

Exceptions should preserve an English representation for existing diagnostics while carrying a stable message ID/parameters for localized presentation. MigrationCancelled, migration failures and rollback failures must remain distinguishable. Do not globally monkeypatch print/input or replace arbitrary substrings.

Render all candidate translations before any device mutation. If a selected translation cannot format, use its validated English message; a translation defect must not trigger a partially completed migration. Ensure graceful output on non-UTF-8 streams, without renaming or changing Unicode filenames on devices. Use Unicode-aware layout or avoid width-sensitive table padding for CJK headings.

Add an optional ui_locale field to modern run.json and human-report metadata, while retaining English machine-schema values and accepting older runs without that field. No personal locale preference file or network telemetry is introduced.

### Input and safety behavior

- Continue accepting y/yes/n/no in every language. Add the explicit Chinese equivalents for yes/no through a reviewed input policy; never derive affirmative meaning from arbitrary translated text.
- Empty responses retain existing safe defaults. Unrecognised input reprompts; there is no new automatic-yes option.
- Numeric menus and typed DELETE RUN_ID confirmations stay exact and language-independent.
- Translate warnings about source/target roles, whole-runtime replacement, credentials, device mismatch, identity cloning, cleanup and recovery together with their explanatory context.
- FULL still includes books/reading data/default root fonts, KOREADER remains directory-only, and target-only books are retained by default. Checksums, backups, locks, rollback and standalone offline operation do not change.

### Implementation tickets and order

| Ticket | Phase | Deliverables | Acceptance |
| --- | --- | --- | --- |
| KM-013 | Locale foundation | Registry/catalog schemas, bootstrap selection, aliases, fallbacks, safe formatting and plural selection. | All three locales resolve deterministically; invalid input cannot access arbitrary files; startup errors occur before device activity. |
| KM-014 | Output and error integration | Console/English-log emitter, owned CLI/help/progress/error text, localized difference/catalog labels, additive ui_locale metadata. | No language-dependent migration decisions; English diagnostics and machine-schema values remain stable; no hardcoded owned UI text omitted from inventory. |
| KM-015 | Three reviewed catalogs | Complete en, zh-Hant and zh-Hans text; shared terminology and safety review. | 100% required message/placeholder coverage; each destructive prompt reviewed in context; no inferred approval from translated wording. |
| KM-016 | Validation and regression | check_locales.py, publication allowlist updates for exact locale/doc/tool paths, CI and parameterized language tests. | Catalog errors fail CI; unknown JSON/device files remain blocked; all existing migration tests plus multilingual safety regressions pass. |
| KM-017 | Documentation and language expansion | English contributor/translation guide, examples, language-status table and manual acceptance instructions. | A contributor can add a supported-rule language using catalog/registry changes and checks; release readiness and pending human review are explicit. |

Implementation order: KM-013 -> KM-014 -> KM-015 -> KM-016 -> KM-017, with focused tests alongside each phase. Test English migration behavior immediately after output routing changes, before integrating all translations. KM-013 is Ready for test. The initial validator, exact publication allowlist and foundation regression checks are implemented as dependencies; the remaining KM-016 migration-translation matrix and KM-014/KM-015/KM-017 work remain Queued.

### Verification matrix

1. Selection: flags/env precedence, ordered preferences, aliases, conflicting script/region, ambiguous zh, C/POSIX, unsupported locales and traversal attempts.
2. Catalog safety: missing/corrupt catalog, duplicate keys, missing/extra entries, placeholder mismatch, invalid formatting, plural forms and control characters.
3. Presentation: owned help/menu/error/progress/cleanup/catalog/difference text in all three languages; English tool-owned log messages; raw external text preserved and marked.
4. Semantics: compare equivalent synthetic workflows in all languages across FULL/KOREADER/LIBRARY/AUDIT, saved-source reuse and target restore. Device trees must match after excluding documented timestamps/random run IDs.
5. Safety: default-No and invalid answers never authorize writes; same-device rejection, compatibility refusal, checksum failure, rollback, cleanup typed confirmation and cancellation remain intact in every language.
6. Compatibility: old source/target snapshots and statuses remain usable; new ui_locale is optional. Test the existing minimum supported Python version via CI.
7. Output/privacy: Unicode filenames, CJK layouts, redirected output, non-UTF-8 streams, secret/path scanning of locale files, explicit publication allowlist and no copied run/device data.
8. Standalone: run tests/self-test without AI credentials/services or network access. No real Kobo is required for automated tests. Physical acceptance/sign-off remains separate.

Do not translate tests through an LLM at runtime. Development translation assistance does not replace human wording review, especially for destructive prompts.

### Adding languages later

Add a registered tag/native name, a UTF-8 catalog, reviewed aliases and supported plural-rule ID; run checks, preview every menu and submit a PR for review. Maintain translation completeness/status explicitly. Incomplete new languages stay experimental and must not be advertised as fully supported.

Do not auto-enable every JSON file found in locales/. Additional languages, right-to-left layout, regional vocabulary/date/number formatting, broad README translations and localization of developer publishing tools are separate scope decisions. Update the allowlist intentionally for each new public language file rather than allowing arbitrary JSON uploads.

### Design references

- Python gettext documents catalog/fallback/plural concepts and LANGUAGE/LC_ALL/LC_MESSAGES/LANG environment discovery: https://docs.python.org/3.12/library/gettext.html
- W3C language tags explain language/script/region distinctions and BCP 47 conventions: https://www.w3.org/International/articles/language-tags/
- Python format-string syntax informs the deliberately restricted named-placeholder validator: https://docs.python.org/3.12/library/string.html#format-string-syntax

These references inform the design; this plan chooses source-reviewable JSON catalogs rather than requiring compiled gettext .mo files.

Publication scope note: the i18n plan and updated guidance change the previously reviewed candidate content. Any later push requires a fresh concrete file/commit scope and privacy review followed by explicit owner approval. No i18n runtime code or remote publication is authorized by this planning record alone.


## KM-013 implementation evidence and handoff

- Version 3.3.0-dev.1. Complete foundation catalogs: 3 locales, 36 message IDs each. English source, independent Chinese wording, one/other vs other-only plural rules.
- --locale, --list-locales and --preview-ui are available. Help descriptions and static samples translate; migration/maintenance output, raw argparse diagnostics and machine schemas stay English. Console/log event separation and ui_locale run metadata remain KM-014 work.
- Missing selected translations use English; corrupt selected catalogs warn/fall back. Invalid English/registry assets stop startup before run/device activity. The complete locales/ directory is now required beside the script.
- Added scripts/check_locales.py, exact four-file locale publication allowlist, CI and publish-helper validation. This does not authorize any remote push or PR creation.
- Local evidence on Python 3.12.2/macOS: 114 tests passed (95 existing + 19 locale tests), including actual ditto fixtures and equivalent synthetic FULL outcomes for en/zh-Hant/zh-Hans. Self-test, catalog validation and candidate privacy checks passed. No physical Kobo was accessed and no real backups were deleted.
- Human translation/usability acceptance is pending. See ACCEPTANCE.md; keep KM-013 Ready for test until explicit sign-off. Proceed to KM-014 only within authorized feature scope and preserve the current safety behavior.
- Prior publication-review hashes/file counts are obsolete after these changes. Before any push, regenerate the exact outgoing scope/privacy report and obtain explicit approval. Do not infer push consent from implementation approval or GitHub OAuth consent.


## Publication documentation review and acceptance timing

- The owner will perform manual testing after an approved feature-branch push. This does not waive pre-push automated tests, locale validation, privacy review or the need for explicit push approval. Keep manual acceptance tickets Ready for test and require sign-off before merge.
- README was reviewed against common public CLI/GitHub documentation practices, not an industry certification. It covers purpose, prerequisites/platform scope, safe quick start, initial-review branch installation, commands/modes, data behavior, recovery, partial i18n, support, validation limits, contribution and license.
- README now distinguishes local test evidence (114 tests on Python 3.12.2/macOS) from configured but not yet confirmed hosted CI and pending physical acceptance. No fabricated CI badge or production-readiness claim was added.
- The initial review branch installation command is explicitly conditional on branch publication, because main currently holds bootstrap docs. Later default-branch installation follows implementation merge.
- No runtime code changed for this documentation pass. No remote writes were performed. Outgoing scope/privacy review must be regenerated after these changes and explicitly approved before any push.
