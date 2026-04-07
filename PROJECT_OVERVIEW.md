# Project Overview

## 1. What This Project Is

This repository contains a multilingual translation web application.

The system has two major parts:

- A FastAPI backend that loads a pretrained Hugging Face translation model and exposes API endpoints.
- A React + TypeScript frontend that sends translation requests and displays the result, alternative candidates, and quality diagnostics.

The project is inference-first rather than training-first. It does not train a base model from scratch. Instead, it improves practical output quality by generating multiple candidate translations, scoring them with heuristics, and selecting the best result.

## 2. Supported Languages

The project currently supports six languages:

- English (`en`)
- Hindi (`hi`)
- Kannada (`kn`)
- Tamil (`ta`)
- Malayalam (`ml`)
- Telugu (`te`)

The system supports any-to-any translation between these languages.

## 3. Top-Level Folder Structure

### Repository root

- `README.md` - main usage and deployment guide.
- `docker-compose.yml` - runs backend and frontend together.
- `deploy/` - Nginx config for serving the frontend and proxying API calls.
- `.github/workflows/` - automation for publishing images and deploying the frontend.
- `backend/` - Python API, model loading, translation pipeline, and scoring logic.
- `frontend/` - React application for the user interface.
- `Tentative UG Course Plan - AI Theory_CSS2203.pdf` - course plan reference.
- `Guidelines for IAI Project Work (A3 and A4)_10M.pdf` - assignment guideline reference.

### Runtime and generated folders

- `.venv/` - local Python virtual environment.
- `.hf-cache/` - Hugging Face model cache and downloaded artifacts.
- `.offload/` - model offload directory for memory-constrained inference.
- `backend/logs/` - logs produced by the model download script.

## 4. Backend Structure

The backend is organized as a small FastAPI application with a service layer.

### `backend/app/main.py`

This is the API entrypoint.

It performs these tasks:

- Creates the FastAPI app.
- Configures CORS so the frontend can call the backend.
- Instantiates the translation pipeline once at startup.
- Exposes health, language list, and translation endpoints.

### `backend/app/core/settings.py`

This file holds application settings.

It defines:

- Application name.
- API prefix.
- Model ID.
- Hugging Face cache and offload paths.
- Whether model downloading is enabled.
- Whether safetensors and HF Transfer are used.
- Allowed frontend origins for CORS.

### `backend/app/core/schemas.py`

This file defines the request and response shapes for the API.

Important models:

- `TranslationRequest` - input from the frontend.
- `CandidateScore` - per-candidate quality breakdown.
- `TranslationCandidate` - one candidate translation.
- `TranslationResponse` - the final API response.
- `HealthResponse` - runtime/model health information.

### `backend/app/core/language.py`

This file stores metadata for the supported languages.

It provides:

- Language codes and display labels.
- NLLB-style metadata codes.
- Script identifiers.
- Helper methods for checking support and forming pair labels.

### `backend/app/services/text_processing.py`

This file normalizes input text before translation.

It removes inconsistent whitespace, normalizes line breaks, and adjusts punctuation spacing.

### `backend/app/services/model_adapter.py`

This file is the model wrapper.

It handles:

- Hugging Face token lookup.
- Cache/offload preparation.
- Verification that model artifacts exist locally.
- Loading the pretrained translation model and processor.
- Running generation with different decoding strategies.
- Estimating confidence from generation scores.

The adapter currently uses `google/translategemma-4b-it`.

### `backend/app/services/scoring.py`

This file scores candidate translations.

It evaluates each candidate using:

- punctuation preservation
- protected token preservation
- length similarity
- target script coverage
- tonality similarity
- confidence from generation

The final score is a weighted combination of those signals.

### `backend/app/services/pipeline.py`

This file orchestrates the translation process.

It does the following:

1. Normalizes the input text.
2. Selects a routing profile based on source and target languages.
3. Generates multiple candidates using different decoding strategies.
4. Scores the candidates.
5. Selects the best one.
6. If the score is weak, retries with a stricter generation profile.
7. Returns the selected translation plus all candidate diagnostics.

### `backend/scripts/download_translategemma.py`

This is a build-time utility script.

Its job is to download and verify the model artifacts ahead of runtime so the Docker image can start without a first-run model download.

It also:

- Uses a lock file so only one download runs at a time.
- Logs progress and throughput.
- Downloads metadata and safetensor shards in staged phases.
- Verifies that required files are present at the end.

### Package marker files

- `backend/app/__init__.py`
- `backend/app/core/__init__.py`
- `backend/app/services/__init__.py`

These only mark the directories as Python packages and contain no runtime logic.

## 5. Backend Runtime Flow

The backend translation flow is:

1. The frontend sends text and language codes to `POST /api/translate`.
2. `main.py` forwards the request to the translation pipeline.
3. The pipeline normalizes the text.
4. The model adapter generates multiple outputs using different strategies.
5. The scorer evaluates each output.
6. The selector picks the strongest candidate.
7. The pipeline returns the final translation and diagnostics.

If the input source and target languages are the same, the pipeline returns the original text as an identity result.

## 6. Frontend Structure

The frontend is a React + TypeScript application built with Vite.

### `frontend/src/main.tsx`

This is the React bootstrap file.

It mounts the app into the root DOM node.

### `frontend/src/App.tsx`

This is the main UI and application state file.

It manages:

- theme state
- selected source and target languages
- input text
- translation response data
- backend health data
- loading and error state

It also:

- fetches `/api/health` on load
- sends translation requests to `/api/translate`
- displays the selected candidate, all alternatives, and score breakdowns
- lets the user swap languages
- stores the theme in localStorage

### `frontend/src/App.css`

This file contains the full visual design.

It defines:

- light and dark theme variables
- cards, panels, and layout grids
- form controls and buttons
- status badges
- candidate cards and score breakdown sections
- responsive behavior for desktop and mobile

### `frontend/src/index.css`

This is the global CSS baseline.

It sets:

- the default font stack
- page background
- box sizing
- root sizing rules

## 7. Frontend Runtime Flow

The frontend flow is:

1. Load the page.
2. Fetch backend health information.
3. Let the user pick source and target languages.
4. Let the user enter text.
5. Send the request to the backend.
6. Show the best translation, other candidates, and diagnostic scores.

The UI is intentionally diagnostic rather than minimal, because it exposes why a translation was selected.

## 8. Dependency Stack

### Backend dependencies

From `backend/requirements.txt`:

- `fastapi`
- `uvicorn`
- `pydantic`
- `rapidfuzz`
- `transformers`
- `sentencepiece`
- `torch`
- `huggingface_hub`
- `hf_transfer`
- `safetensors`
- `accelerate`

### Frontend dependencies

From `frontend/package.json`:

- `react`
- `react-dom`
- `vite`
- `typescript`
- `eslint`
- React and TypeScript type packages

Note: the frontend package list includes `nstall`, which appears to be an extra dependency and should probably be reviewed.

## 9. Docker and Deployment

### `backend/Dockerfile`

This image:

- installs Python dependencies
- copies backend code
- runs the model download script during build
- clears the token after preload
- launches the API with uvicorn

### `frontend/Dockerfile`

This image:

- builds the Vite app
- copies the built static files into Nginx
- serves the frontend from Nginx

### `deploy/nginx.conf`

This config:

- serves the SPA
- proxies `/api` requests to the backend container
- supports client-side routing fallback to `index.html`

### `docker-compose.yml`

This file starts both services together:

- backend on port 8000
- frontend on port 5173

It also passes the Hugging Face token into the backend build stage.

### `.github/workflows/`

The repository includes:

- `publish-images-ghcr.yml` - publishes backend and frontend images to GitHub Container Registry.
- `deploy-frontend-vercel.yml` - deploys the frontend to Vercel.

## 10. What The Project Actually Does Well

The strongest implementation features are:

- model-backed multilingual translation
- multiple decoding strategies per request
- heuristic reranking of candidate outputs
- visible diagnostics in the UI
- containerized deployment
- preloaded model artifacts for faster startup

## 11. What The Project Does Not Yet Include

The project does not currently include:

- LoRA fine-tuning
- dataset download or preprocessing code
- model training scripts
- automated BLEU or chrF evaluation scripts
- report generation templates
- course outcome mapping tables

So the repo is a strong inference system, but not yet a full fine-tuning pipeline.

## 12. LLM-Friendly Summary

If another LLM needs to understand the system quickly, the right abstraction is:

- Input: text, source language, target language
- Model: pretrained multilingual translation model
- Generation: multiple decoding strategies
- Scoring: heuristic quality evaluation
- Selection: choose the best-scoring candidate
- UI: show translation and diagnostics
- Deployment: Docker, Compose, Nginx, Vercel, GHCR

## 13. One-Sentence Description

This is a containerized multilingual translation application that uses a pretrained open model plus heuristic reranking to improve practical translation quality and expose the decision process in the UI.

## 14. File-by-File Details

### `README.md`

This is the highest-level human guide for the repo.

It explains:

- what the project does
- how to run the backend
- how to run the frontend
- how Docker-based deployment works
- what the current translation pipeline behavior is
- how the preloaded image strategy avoids a first-run download delay

### `backend/requirements.txt`

This file defines the Python runtime dependencies.

It establishes the project as a FastAPI + Transformers + PyTorch application and includes the libraries required for model loading, caching, and container-friendly deployment.

### `frontend/package.json`

This file defines the frontend package metadata and build scripts.

The important scripts are:

- `dev` - start the Vite development server
- `build` - type-check and create a production build
- `lint` - run ESLint over the frontend source
- `preview` - preview the built app locally

### `docker-compose.yml`

This file is the local orchestration entrypoint.

It defines two services:

- backend service on port 8000
- frontend service on port 5173 mapped to Nginx port 80 in the container

The frontend depends on the backend so the UI is not started independently of the API in the default container setup.

### `.github/workflows/publish-images-ghcr.yml`

This workflow publishes prebuilt images to GitHub Container Registry.

Its purpose is to distribute a runtime image that already contains model artifacts, which reduces startup friction for end users.

### `.github/workflows/deploy-frontend-vercel.yml`

This workflow deploys the frontend to Vercel.

It is useful when the UI is hosted separately from the backend API.

### `deploy/nginx.conf`

This file is the reverse proxy and static hosting config.

It serves the built React app and forwards `/api` requests to the backend container so the browser can use the same origin for the UI and API in containerized deployment.

## 15. API Contract Details

### `GET /api/health`

Returns runtime metadata.

The response includes:

- `status` - overall service state, usually `ok`
- `model_status` - whether the model is loaded, missing, or unavailable
- `mode` - the model mode string
- `safetensors` - whether safetensors loading is enabled
- `hf_transfer` - whether HF Transfer is enabled

Example shape:

```json
{
	"status": "ok",
	"model_status": "loaded google/translategemma-4b-it in mode=translategemma-image-text-to-text on cpu",
	"mode": "translategemma-image-text-to-text",
	"safetensors": true,
	"hf_transfer": true
}
```

### `GET /api/languages`

Returns the supported language list.

Each item includes:

- language code
- human-readable label
- NLLB-style code
- script identifier

### `POST /api/translate`

Accepts a translation request and returns candidate results.

Request example:

```json
{
	"text": "Good morning",
	"source_language": "en",
	"target_language": "ta",
	"max_candidates": 3
}
```

Response example shape:

```json
{
	"source_language": "en",
	"target_language": "ta",
	"pair_label": "English -> Tamil",
	"input_text": "Good morning",
	"selected_candidate": {
		"candidate_id": "cand-faithful-1",
		"strategy": "greedy",
		"text": "...",
		"confidence": 0.91,
		"score": 0.84,
		"breakdown": {
			"punctuation": 1.0,
			"entities": 1.0,
			"length": 0.96,
			"target_script": 0.98,
			"tonality": 0.81,
			"confidence": 0.91,
			"total": 0.84
		},
		"notes": ["Balanced candidate"]
	},
	"candidates": [],
	"model_status": "loaded ...",
	"retry_used": false,
	"diagnostics": {
		"candidate_count": 3,
		"selected_strategy": "greedy",
		"selected_total_score": 0.84,
		"selected_confidence": 0.91
	}
}
```

## 16. Translation Logic in More Detail

The translation pipeline is designed around the idea that a single generation is not always the best output.

Instead of trusting the first model output, the system:

1. Normalizes the input.
2. Chooses a strategy profile based on whether English is involved.
3. Generates several candidates using decoding variants.
4. Scores the candidates with deterministic heuristics.
5. Chooses the best one.
6. If the total score is below the internal threshold, retries with a stricter profile.

This is important because the project’s AI contribution is not only language generation; it is also output selection. That makes the system more reliable in practice, especially when the base model produces inconsistent results.

### Why the retry exists

The retry mechanism is a fallback for weak generations.

If the selected candidate has a total score below 0.58, the pipeline regenerates translations using a stricter strategy profile. This creates a second chance for the model to produce a cleaner output before the final response is returned.

### Why multiple strategies are used

Different decoding methods often produce different tradeoffs:

- greedy decoding is usually fast and stable
- beam search is often more conservative
- sampling can be more varied but less predictable
- strict decoding raises the bar for repetition and output structure

The project uses those differences as a source of candidate diversity.

## 17. Scoring Logic in More Detail

The scorer approximates what a human reviewer would check in a quick translation review.

### Punctuation score

Checks whether punctuation marks from the source are preserved or transformed reasonably.

### Protected token score

Preserves special tokens such as:

- email addresses
- URLs
- handles
- hashtags
- numbers
- uppercase or title-cased tokens

This matters because names and technical tokens should not be translated away accidentally.

### Length score

Ensures the output is not suspiciously short or suspiciously long relative to the source.

### Script score

Measures whether the target language output uses the expected script.

For example:

- Hindi should be mostly Devanagari
- Tamil should be mostly Tamil script
- English should be mostly Latin script

### Tonality score

Looks for surface features such as exclamation marks, question marks, ellipses, uppercase emphasis, emoji, and politeness words.

### Confidence score

Uses model generation statistics to produce a confidence-like number. This is not a calibrated probability; it is a useful internal signal for ranking.

## 18. Frontend Behavior in More Detail

The frontend is not just a form. It is a translation dashboard.

It shows:

- service health status
- model loading status
- source and target language selectors
- a swap button for easy pair reversal
- a text area for input
- a translate button with loading state
- the selected translation result
- the full candidate list
- per-candidate notes
- the numeric score breakdown

This design helps users inspect the behavior of the translation system rather than treating it as a black box.

### Theme behavior

The app supports light and dark mode.

The selected mode is stored in localStorage so the user preference survives page reloads.

### API base URL behavior

If `VITE_API_BASE_URL` is set, the frontend sends requests to that backend host.

If it is not set, it falls back to relative paths, which is useful for local proxy-based setups.

## 19. Container Build Flow

### Backend image

The backend image build does three expensive things once during image construction:

1. installs Python dependencies
2. downloads the model artifacts
3. verifies the local model cache state

That means runtime startup is faster because the heavy download work has already been done.

### Frontend image

The frontend image build is a standard static SPA workflow:

1. install Node dependencies
2. run the Vite production build
3. copy the generated files into Nginx

### Why this matters

This project uses containerization not just for packaging, but for operational reliability.

The model files are large, so preloading them into the image is a practical deployment optimization.

## 20. Project Strengths and Constraints

### Strengths

- clear separation of API, scoring, and UI layers
- any-to-any support across six Indian languages
- visible candidate ranking and diagnostics
- preloaded model strategy for deployment
- Dockerized local and production-style execution

### Constraints

- no LoRA fine-tuning yet
- no training dataset pipeline yet
- no formal metric harness yet
- the project depends on a large pretrained model
- performance may be slower on CPU than on GPU

## 21. If You Want to Defend the Project in Class

The strongest framing is:

"This project is an efficient multilingual translation system built on a pretrained open model. Its contribution is the quality-control layer: multiple candidate generation, heuristic scoring, reranking, and a retry path. That makes translation more reliable without requiring a proprietary API."

If you later add LoRA and public Indian-language data, the story becomes even stronger because then the project includes both adaptation and inference optimization.

## 22. Short Technical Glossary

- **Inference-first** - using a pretrained model to produce outputs without training a new base model.
- **Candidate generation** - producing multiple possible outputs for the same input.
- **Heuristic scoring** - using hand-designed rules to approximate quality.
- **Reranking** - selecting the best output from a set of candidates.
- **Offload** - moving some model state to slower memory or disk to fit execution on limited hardware.
- **safetensors** - a safer and faster model weight format.
- **HF Transfer** - a faster download backend for Hugging Face assets.

