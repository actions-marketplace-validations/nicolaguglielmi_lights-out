# ADR 0009 — React + Vite + TypeScript, built in a node stage of the backend image, served by FastAPI at `/`; no frontend test framework at M1

- Status: accepted
- Date: 2026-09-14
- Milestone: M1

## Context

Plan §5 requires a React frontend. M2 puts Envoy in front of the app with
two weighted clusters; M8 deploys to Cloud Run, where one container is one
revision. M10 makes a frontend worker read `design/` artefacts. The app must
read in an hour and `./go up` shares a 5-minute pull budget with the whole
L0 plane (ADR 0004). npm facts verified on 2026-09-14.

## Decision

1. **Stack.** `react 19.3.0`, `react-dom`, `vite 8.3.0`,
   `@vitejs/plugin-react 6.1.1`, `typescript 7.0.2` (the native compiler;
   the binary is still `tsc`, `strict` is on by default and `types` defaults
   to `[]`, so `tsconfig.json` lists `vite/client` explicitly). `package.json`
   + committed `package-lock.json`, installed with `npm ci`. Source in
   `app/frontend/src/`: three views, login/signup, meetup list with
   register button, create meetup. Fetches `/api/*` relative, keeps the
   bearer token in memory.
2. **One image, one port.** Stage `frontend` in `app/backend/Containerfile`
   is `FROM docker.io/library/node:24-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553`
   (index updated 2026-09-09, 81 MB per arch); it runs `npm ci`,
   `tsc --noEmit` and `vite build`. The runtime stage copies `dist/` and
   FastAPI mounts `StaticFiles(directory=..., html=True)` at `/` after the
   API routes, so `/api`, `/healthz`, `/metrics` win and everything else is
   the SPA. Envoy and Cloud Run see one upstream.
3. **No vitest at M1.** The type check in the image build is the frontend
   check. The first behavioural frontend test arrives with the first
   frontend ticket (M10 at the latest), written from `design/CONTRACT.md`.
4. **No dev server in compose.** Edit, `./go up` (compose rebuilds the
   changed layer), reload.

## Alternatives rejected

- Separate nginx container: a second image (~50 MB), a second compose
  service, and at M2 either two Envoy routes or an nginx that proxies
  `/api`, doubling the canary wiring for a UI that is three views.
- Frontend built in workbench and bind-mounted into the backend: node is in
  workbench, but the build then depends on the host bind mount and its
  labels, which ADR 0004 defers proving to M2; and Cloud Run needs it in the
  image anyway.
- Committing `dist/`: rots on every edit, and the diff noise hides real
  changes from the review agent.
- `node:24-alpine`: 30 MB smaller, but vite 8's `rolldown` and TS 7 ship
  native binaries and glibc is the path everyone tests. Not worth the risk
  for a build-only stage.
- vitest + jsdom + testing-library at M1: four dev dependencies and a
  config file to test a form; the milestone's acceptance is backend-side.

## Consequences

- The node stage is the single largest cost of `./go up`: node image
  81 MB, plus roughly 100 MB of npm downloads, plus 30–40 s of `npm ci` and
  build. When M2's plane blows the 5-minute budget, the fix is publishing
  the app image by digest with build fallback (same mechanism ADR 0004
  point 3 plans for workbench), not dropping the frontend.
- No frontend test means a broken UI passes `./go test`. Acceptable until
  a frontend ticket exists; the README says it.
- `StaticFiles(html=True)` returns `index.html` for unknown paths, so an
  API typo (`/api/meetup`) gets a 404 from FastAPI only because `/api` is
  matched first. Keep the API prefix; do not add routes outside it.
- TypeScript 7 is two months old; if a template option fails under it, pin
  `typescript 5.9.x` in one commit, nothing else changes.

## Golden-rule check

One extra base image, build-only, no account. Inside budget at M1;
measured and recorded when M1 closes. Passes.
