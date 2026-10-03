import type { CustomSetControls } from '../api'

interface Props {
  open: boolean
  onToggle: () => void
  controls: CustomSetControls
  onChange: (controls: CustomSetControls) => void
  onBuild: () => void
  onEvaluate: () => void
  busy: boolean
}

const SLIDERS: { key: keyof CustomSetControls; label: string; min: number; max: number; step: number }[] = [
  { key: 'duration_ratio', label: 'duration_ratio', min: 0.5, max: 1.8, step: 0.01 },
  { key: 'rom_ratio', label: 'rom_ratio', min: 0.5, max: 1.5, step: 0.01 },
  { key: 'similarity', label: 'similarity', min: 0, max: 1, step: 0.01 },
  { key: 'smoothness', label: 'smoothness', min: 0, max: 1, step: 0.01 },
  { key: 'variability', label: 'variability', min: 0, max: 0.4, step: 0.01 },
]

export function DevPanel({ open, onToggle, controls, onChange, onBuild, onEvaluate, busy }: Props) {
  return (
    <div className="panel">
      <button className="dev-toggle" onClick={onToggle}>
        {open ? '▾' : '▸'} Developer metrics
      </button>
      {open && (
        <div className="dev-body">
          {SLIDERS.map(({ key, label, min, max, step }) => (
            <div className="field" key={key}>
              <label>
                <span>{label}</span>
                <span>{Number(controls[key]).toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={Number(controls[key])}
                onChange={(e) =>
                  onChange({ ...controls, [key]: Number(e.target.value) } as CustomSetControls)
                }
              />
            </div>
          ))}
          <div className="actions">
            <button className="btn btn-ghost" onClick={onBuild} disabled={busy}>
              Build metrics
            </button>
            <button className="btn btn-primary" onClick={onEvaluate} disabled={busy}>
              Evaluate
            </button>
          </div>
          <p className="notice">Adjust ratios to probe the decision engine.</p>
        </div>
      )}
    </div>
  )
}
