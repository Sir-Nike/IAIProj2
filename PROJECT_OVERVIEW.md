# Project Overview

This document is written as a technical handoff for LLMs. It explains the current implementation in terms of real code flow, object responsibilities, and the data contracts between files.

If you want a short reading order:

1. Read [1. System Summary](#1-system-summary).
2. Read [2. End-to-End Request Flow](#2-end-to-end-request-flow).
3. Read [3. Backend Internals](#3-backend-internals).
4. Read [4. Heuristic Scoring Model](#4-heuristic-scoring-model).
5. Read [5. Frontend Internals](#5-frontend-internals).
6. Read [6. Single-Command Launcher](#6-single-command-launcher).

## 1. System Summary

This repository is a multilingual translation application with two runtime layers:

- A FastAPI backend that loads `google/translategemma-4b-it`, generates several candidate translations, scores them, and returns the best result plus diagnostics.
- A React + TypeScript frontend that collects user input, sends translation requests, renders the candidate outputs, and lets the user click a candidate to inspect its heuristic breakdown.

The project is inference-first. It does not train a translation model. It uses candidate generation plus heuristic reranking to choose a result that is more likely to be usable.

The system currently supports these languages:

- `en` - English
- `hi` - Hindi
- `kn` - Kannada
- `ta` - Tamil
- `ml` - Malayalam
- `te` - Telugu

## 2. End-to-End Request Flow

The current runtime path is:

1. The user types text in the frontend.
2. The frontend sends a POST request to `/api/translate`.
3. The backend validates the request with Pydantic.
4. The translation pipeline normalizes input text.
5. The pipeline selects a routing profile for the language pair.
6. The model adapter generates multiple candidate translations using different decoding strategies.
7. The heuristic scorer scores each candidate on semantic quality and preservation signals.
8. The candidate with the best total score is selected.
9. If the best score is too weak, the pipeline retries with a stricter generation profile.
10. The backend returns the selected translation, all candidates, and per-candidate breakdowns.
11. The frontend highlights the best output and shows the heuristic breakdown when the user clicks any output card.

The important design detail is that the UI now shows only two things:

- input controls
- generated outputs

## 3. Backend Internals

### 3.1 API entrypoint: `backend/app/main.py`

This file creates the FastAPI app, registers CORS, instantiates the pipeline once, and exposes the API endpoints.

```python
app = FastAPI(title=settings.app_name)

app.add_middleware(
	CORSMiddleware,
	allow_origins=list(settings.cors_origins),
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

pipeline = TranslationPipeline()
registry = LanguageRegistry()
```

What this means:

- The app title comes from settings.
- CORS is permissive only for the configured frontend origins.
- `TranslationPipeline()` is created once and reused for all requests.
- `LanguageRegistry()` is also created once and used for language metadata and pair labels.

The health route returns model/runtime status:

```python
@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
	return HealthResponse(
		status="ok",
		model_status=pipeline.adapter.status,
		mode=pipeline.adapter.mode,
		safetensors=settings.use_safetensors,
		hf_transfer=settings.use_hf_transfer,
	)
```

This endpoint is useful for both the UI and deployment checks. It does not generate translations; it only reports whether the model adapter has a valid status string.

The translation endpoint is a thin wrapper around the pipeline:

```python
@app.post("/api/translate", response_model=TranslationResponse)
def translate(request: TranslationRequest) -> TranslationResponse:
	try:
		return pipeline.translate(request)
	except KeyError as exc:
		raise HTTPException(status_code=400, detail=str(exc)) from exc
	except RuntimeError as exc:
		raise HTTPException(status_code=503, detail=str(exc)) from exc
```

This endpoint does not itself translate text. It delegates all decision-making to the pipeline and only converts expected failures into HTTP responses.

### 3.2 Runtime settings: `backend/app/core/settings.py`

The settings object centralizes model, cache, and feature flags.

```python
@dataclass(frozen=True)
class AppSettings:
	app_name: str = "Indian Multilingual Translation API"
	api_prefix: str = "/api"
	enable_model_download: bool = True
	model_mode: str = "translategemma-image-text-to-text"
	model_id: str = "google/translategemma-4b-it"
	use_safetensors: bool = True
	use_hf_transfer: bool = True
	require_local_model_files: bool = True
	enable_semantic_similarity: bool = True
	semantic_model_id: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
	enable_model_tonality: bool = True
	tonality_model_id: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
	hf_token_env_var: str = "HF_TOKEN"
	hf_cache_dir: str = str(Path(__file__).resolve().parents[3] / ".hf-cache")
	offload_dir: str = str(Path(__file__).resolve().parents[3] / ".offload")
	max_input_chars: int = 5000
	cors_origins: tuple[str, ...] = (
		"http://localhost:5173",
		"http://127.0.0.1:5173",
	)
```

The important part here is that the backend has three model-level systems:

- the translation model (`model_id`)
- the semantic scorer (`semantic_model_id`)
- the tonality model (`tonality_model_id`)

### 3.3 Schema definitions: `backend/app/core/schemas.py`

These are the exact API contracts.

```python
class TranslationRequest(BaseModel):
	text: str = Field(min_length=1, max_length=5000)
	source_language: str = Field(pattern="^(en|hi|kn|ta|ml|te)$")
	target_language: str = Field(pattern="^(en|hi|kn|ta|ml|te)$")
	max_candidates: int = Field(default=3, ge=1, le=5)
```

The request validation does three things:

- ensures the text is not empty
- limits the length to 5000 characters
- restricts language codes to the supported set
- restricts candidate count to 1 through 5

The score breakdown is now model-centric and no longer includes punctuation:

```python
class CandidateScore(BaseModel):
	entities: float
	length: float
	target_script: float
	tonality: float
	semantic: float
	fluency: float
	confidence: float
	total: float
```

That means the UI and API now focus on higher-signal metrics rather than punctuation drift.

The translation response contains both the selected candidate and all candidates:

```python
class TranslationResponse(BaseModel):
	source_language: str
	target_language: str
	pair_label: str
	input_text: str
	selected_candidate: TranslationCandidate
	candidates: list[TranslationCandidate]
	model_status: str
	retry_used: bool
	diagnostics: dict[str, Any]
```

### 3.4 Translation pipeline: `backend/app/services/pipeline.py`

This file decides what to generate, how to rank it, and when to retry.

The routing layer is extremely small:

```python
class LanguagePairRouter:
	def route(self, source_language: str, target_language: str) -> PairRouting:
		if source_language == "en" or target_language == "en":
			return PairRouting(prompt_profile="faithful", retry_profile="strict")
		return PairRouting(prompt_profile="balanced", retry_profile="strict")
```

This means English-involved pairs are treated as more literal, while non-English pairs use the balanced prompt profile.

The translate method is the top-level orchestration:

```python
def translate(self, request: TranslationRequest) -> TranslationResponse:
	if request.source_language == request.target_language:
		candidate = self._make_identity_candidate(request.text)
		return self._build_response(request, [candidate], candidate, retry_used=False)

	normalized = self.preprocessor.normalize(request.text)
	routing = self.router.route(request.source_language, request.target_language)
	candidates = self._generate_candidates(
		normalized,
		request.source_language,
		request.target_language,
		routing.prompt_profile,
		request.max_candidates,
	)
	selected = self.selector.select(candidates)

	retry_used = False
	if selected.score.total < 0.58:
		retry_used = True
		retry_candidates = self._generate_candidates(
			normalized,
			request.source_language,
			request.target_language,
			routing.retry_profile,
			request.max_candidates,
		)
		candidates.extend(retry_candidates)
		selected = self.selector.select(candidates)

	return self._build_response(request, candidates, selected, retry_used)
```

That function does all of the following:

- short-circuits same-language requests as identity results
- normalizes input text before translation
- generates candidates with the main profile
- selects the best candidate using total score
- retries with a stricter profile if the score is too weak
- returns the whole response object with diagnostics

Candidate generation is strategy-based:

```python
strategy_map = {
	"faithful": ["greedy", "beam", "sample"],
	"balanced": ["beam", "greedy", "sample"],
	"strict": ["strict", "beam", "greedy"],
}
```

This matters because the backend is not relying on one decoding mode. It intentionally asks the model to produce several outputs so the heuristic layer can choose the best one.

Each candidate is scored immediately after generation:

```python
translated, confidence = self.adapter.translate(text, source_language, target_language, strategy)
score = self.scorer.score(text, translated, source_language, target_language, confidence)
notes = self._build_notes(score, confidence)
```

The notes are only diagnostic labels. They are not used for ranking:

```python
if score.entities < 0.5:
	notes.append("Entity handling needs improvement")
if score.tonality < 0.5:
	notes.append("Tone alignment is low")
if score.semantic < 0.5:
	notes.append("Semantic alignment is low")
if score.fluency < 0.5:
	notes.append("Fluency degradation detected")
if score.target_script < 0.5:
	notes.append("Target script coverage is low")
```

The selected response is assembled in `_build_response`:

```python
candidate_models = [
	TranslationCandidate(
		candidate_id=item.candidate_id,
		strategy=item.strategy,
		text=item.text,
		confidence=item.confidence,
		score=item.score.total,
		breakdown=item.score,
		notes=item.notes,
	)
	for item in candidates
]
```

That means the API returns one object for each generated candidate, not just the winner.

### 3.5 Model adapter: `backend/app/services/model_adapter.py`

The model adapter is the only layer that talks directly to Hugging Face Transformers.

Its responsibilities are:

- resolve the HF token
- prepare cache/offload directories
- check for local artifacts
- load the model/processor bundle
- generate text with different strategies
- estimate confidence from output token scores

The core loader flow is:

```python
def _load_model(self) -> Any:
	if self._model_bundle is not None:
		return self._model_bundle

	self._prepare_hf_runtime()
	model_id = settings.model_id
	if not settings.enable_model_download:
		self._status = (
			f"download disabled; model unavailable "
			f"(mode={settings.model_mode}, model={model_id})"
		)
		return None

	if settings.require_local_model_files and not self._has_local_artifacts(model_id):
		self._status = (
			f"model artifacts not ready locally for {model_id}; "
			"cannot run translation until artifacts are present"
		)
		return None

	try:
		if settings.model_mode == "translategemma-image-text-to-text":
			self._model_bundle = self._load_translategemma_bundle(model_id)
			return self._model_bundle
		raise ValueError(f"Unsupported model mode: {settings.model_mode}")
	except Exception as exc:
		self._status = (
			f"model load failure "
			f"(mode={settings.model_mode}, error={exc.__class__.__name__}: {exc})"
		)
		return None
```

The actual generation logic varies by strategy:

```python
generation_args: dict[str, Any] = {
	"max_new_tokens": 256,
	"return_dict_in_generate": True,
	"output_scores": True,
}
if strategy == "beam":
	generation_args.update({"num_beams": 3, "repetition_penalty": 1.08})
elif strategy == "sample":
	generation_args.update({"do_sample": True, "top_p": 0.92, "temperature": 0.75})
elif strategy == "strict":
	generation_args.update({"num_beams": 4, "length_penalty": 1.0, "repetition_penalty": 1.1})
else:
	generation_args.update({"num_beams": 1})
```

This is why the backend can produce several candidate outputs with meaningfully different behavior.

Confidence is estimated from the model’s generated token distributions:

```python
def _estimate_confidence(self, scores: list[Any]) -> float:
	try:
		import torch

		if not scores:
			return 0.5
		confidences: list[float] = []
		for step_scores in scores:
			probabilities = torch.softmax(step_scores[0], dim=-1)
			confidences.append(float(probabilities.max().item()))
		return max(0.05, min(0.98, sum(confidences) / len(confidences)))
	except Exception:
		return 0.5
```

That confidence value is not a semantic guarantee. It is just a generation-level proxy used as one input to ranking.

## 4. Heuristic Scoring Model

This is the most important file for understanding why a candidate wins.

### 4.1 The scorer classes

The scoring module now has three major pieces:

- `SemanticSimilarityScorer`
- `TonalityModelScorer`
- `HeuristicScorer`

`SemanticSimilarityScorer` uses a multilingual embedding model:

```python
tokenizer = AutoTokenizer.from_pretrained(
	settings.semantic_model_id,
	cache_dir=settings.hf_cache_dir,
)
model = AutoModel.from_pretrained(
	settings.semantic_model_id,
	cache_dir=settings.hf_cache_dir,
)
```

The text is encoded, pooled, L2-normalized, and then compared by dot product.

`TonalityModelScorer` uses a sentiment model instead of a word-list heuristic:

```python
tokenizer = AutoTokenizer.from_pretrained(
	settings.tonality_model_id,
	cache_dir=settings.hf_cache_dir,
	use_fast=False,
)
model = AutoModelForSequenceClassification.from_pretrained(
	settings.tonality_model_id,
	cache_dir=settings.hf_cache_dir,
)
```

The slow tokenizer path is intentional because the environment previously hit a protobuf dependency issue with the fast tokenizer path.

### 4.2 What the final score means

The current score is a weighted sum over seven features:

```python
weighted_features = {
	"entities": entities,
	"length": length,
	"target_script": target_script,
	"tonality": tonality,
	"semantic": semantic,
	"fluency": fluency,
	"confidence": confidence_score,
}
total = round(
	sum(self._weights[key] * weighted_features[key] for key in self._weights),
	4,
)
```

Current weights:

```python
self._weights = {
	"entities": 0.20,
	"length": 0.08,
	"target_script": 0.17,
	"tonality": 0.15,
	"semantic": 0.27,
	"fluency": 0.09,
	"confidence": 0.04,
}
```

Interpretation:

- `semantic` gets the largest weight because meaning preservation is the strongest signal.
- `entities` matters because names, URLs, numbers, and handles should not be lost.
- `target_script` matters because output should be in the expected writing system.
- `tonality` matters because the output should preserve sentiment or tone.
- `fluency` catches repetition and noisy outputs.
- `confidence` is the weakest signal because model confidence alone is not enough to rank translations.

### 4.3 Why punctuation is not part of the score anymore

Earlier versions had a punctuation metric. That was removed because it was too surface-level and not useful enough compared with semantic and fluency signals.

That is why `CandidateScore` no longer includes punctuation.

### 4.4 Entity handling

The entity score combines two ideas:

- strict entity preservation for emails, URLs, handles, hashtags, and numbers
- fuzzy preservation for capitalized names and title-like tokens

The key logic is:

```python
strict_entities = self._extract_strict_entities(source_text)
named_entities = self._extract_named_entities(source_text)

strict_score = self._preservation_ratio(strict_entities, candidate_text, use_fuzzy=False)
named_score = self._preservation_ratio(named_entities, candidate_text, use_fuzzy=True)
```

This is more useful than checking only exact string matches because translations may transliterate names or slightly reshape tokens.

### 4.5 Fluency scoring

The fluency score is a lightweight noise detector.

```python
tokens = re.findall(r"\w+", candidate_text, flags=re.UNICODE)
unique_ratio = len(set(lowered)) / len(lowered)
consecutive_repeats = sum(1 for index in range(1, len(lowered)) if lowered[index] == lowered[index - 1])
stretched_chars = len(re.findall(r"(.)\1{3,}", candidate_text))
punct_bursts = len(re.findall(r"[!?.,]{3,}", candidate_text))
```

This catches outputs that look repetitive, noisy, or collapsed.

### 4.6 The score output contract

The final schema returned by the scorer is now:

```python
class CandidateScore(BaseModel):
	entities: float
	length: float
	target_script: float
	tonality: float
	semantic: float
	fluency: float
	confidence: float
	total: float
```

So when the frontend clicks a candidate, this is the breakdown it can show.

## 5. Frontend Internals

The frontend has been simplified into two visual regions:

- input panel
- output panel

### 5.1 UI state in `frontend/src/App.tsx`

Core state:

```tsx
const [sourceLanguage, setSourceLanguage] = useState<LanguageCode>('en')
const [targetLanguage, setTargetLanguage] = useState<LanguageCode>('hi')
const [text, setText] = useState(sampleText)
const [response, setResponse] = useState<TranslationResponse | null>(null)
const [activeCandidateId, setActiveCandidateId] = useState<string | null>(null)
const [loading, setLoading] = useState(false)
const [error, setError] = useState<string | null>(null)
```

This means the component directly owns the translation inputs, the result payload, and the currently inspected candidate.

### 5.2 Sending a translation request

```tsx
const translateText = async () => {
  setLoading(true)
  setError(null)

  try {
	const response = await fetch(apiUrl('/api/translate'), {
	  method: 'POST',
	  headers: {
		'Content-Type': 'application/json',
	  },
	  body: JSON.stringify({
		text,
		source_language: sourceLanguage,
		target_language: targetLanguage,
		max_candidates: 3,
	  }),
	})

	if (!response.ok) {
	  const payload = (await response.json().catch(() => null)) as { detail?: string } | null
	  throw new Error(payload?.detail ?? 'Translation request failed')
	}

	const data = (await response.json()) as TranslationResponse
	setResponse(data)
	setActiveCandidateId(data.selected_candidate.candidate_id)
  } catch (err) {
	setError(err instanceof Error ? err.message : 'Something went wrong')
  } finally {
	setLoading(false)
  }
}
```

This is the only place the frontend talks to the backend for translation.

### 5.3 Highlighting the best output

The best output is the backend-selected candidate:

```tsx
const isBest = candidate.candidate_id === response.selected_candidate.candidate_id
```

The output card gets a special class when it is the winner:

```tsx
className={['candidate-card', isBest ? 'best' : '', isActive ? 'active' : ''].filter(Boolean).join(' ')}
```

Meaning:

- `best` = selected by backend score
- `active` = clicked by the user

The UI intentionally separates these concepts.

### 5.4 Clicking a candidate to inspect the breakdown

```tsx
<button
  key={candidate.candidate_id}
  type="button"
  className={className}
  onClick={() => setActiveCandidateId(candidate.candidate_id)}
>
```

That click does not re-run inference. It only changes which existing candidate is being inspected in the breakdown panel.

The active candidate is derived with `useMemo`:

```tsx
const activeCandidate = useMemo(() => {
  if (!response) {
	return null
  }
  const fallback = response.selected_candidate
  if (!activeCandidateId) {
	return fallback
  }
  return response.candidates.find((candidate) => candidate.candidate_id === activeCandidateId) ?? fallback
}, [response, activeCandidateId])
```

So the breakdown panel always shows a candidate from the current response, falling back to the best-scoring candidate if needed.

### 5.5 What the frontend now shows

The page no longer tries to show extra meta cards or backend health text. It shows only:

- language selection
- input text box
- generate button
- candidate cards
- clickable heuristic breakdown

This matches your request to keep the page focused on input and outputs.

## 6. Single-Command Launcher

The launcher script is `run-website.ps1`.

```powershell
Import-EnvFile (Join-Path $projectRoot '.env.local')
Import-EnvFile (Join-Path $projectRoot '.env')

$backendConnection = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
$frontendConnection = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -First 1
```

What it does:

- loads local environment variables into the current process
- checks whether backend and frontend are already running
- starts only what is missing
- opens the website in the browser

The backend start command is:

```powershell
& .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

The frontend start command is:

```powershell
& 'npm.cmd' run dev -- --host 127.0.0.1 --port 5173
```

The browser open step is:

```powershell
Start-Process $siteUrl
```

So the expected user command is:

```powershell
.\run-website.ps1
```

## 7. Weight Tuning Script

`backend/scripts/tune_heuristic_weights.py` is an offline calibration tool for score weights.

The script works in two phases:

1. call the live API once per sample case and collect candidate breakdowns
2. score those same breakdowns with many random weight vectors without re-running translation

That is why it is safe to test many values quickly after the candidate set has been collected.

The script compares each candidate weight vector against an oracle utility function that emphasizes semantic quality more strongly than the current ranker.

This is important because it lets you tune weights against a repeatable local objective instead of guessing.

## 8. What To Tell Another LLM About This Project

If you need to hand this project to another model, the important facts are:

- The backend is a FastAPI inference service.
- The translation model is `google/translategemma-4b-it`.
- The system generates multiple candidates per request.
- A heuristic scorer ranks candidates using entities, length, target script, tonality, semantic similarity, fluency, and confidence.
- Punctuation drift was removed from the score.
- Tonality is model-based, not word-list based.
- The frontend is now intentionally minimal: input on one side, outputs on the other.
- The best output is highlighted, and clicking any output shows its breakdown.

## 9. File Map

### Backend

- [backend/app/main.py](backend/app/main.py)
- [backend/app/core/settings.py](backend/app/core/settings.py)
- [backend/app/core/schemas.py](backend/app/core/schemas.py)
- [backend/app/services/model_adapter.py](backend/app/services/model_adapter.py)
- [backend/app/services/pipeline.py](backend/app/services/pipeline.py)
- [backend/app/services/scoring.py](backend/app/services/scoring.py)
- [backend/scripts/tune_heuristic_weights.py](backend/scripts/tune_heuristic_weights.py)

### Frontend

- [frontend/src/App.tsx](frontend/src/App.tsx)
- [frontend/src/App.css](frontend/src/App.css)
- [frontend/src/main.tsx](frontend/src/main.tsx)

### Launcher and deployment

- [run-website.ps1](run-website.ps1)
- [docker-compose.yml](docker-compose.yml)
- [README.md](README.md)

## 10. Current Implementation Status

The current codebase is set up so that:

- the website can be launched from one command
- the backend loads local model artifacts when available
- the frontend shows only the essential translation workflow
- the heuristic explanation is visible only when a candidate is selected

That is the current behavior of the repository as of this overview.
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

