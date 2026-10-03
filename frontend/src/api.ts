import type {
  EvaluationResult,
  ExerciseProfile,
  Health,
  RepMetrics,
  ScenarioSummary,
  SetMetrics,
} from './types'

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
}
