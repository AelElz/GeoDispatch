# GeoDispatch frontend preview

This directory is a standalone copy of the GeoDispatch dashboard frontend for
static hosting and visual review. It contains no supervisor, AI agent, CAMARA
service, database, or Docker configuration.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. The interface can run its clearly labelled
in-browser simulation without a backend. Backend-connected features remain
offline unless `VITE_WS_URL` points to a public GeoDispatch supervisor.

## Deploy to Vercel

Import the repository and use these settings:

- Root Directory: `preview`
- Framework Preset: `Vite`
- Build Command: `npm run build`
- Output Directory: `dist`

No environment variables are required for the frontend-only preview.

The complete runnable stack remains in the repository root. People who clone
the repository can run it with `make` and are not expected to use this preview
directory for the backend.
