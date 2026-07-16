# Data Governance and Minimization

This document describes the default data posture of the public repository and
the decisions deployers still need to make for lawful, responsible use.

## Repository default posture

The public open-source release is intentionally conservative:

- raw video is not archived by the backend by default
- evidence capture is disabled by default
- live preview snapshots and setup previews are short-lived runtime artifacts
- dashboard-uploaded analysis videos and derived outputs are temporary
  research-session files, retained for 24 hours by default
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
- temporary uploaded-video reports and annotated output when a researcher
  explicitly uses the `Video Analysis` workspace

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
- `VIDEO_ANALYSIS_RETENTION_SECONDS` (default `86400`)
- `VIDEO_ANALYSIS_MAX_UPLOAD_MB` (default `500`)
- `VIDEO_ANALYSIS_MAX_CONCURRENT_JOBS` (default `1`)

These controls should be reviewed and set before any field or pilot deployment.

## Privacy redaction

When the platform writes imagery (violation evidence, analysis video), it blurs
faces and licence plates by default (`REDACTION_ENABLED=true`). The blur is a
heuristic derived from existing person/vehicle detections rather than a
dedicated face/plate detector, so it is approximate; operators storing evidence
should treat it as risk-reduction, not a guarantee. `REDACTION_MIN_GROUP`
(default off) additionally applies k-anonymity suppression to small groups in
the aggregate research endpoints. See `docs/deployment_guide.md` for details.

## Uploaded-video analysis isolation

The dashboard `Video Analysis` workspace accepts a researcher-supplied licensed
video and holds its source, extracted preview, annotated video, and reports
under temporary runtime artifact storage. Its counting and zebra-event outputs
are not inserted into the live detections, crossings, speeds, or safety-event
tables. The uploaded original is not offered as a download through the API.

Temporary files are removed when the user deletes the session or when the
retention period expires. Annotated video remains privacy-sensitive derived
media and must be handled with the same care as the source.

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
