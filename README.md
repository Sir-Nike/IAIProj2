# Indian Multilingual Translation Project

FastAPI + React translation system for six languages:

- English (`en`)
- Hindi (`hi`)
- Kannada (`kn`)
- Tamil (`ta`)
- Malayalam (`ml`)
- Telugu (`te`)

The backend uses `google/translategemma-4b-it` directly for inference. Glossary-based translation fallback has been removed.

## Current Status

- Model download complete (safetensors shards present)
- Backend loads TranslateGemma successfully
- Frontend connected to backend
- All directed pairs validated: `30/30` passed

## Project Structure

- `backend/`: FastAPI service and translation pipeline
- `frontend/`: React + Vite UI

## UI

- Minimalist interface with light/dark mode toggle
- Clear source/target controls and candidate diagnostics
- Works on desktop and mobile layouts

## Run Backend

From repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health -Method Get
```

Expected key signal in `model_status`:

- `loaded google/translategemma-4b-it in mode=translategemma-image-text-to-text ...`

## Run Frontend

If `node` is already on PATH:

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

If Node is installed but not on PATH:

```powershell
$env:Path = 'C:\Program Files\nodejs;' + $env:Path
cd frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

Open:

- `http://127.0.0.1:5173`

## Run Website In One Command

From repository root:

```powershell
.\run-website.ps1
```

What it does:

1. Loads `.env.local` (and `.env` if present) into the current process.
2. Starts backend on `127.0.0.1:8000` if not already running.
3. Starts frontend on `127.0.0.1:5173` if not already running.
4. Opens `http://127.0.0.1:5173` in your browser.

## Deployment Without First-Run Model Download

This repository now includes container deployment that preloads model weights at image build time.

Files added:

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `deploy/nginx.conf`
- `docker-compose.yml`
- `.dockerignore`

### Build and Run (Local Docker)

Prerequisites:

1. Docker Desktop running
2. Access token accepted for `google/translategemma-4b-it`

PowerShell:

```powershell
$env:HF_TOKEN = "your_hf_token_here"
docker compose build
docker compose up -d
```

Open:

- Frontend: `http://localhost:5173`
- Backend health: `http://localhost:8000/api/health`

### Publish Preloaded Image (Example: GHCR)

This is the practical replacement for "pushing model weights to GitHub repo". Instead of committing multi-GB shards to Git, publish a preloaded container image.

```powershell
# Login to GHCR
echo $env:GITHUB_TOKEN | docker login ghcr.io -u <github-username> --password-stdin

# Build backend image with model included
$env:HF_TOKEN = "your_hf_token_here"
docker build -f backend/Dockerfile -t ghcr.io/<owner>/iai-translation-backend:latest --build-arg HF_TOKEN=$env:HF_TOKEN .

# Build frontend image
docker build -f frontend/Dockerfile -t ghcr.io/<owner>/iai-translation-frontend:latest .

# Push
docker push ghcr.io/<owner>/iai-translation-backend:latest
docker push ghcr.io/<owner>/iai-translation-frontend:latest
```

Users can then run your images directly, with no first-run model download delay.

### Automated GHCR Publishing (GitHub Actions)

Workflow file:

- `.github/workflows/publish-images-ghcr.yml`

Triggers:

1. Manual dispatch
2. Push tag matching `v*`

Required repository secret:

1. `HF_TOKEN` (must have access to `google/translategemma-4b-it`)

Result:

1. Publishes backend and frontend images to GHCR as `latest` and tag-versioned images.

## Vercel Website Setup

This project deploys the frontend to Vercel and points API calls to your backend URL.

Files added:

1. `.github/workflows/deploy-frontend-vercel.yml`
2. `frontend/vercel.json`
3. `frontend/.env.example`

### One-time Vercel Project Setup

1. Import this GitHub repository into Vercel.
2. Set Root Directory to `frontend`.
3. Add environment variable `VITE_API_BASE_URL` to your deployed backend URL (for example, `https://your-backend-domain.com`).

### Required GitHub Secrets for Auto-Deploy Workflow

1. `VERCEL_TOKEN`
2. `VERCEL_ORG_ID`
3. `VERCEL_PROJECT_ID`
4. `VITE_API_BASE_URL`

After these are set, pushes to `master` that affect `frontend/**` will auto-deploy the site to Vercel.

## API Endpoints

- `GET /api/health`
- `GET /api/languages`
- `POST /api/translate`

Example translate request:

```json
{
	"text": "Good morning",
	"source_language": "en",
	"target_language": "ta",
	"max_candidates": 3
}
```

## Translation Pipeline Behavior

- Generates multiple candidates using decoding strategies (`greedy`, `beam`, `sample`, `strict`)
- Scores candidates using:
	- punctuation consistency
	- protected token preservation (emails/URLs/handles/numbers/title-cased tokens)
	- length consistency
	- target-script coverage
	- confidence estimate
- Selects highest-scoring candidate
- Uses retry with stricter profile when score is weak

## Pair Validation Summary

Validated in this workspace run:

- `total_pairs=30`
- `ok_pairs=30`
- `loaded_pairs=30`
- `failures=none`

## Notes

- The model currently runs on CPU in this environment; GPU will improve latency significantly.
- Terminal output may show garbled Indic characters due console encoding. API/UI output remains valid Unicode.

## Future Steps

1. Add GPU deployment profile with automatic `torch_dtype` and memory-aware generation settings.
2. Add server-side caching for repeated source-target pairs to reduce latency.
3. Add automated regression suite that runs all directed language pairs on every release.
4. Add translation quality dashboards (BLEU/chrF + human review snapshots).
5. Add CI workflow to build/publish preloaded images to GHCR on tagged releases.

## Model Weights and GitHub

The current model shards are very large. Pushing them directly into a normal GitHub repo is not practical due platform limits.

- Normal GitHub Git storage limit per file: 100 MB (hard block)
- Git LFS also has per-file and quota constraints, and these shards are multi-GB

Practical no-wait distribution options are:

1. Publish a prebuilt runtime image (container/VM) that already contains model weights.
2. Host weights on Hugging Face (current source of truth) and mirror to fast object storage/CDN near users.
3. Split and package model shards into release assets with reassembly step (more operational overhead).

If you want, the next pass can implement option 1 with a deployment image so users run immediately without a separate model download step.
