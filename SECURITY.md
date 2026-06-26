# Security Policy

## Supported Versions

Security fixes target the current `main` branch and the latest released package version.

## Reporting A Vulnerability

Do not open a public issue for suspected credential leaks or exploitable vulnerabilities.

Report security issues privately to the repository owner through GitHub. Include:

- Affected command, plugin, or module.
- Reproduction steps.
- Expected impact.
- Any safe proof-of-concept details.

## Secret Handling

Never commit real `.env` files, API tokens, passwords, certificates, private keys, or service-account files. If a secret may have been committed, revoke it before removing it from repository history.
