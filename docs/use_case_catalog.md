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
