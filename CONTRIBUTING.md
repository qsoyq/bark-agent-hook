# Contributing

This repository uses GitHub Flow.

## Workflow

1. Open or pick an issue before starting work.
2. Create a branch from `main`.
3. Keep changes scoped to the issue.
4. Run local checks before opening a pull request.
5. Open a pull request and fill in the repository template.

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

## Security

Do not commit API keys, tokens, passwords, private keys, `.env`, local virtual environments, build outputs, or cache directories.
