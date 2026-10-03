export interface RepMetrics {
  exercise_id: string
  rep_number: number
  duration_ms: number
  reference_duration_ms: number | null
  duration_ratio: number | null
  rom_deg: number | null
  reference_rom_deg: number | null
  rom_ratio: number | null
  peak_angular_velocity_dps: number | null
  reference_peak_velocity_dps: number | null
  peak_velocity_ratio: number | null
  smoothness_score: number | null
  similarity_score: number | null
  confidence: number | null
}

export interface SetMetrics {
  exercise_id: string
  rep_count: number
  reps: RepMetrics[]
  average_duration_ms: number | null
  duration_variability: number | null
  average_rom_deg: number | null
  rom_variability: number | null
  tempo_drift_pct: number | null
  rom_drift_pct: number | null
  consistency_score: number | null
  reference_similarity_mean: number | null
  reference_duration_ms: number | null
  reference_rom_deg: number | null
  reference_peak_velocity_dps: number | null
  metadata: Record<string, unknown>
}

export type PrimaryIssue =
  | 'GOOD'
  | 'TOO_FAST'
  | 'TOO_SLOW'
  | 'INSUFFICIENT_ROM'
  | 'EXCESSIVE_ROM'
  | 'INCONSISTENT'
  | 'UNSTABLE'
  | 'OTHER'

export type CoachingPriority = 'TEMPO' | 'ROM' | 'CONTROL' | 'CONSISTENCY' | 'NONE'
export type Severity = 'NONE' | 'MILD' | 'MODERATE' | 'MAJOR'
export type OverallQuality = 'POOR' | 'FAIR' | 'GOOD' | 'EXCELLENT'

export interface MovementDecision {
  primary_issue: PrimaryIssue
  coaching_priority: CoachingPriority
  severity: Severity
  should_speak: boolean
  overall_quality: OverallQuality
  confidence: number | null
  evidence: string[]
  alternatives: Record<string, number>
  provider: string
  model_version: string | null
  latency_ms: number | null
}

export interface CoachingResponse {
  text: string
  short_label: string
  tone: string
  provider: string
  model_version: string | null
  latency_ms: number | null
}

export interface EvaluationResult {
  metrics: SetMetrics | RepMetrics
  decision: MovementDecision
  coaching: CoachingResponse
  timings_ms: Record<string, number>
}

export interface ScenarioSummary {
  id: string
  label: string
  description: string
}

export interface ExerciseProfile {
  id: string
  display_name: string
  description: string
  key_dimensions: string[]
}

export interface ProviderStatus {
  mode: string
  configured: boolean
  model: string | null
}

export interface Health {
  status: string
  app_env: string
  providers: {
    decision: ProviderStatus
    language: ProviderStatus
    voice: ProviderStatus
  }
}
