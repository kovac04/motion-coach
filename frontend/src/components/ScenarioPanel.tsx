import type { ScenarioSummary } from '../types'

interface Props {
  scenarios: ScenarioSummary[]
  selected: string | null
  onSelect: (id: string) => void
}

export function ScenarioPanel({ scenarios, selected, onSelect }: Props) {
  return (
    <div className="panel">
      <h2>Demo Simulator</h2>
      <p className="meta-line">Synthetic sets — no sensors required.</p>
      <div className="scenario-list">
        {scenarios.map((s) => (
          <button
            key={s.id}
            className={`scenario-btn${selected === s.id ? ' active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <div className="label">{s.label}</div>
            <div className="desc">{s.description}</div>
          </button>
        ))}
      </div>
    </div>
  )
}
