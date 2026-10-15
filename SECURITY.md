# Security and privacy

This experimental tool handles private device files. Only the current development version receives fixes; older copies should not be assumed to contain current safety checks.

## Reporting

Do not post secrets, ebooks, raw device backups, unredacted logs, reading history, databases or serial numbers in public issues. Prefer a synthetic reproduction with the version, affected operation and a description of the failure. If GitHub's private vulnerability reporting is enabled for this repository, use its Security tab to report sensitive findings privately. Otherwise do not disclose exploit details or private data in public; request a private reporting route from the maintainer.

Credential exposure requires revocation/rotation of affected credentials. Removing a file from Git or adding it to `.gitignore` does not revoke a secret or remove it from existing history.

## Safety boundaries

- SOURCE is not intentionally modified. Lua is never executed and plugins are not invoked.
- Target changes follow backups and confirmations; archive hashes, paths, symlinks and collisions are checked.
- Device fingerprint checks and OS locks protect participating workers. Old workers and other programs may not honour those locks.
- Caught failures attempt rollback. Power loss, disconnection and hardware failure may need manual recovery.
- Backups are not encrypted. Store them privately, including output roots outside the repository.
- Publication checks enforce a source-file allowlist and common secret/path heuristics. They cannot prove that arbitrary text is free of personal data. Review staged content and history before upload.

Do not weaken path validation, fingerprint guards, confirmations or backup requirements to work around an error. Preserve original artifacts while investigating a recovery failure.
