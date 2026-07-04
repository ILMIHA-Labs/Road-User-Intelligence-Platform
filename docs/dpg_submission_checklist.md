# DPG Submission Checklist

Use this checklist to distinguish engineering-complete repository work from the
items that still require owner or legal approval before a formal DPG
submission.

## Engineering-complete items

- MIT license is published in `LICENSE`
- governance, security, privacy, conduct, contribution, and notice files exist
- DPG evidence mapping exists in `docs/dpg_readiness.md`
- privacy-sensitive defaults are conservative in code and environment examples
- repository hygiene excludes tracked runtime junk
- reproducible install and test path exists
- CI checks tests, governance files, and tracked-junk hygiene
- public documentation uses repository-relative paths rather than local machine
  paths
- the official public workflow is documented in:
  - `README.md`
  - `docs/demo_guide.md`
  - `docs/release_checklist.md`

## Owner-review items

- confirm SDG 11 framing is the desired public positioning
- confirm ILMIHA Labs stewardship and maintainer information
- confirm the intended public scope remains “research-reference MVP”
- approve release notes and version for the first public research release


## Submission-ready evidence map

Before submission, verify that the current DPG indicator set is covered by:

| DPG indicator | Required repository evidence |
| --- | --- |
| 1. SDG Relevance | `README.md`, `docs/safety_and_risk.md`, `docs/use_case_catalog.md` |
| 2. Open Licencing | `LICENSE`, `NOTICE`, `pyproject.toml` |
| 3. Clear Ownership | `NOTICE`, `GOVERNANCE.md`, `CONTRIBUTING.md`, `CITATION.cff` |
| 4. Platform Independence | `README.md`, `docs/deployment_guide.md`, `docs/installation_and_deployment.md`, `docs/live_validation_guide.md`, `Dockerfile`, `docker-compose.yml` |
| 5. Documentation | `README.md`, `docs/demo_guide.md`, `docs/functional_requirements.md`, `docs/use_case_catalog.md`, `docs/system_architecture.md` |
| 6. Non-PII Data Extraction | `PRIVACY_POLICY.md`, `docs/data_governance.md`, `src/backend_api/main.py` |
| 7. Privacy & Applicable Laws | `PRIVACY_POLICY.md`, `docs/data_governance.md`, `docs/safety_and_risk.md` |
| 8. Open Standards & Best Practices | `docs/standards_compliance.md`, `.github/workflows/ci.yml`, `src/common/event_schemas.py`, `src/backend_api/routes/metrics.py` |
| 9A. Data Privacy & Security | `SECURITY.md`, `PRIVACY_POLICY.md`, `deploy/env/server-common.env.example`, `src/backend_api/main.py` |
| 9B. Inappropriate & Illegal Content | `docs/safety_and_risk.md`, `PRIVACY_POLICY.md`, `README.md` |
| 9C. Protection from Harassment | `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md` |

The canonical narrative and cross-file evidence map is
`docs/dpg_readiness.md`.

## Final release gate

The repository is ready for a formal DPG submission handoff only when:

- engineering-complete items are done
- unresolved items are owner or legal approvals only
- the public workflow has been re-validated from a clean clone
