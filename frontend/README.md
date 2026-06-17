# Scanner Platform Frontend

This new frontend scaffold is a modern React/Next.js trading terminal UI for the existing Python backend.

## Goals

- Premium terminal-style interface for professional traders
- Scalable design for Dashboard, Premarket, Intraday, Swing, Scan Center, Reports, Settings, Watchlist
- Real-time updates, dark/light mode, responsive desktop/tablet/mobile layout
- Reusable component library with atomic design principles
- Backend-safe integration layer using existing API routes

## Installation

```bash
cd frontend
npm install
npm run dev
```

## Architecture

- `src/app` — Next.js app entry and global layout
- `src/components` — Atoms, molecules, organisms, page modules
- `src/lib` — API adapters, real-time services, typed contracts
- `src/state` — Redux slices for shared feature state
- `src/hooks` — reusable data and real-time hooks
- `src/styles` — theme and responsive CSS utilities
- `src/utils` — formatters, error mapping, helper utilities

## Backend Integration

This frontend is designed to consume existing endpoints from `ui/app.py` and backend APIs via:

- `/api/health`
- `/api/scan`
- `/api/scan/start`
- `/api/scan/stop`
- `/api/scan/{scan_id}/status`
- `/api/scans`
- `/api/scans/{scan_id}`
- `/api/history`
- `/api/settings`
- `/api/strategies`
- `/api/market-open-analysis`
- `/api/candlestick`
- `/api/export/watchlist`

A real-time transport layer will be added for market events and scan progress.
