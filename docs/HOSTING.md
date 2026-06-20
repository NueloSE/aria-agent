# Hosting — public dashboard (Vercel UI + Railway API)

The dashboard's data is a SQLite file on Railway's persistent volume (`/data`). The
API must therefore run **on Railway**, next to that file — it can't move to Vercel's
serverless runtime. So:

```
Browser ─▶ Vercel (static React UI) ──/api/* rewrite──▶ Railway (FastAPI + agent loop + DB on /data)
```

- **Railway** runs the agent loop **and** the FastAPI API in one service (they share
  the `/data` volume). The API is exposed publicly and **read-only**.
- **Vercel** hosts only the built React app and proxies `/api/*` to the Railway API,
  so the frontend keeps calling relative `/api` paths — no CORS, no code change.

## Railway (the API + agent)

The service runs [`deploy/railway-start.sh`](../deploy/railway-start.sh) (wired via
[`railway.json`](../railway.json) `startCommand`): it starts `python -m aria.main --loop`
and `uvicorn aria.api:app --host 0.0.0.0 --port $PORT` as siblings, and exits (so Railway
restarts the whole service) if either dies.

One-time setup in the Railway dashboard (service `aria-agent`, production env):

1. **Env var** → Variables → add `DASHBOARD_READONLY=true`.
   (Makes the public API's POST control endpoints return 403; the agent is unaffected.)
2. **Deploy the new code** → Settings → Source → **Check for updates**
   (the auto-deploy webhook is broken — trigger it manually after every push).
3. **Expose it** → Settings → Networking → **Generate Domain** → copy the URL,
   e.g. `https://aria-agent-production-xxxx.up.railway.app`.
4. **Verify**: `curl https://<RAILWAY-DOMAIN>/api/status` returns JSON with
   `"config": { ..., "readonly": true }`, and
   `curl -X POST https://<RAILWAY-DOMAIN>/api/override -d '{"value":"off"}' -H 'Content-Type: application/json'`
   returns **403**.

⚠️ The `/data` volume persists the SQLite DB across redeploys, so the running paper
agent's history survives. The launcher was smoke-tested locally (both processes up,
agent ticks, `/api/status` 200, POSTs 403) before this was wired in.

## Vercel (the UI)

1. Put the Railway domain into [`dashboard/vercel.json`](../dashboard/vercel.json),
   replacing `REPLACE_WITH_RAILWAY_DOMAIN.up.railway.app` with the real host.
2. New Project → import `NueloSE/aria-agent` →
   - **Root Directory:** `dashboard`
   - **Framework Preset:** Vite
   - **Build Command:** `npm run build`   **Output Directory:** `dist`
3. Deploy. Open the Vercel URL → the dashboard loads and shows live data from Railway
   (the `/api/*` rewrite proxies to the Railway domain). The operator controls render
   but are disabled with a "read-only" note.

## Private operator dashboard (unchanged)

The full read/write dashboard (emergency stop, clear-halt, window) stays private and
localhost-only — do **not** expose it. View it over an SSH tunnel to the box running
`uvicorn aria.api:app --host 127.0.0.1 --port 8000` (`DASHBOARD_READONLY` unset), per
[`deploy/aria-dashboard.service`](../deploy/aria-dashboard.service).
