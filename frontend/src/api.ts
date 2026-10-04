import type {
  CoachingResult,
  EvaluationResult,
  ExerciseProfile,
  Health,
  MotionStatus,
  RepMetrics,
  ScenarioSummary,
  SetMetrics,
} from './types'

export interface CalibrationResult {
  ok: boolean
  error?: string
  exercise_id?: string
  reps_used?: number
  reference_duration_ms?: number
  reference_excursion_deg?: number
  reference_peak_dps?: number
  noise_dps?: number
}

export interface MotionActionResult {
  ok: boolean
  error?: string
  target_reps?: number
  auto_finish?: boolean
}

export type MotionFinishResult = CoachingResult & { ok?: boolean; error?: string }

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} -> ${res.status}`)
  return (await res.json()) as T
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`${url} -> ${res.status} ${detail}`)
  }
  return (await res.json()) as T
}

export interface CustomSetControls {
  exercise_id: string
  duration_ratio: number
  rom_ratio: number
  similarity: number
  smoothness: number
  variability: number
  rep_count: number
}

export const api = {
  health: () => getJson<Health>('/health'),
  scenarios: () => getJson<ScenarioSummary[]>('/api/demo/scenarios'),
  scenario: (id: string) => getJson<SetMetrics>(`/api/demo/scenarios/${id}`),
  exercises: () => getJson<ExerciseProfile[]>('/api/exercises'),
  customSet: (controls: CustomSetControls) => postJson<SetMetrics>('/api/demo/custom', controls),
  evaluateSet: (metrics: SetMetrics) => postJson<EvaluationResult>('/api/evaluate/set', metrics),
  evaluateRep: (metrics: RepMetrics) => postJson<EvaluationResult>('/api/evaluate/rep', metrics),
  motionStatus: () => getJson<MotionStatus>('/api/motion/status'),
  motionSetStart: () => postJson<MotionActionResult>('/api/motion/set/start', {}),
  motionSetFinish: () => postJson<MotionFinishResult>('/api/motion/set/finish', {}),
  motionCalibrateStart: () => postJson<MotionActionResult>('/api/motion/calibrate/start', {}),
  motionCalibrateFinish: () => postJson<CalibrationResult>('/api/motion/calibrate/finish', {}),
  motionSetAutoFinish: (enabled: boolean) =>
    postJson<MotionActionResult>('/api/motion/auto-finish', { enabled }),
}
