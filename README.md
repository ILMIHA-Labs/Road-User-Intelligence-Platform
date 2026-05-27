# Road User Intelligence Platform

Road User Intelligence Platform is an open-source, research-reference MVP for
camera-based traffic analytics with a current emphasis on **zebra-crossing road
safety**.

The project supports:

- road-user detection and classification
- directional counting across configured lines
- speed estimation
- configurable safety-event detection
- event review with optional evidence capture
- live dashboard-based monitoring and export

This public release is framed primarily around **SDG 11 road safety** and is
intended to help researchers and evaluators study safer urban mobility
scenarios.

## Public release posture

This repository is published as:

- open-source software under the MIT license
- a research-reference MVP
- a privacy-conscious baseline, not a production-ready surveillance platform

## Quickstart

```bash
git clone https://github.com/ILMIHA-Labs/Road-User-Intelligence-Platform.git
cd Road-User-Intelligence-Platform
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
export PYTHONPATH=$PWD/src
python -m unittest discover -s tests -v
```

## Run the MVP

The public repository does not assume a bundled redistributable demo video.
Provide your own licensed clip or camera source. The canonical public demo path
uses `run_pipeline.sh` with an explicit `DEMO_VIDEO_SOURCE`.

```bash
export DEMO_VIDEO_SOURCE=/absolute/path/to/your/video.mp4
bash run_pipeline.sh
```

The script prints the exact backend and dashboard URL it is serving.

Always use the backend-served dashboard. Do not use the raw `file://` copy of
`src/dashboard/app/index.html` as your primary application surface.

## Dashboard video analysis

The dashboard includes a `Video Analysis` workspace for a researcher who wants
to analyze a permitted prerecorded clip without adding it to live operations:

1. open the backend-served `/dashboard/` URL and choose `Video Analysis`
2. upload an `.mp4`, `.mov`, `.avi`, `.mkv`, or `.webm` source you are
   permitted to analyze
3. draw one or more counting lines and at least one zebra-crossing polygon
4. set pixels-per-metre, zebra speed threshold, and approach deadband
5. run the temporary analysis and review the annotated video and downloadable
   JSON/CSV reports

Uploaded-video detections and zebra interactions are not inserted into the
live operational event database. The upload, annotated media, and reports are
privacy-sensitive temporary session files that expire automatically, or can
be deleted sooner from the page.

Runtime controls for this workspace are:

- `VIDEO_ANALYSIS_RETENTION_SECONDS=86400`
- `VIDEO_ANALYSIS_MAX_UPLOAD_MB=500`
- `VIDEO_ANALYSIS_MAX_CONCURRENT_JOBS=1`

## Live-device path

```bash
bash scripts/start_central_stack.sh
```

Then validate a live camera with:

```bash
bash scripts/check_live_pipeline.sh http://127.0.0.1:${BACKEND_PORT:-8000} recam_01
```

`reCamera` is optional. Generic webcam, RTSP, and file-based inputs remain
supported.

## Canonical evaluation workflow

The official researcher path is:

1. install dependencies from `requirements-dev.txt`
2. run `python -m unittest discover -s tests -v`
3. provide a licensed local video through `DEMO_VIDEO_SOURCE`
4. run `bash run_pipeline.sh`
5. open the printed backend-served `/dashboard/` URL
6. inspect detections, counts, speeds, safety events, and exports

## Research use

This release is intended to support:

- traffic analytics experiments
- zebra-crossing and stop-line safety studies
- calibration and counting evaluations
- speed-estimation benchmarking
- rule-tuning and false-positive review workflows

Expected outputs include:

- detections by class
- directional counting events
- speed samples
- safety-event records
- dashboard summaries and exports

Known reproducibility limits:

- results depend heavily on camera placement and calibration
- object detection quality depends on scene conditions and model behavior
- safety-event logic is scene-sensitive and threshold-sensitive
- live previews are snapshot-based rather than full streaming transport

## Responsible deployment

If you deploy this software outside a lab or research setting, review:

- `PRIVACY_POLICY.md`
- `SECURITY.md`
- `docs/data_governance.md`
- `docs/safety_and_risk.md`
- `docs/dpg_readiness.md`

The public release is conservative by default:

- `EVIDENCE_CAPTURE_ENABLED=false`
- preview and setup-preview artifacts are treated as short-lived runtime files
- raw video is not archived by the backend by default
- explicitly uploaded research-analysis clips and their derived media expire
  after the configured temporary-analysis retention period

## Configuration

The authoritative runtime configuration is:

- `config/cameras.yaml`

Helper files in `config/` are calibration or reference assets and should not be
treated as the canonical runtime source of truth unless explicitly documented.

The bundled `sample_video_01` profile is a demo template only. It does not mean
that a sample video is guaranteed to ship with the public repository.

## Documentation map

- `docs/demo_guide.md`
- `docs/deployment_guide.md`
- `docs/installation_and_deployment.md`
- `docs/system_architecture.md`
- `docs/dpg_readiness.md`
- `docs/dpg_submission_checklist.md`
- `docs/data_governance.md`
- `docs/release_checklist.md`
- `docs/safety_and_risk.md`
- `docs/standards_compliance.md`
- `CHANGELOG.md`

## Governance files

- `LICENSE`
- `NOTICE`
- `CITATION.cff`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `GOVERNANCE.md`
- `SECURITY.md`
- `PRIVACY_POLICY.md`
