---
name: Safety-event / calibration report
about: Report a false positive, false negative, or calibration issue in a safety event or count
title: "[Calibration]: "
labels: calibration
---

## Safety-event or measure type

<!-- Delete the ones that don't apply. -->

- zebra-crossing interaction / yielding
- stop-line violation
- speed / speed compliance
- helmet
- directional counting / crossings
- pedestrian episode / post-encroachment time (PET)
- other:

## What went wrong

<!-- e.g. "vehicle flagged as not yielding when it clearly stopped", or
"pedestrian crossings undercounted". -->

## Scene description

<!-- Camera placement, angle, approximate field of view, lighting, weather. -->

## Calibration values used

- pixels_per_meter:
- speed_limit_kmh:
- zebra / counting-line setup:
- relevant thresholds:

## Expected vs. observed behaviour

- Expected:
- Observed:

## How often it occurs

<!-- Every time / intermittently / specific conditions only. -->

## Evidence

> Attach **sanitized** evidence only — event-level CSV/JSON rows, metrics
> summaries, or redacted images. Do not attach raw footage or PII. See
> `docs/data_governance.md`.
