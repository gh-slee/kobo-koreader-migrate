# Contributing

Start with README.md for usage and AGENTS.md for shared development guidance. Use TRACKER.md when planning features and ACCEPTANCE.md for manual verification. Public code, comments and canonical developer documentation use English; owned user-facing translations belong in reviewed locale catalogs.

## Runtime requirements

All features must run as standalone offline code. AI-assisted development is welcome, but the released tool must not depend on inference APIs, downloaded models, model servers, agent frameworks or an active assistant session.

Preserve the existing mode semantics and data protections described in AGENTS.md. Use disposable synthetic devices and never execute device Lua. Fixture tests do not authorize physical-device operations or real backup deletion.

## Development workflow

1. Check existing issues and the tracker before a substantial change. Keep PRs focused and describe the problem and intended behavior.
2. Create a feature branch from the intended review base. During initial review, the complete implementation is on feature/public-release in PR #1; main contains bootstrap documentation only.
3. Implement the change and add meaningful regressions for changed behavior or safety boundaries. Update relevant documentation and feature/acceptance status; update version/changelog when runtime behavior changes.
4. Run checks appropriate to the change. For runtime, catalog, test or guard changes, use the commands below. Documentation-only changes need link/example/privacy checks.
5. Inspect the exact staged diff and reachable history. Keep credentials, private instructions and device artifacts out of Git; use explicit file paths when staging.
6. Publish your reviewed branch to the appropriate fork or repository and submit a PR with changes, validation and limitations. Agents acting on someone's behalf must follow that person's publication authorization; these instructions grant no upload or merge permission.
7. Wait for maintainer review and required human acceptance. Do not infer release or hardware readiness from CI alone.

```bash
python3 scripts/check_locales.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 kobo-koreader-migrate.py --self-test
python3 scripts/check_publication.py --worktree --history
git diff --cached
```

Tests use temporary fixtures. On macOS, the actual ditto fixture exercises archive/restore behavior without reading a physical Kobo. Run it when changing those workflows. Linux CI validates fixtures, not Linux device migration.

## Working with coding agents

The root [AGENTS.md](AGENTS.md) is the shared source of agent guidance using the [AGENTS.md open format](https://agents.md/). Keep it concise and link task-specific documentation rather than duplicating it in multiple vendor rule files. Contributors remain responsible for understanding, testing and reviewing AI-assisted changes.

For personal Codex defaults, use its documented user-level AGENTS.md. For private project-specific instructions, Codex supports a Git-ignored AGENTS.override.md. At one directory level, Codex selects the override instead of AGENTS.md; a local override must explicitly read the public AGENTS.md to retain this project's shared rules. This is a Codex feature, not a universal private-file standard. See [official instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

Codex's local managed worktrees automatically copy an ignored AGENTS.override.md. Other ignored files require deliberate .worktreeinclude configuration; ordinary clones, manual Git worktrees and remote environments do not gain this behavior. See [official worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees). This project needs no extra private Markdown loader or worktree include file for its local override. Private instructions and credentials must never be added to a public commit.

Validate setup from a fresh session started in the repository: ask the tool which instructions it loaded and verify that shared rules remain active. Other assistants have their own discovery and subagent inheritance rules. Give delegated agents the applicable guidance and task context; do not assume automatic inheritance. Development guidance never changes the migration tool's offline runtime requirements.

## Publication privacy

Use a GitHub user noreply author/committer email. The history guard also accepts the exact public platform committer noreply@github.com on merge commits; authors still require user noreply IDs. Personal emails, platform authors/non-merge committers and lookalike domains are rejected.

The privacy guard inspects actual staged blobs and every locally reachable commit. .gitignore does not untrack existing files or remove their history. Moving internal notes out of current public docs does not erase older commits. Retain allowlist entries needed to inspect historical public paths even after deleting those paths from the current tree. Handle any history remediation separately; do not bypass the guard.

Install the local pre-push hook:

```bash
git config --local core.hooksPath .githooks
```

The guard uses a public-path allowlist and secret/path heuristics. Human review remains necessary. Hooks can be bypassed, and hosted CI runs after upload. Branch protection and repository permissions are separate controls.

## Maintainer PR helper

GitHub CLI is optional maintainer tooling, unnecessary for migration. Authenticate with its browser/OS credential-store flow. Never print tokens or paste credentials into source, logs, issues or an AI chat.

When authorized to publish a committed, clean feature branch, prepare a reviewed English PR body and run:

```bash
python3 scripts/publish.py --repository OWNER/REPO \
  --title "Explain the change" --body-file /tmp/pr-body.md
```

Use the exact repository identity shown by origin. The helper checks the destination, branch, clean tree, PR content, privacy, locales, tests and self-test. It performs an ordinary push and creates/reuses an open PR. It never merges, force-pushes or publishes releases. Publication helpers do not replace the operator's authorization requirements.

## Reporting and licensing

Report the tool/macOS/Python versions, mode, expected behavior and a minimal synthetic reproduction or redacted message. Do not attach actual books, serials, settings, databases, raw logs, manifests or archives. Follow SECURITY.md for sensitive findings.

Contributions are under the MIT License. Do not add copied KOReader/device assets or third-party books/fonts/plugins.
