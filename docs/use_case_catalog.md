# Use-Case Catalog

This catalog maps expected user personas to outcomes for the Road User Intelligence Platform.

## UC-1 Real-Time Traffic Monitoring

- Persona: City traffic operations team
- Goal: Monitor traffic flow and road-user activity in near real time
- Inputs: Edge camera streams, RTSP camera streams
- Outputs: Detection events, dashboard insights
- Success metric: Continuous event flow with low interruption rate

## UC-2 Speeding Detection

- Persona: Road safety authority
- Goal: Identify vehicles exceeding configured speed thresholds
- Inputs: Detection tracks and calibrated camera metadata
- Outputs: Speed events and violation events
- Success metric: Speed event coverage and validated estimation accuracy

## UC-3 Rule-Based Violation Alerting

- Persona: Enforcement analytics team
- Goal: Flag safety violations (speed, zebra crossing, helmet rule where enabled)
- Inputs: Detection and speed streams
- Outputs: Violation event records and backend-queryable history
- Success metric: Low false-positive trend and complete event persistence

## UC-4 Historical Analytics and Reporting

- Persona: Transport policy and planning team
- Goal: Use historical data for trend analysis and intervention planning
- Inputs: Persisted detections/speeds/violations/trajectories
- Outputs: Aggregated metrics and reporting datasets
- Success metric: Queryable historical coverage for configured time windows

## UC-5 Simulation-Based Validation

- Persona: Research and evaluation engineer
- Goal: Validate pipeline behavior under synthetic scenarios
- Inputs: Simulated detection and trajectory events
- Outputs: Comparable downstream analytics and model evaluation metrics
- Success metric: Repeatable scenario execution with expected downstream outputs

## UC-6 Edge Deployment Readiness

- Persona: Edge platform engineer
- Goal: Deploy stable camera processing on ReCamera-like devices
- Inputs: Runtime audit scripts and deployment checklists
- Outputs: Runtime evidence, decision gate, release branch recommendation
- Success metric: Stable sustained run and successful publish to broker

## UC-7 Crossing-Safety Research Measures

- Persona: Road-safety researcher
- Goal: Quantify pedestrian–vehicle interaction quality at zebra crossings
- Inputs: Detection/speed tracks and configured zebra zones (live pipeline or
  the uploaded-video `Video Analysis` workspace)
- Outputs: Pedestrian crossing episodes (wait + crossing time), driver
  yielding rate, post-encroachment time (PET) events, and per-class speed
  compliance — as CSVs and aggregate metrics
- Success metric: Reproducible measures that align with manual review on
  labelled scenarios

## UC-8 Demand & Reproducible Dataset Export

- Persona: Transport planning / open-data researcher
- Goal: Produce publishable demand statistics and a reproducible dataset
- Inputs: Persisted crossings/speeds/detections plus optional lighting/weather
  scene-condition tags
- Outputs: Hourly/peak-hour profiles, vehicle headway distributions, and a
  one-download `research-bundle.zip` (event CSVs + `traffic_flow.json` +
  `manifest.json` with schema, calibration, and platform version)
- Success metric: A downloaded bundle that reproduces the reported aggregates
  from its own CSVs
