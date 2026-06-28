# Road User Intelligence Platform — Improvement Plan

**Prepared by:** Engineering  
**Date:** 2026-06-28  
**Status:** Draft — open for team review  
**Target audiences:** Backend, CV/ML, DevOps contributors

---

## Background

An audit of the current codebase identified 15 improvement areas spanning correctness bugs, maintainability, performance, and security. This document organises those findings into three delivery phases so the team can plan sprints, assign ownership, and track progress without disrupting active research work.

The platform is a research MVP and improvements are scoped accordingly — we are hardening what exists, not rebuilding it.

---

## Summary Table

| # | Item | Priority | Effort | Phase |
|---|------|----------|--------|-------|
| 1 | Complete `speed_calc.py` truncated function | Critical | XS | 1 |
| 2 | Standardise datetime to UTC-aware | Critical | S | 1 |
| 3 | Replace broad `except Exception` handlers | High | S | 1 |
| 4 | Replace `print()` calls with `logger` | High | XS | 1 |
| 5 | Extract magic numbers to constants | High | S | 1 |
| 6 | Add MQTT broker health check & retry | High | S | 1 |
| 7 | Fix database migration idempotency | High | S | 1 |
| 8 | Split `backend_api/main.py` into route modules | Medium | M | 2 |
| 9 | Add thread-safety locks to shared state | Medium | S | 2 |
| 10 | Add API authentication middleware | Medium | M | 2 |
| 11 | Batch MQTT → HTTP forwarding | Medium | S | 2 |
| 12 | Complete type hint coverage + run mypy | Medium | M | 2 |
| 13 | Centralise logging configuration | Low | XS | 3 |
| 14 | Add API versioning (`/api/v1/`) | Low | S | 3 |
| 15 | Split `traffic_metrics.py` into focused modules | Low | M | 3 |

**Effort key:** XS < 2 h · S = half day · M = 1–2 days

---

## Phase 1 — Correctness & Stability
**Goal:** Eliminate known bugs and silent failures before the next demo or data collection run.  
**Suggested timeframe:** 1 sprint (1–2 weeks)

---

### 1. Complete truncated `speed_calc.py` function

**File:** `src/speed_estimation/speed_calc.py`  
**Problem:** `clean_old_tracks()` is cut off mid-function — the deletion loop never executes. Stale track records accumulate without bound, growing memory usage over long runs.  
**Fix:** Restore the missing lines that pop `keys_to_remove` from `self.tracks`.  
**Effort:** XS  
**Test:** Run the speed estimation service for > 60 s; confirm `len(tracks)` does not grow monotonically.

---

### 2. Standardise datetime handling to UTC-aware

**Files:** `src/backend_api/main.py`, `src/backend_api/models.py`, multiple services  
**Problem:** Mixed use of `datetime.utcnow()` (naive, no tzinfo) and `datetime.now(timezone.utc)` (aware) forces defensive `if value.tzinfo is None` patches throughout the codebase. Comparisons between naive and aware datetimes raise `TypeError` at runtime.  
**Fix:** Replace every `datetime.utcnow()` call with `datetime.now(timezone.utc)`. Update any ORM `default=` lambdas to match.  
**Effort:** S  
**Test:** Grep for `utcnow` returns zero results after the change; existing datetime-comparison unit tests pass.

---

### 3. Replace broad `except Exception` handlers

**File:** `src/backend_api/main.py` (21 instances)  
**Problem:** Catching the base `Exception` class hides programming errors (e.g., `AttributeError`, `KeyError`) behind a generic 500 response, making bugs invisible in logs.  
**Fix:** Replace with targeted catches — `except (IntegrityError, OperationalError)` for database operations; re-raise unexpected exceptions or log them with full tracebacks before responding 500.  
**Effort:** S  
**Test:** Introduce a deliberate schema mismatch in a dev environment; confirm the real error surfaces in logs.

---

### 4. Replace `print()` with structured logging

**File:** `src/video_analysis/traffic_metrics.py` (lines 557, 582, 1560)  
**Problem:** Three `print()` calls bypass the logging system, so output does not appear in log files or log aggregators, and cannot be filtered by level.  
**Fix:** Replace with `logger.info(...)` using the module-level logger already present in the file.  
**Effort:** XS

---

### 5. Extract magic numbers to a constants file

**Files:** `src/edge_vision/detection.py`, `src/speed_estimation/speed_calc.py`, `src/violation_detection/violation_rules.py`  
**Problem:** Values such as detection confidence (`0.25`), speed cap (`200.0 km/h`), YOLO class IDs (`[0,1,2,3,5,7]`), and safety time-windows (`3.0 s`, `2.0 s`, `0.75 s`) are scattered inline. Changing a threshold requires a codebase-wide grep.  
**Fix:** Create `src/common/constants.py` and centralise these values. Reference them by name from all call sites.  
**Effort:** S

---

### 6. Add MQTT broker health check and retry

**Files:** `src/edge_vision/publisher.py`, `src/speed_estimation/main.py`, `src/violation_detection/main.py`  
**Problem:** If the MQTT broker is unavailable at startup, services start silently and publish nothing — no error is raised and no log message indicates the failure.  
**Fix:** Add a startup connectivity check with exponential backoff (max 3 retries). Log a clear `CRITICAL` message and exit with a non-zero code if the broker is unreachable.  
**Effort:** S

---

### 7. Fix database migration idempotency

**File:** `src/backend_api/database.py`  
**Problem:** `ALTER TABLE ... ADD COLUMN` statements run unconditionally on every startup. A second run raises `OperationalError: duplicate column name`, crashing the backend.  
**Fix:** Wrap each migration step in an existence check, or adopt **Alembic** for proper migration versioning. At minimum add `IF NOT EXISTS` guards (supported in SQLite 3.37+).  
**Effort:** S

---

## Phase 2 — Maintainability & Robustness
**Goal:** Reduce the cost of future changes; address correctness issues that affect concurrent workloads.  
**Suggested timeframe:** 2–3 weeks after Phase 1 lands

---

### 8. Split `backend_api/main.py` into route modules

**File:** `src/backend_api/main.py` (2 261 lines)  
**Problem:** A single file contains route definitions, business logic, export utilities, and database helpers for 36 endpoints. This makes code review, testing, and parallel development difficult.  
**Proposed structure:**
```
src/backend_api/
├── main.py              # App factory + middleware only
├── routes/
│   ├── cameras.py       # /cameras/*, /setup/*
│   ├── analytics.py     # /analytics/*
│   ├── violations.py    # /violations/*
│   ├── exports.py       # /exports/*
│   ├── video_analysis.py # /video-analysis/*
│   └── live.py          # /live/*
├── services/            # Business logic (no FastAPI imports)
├── models.py
├── schemas.py
└── database.py
```
**Effort:** M  
**Note:** No behaviour changes in this refactor; all existing tests must pass unchanged.

---

### 9. Add thread-safety locks to shared state

**Files:** `src/speed_estimation/speed_calc.py`, `src/data_streaming/mqtt_forwarder.py`  
**Problem:** `SpeedCalculator.tracks` and `SpeedCalculator.last_speeds` are written by one thread and read by another (periodic cleanup vs. incoming detections) without synchronisation. The shared MQTT client is similarly unprotected.  
**Fix:** Wrap mutable shared state with `threading.Lock` (or switch to `asyncio`-native queues if the service is refactored to async).  
**Effort:** S

---

### 10. Add API authentication middleware

**File:** `src/backend_api/main.py`  
**Problem:** All endpoints — including video upload, camera configuration, and violation log access — are unauthenticated. Any process that can reach port 8000 can read or modify data.  
**Fix:** Add a FastAPI dependency that validates a bearer API key from an environment variable (`RUIP_API_KEY`). Exempt the dashboard static files and health check endpoint. Document the key in the deployment guide.  
**Effort:** M  
**Note:** This is not a full auth system — it is a minimal access gate appropriate for a research deployment on a controlled network.

---

### 11. Batch MQTT → HTTP event forwarding

**File:** `src/data_streaming/mqtt_forwarder.py`  
**Problem:** One HTTP POST is fired per MQTT message. At 25 fps with multiple tracked objects, this can generate hundreds of requests per second, saturating the backend and SQLite write queue.  
**Fix:** Buffer incoming events for 100 ms (configurable) and POST them as a JSON array to a new `/batch` endpoint. Fall back to individual POSTs if the backend does not support batching.  
**Effort:** S

---

### 12. Complete type hint coverage and add `mypy` to CI

**Files:** `src/edge_vision/detection.py`, `src/violation_detection/violation_rules.py`, `src/edge_vision/publisher.py`  
**Problem:** Key modules have missing or incomplete return type annotations, making IDE assistance and static analysis unreliable.  
**Fix:** Add type hints to all public function signatures in the above files. Run `mypy --strict src/` and resolve all errors. Add `mypy` as a CI step (GitHub Actions or pre-commit hook).  
**Effort:** M

---

## Phase 3 — Polish & Scalability
**Goal:** Quality-of-life improvements that reduce operational friction as the platform grows.  
**Suggested timeframe:** Ongoing, pick up after Phase 2 stabilises

---

### 13. Centralise logging configuration

**Problem:** `logging.basicConfig(...)` is called independently in every module. When multiple modules are imported together, later calls to `basicConfig` are silently ignored, leading to inconsistent log formats and potential duplicate handlers.  
**Fix:** Call `basicConfig` (or configure a `logging.config.dictConfig`) exactly once in each service's entry-point `main.py`. All other modules should only create a module-level logger with `logging.getLogger(__name__)`.  
**Effort:** XS

---

### 14. Add API versioning

**File:** `src/backend_api/main.py`  
**Problem:** All routes are at the root path. A breaking change in any endpoint will immediately break consumers without a migration path.  
**Fix:** Mount all routes under `/api/v1/` using FastAPI's `APIRouter(prefix="/api/v1")`. Keep unversioned routes as redirects during a short transition period.  
**Effort:** S

---

### 15. Decompose `traffic_metrics.py`

**File:** `src/video_analysis/traffic_metrics.py` (1 566 lines)  
**Problem:** Detection, frame analysis, metrics aggregation, serialisation, and file I/O are all mixed in one class. Adding a new analysis mode requires editing a file that touches everything.  
**Proposed split:**
```
src/video_analysis/
├── detector.py        # YOLOv8 wrapper + tracking
├── analyzer.py        # Frame-level metrics + aggregation
├── serializer.py      # JSON / CSV output
└── traffic_metrics.py # Orchestrator (thin, imports the above)
```
**Effort:** M

---

## Ownership Suggestions

These are starting points — adjust based on current workloads.

| Area | Suggested Owner |
|------|----------------|
| CV / detection pipeline (items 1, 5, 15) | CV/ML engineer |
| Backend API (items 3, 7, 8, 10, 11, 14) | Backend engineer |
| Infrastructure / services (items 6, 9, 13) | DevOps / backend |
| Code quality / tooling (items 2, 4, 12) | Any contributor, good onboarding tasks |

---

## Definition of Done

An item is complete when:
1. Code is merged to `main` via a reviewed pull request.
2. Existing tests pass (no regressions).
3. A new or updated test covers the changed behaviour where applicable.
4. The relevant section in `docs/` is updated if the change affects setup or configuration.

---

## Out of Scope (Future Consideration)

The following were identified in the audit but are **not** included in this plan because they require broader architectural decisions:

- Full user authentication and role-based access control
- Multi-tenancy (per-camera or per-organisation data isolation)
- OpenTelemetry distributed tracing
- Prometheus metrics endpoint
- Alerting / notification framework
- Data retention policy enforcement

These should be revisited when the platform moves beyond a research deployment.

---

## How to Contribute

1. Pick an item from the table above and comment on this document or open a GitHub issue.
2. Create a branch named `improve/<short-description>` (e.g., `improve/datetime-utc`).
3. Follow the fix guidance in the relevant section.
4. Open a PR referencing this document.

Questions or disagreements with the prioritisation? Raise them in the team channel or open a discussion on the repository.
