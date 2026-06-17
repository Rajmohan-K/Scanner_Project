Running the frontend with Docker

1. Build and start the container (requires Docker installed):

```bash
cd frontend
docker compose up --build
```

2. Open the app at http://localhost:3000

Notes:
- The container exposes port `3000` and sets `NEXT_PUBLIC_API_BASE_URL` to point at `host.docker.internal:5000` so the frontend can talk to a locally running Python backend on port 5000.
- If your backend runs elsewhere, override the env var in `docker-compose.yml`.
