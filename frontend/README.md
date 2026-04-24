# RiskLens Frontend (Cloudflare Pages)

This folder is the separated frontend app for the RiskLens project.

## Stack

- React + TypeScript + Vite
- Tailwind CSS (keeps the original Streamlit visual structure)
- React Router (SPA routes)
- API client wrapper for Railway backend

## Run locally

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## Build

```bash
npm run build
```

Build output is in `frontend/dist`.

## Cloudflare Pages settings

- Framework preset: `Vite`
- Build command: `npm run build`
- Build output directory: `dist`
- Root directory: `frontend`

## Environment variables (Cloudflare Pages)

- `VITE_API_BASE_URL`: your Railway backend URL
- `VITE_REQUEST_TIMEOUT_MS`: optional request timeout in ms

Example:

```env
VITE_API_BASE_URL=https://api.yourdomain.com
VITE_REQUEST_TIMEOUT_MS=30000
```

## Current API wrappers

- `GET /health`
- `GET /records`
- `POST /upload`
- `POST /compare`

All API request logic is centralized in:

- `src/services/http.ts`
- `src/services/risklensApi.ts`

You can continue adding endpoints there without changing page-level request patterns.
