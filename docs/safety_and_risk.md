# Safety and Risk Considerations

This repository is published for research and evaluation. It is not a claim
that automated traffic analytics are harmless by default. Deployers should
review the risks below before operational use.

## 1. Surveillance and privacy risk

Roadside camera systems can affect people who have not explicitly consented to
being observed. Even when the software is used for public-interest road-safety
goals, deployers should minimize collection, minimize retention, and avoid
unnecessary evidence capture.

## 2. False positives and false negatives

Safety-event outputs are scene-sensitive and threshold-sensitive. This creates
two important risks:

- false positives that overstate dangerous behavior
- false negatives that miss important safety issues

Human review remains important, especially when outputs influence reporting,
enforcement, or public claims.

## 3. Bias and environmental limitations

Model performance can vary with:

- lighting
- weather
- camera angle
- occlusion
- traffic density
- local vehicle and pedestrian behavior

Deployers should evaluate performance on the actual scene they care about
rather than assuming one configuration generalizes safely everywhere.

## 4. Harm to vulnerable road users

Crossing-safety studies often involve children, older adults, cyclists, and
other vulnerable users. Poor calibration or careless evidence handling can
increase harm rather than reduce it. Sensitive locations require extra review.

## 5. Misuse and operator abuse

This repository should not be treated as a turnkey surveillance tool. Risks of
misuse include:

- enabling evidence capture without a clear need
- storing previews or evidence longer than necessary
- using scene analytics outside the stated research or safety purpose
- exposing dashboards or exports without access control

## 6. Recommended deployment guardrails

For safer use:

- keep privacy-sensitive features disabled unless justified
- document retention periods before deployment
- limit who can access evidence or exported records
- review sample outputs for false positives before publishing findings
- keep calibration files and operating assumptions under version control
- perform local legal and ethics review when cameras cover public spaces

## 7. Public-repository boundary

The open-source repository can document conservative defaults, but it cannot by
itself guarantee lawful or ethical use. Responsible deployment depends on the
organization operating the system, the jurisdiction, and the context of use.
