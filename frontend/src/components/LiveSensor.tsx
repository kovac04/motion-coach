import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { CoachingResult, MotionStatus, SensorPoint, SensorStatus } from '../types'
import { playCoaching, type VoiceUsed } from '../tts'

interface StreamMessage {
  type: string
  status: SensorStatus
  motion: MotionStatus
  samples: SensorPoint[]
}

function polyline(values: number[], width: number, height: number, max: number): string {
  if (values.length < 2) return ''
  const step = width / (values.length - 1)
  return values
    .map((value, i) => {
      const y = height - Math.min(Math.max(value / max, 0), 1) * height
      return `${(i * step).toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

function Sparkline({ points }: { points: SensorPoint[] }) {
  const width = 300
  const height = 60
  const gyro = points.map((p) => p[1])
  const accel = points.map((p) => p[2])
  const gyroMax = Math.max(1, ...gyro)
  const accelMax = Math.max(1, ...accel)

  return (
    <svg
      className="spark-svg"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Gyro and acceleration magnitude over the last seconds"
    >
      {accel.length > 1 && (
        <polyline points={polyline(accel, width, height, accelMax)} fill="none"
          stroke="var(--warn)" strokeWidth="1.5" opacity="0.7" />
      )}
      {gyro.length > 1 && (
        <polyline points={polyline(gyro, width, height, gyroMax)} fill="none"
          stroke="var(--accent)" strokeWidth="1.8" />
      )}
    </svg>
  )
}

function MotionBlock({ motion }: { motion: MotionStatus }) {
  const state = motion.has_profile ? motion.state : 'NO PROFILE'
  const active = motion.state === 'ACTIVE'
  return (
    <div className="motion-block">
      <span className={`chip ${active ? 'live' : ''}`}>{state}</span>
      {active && <span className="chip">rep {motion.rep_count}</span>}
    </div>
  )
}

function EvaluationBlock({ evaluation }: { evaluation: CoachingResult | null }) {
  if (!evaluation) return null
  if (evaluation.rejected) {
    return (
      <p className="notice motion-rejected">
        SET_REJECTED — {evaluation.reason}
      </p>
    )
  }
  const decision = evaluation.decision
  const coaching = evaluation.coaching
  return (
    <div className="motion-coaching">
      {decision && (
        <div className={`decision-issue severity-${decision.severity}`}>
          {decision.primary_issue.replaceAll('_', ' ')}
        </div>
      )}
      {coaching && <p className="coach-text small">{coaching.text}</p>}
      {decision && (
        <p className="notice">
          priority {decision.coaching_priority} · confidence{' '}
          {decision.confidence !== null ? `${(decision.confidence * 100).toFixed(0)}%` : '—'}
          {evaluation.rep_count !== undefined && ` · ${evaluation.rep_count} reps`}
        </p>
      )}
    </div>
  )
}

interface Props {
  voiceMode: string
  autoSpeak: boolean
}

export function LiveSensor({ voiceMode, autoSpeak }: Props) {
  const [status, setStatus] = useState<SensorStatus | null>(null)
  const [motion, setMotion] = useState<MotionStatus | null>(null)
  const [points, setPoints] = useState<SensorPoint[]>([])
  const [calibrating, setCalibrating] = useState(false)
  const [calibrationMessage, setCalibrationMessage] = useState<string | null>(null)
  const [voiceUsed, setVoiceUsed] = useState<VoiceUsed | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const lastSpoken = useRef<string | null>(null)

  useEffect(() => {
    let closed = false
    let retryTimer: number | undefined

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const socket = new WebSocket(`${proto}://${window.location.host}/api/sensor/stream`)
      socketRef.current = socket
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as StreamMessage
        setStatus(message.status)
        setMotion(message.motion)
        setPoints(message.samples)
      }
      socket.onclose = () => {
        if (!closed) retryTimer = window.setTimeout(connect, 1500)
      }
      socket.onerror = () => socket.close()
    }

    connect()
    return () => {
      closed = true
      if (retryTimer) window.clearTimeout(retryTimer)
      socketRef.current?.close()
    }
  }, [])

  // Speak a new coaching cue once (the athlete should not click per rep).
  useEffect(() => {
    const evaluation = motion?.last_evaluation
    const text = evaluation?.coaching?.text
    if (autoSpeak && text && !evaluation?.rejected && text !== lastSpoken.current) {
      lastSpoken.current = text
      void playCoaching(text, voiceMode).then(setVoiceUsed)
    }
  }, [motion, autoSpeak, voiceMode])

  const sample = status?.sample ?? null

  const handleCalibrate = async () => {
    setCalibrating(true)
    setCalibrationMessage('Calibrating — perform 5 controlled reps now…')
    try {
      const result = await api.calibrateMotion('bicep_curl', 20)
      setCalibrationMessage(
        result.ok
          ? `Calibrated: ${result.reps_used} reps, ref ${result.reference_duration_ms?.toFixed(0)}ms, ` +
            `${result.reference_excursion_deg?.toFixed(0)}°.`
          : `Calibration failed: ${result.error}`,
      )
    } catch (error) {
      setCalibrationMessage(`Calibration failed: ${(error as Error).message}`)
    } finally {
      setCalibrating(false)
    }
  }

  return (
    <div className="panel">
      <h2>Live Sensor</h2>
      <div className="live-status">
        <span className={`chip ${status?.connected ? 'live' : 'fallback'}`}>
          {status?.connected ? 'IMU CONNECTED' : 'IMU DISCONNECTED'}
        </span>
        {status && <span className="chip">{status.sample_rate_hz.toFixed(1)} Hz</span>}
        {status && <span className="chip">gaps {status.sequence_gaps}</span>}
        {voiceUsed && voiceMode === 'elevenlabs' && <span className="chip">voice {voiceUsed}</span>}
      </div>

      {motion && <MotionBlock motion={motion} />}

      {sample ? (
        <div className="live-values">
          <div>
            <span className="name">accel</span>
            <span className="mono">{sample.ax}, {sample.ay}, {sample.az}</span>
          </div>
          <div>
            <span className="name">gyro</span>
            <span className="mono">{sample.gx}, {sample.gy}, {sample.gz}</span>
          </div>
        </div>
      ) : (
        <p className="notice">Waiting for the wearable. Power it on and keep it in BLE range.</p>
      )}

      <Sparkline points={points} />

      <div className="actions">
        <button className="btn btn-ghost" onClick={() => void handleCalibrate()}
          disabled={calibrating || !status?.connected}>
          {calibrating ? 'Calibrating…' : 'Calibrate Bicep Curl'}
        </button>
      </div>
      {calibrationMessage && <p className="notice">{calibrationMessage}</p>}

      {motion && <EvaluationBlock evaluation={motion.last_evaluation} />}
    </div>
  )
}
