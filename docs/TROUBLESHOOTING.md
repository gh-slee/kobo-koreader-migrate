# Troubleshooting

[Home](../README.md) · [Usage](USAGE.md) · [Recovery](RECOVERY.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Development](DEVELOPMENT.md) · [Maintaining](MAINTAINING.md)

Use the recorded phase and run status to identify the problem. Preserve backups when recovery is uncertain; do not bypass identity, archive or path checks.

## Common messages

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

## Exit codes

Exit codes: `0` means success, completed audit/preview or ordinary cancellation; consult `run.json` to distinguish them. `1` means an error (a target may need recovery if the run says so). `2` means failed operation with successful rollback, or an argument-parser usage error before a run. `3` means failed/incomplete rollback; recovery is needed. `130` means an uncaught user interruption. Interrupted copying caught inside a transaction may instead return the rollback code.

## Reporting a problem

Use [GitHub Issues](https://github.com/gh-slee/koreader-bridge/issues) for reproducible bugs and feature requests. Include the tool/macOS/Python versions, mode, expected result and a minimal synthetic reproduction or redacted error message. Never upload actual books, device backups, serials, raw settings, databases or unredacted logs/reports.

For sensitive security findings, follow [SECURITY.md](../SECURITY.md) instead of disclosing private data in a public issue. The repository is maintained by its [project contributors](https://github.com/gh-slee/koreader-bridge/graphs/contributors); contribution instructions are in [CONTRIBUTING.md](../CONTRIBUTING.md).
