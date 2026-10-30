<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Kokonut UI

This project installs components from Kokonut UI, a shadcn/ui registry.
The registry is set in components.json as "@kokonutui".

- Before building an animated or interactive component from scratch, check
  Kokonut UI: https://kokonutui.com/llms.txt lists every component with a
  one-line description.
- Install with the shadcn CLI, never by pasting code:
  npx shadcn@latest add @kokonutui/<name>
  It writes components/kokonutui/<name>.tsx and installs its dependencies.
- Installed components are project code. Edit them in place rather than
  wrapping them.
- Any docs page is available as Markdown, with the full source, by adding
  .md to its URL, e.g. https://kokonutui.com/docs/buttons/particle-button.md

# Bklit UI (charts)

This project installs charts from Bklit UI, a shadcn/ui registry.
The registry is set in components.json as "@bklit" (https://bklit.com/r/{name}.json).

- Install with the shadcn CLI: npx shadcn@latest add @bklit/<name>
  Chart files land in components/charts/. After installing, read the
  installed source to confirm props — you own that code.
- Series colors come from --chart-1..5; sequential scales (heatmap /
  choropleth) from --chart-scale-01..05. Both are defined in globals.css.
- Compose: root chart → Grid → series → axes → overlays → ChartTooltip.
