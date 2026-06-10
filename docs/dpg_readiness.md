# DPG Readiness Mapping

This document maps the Road User Intelligence Platform repository to the
current Digital Public Goods Standard indicators for submission preparation and
internal self-audit.

Reference standard: <https://www.digitalpublicgoods.net/standard>

Last self-audit update: 2026-06-09.

The project is framed as a **research-reference open-source MVP** with primary
public-interest relevance to **SDG 11 road safety**. This document describes
the repository evidence that supports a DPG submission. It does not claim that
any particular deployment is already certified or legally approved.

The Digital Public Goods Alliance reviews the design of the core solution, not
every local implementation. This mapping therefore describes repository-level
evidence and separates deployment-specific legal or owner approvals as open
items.

## Indicator 1: SDG Relevance

- Primary framing: SDG 11, safer and more inclusive urban mobility
- Repository evidence:
  - [README.md](../README.md)
  - [docs/safety_and_risk.md](safety_and_risk.md)
  - [docs/use_case_catalog.md](use_case_catalog.md)

## Indicator 2: Open Licensing

- License: MIT
- Repository evidence:
  - [LICENSE](../LICENSE)
  - [NOTICE](../NOTICE)
  - [pyproject.toml](../pyproject.toml)

## Indicator 3: Clear Ownership

- Maintainer and stewardship information is documented for open-source
  governance and contribution review.
- Repository evidence:
  - [GOVERNANCE.md](../GOVERNANCE.md)
  - [CONTRIBUTING.md](../CONTRIBUTING.md)
  - [CITATION.cff](../CITATION.cff)
  - [NOTICE](../NOTICE)

## Indicator 4: Platform Independence

- The software supports file, webcam, RTSP, and optional `reCamera` inputs.
- `reCamera` is documented as optional rather than mandatory.
- Repository evidence:
  - [README.md](../README.md)
  - [docs/deployment_guide.md](deployment_guide.md)
  - [docs/installation_and_deployment.md](installation_and_deployment.md)
  - [docs/live_validation_guide.md](live_validation_guide.md)

## Indicator 5: Documentation

- Quickstart, demo, deployment, architecture, and governance documentation are
  published with the repository.
- Repository evidence:
  - [README.md](../README.md)
  - [docs/demo_guide.md](demo_guide.md)
  - [docs/deployment_guide.md](deployment_guide.md)
  - [docs/installation_and_deployment.md](installation_and_deployment.md)
  - [docs/functional_requirements.md](functional_requirements.md)
  - [docs/use_case_catalog.md](use_case_catalog.md)
  - [docs/system_architecture.md](system_architecture.md)

## Indicator 6: Non-PII Data Extraction

- The repository provides non-PII-oriented operational exports in common,
  non-proprietary formats, including JSON and CSV.
- The repository is designed around event-oriented analytics rather than raw
  video archiving by default.
- Public defaults minimize evidence capture and retention.
- Repository evidence:
  - [PRIVACY_POLICY.md](../PRIVACY_POLICY.md)
  - [docs/data_governance.md](data_governance.md)
  - [src/backend_api/main.py](../src/backend_api/main.py)
  - [docs/demo_guide.md](demo_guide.md)

## Indicator 7: Privacy and Applicable Laws

- Privacy obligations, operator responsibilities, and legal-review boundaries
  are documented explicitly.
- Repository evidence:
  - [PRIVACY_POLICY.md](../PRIVACY_POLICY.md)
  - [docs/data_governance.md](data_governance.md)
  - [docs/safety_and_risk.md](safety_and_risk.md)

## Indicator 8: Open Standards and Best Practices

- The system uses open messaging and API patterns such as MQTT, JSON, HTTP, and
  FastAPI/OpenAPI.
- Repository evidence:
  - [docs/standards_compliance.md](standards_compliance.md)
  - [src/data_streaming/mqtt_forwarder.py](../src/data_streaming/mqtt_forwarder.py)
  - [src/backend_api/main.py](../src/backend_api/main.py)
  - [.github/workflows/ci.yml](../.github/workflows/ci.yml)

## Indicator 9A: Data Privacy and Security

- The public release defaults to disabled evidence capture and retention-based
  cleanup for evidence and preview artifacts.
- Repository evidence:
  - [SECURITY.md](../SECURITY.md)
  - [PRIVACY_POLICY.md](../PRIVACY_POLICY.md)
  - [src/backend_api/main.py](../src/backend_api/main.py)
  - [deploy/env/server-common.env.example](../deploy/env/server-common.env.example)
  - [docs/data_governance.md](data_governance.md)

## Indicator 9B: Inappropriate and Illegal Content

- This repository does not distribute a moderation system for general content
  platforms, but it does document deployment guardrails, scope boundaries, and
  responsible-use expectations for public-space video analytics.
- Repository evidence:
  - [docs/safety_and_risk.md](safety_and_risk.md)
  - [README.md](../README.md)
  - [PRIVACY_POLICY.md](../PRIVACY_POLICY.md)

## Indicator 9C: Protection from Harassment

- Community participation is governed by a contributor code of conduct and
  contribution rules for respectful collaboration.
- Repository evidence:
  - [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
  - [CONTRIBUTING.md](../CONTRIBUTING.md)
  - [SECURITY.md](../SECURITY.md)

## Open items requiring owner or legal review

- Final approval of governance, privacy, security, and DPG evidence wording by
  ILMIHA Labs or another authorized project representative
- Deployment-specific lawful basis analysis for any non-research use
- Confirmation that any future demo datasets included in the repository are
  redistributable under documented terms

For submission handoff, use:

- `docs/dpg_submission_checklist.md`
- `docs/release_checklist.md`
