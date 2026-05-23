# Public Research Release Checklist

Use this checklist before calling the repository ready for outside researchers.

## Canonical workflow

The official public workflow is:

1. clone the repository
2. create and activate `.venv`
3. install `requirements-dev.txt`
4. run `python -m unittest discover -s tests -v`
5. provide a licensed local video through `DEMO_VIDEO_SOURCE`
6. run `bash run_pipeline.sh`
7. open the backend-served dashboard URL printed by the startup script
8. inspect detections, counts, speeds, safety events, and exports

## Commands that must work

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
export PYTHONPATH=$PWD/src
python -m unittest discover -s tests -v
export DEMO_VIDEO_SOURCE=/absolute/path/to/licensed/video.mp4
bash run_pipeline.sh
```

## Passing release signals

- tests pass from a clean environment
- `run_pipeline.sh` rejects a missing `DEMO_VIDEO_SOURCE` with a clear message
- `run_pipeline.sh` prints the exact backend and dashboard URL it serves
- the dashboard is reachable at the printed `/dashboard/` route
- the demo camera shows:
  - detections
  - class breakdowns
  - directional counting
  - speed samples
  - safety events
  - exports
- the repository contains no tracked `.DS_Store` files or local SQLite runtime
  database

## Known limitations that must stay documented

- the public repository does not bundle a guaranteed redistributable demo video
- evidence capture is disabled by default
- live previews are snapshot-based in this MVP
- scene results remain calibration-sensitive and threshold-sensitive
- this is a research-reference MVP, not a production-ready surveillance system

## Configuration expectations

- `config/cameras.yaml` is the only authoritative runtime configuration file
- helper files in `config/` are calibration or reference assets only
- any demo-specific camera profile must not imply that a bundled sample video is
  part of the public package
