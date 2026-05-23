# Data Governance and Minimization

This document describes the default data posture of the public repository and
the decisions deployers still need to make for lawful, responsible use.

## Repository default posture

The public open-source release is intentionally conservative:

- raw video is not archived by the backend by default
- evidence capture is disabled by default
- live preview snapshots and setup previews are short-lived runtime artifacts
- the main retained records are event-oriented analytics such as detections,
  speeds, line crossings, and safety-event metadata

## What the system extracts

The software can derive and store:

- camera identifiers
- timestamps
- detection classes and bounding boxes
- tracking identifiers generated for analytics
- speed estimates
- directional counting events
- safety-event records
- optional evidence image paths when evidence capture is explicitly enabled

## What the system does not store by default

In the public profile, the repository does not treat the following as default
long-term outputs:

- raw source video archives
- always-on evidence image retention
- indefinite live-preview retention
- unrestricted public sharing of event data

## Retention controls

Important runtime controls include:

- `EVIDENCE_CAPTURE_ENABLED`
- `VIOLATION_EVIDENCE_RETENTION_SECONDS`
- `LIVE_PREVIEW_RETENTION_SECONDS`
- `SETUP_PREVIEW_RETENTION_SECONDS`

These controls should be reviewed and set before any field or pilot deployment.

## Operator responsibilities

Deployers are responsible for deciding:

- whether video collection is lawful and necessary
- whether evidence capture should be enabled at all
- how long evidence and previews may be retained
- who can access stored evidence or event records
- whether a deployment requires community notice, signage, consent, or formal
  institutional review

## Research release guidance

For outside researchers using this repository:

- use licensed or self-collected video only
- avoid publishing identifiable evidence images unless ethically and legally
  justified
- document calibration choices and threshold changes for reproducibility
- keep event exports and preview artifacts under project-level access control

## Open governance and legal placeholders

The following require deployment-owner review rather than repository-only
decisions:

- lawful basis under applicable privacy or data-protection law
- local public-space monitoring obligations
- retention policies imposed by funders, institutions, or regulators
- special handling for schools, children, hospitals, or other sensitive areas
