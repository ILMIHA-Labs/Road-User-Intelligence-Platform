# Privacy Policy

## Summary

Road User Intelligence Platform is published as open-source software for
research and evaluation. The software can process camera feeds, derive traffic
events, and optionally store evidence snapshots. Privacy-sensitive behavior is
configurable, and the public repository defaults are designed to minimize data
retention.

This document is part of a research-reference, non-production public release.

## Data the software can process

Depending on deployment choices, the software may process:

- live video or recorded video files supplied by the operator
- object detections and tracked bounding boxes
- timestamps, camera identifiers, and object identifiers
- speed estimates
- directional counting events
- safety event records
- optional evidence images and live preview snapshots

## Data minimization posture in the public release

The public open-source defaults are intentionally conservative:

- raw video is not persisted by default
- evidence snapshot capture is disabled by default
- live preview and setup preview artifacts are runtime files, not long-term
  archival storage
- only event-oriented analytics are intended to be retained by default

## Purpose of processing

The software is intended for:

- road safety research
- traffic analytics and evaluation
- zebra-crossing and stop-line safety studies
- calibration and benchmarking of computer vision traffic workflows

The software is **not** published as a general-purpose surveillance platform.

## Operator responsibility

Anyone deploying this software is responsible for:

- determining the lawful basis for processing under applicable law
- validating whether video, preview, or evidence storage is permitted
- configuring retention periods suitable for the deployment context
- informing affected communities and stakeholders where required
- disabling or limiting features that are not necessary for the intended study
  or pilot

## Retention and deletion

The public repository exposes runtime controls for privacy-sensitive data:

- `EVIDENCE_CAPTURE_ENABLED=false` by default
- `VIOLATION_EVIDENCE_RETENTION_SECONDS` for evidence cleanup
- `LIVE_PREVIEW_RETENTION_SECONDS` for preview cleanup
- `SETUP_PREVIEW_RETENTION_SECONDS` for setup-preview cleanup
- `VIDEO_ANALYSIS_RETENTION_SECONDS` for temporary uploaded-video analysis
  sessions and derived artifacts
- `VIDEO_ANALYSIS_MAX_UPLOAD_MB` and `VIDEO_ANALYSIS_MAX_CONCURRENT_JOBS` for
  limiting temporary research-session uploads and workload

Deployers should set explicit retention values appropriate to the laws and
policies that apply to them.

## Sharing and disclosure

This repository does not send data to a proprietary cloud service by default.
However, deployers may choose to:

- publish dashboards
- move event data to external storage
- place the backend behind additional infrastructure

Any such sharing is the responsibility of the deployer and should be governed
by local policy and law.

## Applicable laws and frameworks

Deployers should review compliance obligations that may apply to them,
including, where relevant:

- data protection and privacy laws
- public-space monitoring laws
- sector-specific public safety or transport regulations
- child or vulnerable-person protections where cameras cover schools or
  sensitive environments

For international or internet-facing use, this may include frameworks such as
GDPR or equivalent data-protection regimes.

## Contact

Project governance and publication contact:

- ILMIHA Labs
- Repository maintainer of record: Clement Ampofo
