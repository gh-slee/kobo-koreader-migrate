# Contributing

Start with README.md, TRACKER.md and AGENTS.md. Use English for public code, comments, CLI messages and documentation. Communicate with contributors in their requested language.

## Runtime requirements

Every feature must work as ordinary standalone code from Terminal. Do not add inference APIs, downloaded models, local model servers, agent frameworks or dependence on an active AI development session. Development assistance is allowed; runtime decisions must be explicit code and ordinary confirmations.

Preserve FULL, KOREADER, LIBRARY and AUDIT. SOURCE remains read-only, target-only books remain by default, and target writes require backups, identity checks and explicit final confirmation. Never execute device Lua. Use synthetic fixtures; accessing real devices or deleting real backups requires the user's authorization.

## Development workflow

1. Create a feature branch from an up-to-date `main` (for example `feature/progress-report`).
2. Implement the requested scope. Update tracker status, acceptance criteria, version/changelog and documentation together.
3. Run the fixture suite and self-test. Do not mark physical acceptance complete based on synthetic tests.
4. Review the exact staged diff and author email. Use a public alias and a GitHub-provided `@users.noreply.github.com` address. This repository's history guard requires noreply author/committer emails.
5. Run the publication guard. Stage explicit files; avoid indiscriminate `git add .` around device artifacts.
6. Commit locally and present the changes, exact outgoing file/commit scope, privacy-check results, public metadata and limitations to the project owner. Obtain explicit approval before pushing; implementation authorization, OAuth consent and passing tests do not constitute publication approval. If the scope changes, ask again.
7. After approval, push the reviewed feature branch and open a pull request with changes, validation and remaining limitations.
8. Wait for human sign-off before merge. No automatic merge, force push, remote deletion or release publishing is implied by ordinary feature authorization.

```bash
git config --local core.hooksPath .githooks
python3 -m unittest discover -s tests -p 'test_*.py'
python3 kobo-koreader-migrate.py --self-test
git diff --cached
python3 scripts/check_publication.py --history
```

The privacy guard checks the current index and every locally reachable commit, not just the working tree. An ignored file already committed remains in history. Do not push a repository with private history; prepare a clean public history. If a secret was already public, revoke/rotate it and handle history remediation separately.

## PR helper

Git and [GitHub CLI](https://cli.github.com/) are development tools only. Authenticate using `gh auth login` with its browser flow and operating-system credential store. Never paste tokens into issues, source files, logs or an AI chat. Do not use `gh auth status --show-token` or `--insecure-storage`.

After obtaining explicit human approval to push the reviewed changes on a committed feature branch, prepare an English PR body outside the repository or in ignored `.local/`. Include the concrete problem/result, meaningful tests and hardware acceptance status. Then run:

```bash
python3 scripts/publish.py --repository OWNER/REPO \
  --title "Explain the change" --body-file /tmp/pr-body.md
```

Replace `OWNER/REPO` with the exact repository identity shown by `origin`. The helper refuses default/base branches, a dirty working tree, missing CLI/authentication and mismatched/multiple push URLs. It runs tests, self-test and privacy checks, uses an ordinary non-force push, then creates or reports an existing open PR. It never merges. Re-running after a partial success is safe: already-pushed commits are retained and an existing PR is reused.

The pre-push hook also checks publication data, but hooks are local and can be bypassed. Hosted CI runs the fixture checks and privacy guard after push. Repository branch rules must separately enforce review requirements if maintainers enable them. CI is not proof of hardware compatibility or a substitute for human review.

## Reports and tests

Use minimal synthetic examples instead of actual ebooks, device serials, reading history or settings. Do not attach ZIPs, Lua sidecars, databases, logs or unredacted manifests. Report the tool version, macOS/Python version, mode, redacted message, expected behaviour and a safe reproduction.

Add meaningful tests for safety boundaries, failure/rollback handling and observable behavior. Avoid tests that simply repeat implementation details. Run the actual `ditto` fixture test on macOS when changing archive/restore workflows; Linux fixture success is not macOS runtime validation.

All contributions to this tool are under the MIT License. Do not add copied KOReader/device assets or third-party books/fonts/plugins to this repository.
