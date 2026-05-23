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
- the official public workflow is documented in:
  - `README.md`
  - `docs/demo_guide.md`
  - `docs/release_checklist.md`

## Owner-review items

- confirm SDG 11 framing is the desired public positioning
- confirm ILMIHA Labs stewardship and maintainer information
- confirm the intended public scope remains “research-reference MVP”
- approve release notes and version for the first public research release

## Legal-review items

- approve the wording in `PRIVACY_POLICY.md`
- approve the wording in `SECURITY.md` if required by organizational policy
- confirm lawful-basis and deployment-language disclaimers are acceptable
- confirm the repository does not include unlicensed demo media or assets
- approve any future bundled dataset or video before publication

## Submission-ready evidence map

Before submission, verify that the current indicator set is covered by:

- `README.md`
- `LICENSE`
- `NOTICE`
- `CITATION.cff`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `GOVERNANCE.md`
- `SECURITY.md`
- `PRIVACY_POLICY.md`
- `docs/dpg_readiness.md`
- `docs/data_governance.md`
- `docs/safety_and_risk.md`
- `docs/standards_compliance.md`
- `docs/release_checklist.md`

## Final release gate

The repository is ready for a formal DPG submission handoff only when:

- engineering-complete items are done
- unresolved items are owner or legal approvals only
- the public workflow has been re-validated from a clean clone
