# Security Policy

## Scope

This repository is an open-source research-reference MVP. It is not presented
as production-hardened software. Security-sensitive deployments should perform
their own hardening, review, and infrastructure controls before operational
use.

## Supported versions

Security fixes, when made, will be applied to the active `main` branch unless a
maintained release branch is announced separately.

## Reporting a vulnerability

Please do **not** open a public issue for a suspected security vulnerability.

Instead:

1. Email the maintainer or ILMIHA Labs contact listed in project materials.
2. Include:
   - a clear description of the issue
   - affected files or runtime components
   - reproduction steps if safe to share
   - impact assessment
3. Allow reasonable time for triage before public disclosure.

## Response expectations

Target response expectations for this repository:

- acknowledgement within 7 calendar days
- initial triage within 14 calendar days when maintainers are available
- coordinated disclosure timing based on severity and exploitability

These are project goals, not contractual guarantees.

## Security expectations for deployers

Deployers should not assume the repository alone is sufficient for secure
production use. Recommended controls include:

- authenticated access to the backend and dashboard
- secure network placement for MQTT and API services
- environment-specific secret management
- limited retention for previews and evidence
- hardening of any device or server that runs the software
- access logging and administrative review for evidence handling

## Out of scope

The following are out of scope for security support unless explicitly stated
otherwise:

- vulnerabilities in third-party operating systems or camera firmware
- issues caused by unsupported local modifications
- policy-only concerns that do not involve a defect in this repository
