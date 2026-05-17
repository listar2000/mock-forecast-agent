# Mock forecast agent

Minimal FastAPI agent that returns a valid (but fake) probability
distribution. Useful for end-to-end testing the Prophet Hacks
`/submit-endpoint` form's optional health + forecast checks against
something other than `localhost`.

No LLM, no API keys, no external calls. Outputs are deterministic for
a given event so re-running the forecast check produces the same
numbers.

## Run locally

```bash
pip install -r requirements.txt
python example_agent.py
```

Hits:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"event_ticker":"x","market_ticker":"x","title":"t",
       "category":"c","close_time":"2026-06-30T23:59:59Z",
       "outcomes":["A","B","C","D"]}'
```

## Python version

This project pins Python via `.python-version` to **3.12.7**. Render
defaults to the newest Python release (3.14 as of writing), which has
no pre-built wheels for `pydantic-core==2.23.4` — pip then tries to
build from Rust source and fails on Render's read-only cargo cache.
Keeping the pin avoids that whole detour.

## Deploy to Render (free Web Service)

1. Initialize this directory as its own git repo and push to GitHub:

   ```bash
   cd tmp/mock-agent
   git init
   git add .
   git commit -m "Mock forecast agent"
   gh repo create mock-forecast-agent --public --source=. --push
   ```

2. In the Render dashboard: **New +** → **Web Service** → connect that
   repo.

3. Settings:

   - **Runtime**: Python 3
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn example_agent:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
   - **Region**: anywhere; doesn't matter for testing.

4. Hit Deploy. After ~1 minute Render gives you a public URL like
   `https://mock-forecast-agent.onrender.com`.

5. Test it:

   - Open the Prophet Hacks `/submit-endpoint` page.
   - Enter your (email, name).
   - Endpoint URL: `https://mock-forecast-agent.onrender.com/predict`
   - Click **Run health check** with path `/health` → expect green OK.
   - Click **Run forecast check** → expect green OK with sum 1.0.

### Free-tier caveat

Render's free Web Services spin down after ~15 minutes of inactivity.
The first request after a spin-down can take 30–60 seconds (cold
boot). Our forecast-check route times out at 25s, so if you hit a cold
boot the first attempt will fail — just hit it twice. The health-check
route times out at 8s, so for the first wake-up either bump the
timeout in `src/app/api/test-endpoint/health/route.ts` or run the
forecast check first to warm the dyno.
