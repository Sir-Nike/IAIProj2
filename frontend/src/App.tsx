import { useMemo, useState } from 'react'
import './App.css'

type LanguageCode = 'en' | 'hi' | 'kn' | 'ta' | 'ml' | 'te'

type LanguageOption = {
  code: LanguageCode
  label: string
}

type CandidateBreakdown = {
  entities: number
  length: number
  target_script: number
  tonality: number
  semantic: number
  fluency: number
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
}

type TranslationResponse = {
  source_language: LanguageCode
  target_language: LanguageCode
  pair_label: string
  input_text: string
  selected_candidate: TranslationCandidate
  candidates: TranslationCandidate[]
  retry_used: boolean
  diagnostics: Record<string, unknown>
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
  const [sourceLanguage, setSourceLanguage] = useState<LanguageCode>('en')
  const [targetLanguage, setTargetLanguage] = useState<LanguageCode>('hi')
  const [text, setText] = useState(sampleText)
  const [response, setResponse] = useState<TranslationResponse | null>(null)
  const [activeCandidateId, setActiveCandidateId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const swapLanguages = () => {
    setSourceLanguage(targetLanguage)
    setTargetLanguage(sourceLanguage)
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
      setActiveCandidateId(data.selected_candidate.candidate_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

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

  return (
    <main className="shell">
      <section className="workspace">
        <div className="panel composer">
          <h1 className="title">Translator</h1>
          <div className="controls">
            <label>
              <span>Source</span>
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
              <span>Target</span>
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
            <span>Input text</span>
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Type your text here..."
              rows={10}
            />
          </label>

          {error ? <div className="error-banner">{error}</div> : null}

          <div className="action-row">
            <button className="primary-button" type="button" onClick={translateText} disabled={loading || text.trim().length === 0}>
              {loading ? 'Translating...' : 'Generate outputs'}
            </button>
            <button className="ghost-button" type="button" onClick={() => setText(sampleText)}>
              Load sample
            </button>
          </div>
        </div>

        <div className="panel output">
          <h2 className="section-title">Generated outputs</h2>

          {response ? (
            <>
              <div className="candidate-list">
                {response.candidates.map((candidate) => {
                  const isBest = candidate.candidate_id === response.selected_candidate.candidate_id
                  const isActive = candidate.candidate_id === activeCandidate?.candidate_id
                  const className = [
                    'candidate-card',
                    isBest ? 'best' : '',
                    isActive ? 'active' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')

                  return (
                    <button
                      key={candidate.candidate_id}
                      type="button"
                      className={className}
                      onClick={() => setActiveCandidateId(candidate.candidate_id)}
                    >
                      <div className="candidate-head">
                        <strong>{candidate.strategy}</strong>
                        <span>{Math.round(candidate.score * 100)} / 100</span>
                      </div>
                      <p>{candidate.text}</p>
                      <div className="chip-row">
                        <span>Confidence {Math.round(candidate.confidence * 100)}%</span>
                        {isBest ? <span>Best score</span> : null}
                      </div>
                    </button>
                  )
                })}
              </div>

              {activeCandidate ? (
                <div className="details-panel">
                  <h3>Heuristic breakdown</h3>
                  <div className="breakdown-grid">
                    <div className="mini-card">
                      <span>Entities</span>
                      <strong>{Math.round(activeCandidate.breakdown.entities * 100)}%</strong>
                    </div>
                    <div className="mini-card">
                      <span>Length</span>
                      <strong>{Math.round(activeCandidate.breakdown.length * 100)}%</strong>
                    </div>
                    <div className="mini-card">
                      <span>Target script</span>
                      <strong>{Math.round(activeCandidate.breakdown.target_script * 100)}%</strong>
                    </div>
                    <div className="mini-card">
                      <span>Tonality</span>
                      <strong>{Math.round(activeCandidate.breakdown.tonality * 100)}%</strong>
                    </div>
                    <div className="mini-card">
                      <span>Semantic</span>
                      <strong>{Math.round((activeCandidate.breakdown.semantic ?? 0) * 100)}%</strong>
                    </div>
                    <div className="mini-card">
                      <span>Fluency</span>
                      <strong>{Math.round((activeCandidate.breakdown.fluency ?? 0) * 100)}%</strong>
                    </div>
                    <div className="mini-card">
                      <span>Confidence</span>
                      <strong>{Math.round(activeCandidate.breakdown.confidence * 100)}%</strong>
                    </div>
                    <div className="mini-card">
                      <span>Total</span>
                      <strong>{Math.round(activeCandidate.breakdown.total * 100)}%</strong>
                    </div>
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <div className="empty-state">
              <p>Generate outputs to view candidates and click one to inspect its heuristic breakdown.</p>
            </div>
          )}
        </div>
      </section>
    </main>
  )
}

export default App
