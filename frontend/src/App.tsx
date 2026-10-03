import { useCallback, useEffect, useState } from 'react'
import { api, type CustomSetControls } from './api'
import { CoachPanel } from './components/CoachPanel'
import { DecisionPanel } from './components/DecisionPanel'
import { DevPanel } from './components/DevPanel'
import { RepHistory } from './components/RepHistory'
import { ScenarioPanel } from './components/ScenarioPanel'
import { SetSummary } from './components/SetSummary'
import { playCoaching, stopSpeaking, type VoiceUsed } from './tts'
import type { EvaluationResult, ExerciseProfile, Health, ScenarioSummary, SetMetrics } from './types'

const DEFAULT_CONTROLS: CustomSetControls = {
  exercise_id: 'bicep_curl',
  duration_ratio: 1.0,
  rom_ratio: 1.0,
  similarity: 0.9,
  smoothness: 0.9,
  variability: 0.05,
  rep_count: 5,
}

function providerChip(name: string, mode: string, configured: boolean) {
  const real = mode !== 'mock' && mode !== 'fallback' && mode !== 'browser' && mode !== 'disabled'
  return (
    <span key={name} className={`chip ${real ? (configured ? 'live' : 'fallback') : ''}`}>
      {name}: {mode}
    </span>
  )
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([])
  const [exercises, setExercises] = useState<ExerciseProfile[]>([])
  const [exerciseId, setExerciseId] = useState('bicep_curl')
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<SetMetrics | null>(null)
  const [result, setResult] = useState<EvaluationResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoSpeak, setAutoSpeak] = useState(true)
  const [speaking, setSpeaking] = useState(false)
  const [voiceUsed, setVoiceUsed] = useState<VoiceUsed | null>(null)
  const [devOpen, setDevOpen] = useState(false)
  const [controls, setControls] = useState<CustomSetControls>(DEFAULT_CONTROLS)

  const voiceMode = health?.providers.voice.mode ?? 'browser'

  const speak = useCallback(
    async (text: string) => {
      setSpeaking(true)
      const used = await playCoaching(text, voiceMode)
      setVoiceUsed(used)
      setSpeaking(false)
    },
    [voiceMode],
  )

  const evaluate = useCallback(
    async (forceSpeak = false) => {
      if (!metrics) return
      setBusy(true)
      setError(null)
      try {
        const scoped: SetMetrics = {
          ...metrics,
          exercise_id: exerciseId,
          reps: metrics.reps.map((rep) => ({ ...rep, exercise_id: exerciseId })),
        }
        const evaluation = await api.evaluateSet(scoped)
        setResult(evaluation)
        if (forceSpeak || autoSpeak) await speak(evaluation.coaching.text)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Evaluation failed')
      } finally {
        setBusy(false)
      }
    },
    [metrics, exerciseId, autoSpeak, speak],
  )

  const loadScenario = useCallback(
    async (id: string) => {
      setSelectedScenario(id)
      setError(null)
      try {
        const data = await api.scenario(id)
        setMetrics(data)
        setResult(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load scenario')
      }
    },
    [],
  )

  useEffect(() => {
    void (async () => {
      try {
        const [h, s, ex] = await Promise.all([api.health(), api.scenarios(), api.exercises()])
        setHealth(h)
        setScenarios(s)
        setExercises(ex)
        await loadScenario('too_fast')
      } catch (e) {
        setError(
          e instanceof Error
            ? `${e.message} — is the backend running? (make backend)`
            : 'Backend unavailable',
        )
      }
    })()
  }, [loadScenario])

  const handleBuildCustom = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await api.customSet({ ...controls, exercise_id: exerciseId })
      setMetrics(data)
      setResult(null)
      setSelectedScenario(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not build metrics')
    } finally {
      setBusy(false)
    }
  }, [controls, exerciseId])

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div>
            <h1>Motion Coach</h1>
            <p>Wearable Movement Intelligence</p>
          </div>
        </div>
        <div className="status-row">
          {health &&
            (['decision', 'language', 'voice'] as const).map((key) =>
              providerChip(key, health.providers[key].mode, health.providers[key].configured),
            )}
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="grid">
        <div className="stack">
          <div className="panel">
            <h2>Exercise</h2>
            <div className="field">
              <select value={exerciseId} onChange={(e) => setExerciseId(e.target.value)}>
                {exercises.map((ex) => (
                  <option key={ex.id} value={ex.id}>
                    {ex.display_name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <ScenarioPanel
            scenarios={scenarios}
            selected={selectedScenario}
            onSelect={(id) => void loadScenario(id)}
          />

          <DevPanel
            open={devOpen}
            onToggle={() => setDevOpen((v) => !v)}
            controls={controls}
            onChange={setControls}
            onBuild={() => void handleBuildCustom()}
            onEvaluate={() => void evaluate()}
            busy={busy}
          />
        </div>

        <div className="stack">
          {metrics && <SetSummary metrics={metrics} />}

          <div className="actions">
            <button className="btn btn-primary" onClick={() => void evaluate()} disabled={busy || !metrics}>
              {busy ? 'Analyzing…' : 'Analyze Set'}
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => {
                stopSpeaking()
                void evaluate(true)
              }}
              disabled={busy || !metrics}
            >
              Run Full Demo
            </button>
          </div>

          {result ? (
            <>
              <DecisionPanel decision={result.decision} />
              <CoachPanel
                coaching={result.coaching}
                autoSpeak={autoSpeak}
                onToggleAutoSpeak={() => setAutoSpeak((v) => !v)}
                onSpeak={() => void speak(result.coaching.text)}
                speaking={speaking}
                voiceUsed={voiceUsed}
                timings={result.timings_ms}
              />
            </>
          ) : (
            <div className="panel">
              <h2>Decision</h2>
              <p className="notice">
                Select a scenario and press Analyze Set. Running in mock mode — no credentials needed.
              </p>
            </div>
          )}

          {metrics && <RepHistory metrics={metrics} />}
        </div>
      </div>
    </div>
  )
}
