import type { SetMetrics } from '../types'

interface Props {
  metrics: SetMetrics
}

function mean(values: (number | null)[]): number | null {
  const present = values.filter((v): v is number => v !== null)
  if (present.length === 0) return null
  return present.reduce((a, b) => a + b, 0) / present.length
}

function fmt(value: number | null, digits = 2, suffix = ''): string {
  if (value === null) return '—'
  return `${value.toFixed(digits)}${suffix}`
}

export function SetSummary({ metrics }: Props) {
  const avgDurationRatio = mean(metrics.reps.map((r) => r.duration_ratio))
  const avgRomRatio = mean(metrics.reps.map((r) => r.rom_ratio))
  const maxDuration = Math.max(...metrics.reps.map((r) => r.duration_ms), 1)

  return (
    <div className="panel">
      <h2>Current Set</h2>
      <p className="meta-line">
        {metrics.rep_count} reps · {metrics.exercise_id}
      </p>
      <div className="metrics">
        <div className="metric">
          <div className="value">{metrics.rep_count}</div>
          <div className="name">Reps</div>
        </div>
        <div className="metric">
          <div className="value">{fmt(metrics.reference_similarity_mean, 2)}</div>
          <div className="name">Similarity</div>
        </div>
        <div className="metric">
          <div className="value">{fmt(metrics.consistency_score, 2)}</div>
          <div className="name">Consistency</div>
        </div>
        <div className="metric">
          <div className="value">{fmt(avgDurationRatio, 2, 'x')}</div>
          <div className="name">Tempo</div>
        </div>
        <div className="metric">
          <div className="value">{fmt(avgRomRatio, 2, 'x')}</div>
          <div className="name">Range</div>
        </div>
      </div>

      <div className="spark">
        {metrics.reps.map((rep) => (
          <div className="col" key={rep.rep_number}>
            <div
              className="stem"
              style={{ height: `${Math.round((rep.duration_ms / maxDuration) * 100)}%` }}
              title={`${Math.round(rep.duration_ms)}ms`}
            />
            <div className="cap">{rep.rep_number}</div>
          </div>
        ))}
      </div>
      <p className="notice">
        Rep duration (ms). Drift {fmt(metrics.tempo_drift_pct, 0, '%')} · ROM drift{' '}
        {fmt(metrics.rom_drift_pct, 0, '%')}
      </p>
    </div>
  )
}
