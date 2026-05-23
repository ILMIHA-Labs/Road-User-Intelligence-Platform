# DPG Readiness Mapping

This document maps the Road User Intelligence Platform repository to the
current Digital Public Goods Standard indicators for submission preparation and
internal self-audit.

The project is framed as a **research-reference open-source MVP** with primary
public-interest relevance to **SDG 11 road safety**. This document describes
the repository evidence that supports a DPG submission. It does not claim that
any particular deployment is already certified or legally approved.

## Indicator 1: SDG Relevance

- Primary framing: SDG 11, safer and more inclusive urban mobility
- Repository evidence:
  - [README.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/README.md)
  - [docs/safety_and_risk.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/safety_and_risk.md)

## Indicator 2: Open Licensing

- License: MIT
- Repository evidence:
  - [LICENSE](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/LICENSE)
  - [NOTICE](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/NOTICE)

## Indicator 3: Clear Ownership

- Maintainer and stewardship information is documented for open-source
  governance and contribution review.
- Repository evidence:
  - [GOVERNANCE.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/GOVERNANCE.md)
  - [CONTRIBUTING.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/CONTRIBUTING.md)
  - [CITATION.cff](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/CITATION.cff)

## Indicator 4: Platform Independence

- The software supports file, webcam, RTSP, and optional `reCamera` inputs.
- `reCamera` is documented as optional rather than mandatory.
- Repository evidence:
  - [README.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/README.md)
  - [docs/deployment_guide.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/deployment_guide.md)
  - [docs/installation_and_deployment.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/installation_and_deployment.md)

## Indicator 5: Documentation

- Quickstart, demo, deployment, architecture, and governance documentation are
  published with the repository.
- Repository evidence:
  - [README.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/README.md)
  - [docs/demo_guide.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/demo_guide.md)
  - [docs/deployment_guide.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/deployment_guide.md)
  - [docs/system_architecture.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/system_architecture.md)

## Indicator 6: Non-PII Data Extraction

- The repository is designed around event-oriented analytics rather than raw
  video archiving by default.
- Public defaults minimize evidence capture and retention.
- Repository evidence:
  - [PRIVACY_POLICY.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/PRIVACY_POLICY.md)
  - [docs/data_governance.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/data_governance.md)
  - [src/backend_api/main.py](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/src/backend_api/main.py)

## Indicator 7: Privacy and Applicable Laws

- Privacy obligations, operator responsibilities, and legal-review boundaries
  are documented explicitly.
- Repository evidence:
  - [PRIVACY_POLICY.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/PRIVACY_POLICY.md)
  - [docs/data_governance.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/data_governance.md)
  - [docs/safety_and_risk.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/safety_and_risk.md)

## Indicator 8: Open Standards and Best Practices

- The system uses open messaging and API patterns such as MQTT, JSON, HTTP, and
  FastAPI/OpenAPI.
- Repository evidence:
  - [docs/standards_compliance.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/standards_compliance.md)
  - [src/data_streaming/mqtt_forwarder.py](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/src/data_streaming/mqtt_forwarder.py)
  - [src/backend_api/main.py](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/src/backend_api/main.py)

## Indicator 9A: Data Privacy and Security

- The public release defaults to disabled evidence capture and retention-based
  cleanup for evidence and preview artifacts.
- Repository evidence:
  - [SECURITY.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/SECURITY.md)
  - [PRIVACY_POLICY.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/PRIVACY_POLICY.md)
  - [src/backend_api/main.py](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/src/backend_api/main.py)
  - [deploy/env/server-common.env.example](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/deploy/env/server-common.env.example)

## Indicator 9B: Inappropriate and Illegal Content

- This repository does not distribute a moderation system for general content
  platforms, but it does document deployment guardrails, scope boundaries, and
  responsible-use expectations for public-space video analytics.
- Repository evidence:
  - [docs/safety_and_risk.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/docs/safety_and_risk.md)
  - [README.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/README.md)

## Indicator 9C: Protection from Harassment

- Community participation is governed by a contributor code of conduct and
  contribution rules for respectful collaboration.
- Repository evidence:
  - [CODE_OF_CONDUCT.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/CODE_OF_CONDUCT.md)
  - [CONTRIBUTING.md](/Users/a2.0/Desktop/Road-User-Intelligence-Platform/CONTRIBUTING.md)

## Open items requiring owner or legal review

- Final approval of governance and privacy policy wording by ILMIHA Labs
- Deployment-specific lawful basis analysis for any non-research use
- Confirmation that any future demo datasets included in the repository are
  redistributable under documented terms

For submission handoff, use:

- `docs/dpg_submission_checklist.md`
- `docs/release_checklist.md`
