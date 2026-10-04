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

export interface SensorSamplePayload {
  sequence: number
  timestamp_ms: number
  ax: number
  ay: number
  az: number
  gx: number
  gy: number
  gz: number
  accel_magnitude: number
  gyro_magnitude: number
}

export interface SensorStatus {
  connected: boolean
  device_name: string
  address: string | null
  sample_rate_hz: number
  sequence_gaps: number
  missing_samples: number
  malformed: number
  connections: number
  last_error: string | null
  last_seen: number | null
  sample: SensorSamplePayload | null
}

// [host_timestamp, gyro_magnitude, accel_magnitude]
export type SensorPoint = [number, number, number]

export interface CoachingResult {
  rejected: boolean
  reason?: string
  source?: string
  set_seq?: number
  rep_count?: number
  metrics?: unknown
  decision?: MovementDecision
  coaching?: CoachingResponse
  timings_ms?: Record<string, number>
  providers?: { decision: string; language: string }
}

export interface MotionCalibration {
  active: boolean
  phase: string // IDLE | WAITING_STILL | REPS
  reps: number
  target: number
  baseline_noise_dps: number | null
  result: {
    ok: boolean
    error?: string
    reps_used?: number
    reference_duration_ms?: number
    reference_excursion_deg?: number
    reference_peak_dps?: number
    noise_dps?: number
  } | null
}

export interface MotionLatency {
  metrics?: number
  jev?: number
  gemini?: number
}

export interface AvailableExercise {
  id: string
  display_name: string
  calibrated: boolean
}

export interface ProfileInfo {
  reference_duration_ms: number
  reference_excursion_deg: number
  reference_peak_dps: number
  axis_variance_fraction: number
  noise_dps: number
  axis: number[]
}

export interface MotionStatus {
  mode: string // NO_PROFILE | CALIBRATING | READY | SET_ACTIVE | ANALYZING | COACHING
  state: string // READY | ACTIVE
  rep_count: number
  auto_finish: boolean
  idle_timeout_s: number
  exercise_id: string
  has_profile: boolean
  available_profiles: string[]
  available_exercises: AvailableExercise[]
  profile_info: ProfileInfo | null
  calibration: MotionCalibration
  last_evaluation: CoachingResult | null
  latency_ms: MotionLatency | null
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
