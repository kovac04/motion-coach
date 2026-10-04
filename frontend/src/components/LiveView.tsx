import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type {
  CoachingResult,
  EvaluationResult,
  MotionStatus,
  SensorPoint,
  SensorStatus,
  SetMetrics,
} from '../types'
import { playCoaching, stopSpeaking, type VoiceUsed } from '../tts'
import { CoachPanel } from './CoachPanel'
import { DecisionPanel } from './DecisionPanel'
import { RepHistory } from './RepHistory'
import { SetSummary } from './SetSummary'

interface StreamMessage {
  type: string
  status: SensorStatus
  motion: MotionStatus
  samples: SensorPoint[]
}

interface Latency {
  metrics?: number
  jev?: number
  gemini?: number
  elevenlabs?: number
  total?: number
}

function polyline(values: number[], width: number, height: number, max: number): string {
  if (values.length < 2) return ''
  const step = width / (values.length - 1)
  return values
    .map((value, i) => `${(i * step).toFixed(1)},${(height - Math.min(Math.max(value / max, 0), 1) * height).toFixed(1)}`)
    .join(' ')
}

function Sparkline({ points }: { points: SensorPoint[] }) {
  const width = 300
  const height = 56
  const gyro = points.map((p) => p[1])
  const accel = points.map((p) => p[2])
  return (
    <svg className="spark-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      {accel.length > 1 && (
        <polyline points={polyline(accel, width, height, Math.max(1, ...accel))}
          fill="none" stroke="var(--warn)" strokeWidth="1.4" opacity="0.6" />
      )}
      {gyro.length > 1 && (
        <polyline points={polyline(gyro, width, height, Math.max(1, ...gyro))}
          fill="none" stroke="var(--accent)" strokeWidth="1.8" />
      )}
    </svg>
  )
}

const STEPS = [
  'Put on the wristband.',
  'Calibrate with 5 controlled reps.',
  'Press Start Set.',
  'Perform your set.',
  'Press Finish Set (or stop moving).',
]

function currentStep(motion: MotionStatus | null): number {
  if (!motion) return 0
  if (!motion.has_profile) return 1
  if (motion.mode === 'CALIBRATING') return 1
  if (motion.mode === 'SET_ACTIVE') return 3
  if (motion.mode === 'ANALYZING' || motion.mode === 'COACHING') return 4
  return 2
}

interface Props {
  voiceMode: string
  onSyntheticTab: () => void
}

export function LiveView({ voiceMode, onSyntheticTab }: Props) {
  const [status, setStatus] = useState<SensorStatus | null>(null)
  const [motion, setMotion] = useState<MotionStatus | null>(null)
  const [points, setPoints] = useState<SensorPoint[]>([])
  const [countdown, setCountdown] = useState<number | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [liveMetrics, setLiveMetrics] = useState<SetMetrics | null>(null)
  const [liveResult, setLiveResult] = useState<EvaluationResult | null>(null)
  const [latency, setLatency] = useState<Latency>({})
  const [providers, setProviders] = useState<{ decision: string; language: string } | null>(null)
  const [voiceUsed, setVoiceUsed] = useState<VoiceUsed | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [autoSpeak, setAutoSpeak] = useState(true)
  const [showDebug, setShowDebug] = useState(false)

  const socketRef = useRef<WebSocket | null>(null)
  const lastEvalRef = useRef<string>('')
  const finishAtRef = useRef<number | null>(null)

  const speak = useCallback(
    async (text: string, totalFromFinish: boolean) => {
      setSpeaking(true)
      const result = await playCoaching(text, voiceMode)
      setVoiceUsed(result.voice)
      setLatency((prev) => ({
        ...prev,
        elevenlabs: Math.round(result.ttsMs),
        total: totalFromFinish && finishAtRef.current
          ? Math.round(performance.now() - finishAtRef.current)
          : Math.round(((prev.metrics ?? 0) + (prev.jev ?? 0) + (prev.gemini ?? 0)) + result.totalMs),
      }))
      setSpeaking(false)
    },
    [voiceMode],
  )

  const applyEvaluation = useCallback(
    (evaluation: CoachingResult, totalFromFinish: boolean) => {
      if (evaluation.rejected || !evaluation.metrics || !evaluation.decision || !evaluation.coaching) {
        return
      }
      // De-duplicate: the WS may deliver the same evaluation the finish call returns.
      const key = JSON.stringify(evaluation.coaching)
      if (key === lastEvalRef.current) return
      lastEvalRef.current = key
      const mapped: EvaluationResult = {
        metrics: evaluation.metrics as SetMetrics,
        decision: evaluation.decision,
        coaching: evaluation.coaching,
        timings_ms: evaluation.timings_ms ?? {},
      }
      setLiveMetrics(evaluation.metrics as SetMetrics)
      setLiveResult(mapped)
      setProviders(evaluation.providers ?? null)
      setLatency((prev) => ({
        ...prev,
        metrics: Math.round(evaluation.timings_ms?.metrics ?? 0),
        jev: Math.round(evaluation.timings_ms?.jev ?? 0),
        gemini: Math.round(evaluation.timings_ms?.gemini ?? 0),
      }))
      if (autoSpeak) void speak(evaluation.coaching.text, totalFromFinish)
    },
    [autoSpeak, speak],
  )

  useEffect(() => {
    let closed = false
    let retryTimer: number | undefined
    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const socket = new WebSocket(`${proto}://${window.location.host}/api/sensor/stream`)
      socketRef.current = socket
      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data) as StreamMessage
        setStatus(msg.status)
        setMotion(msg.motion)
        setPoints(msg.samples)
        const evaluation = msg.motion.last_evaluation
        if (evaluation && !evaluation.rejected) {
          const key = JSON.stringify(evaluation.coaching)
          if (key !== lastEvalRef.current) {
            lastEvalRef.current = key
            applyEvaluation(evaluation, false)
          }
        }
      }
      socket.onclose = () => { if (!closed) retryTimer = window.setTimeout(connect, 1500) }
      socket.onerror = () => socket.close()
    }
    connect()
    return () => {
      closed = true
      if (retryTimer) window.clearTimeout(retryTimer)
      socketRef.current?.close()
    }
  }, [applyEvaluation])

  const connected = status?.connected ?? false
  const mode = motion?.mode ?? 'NO_PROFILE'
  const cal = motion?.calibration

  const runCalibration = async () => {
    setMessage(null)
    stopSpeaking()
    for (const n of [3, 2, 1]) {
      setCountdown(n)
      await new Promise((r) => setTimeout(r, 1000))
    }
    setCountdown(0)
    await api.motionCalibrateStart()
    await new Promise((r) => setTimeout(r, 400))
    setCountdown(null)
  }

  const startSet = async () => {
    stopSpeaking()
    setLiveMetrics(null)
    setLiveResult(null)
    setLatency({})
    setMessage(null)
    const result = await api.motionSetStart()
    if (!result.ok) setMessage(result.error ?? 'Could not start set')
  }

  const finishSet = async () => {
    finishAtRef.current = performance.now()
    setMessage('Analyzing…')
    const result = await api.motionSetFinish()
    if (result.ok && !result.rejected) {
      applyEvaluation(result, true)
      setMessage(null)
      return
    }
    if (result.rejected) {
      setMessage(result.reason ?? 'Set rejected')
      return
    }
    // No active set: it likely auto-finished already. Show that result if present.
    const current = await api.motionStatus()
    const evaluation = current.last_evaluation
    if (evaluation && !evaluation.rejected) {
      applyEvaluation(evaluation, false)
      setMessage(null)
    } else {
      setMessage(result.error ?? 'No active set')
    }
  }

  const toggleAutoFinish = async (enabled: boolean) => {
    await api.motionSetAutoFinish(enabled)
    setMotion((prev) => (prev ? { ...prev, auto_finish: enabled } : prev))
  }

  const step = currentStep(motion)
  const stateLabel = mode === 'SET_ACTIVE' ? 'SET ACTIVE'
    : mode === 'ANALYZING' ? 'ANALYZING…'
    : mode === 'CALIBRATING' ? 'CALIBRATING'
    : mode === 'COACHING' ? 'SET COMPLETE'
    : mode

  return (
    <div className="grid">
      <div className="stack">
        <div className="panel">
          <h2>Live Wearable</h2>
          <div className="live-status">
            <span className={`chip ${connected ? 'live' : 'fallback'}`}>
              {connected ? 'IMU CONNECTED' : 'IMU DISCONNECTED'}
            </span>
            {status && <span className="chip">{status.sample_rate_hz.toFixed(1)} Hz</span>}
            {status && <span className="chip">gaps {status.sequence_gaps}</span>}
          </div>

          {mode !== 'CALIBRATING' && (
            <div className={`live-state state-${mode}`}>{stateLabel}</div>
          )}
          {mode === 'SET_ACTIVE' && <div className="meta-line">rep {motion?.rep_count ?? 0} detected</div>}
          {cal?.active && cal.phase === 'WAITING_STILL' && (
            <>
              <div className="live-state state-CALIBRATING">HOLD STILL</div>
              <p className="notice">
                Getting a quiet baseline…
                {cal.baseline_noise_dps != null ? ` (${cal.baseline_noise_dps} dps)` : ''}
              </p>
            </>
          )}
          {cal?.active && cal.phase === 'REPS' && (
            <>
              <div className="live-state state-SET_ACTIVE">REFERENCE REPS {cal.reps}/{cal.target}</div>
              <p className="notice">Perform 5 controlled reps.</p>
            </>
          )}

          <ol className="steps">
            {STEPS.map((text, i) => (
              <li key={text} className={i === step ? 'active' : i < step ? 'done' : ''}>{text}</li>
            ))}
          </ol>

          {countdown !== null && <div className="countdown">{countdown > 0 ? countdown : 'GO'}</div>}
          {message && <p className="notice">{message}</p>}
        </div>

        <div className="panel">
          <h2>Controls</h2>
          <div className="actions">
            <button className="btn btn-ghost" onClick={() => void runCalibration()}
              disabled={!connected || mode === 'CALIBRATING' || countdown !== null}>
              {mode === 'NO_PROFILE' ? 'Calibrate Bicep Curl' : 'Calibrate'}
            </button>
            <button className="btn btn-primary" onClick={() => void startSet()}
              disabled={!connected || !motion?.has_profile || mode === 'SET_ACTIVE' || cal?.active}>
              Start Set
            </button>
            <button className="btn btn-primary" onClick={() => void finishSet()}
              disabled={mode !== 'SET_ACTIVE'}>
              Finish Set
            </button>
          </div>
          <div className="toggle" style={{ marginTop: 10 }}>
            <button className="switch" data-on={motion?.auto_finish ?? true}
              onClick={() => void toggleAutoFinish(!(motion?.auto_finish ?? true))} />
            Auto finish after {motion?.idle_timeout_s ?? 3}s idle
          </div>
          {cal?.result && !cal.active && (
            <p className="notice">
              {cal.result.ok
                ? `Calibrated: ${cal.result.reps_used} reps · tempo ${cal.result.reference_duration_ms?.toFixed(0)}ms · ` +
                  `range ${cal.result.reference_excursion_deg?.toFixed(0)}° · peak ${cal.result.reference_peak_dps?.toFixed(0)}°/s`
                : `Calibration failed: ${cal.result.error}`}
            </p>
          )}
        </div>

        <div className="panel">
          <h2>Signal</h2>
          {status?.sample ? (
            <div className="live-values">
              <div><span className="name">accel</span><span className="mono">{status.sample.ax}, {status.sample.ay}, {status.sample.az}</span></div>
              <div><span className="name">gyro</span><span className="mono">{status.sample.gx}, {status.sample.gy}, {status.sample.gz}</span></div>
            </div>
          ) : (
            <p className="notice">Waiting for the wearable.</p>
          )}
          <Sparkline points={points} />
        </div>

        <div className="panel">
          <button className="dev-toggle" onClick={() => setShowDebug((v) => !v)}>
            {showDebug ? '▾' : '▸'} Latency (measured)
          </button>
          {showDebug && (
            <p className="notice mono">
              metrics {latency.metrics ?? '—'} ms · Jev {latency.jev ?? '—'} ms · Gemini {latency.gemini ?? '—'} ms
              <br />ElevenLabs {latency.elevenlabs ?? '—'} ms · total→audio {latency.total ?? '—'} ms
              <br />providers: JEV={providers?.decision ?? '—'} · GEMINI={providers?.language ?? '—'} · voice {voiceUsed ?? '—'}
            </p>
          )}
        </div>
      </div>

      <div className="stack">
        {liveMetrics ? (
          <>
            <div className="panel banner-complete">SET COMPLETE — {liveMetrics.rep_count} reps</div>
            <SetSummary metrics={liveMetrics} />
          </>
        ) : (
          <div className="panel">
            <h2>Set</h2>
            <p className="notice">
              No live set yet. Follow the steps on the left, then press Start Set.
            </p>
          </div>
        )}

        {liveResult ? (
          <>
            <DecisionPanel decision={liveResult.decision} />
            <CoachPanel
              coaching={liveResult.coaching}
              autoSpeak={autoSpeak}
              onToggleAutoSpeak={() => setAutoSpeak((v) => !v)}
              onSpeak={() => void speak(liveResult.coaching.text, false)}
              speaking={speaking}
              voiceUsed={voiceUsed}
              timings={liveResult.timings_ms}
            />
            {liveMetrics && <RepHistory metrics={liveMetrics} />}
          </>
        ) : (
          <div className="panel">
            <h2>Coaching</h2>
            <p className="notice">
              The result of your set will appear here. For mock data instead,{' '}
              <button className="link-btn" onClick={onSyntheticTab}>open the Synthetic Demo</button>.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
