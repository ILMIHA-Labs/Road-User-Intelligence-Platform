# Road User Intelligence Platform

Road User Intelligence Platform is an MVP traffic analytics system for ingesting camera video, detecting and tracking road users, estimating speed, detecting violations, streaming events over MQTT, storing them through a FastAPI backend, and exposing live/analytics dashboard data.

For a contributor-oriented tour of the codebase, start with [docs/contributor_codebase_guide.md](docs/contributor_codebase_guide.md).

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
python -m unittest discover -s tests
```

To run the local MVP pipeline with the sample video:

```bash
./run_pipeline.sh
```

The pipeline expects an MQTT broker implementation. `run_pipeline.sh` tries `amqtt` first and falls back to `mosquitto`.

## Main Documentation

- [Contributor Codebase Guide](docs/contributor_codebase_guide.md): practical map for new contributors.
- [System Architecture](docs/system_architecture.md): high-level architecture and MQTT topics.
- [Integration Guide](docs/integration_guide.md): module-to-module data flow.
- [Installation and Deployment](docs/installation_and_deployment.md): setup and deployment notes.
- [Live Validation Guide](docs/live_validation_guide.md): checks for live camera/backend validation.
- [Functional Requirements](docs/functional_requirements.md): expected platform capabilities.
- [Use Case Catalog](docs/use_case_catalog.md): supported user and system use cases.

## Repository Scope Note

The road-user platform lives under `src/`, `config/`, `docs/`, `deploy/`, `scripts/`, and `tests/`.
