import type { SetMetrics } from '../types'

interface Props {
  metrics: SetMetrics
}

function fmt(value: number | null, digits = 2): string {
  return value === null ? '—' : value.toFixed(digits)
}

export function RepHistory({ metrics }: Props) {
  return (
    <div className="panel">
      <h2>Rep History</h2>
      <table className="rep-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Duration</th>
            <th>Tempo ×</th>
            <th>ROM ×</th>
            <th>Similarity</th>
            <th>Smoothness</th>
          </tr>
        </thead>
        <tbody>
          {metrics.reps.map((rep) => (
            <tr key={rep.rep_number}>
              <td className="num">{rep.rep_number}</td>
              <td>{Math.round(rep.duration_ms)}ms</td>
              <td>{fmt(rep.duration_ratio)}</td>
              <td>{fmt(rep.rom_ratio)}</td>
              <td>{fmt(rep.similarity_score)}</td>
              <td>{fmt(rep.smoothness_score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
