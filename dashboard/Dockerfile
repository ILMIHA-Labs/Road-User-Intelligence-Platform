# Multi-stage build for the dashboard, using Next.js standalone output.
# Runs as a Node server (node server.js) — the chat proxy needs a server runtime.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Build-time config baked into the app. Override with --build-arg as needed.
ARG API_ORIGIN=http://localhost:8000
ARG NEXT_PUBLIC_API_BASE_URL=/api/v1
ENV API_ORIGIN=$API_ORIGIN \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
# ANTHROPIC_API_KEY (and optionally ASSISTANT_MODEL) are provided at runtime.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
