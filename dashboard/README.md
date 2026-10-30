# RUIP Analytics Dashboard

Next.js + Tailwind v4 + shadcn/ui app that visualizes the **offline video-analysis job outputs** of the Road User Intelligence Platform, with a Claude-grounded chat and Web Speech voice Q&A.

Part of the wayfinder effort [**[wayfinder] Offline Analytics Dashboard**](https://github.com/ILMIHA-Labs/Road-User-Intelligence-Platform/issues/12).

## Stack

- **Next.js 16** (App Router, TypeScript, `src/`, alias `@/*` → `src/*`)
- **Tailwind CSS v4** with shadcn/ui tokens (neutral base) in `src/app/globals.css`
- **shadcn/ui** configured in `components.json`, with two registries pre-wired:
  - `@kokonutui` → `https://kokonutui.com/r/{name}.json` (UI components)
  - `@bklit` → `https://ui.bklit.com/r/{name}.json` (charts)
- Chart tokens: categorical `--chart-1…5`, sequential `--chart-scale-01…05` (used by Bklit heatmap/choropleth).

The Google-font dependency from the default scaffold was removed so the app builds without network access to font hosts.

## Prerequisite: allow the registry hosts

The shadcn CLI downloads component source from the registry hosts. In this cloud session they must be allowed in **Network access** (environment settings → Edit):

- `ui.shadcn.com` (base shadcn registry)
- `kokonutui.com` (Kokonut UI)
- `ui.bklit.com` (Bklit charts)

`registry.npmjs.org` is already allowed, so `npm install` works regardless.

## Adding components (after the hosts are allowed)

`components.json` is already set up, so you can add directly — no `shadcn init` needed:

```bash
# Bklit charts (land in components/charts/)
npx shadcn@latest add @bklit/area-chart
npx shadcn@latest add @bklit/bar-chart @bklit/line-chart

# Kokonut UI components
npx shadcn@latest add @kokonutui/<component>

# Base shadcn primitives if needed
npx shadcn@latest add button card tabs
```

If `shadcn add` reports the registry is unconfigured, confirm the `registries` block in `components.json`, or install by full URL:
`npx shadcn@latest add https://ui.bklit.com/r/area-chart.json`.

## Develop

```bash
npm run dev     # http://localhost:3000
npm run build   # production build
```

## Serving & deployment

The dashboard runs as a **Node server** (not a static export) because the chat
proxy (`/api/assistant/chat`) needs a server runtime (#15, #17).

- **Same-origin API.** The browser calls the backend at `/api/v1/*`. In dev,
  `next.config.ts` rewrites that to the Python FastAPI backend (`API_ORIGIN`,
  default `http://localhost:8000`), so there is **no CORS** to configure. The
  dashboard's own `/api/assistant/*` route is matched before the rewrite.
- **Local dev:** run the Python API, then `npm run dev`. Override the backend
  with `API_ORIGIN=http://host:port`.
- **Production:** build with `output: "standalone"` and run `node server.js`
  (see the `Dockerfile`). Put it behind a reverse proxy that routes `/api/v1/*`
  to the backend and everything else to the dashboard.
- **Auth:** none in-app — deploy behind the platform's existing auth / a trusted
  boundary. The Anthropic key stays server-side (`ANTHROPIC_API_KEY`); the
  browser never sees it.

Build and run the container:

```bash
docker build -t ruip-dashboard --build-arg API_ORIGIN=http://backend:8000 .
docker run -p 3000:3000 -e ANTHROPIC_API_KEY=... ruip-dashboard
```

See `.env.example` for all environment variables.

## Where the data comes from

Two interchangeable sources feed one normalized model (see wayfinder ticket #14):
- the live `/api/v1/video-analysis/jobs/{id}` API, and
- imported export files (`summary.json`, the CSV bundle, or a research `.zip`).

Chat uses Anthropic Claude via a server-side proxy (key never in the browser); voice uses the browser Web Speech API (see tickets #15 and #16).
