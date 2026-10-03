import type { MovementDecision } from '../types'

interface Props {
  decision: MovementDecision
}

export function DecisionPanel({ decision }: Props) {
  const issueLabel = decision.primary_issue.replaceAll('_', ' ')
  const alternatives = Object.entries(decision.alternatives).sort((a, b) => b[1] - a[1])

  return (
    <div className="panel">
      <h2>Decision</h2>
      <div className={`decision-issue severity-${decision.severity}`}>{issueLabel}</div>
      <div className="meta-line">
        severity {decision.severity} · priority {decision.coaching_priority} ·{' '}
        {decision.overall_quality}
        {decision.confidence !== null && ` · confidence ${(decision.confidence * 100).toFixed(0)}%`}
      </div>

      {decision.evidence.length > 0 && (
        <ul className="evidence">
          {decision.evidence.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )}

      {alternatives.length > 0 && (
        <div className="alts">
          <div className="meta-line" style={{ marginBottom: 6 }}>
            Decision details
          </div>
          {alternatives.map(([name, prob]) => (
            <div className="alt-row" key={name}>
              <span className="alt-name">{name.replaceAll('_', ' ')}</span>
              <span className="alt-bar">
                <span style={{ width: `${Math.round(prob * 100)}%` }} />
              </span>
              <span>{(prob * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}

      <p className="notice">
        provider {decision.provider}
        {decision.model_version ? ` · ${decision.model_version}` : ''}
        {decision.latency_ms !== null ? ` · ${decision.latency_ms.toFixed(0)}ms` : ''}
      </p>
    </div>
  )
}
