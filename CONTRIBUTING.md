# Contributing Guide

## Summary

Thank you for contributing to Road User Intelligence Platform. This repository
is maintained as a research-reference open-source MVP with a strong emphasis on
road safety, reproducibility, and privacy-aware deployment.

## Before you contribute

- read `README.md`
- read `CODE_OF_CONDUCT.md`
- read `docs/data_governance.md` and `docs/safety_and_risk.md` if your change
  affects data handling, previews, evidence, or safety-event logic

## Contribution priorities

Contributions are most helpful when they improve:

- reproducibility
- documentation quality
- privacy and security posture
- test coverage
- rule calibration and reliability
- interoperability for research use

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
export PYTHONPATH=$PWD/src
python -m unittest discover -s tests -v
```

## Pull request expectations

Please keep pull requests focused and explain:

- the problem being solved
- the intended user or operator impact
- any privacy or safety implications
- any configuration or migration changes
- how the change was tested

## Documentation expectations

If your change affects:

- public APIs
- runtime defaults
- retention behavior
- setup/calibration workflow
- dashboard interpretation

then update the relevant docs in the same pull request.

## Data and asset rules

- do not commit local databases, logs, or generated previews
- do not add redistributable uncertainty around sample videos or third-party
  assets
- do not enable privacy-sensitive storage by default without updating policy
  docs and tests

## Review and governance

Maintainers may decline contributions that conflict with:

- privacy-minimizing defaults
- the research-reference scope of the public release
- responsible road-safety framing
- the documented governance or code of conduct
