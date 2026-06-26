# GitHub Governance Audit

Date: 2026-06-26

## Context

`/github-project-check` was run against `qsoyq/bark-agent-hook` to verify repository collaboration readiness, security gates, CI, and AI assistant context.

The local repository already had these baseline controls:

- README, `.gitignore`, `.gitattributes`, `CODEOWNERS`, `CONTRIBUTING.md`, and `SECURITY.md`.
- GitHub issue templates and a PR template.
- CI with explicit workflow permissions, job timeouts, required matrix checks, release concurrency, and the `pypi` environment for publishing.
- Dependabot configuration for GitHub Actions and `uv`.
- Sanitized security requirements in `CLAUDE.md` and `AGENTS.md`.

## Platform Changes Applied

The following platform-side changes were applied with `gh` during the audit:

- Enabled `main` branch protection.
- Required status checks: `test (3.10)`, `test (3.11)`, `test (3.12)`, `test (3.13)`, `test (3.14)`, and `lint`.
- Required one approving pull request review.
- Required CODEOWNERS review.
- Enabled stale-review dismissal and last-push approval.
- Required conversation resolution.
- Disabled force pushes and deletions on `main`.
- Enabled Dependabot vulnerability alerts.
- Confirmed automated security fixes are enabled.
- Added a required reviewer for the `pypi` environment.
- Created the `maintenance` label referenced by the Tech Task issue template.

Verification commands:

```shell
gh api --method GET repos/qsoyq/bark-agent-hook/branches/main/protection
gh api --method GET repos/qsoyq/bark-agent-hook/vulnerability-alerts --include --silent
gh api --method GET repos/qsoyq/bark-agent-hook/automated-security-fixes --include --silent
gh api --method GET repos/qsoyq/bark-agent-hook/environments/pypi
```

## Repository Changes Needed

Issue #13 tracks the code-side remediation:

- Expand README governance, release, branch, documentation, and ownership context.
- Add GitHub Copilot instructions.
- Create starter documentation areas for decisions, release notes, postmortems, design notes, and technical notes.
- Record platform-side audit actions in repository documentation.

## Remaining Confirmation Items

These items need periodic owner confirmation because they depend on GitHub platform state or token scopes:

- Secret scanning and push protection status.
- Code scanning status; the audit token did not have the extra `admin:repo_hook` scope requested by the code scanning API.
- Organization or collaborator permissions against the least-privilege expectation.
- Whether GitHub Actions SHA pinning should be enforced at the repository or organization level.
