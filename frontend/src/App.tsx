import { useEffect, useMemo, useState } from 'react'
import './App.css'

type LanguageCode = 'en' | 'hi' | 'kn' | 'ta' | 'ml' | 'te'
type ThemeMode = 'light' | 'dark'

type LanguageOption = {
  code: LanguageCode
  label: string
}

type CandidateBreakdown = {
  punctuation: number
  entities: number
  length: number
  target_script: number
  tonality: number
  confidence: number
  total: number
}

type TranslationCandidate = {
  candidate_id: string
  strategy: string
  text: string
  confidence: number
  score: number
  breakdown: CandidateBreakdown
  notes: string[]
}

type TranslationResponse = {
  source_language: LanguageCode
  target_language: LanguageCode
  pair_label: string
  input_text: string
  selected_candidate: TranslationCandidate
  candidates: TranslationCandidate[]
  model_status: string
  retry_used: boolean
  diagnostics: Record<string, unknown>
}

type HealthResponse = {
  status: string
  model_status: string
}

const languageOptions: LanguageOption[] = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'kn', label: 'Kannada' },
  { code: 'ta', label: 'Tamil' },
  { code: 'ml', label: 'Malayalam' },
  { code: 'te', label: 'Telugu' },
]

const sampleText =
  'Please translate this project description clearly. Keep proper nouns, punctuation, and tone consistent.'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

function apiUrl(path: string): string {
  return apiBaseUrl ? `${apiBaseUrl}${path}` : path
}

function App() {
  const [themeMode, setThemeMode] = useState<ThemeMode>('light')
  const [sourceLanguage, setSourceLanguage] = useState<LanguageCode>('en')
  const [targetLanguage, setTargetLanguage] = useState<LanguageCode>('hi')
  const [text, setText] = useState(sampleText)
  const [response, setResponse] = useState<TranslationResponse | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedLanguages = useMemo(
    () =>
      languageOptions.reduce<Record<LanguageCode, string>>((accumulator, item) => {
        accumulator[item.code] = item.label
        return accumulator
      }, {} as Record<LanguageCode, string>),
    [],
  )

  useEffect(() => {
    const savedTheme = window.localStorage.getItem('theme-mode')
    if (savedTheme === 'light' || savedTheme === 'dark') {
      setThemeMode(savedTheme)
      return
    }

    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    setThemeMode(prefersDark ? 'dark' : 'light')
  }, [])

  useEffect(() => {
    window.localStorage.setItem('theme-mode', themeMode)
  }, [themeMode])

  useEffect(() => {
    const loadHealth = async () => {
      try {
        const response = await fetch(apiUrl('/api/health'))
        if (!response.ok) {
          throw new Error('Health check failed')
        }
        const data = (await response.json()) as HealthResponse
        setHealth(data)
      } catch {
        setHealth({ status: 'offline', model_status: 'backend unavailable' })
      }
    }

    void loadHealth()
  }, [])

  const swapLanguages = () => {
    setSourceLanguage(targetLanguage)
    setTargetLanguage(sourceLanguage)
  }

  const toggleTheme = () => {
    setThemeMode((current) => (current === 'dark' ? 'light' : 'dark'))
  }

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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="shell" data-theme={themeMode}>
      <header className="topbar">
        <div>
          <span className="eyebrow">Indian Multilingual Translation</span>
          <h1 className="title">Translation Studio</h1>
        </div>
        <button className="theme-toggle" type="button" onClick={toggleTheme}>
          {themeMode === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>
      </header>

      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow">Model-first pipeline</span>
          <h2>Translate across six Indian languages with ranked candidates.</h2>
          <p className="lede">
            This UI uses direct TranslateGemma inference, generates multiple
            candidates, scores each output, and selects the strongest
            translation for the requested language pair.
          </p>

          <div className="status-row">
            <div className="status-card">
              <span>API</span>
              <strong>{health?.status ?? 'checking...'}</strong>
            </div>
            <div className="status-card">
              <span>Model</span>
              <strong>{health?.model_status ?? 'loading...'}</strong>
            </div>
            <div className="status-card">
              <span>Scope</span>
              <strong>Any-to-any pairs</strong>
            </div>
          </div>
        </div>

        <div className="hero-card glass">
          <div className="hero-card-header">
            <span>Pipeline</span>
            <strong>Model → Candidates → Heuristics → Retry</strong>
          </div>
          <div className="pipeline-steps">
            <div>
              <span>1</span>
              <p>Normalize input</p>
            </div>
            <div>
              <span>2</span>
              <p>Generate multiple translations</p>
            </div>
            <div>
              <span>3</span>
              <p>Score with quality checks</p>
            </div>
            <div>
              <span>4</span>
              <p>Select the strongest result</p>
            </div>
          </div>
        </div>
      </section>

      <section className="workspace">
        <div className="panel composer glass">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Translator</span>
              <h2>Enter text and choose languages</h2>
            </div>
            <button className="ghost-button" type="button" onClick={() => setText(sampleText)}>
              Load sample
            </button>
          </div>

          <div className="controls">
            <label>
              <span>Source language</span>
              <select value={sourceLanguage} onChange={(event) => setSourceLanguage(event.target.value as LanguageCode)}>
                {languageOptions.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <button className="swap-button" type="button" onClick={swapLanguages} aria-label="Swap languages">
              ⇅
            </button>

            <label>
              <span>Target language</span>
              <select value={targetLanguage} onChange={(event) => setTargetLanguage(event.target.value as LanguageCode)}>
                {languageOptions.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="textarea-field">
            <span>Text to translate</span>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Type a sentence or paragraph here..."
              rows={8}
            />
          </label>

          {error ? <div className="error-banner">{error}</div> : null}

          <div className="action-row">
            <button className="primary-button" type="button" onClick={translateText} disabled={loading || text.trim().length === 0}>
              {loading ? 'Translating...' : 'Translate text'}
            </button>
            <div className="hint">
              Current pair: {selectedLanguages[sourceLanguage]} to {selectedLanguages[targetLanguage]}
            </div>
          </div>
        </div>

        <div className="panel output glass">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Result</span>
              <h2>Best candidate and diagnostics</h2>
            </div>
            {response ? <span className={response.retry_used ? 'badge warning' : 'badge success'}>{response.retry_used ? 'Retry used' : 'Direct select'}</span> : null}
          </div>

          {response ? (
            <>
              <div className="selected-card">
                <div className="selected-top">
                  <div>
                    <span>{response.pair_label}</span>
                    <strong>{response.selected_candidate.strategy}</strong>
                  </div>
                  <div className="score-pill">{Math.round(response.selected_candidate.score * 100)} / 100</div>
                </div>
                <p>{response.selected_candidate.text}</p>
                <div className="meta-grid">
                  <div>
                    <span>Confidence</span>
                    <strong>{Math.round(response.selected_candidate.confidence * 100)}%</strong>
                  </div>
                  <div>
                    <span>Candidate ID</span>
                    <strong>{response.selected_candidate.candidate_id}</strong>
                  </div>
                  <div>
                    <span>Retry</span>
                    <strong>{response.retry_used ? 'Yes' : 'No'}</strong>
                  </div>
                  <div>
                    <span>Model status</span>
                    <strong>{response.model_status}</strong>
                  </div>
                </div>
              </div>

              <div className="candidate-list">
                {response.candidates.map((candidate) => (
                  <article key={candidate.candidate_id} className={candidate.candidate_id === response.selected_candidate.candidate_id ? 'candidate-card active' : 'candidate-card'}>
                    <div className="candidate-head">
                      <strong>{candidate.strategy}</strong>
                      <span>{Math.round(candidate.score * 100)} / 100</span>
                    </div>
                    <p>{candidate.text}</p>
                    <div className="chip-row">
                      <span>Confidence {Math.round(candidate.confidence * 100)}%</span>
                      {candidate.notes.map((note) => (
                        <span key={note}>{note}</span>
                      ))}
                    </div>
                  </article>
                ))}
              </div>

              <div className="breakdown-grid">
                <div className="mini-card">
                  <span>Punctuation</span>
                  <strong>{Math.round(response.selected_candidate.breakdown.punctuation * 100)}%</strong>
                </div>
                <div className="mini-card">
                  <span>Entities</span>
                  <strong>{Math.round(response.selected_candidate.breakdown.entities * 100)}%</strong>
                </div>
                <div className="mini-card">
                  <span>Length</span>
                  <strong>{Math.round(response.selected_candidate.breakdown.length * 100)}%</strong>
                </div>
                <div className="mini-card">
                  <span>Target script</span>
                  <strong>{Math.round(response.selected_candidate.breakdown.target_script * 100)}%</strong>
                </div>
                <div className="mini-card">
                  <span>Tonality</span>
                  <strong>{Math.round(response.selected_candidate.breakdown.tonality * 100)}%</strong>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <p>
                Run a translation to see the selected candidate, all alternatives,
                and the heuristic breakdown.
              </p>
            </div>
          )}
        </div>
      </section>

      <section className="footer-note glass">
        <div>
          <span className="eyebrow">Architecture</span>
          <p>
            Model-only inference, candidate reranking, and clean API/UI
            separation with deployment-ready structure.
          </p>
        </div>
      </section>
    </main>
  )
}

export default App
