import { useEffect, useRef, useState } from 'react'
import type { SensorPoint, SensorStatus } from '../types'

interface StreamMessage {
  type: string
  status: SensorStatus
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
        <polyline
          points={polyline(accel, width, height, accelMax)}
          fill="none"
          stroke="var(--warn)"
          strokeWidth="1.5"
          opacity="0.7"
        />
      )}
      {gyro.length > 1 && (
        <polyline
          points={polyline(gyro, width, height, gyroMax)}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.8"
        />
      )}
    </svg>
  )
}

export function LiveSensor() {
  const [status, setStatus] = useState<SensorStatus | null>(null)
  const [points, setPoints] = useState<SensorPoint[]>([])
  const socketRef = useRef<WebSocket | null>(null)

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

  const sample = status?.sample ?? null

  return (
    <div className="panel">
      <h2>Live Sensor</h2>
      <div className="live-status">
        <span className={`chip ${status?.connected ? 'live' : 'fallback'}`}>
          {status?.connected ? 'IMU CONNECTED' : 'IMU DISCONNECTED'}
        </span>
        {status && <span className="chip">{status.sample_rate_hz.toFixed(1)} Hz</span>}
        {status && <span className="chip">gaps {status.sequence_gaps}</span>}
      </div>

      {sample ? (
        <div className="live-values">
          <div>
            <span className="name">accel</span>
            <span className="mono">
              {sample.ax}, {sample.ay}, {sample.az}
            </span>
          </div>
          <div>
            <span className="name">gyro</span>
            <span className="mono">
              {sample.gx}, {sample.gy}, {sample.gz}
            </span>
          </div>
        </div>
      ) : (
        <p className="notice">
          Waiting for the wearable. Power it on and keep it in BLE range.
        </p>
      )}

      <Sparkline points={points} />
      <p className="notice">
        <span style={{ color: 'var(--accent)' }}>gyro |mag|</span>{' '}
        <span style={{ color: 'var(--warn)' }}>accel |mag|</span> · last few seconds
      </p>
    </div>
  )
}
