# Contributing

This repository uses GitHub Flow.

## Workflow

1. Open or pick an issue before starting work.
2. Create a branch from `main`.
3. Keep changes scoped to the issue.
4. Run local checks before opening a pull request.
5. Open a pull request and fill in the repository template.

Use branch names that include the issue number and a short slug, for example:

```text
chore/13-governance-audit-remediation
fix/24-redact-audit-click-url
```

## Local Checks

```shell
uv sync --group dev
uv run pytest -q
uv run pre-commit run --all-files
uv build
```

## Commit Messages

Use Conventional Commits:

```text
type(scope): short summary (#issue)
```

Examples:

```text
fix(audit): avoid persisting click URLs (#24)
docs: document PyPI release gate (#13)
```

## Pull Requests

Pull requests should:

- Link the issue with `Closes #<issue>`.
- Summarize user-visible and operational impact.
- Include validation commands and any manual checks.
- Explain risk and rollback for release, security, or hook behavior changes.
- State whether AI assistance was used.

Do not include generated command documentation. The CLI help output is the command reference.

## Security

Do not commit API keys, tokens, passwords, private keys, `.env`, local virtual environments, build outputs, or cache directories.
