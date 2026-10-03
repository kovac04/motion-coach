import type { CoachingResponse } from '../types'
import type { VoiceUsed } from '../tts'

interface Props {
  coaching: CoachingResponse
  autoSpeak: boolean
  onToggleAutoSpeak: () => void
  onSpeak: () => void
  speaking: boolean
  voiceUsed: VoiceUsed | null
  timings?: Record<string, number>
}

export function CoachPanel({
  coaching,
  autoSpeak,
  onToggleAutoSpeak,
  onSpeak,
  speaking,
  voiceUsed,
  timings,
}: Props) {
  return (
    <div className="panel">
      <h2>Coach</h2>
      <p className="coach-text">{coaching.text}</p>
      <div className="coach-actions">
        <button className="btn btn-primary" onClick={onSpeak} disabled={speaking}>
          {speaking ? 'Speaking…' : 'Replay'}
        </button>
        <div className="toggle">
          <button
            className="switch"
            data-on={autoSpeak}
            aria-label="Auto speak"
            onClick={onToggleAutoSpeak}
          />
          Auto speak
        </div>
      </div>
      <p className="notice">
        label “{coaching.short_label}” · language {coaching.provider}
        {voiceUsed ? ` · voice ${voiceUsed}` : ''}
        {timings ? ` · decision ${timings.decision?.toFixed(0)}ms / text ${timings.coaching?.toFixed(0)}ms` : ''}
      </p>
    </div>
  )
}
