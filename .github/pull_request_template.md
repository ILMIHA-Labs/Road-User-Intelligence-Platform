<!--
Thanks for contributing to the Road User Intelligence Platform.
Please keep this pull request focused. See CONTRIBUTING.md for full expectations.
-->

## Summary

<!-- The problem being solved. -->

## User / operator impact

<!-- Who benefits and how (researcher, operator, evaluator)? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor (no behaviour change)
- [ ] Tests
- [ ] CI / tooling

## Privacy & safety implications

<!-- Evidence capture, retention, PII exposure, or safety-event logic. State
"None" if not applicable. -->

## Configuration / migration / retention changes

<!-- New env vars, schema/table changes, changed defaults, retention behaviour.
State "None" if not applicable. -->

## Documentation

- [ ] Docs updated, or not required for this change

<!-- Per CONTRIBUTING.md, update the relevant docs when the change affects
public APIs, runtime defaults, retention behaviour, the setup/calibration
workflow, or dashboard interpretation. -->

## How tested

```bash
export PYTHONPATH=$PWD/src
python -m unittest discover -s tests -v
ruff check src tests
mypy src
```

<!-- Add any manual verification steps. -->

## Checklist

- [ ] The pull request is focused on a single concern
- [ ] Tests pass locally (and new/updated tests cover the change where applicable)
- [ ] Documentation updated if needed
- [ ] No databases, logs, or generated previews are committed
- [ ] Privacy-minimizing defaults are preserved (or policy docs + tests updated)
