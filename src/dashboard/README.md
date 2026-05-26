# Dashboard Structure

This folder is organized into three parts:

- `app/`
  The live dashboard served by the backend at `/dashboard/`.

- `templates/`
  Static source templates grouped by screen type:
  - `analytics/`
  - `cameras/`
  - `violations/`
  - `settings/`

- `docs/`
  Design notes and visual direction for the dashboard system.

Current live entrypoint:

- `app/index.html`

Primary design reference:

- `docs/DESIGN.md`

## Fleet configuration view

The configuration surface is designed to remain responsive for large camera
registries. It requests bounded pages of effective profiles, supports indexed
camera ID or location-prefix search, and shows fleet totals separately from the
profiles currently rendered. The live dashboard stream likewise carries only a
small preview window of configured feeds.

`config/cameras.yaml` remains the authoritative runtime configuration for the
current agents. The backend mirrors those profiles into its indexed
configuration registry for efficient frontend browsing.
