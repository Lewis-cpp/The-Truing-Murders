// Public DTOs from backend/src/backend/api/schemas/responses.py. Only player-visible fields.

export type Phase =
  'INVESTIGATION' | 'INTERROGATION' | 'DEEP_INVESTIGATION' | 'ACCUSATION' | 'REVIEW' | 'FINISHED'

export interface ApiErrorBody {
  code: string
  message: string
  details: Record<string, unknown>
  retryable: boolean
  trace_id?: string | null
}

export interface CaseSummary {
  case_id: string
  case_version: string
  title: string
  synopsis: string
}

export interface SessionSummary {
  session_id: string
  case_id: string
  case_version: string
  title: string
  phase: Phase
  state_version: number
  active_npc_id: string | null
  is_current: boolean
  created_at: string
  saved_at: string
  closed_at: string | null
  finished_at: string | null
  available_actions: string[]
}

export interface InvestigationOption {
  action_id: string
  label: string
  completed: boolean
  enabled: boolean
  disabled_reason: string | null
}

export interface SceneView {
  scene_id: string
  name: string
  description: string
  visited: boolean
  actions: InvestigationOption[]
}

export interface PublicSource {
  kind: string
  id: string | null
  label: string
}

export interface EvidenceView {
  evidence_id: string
  name: string
  content: string
  source: PublicSource
  credibility: string
  discovered_at: string
}

export interface KnownInformation {
  information_ref: { kind: string; id: string }
  content: string
  assertion_kind: string
  source: PublicSource
  credibility: string
  discovered_at: string | null
}

export interface TopicView {
  topic_id: string
  label: string
  asked: boolean
}

export interface NpcView {
  npc_id: string
  name: string
  public_identity: string
  is_contactable: boolean
  is_active: boolean
  is_evading: boolean
  emotion: string
  admission_progress: string
  display_state: string
  fixed_statement: string | null
  presented_evidence_ids: string[]
  topics: TopicView[]
}

export interface Option {
  id: string
  label: string
}

export interface AccusationOptions {
  suspects: Option[]
  weapons: Option[]
  motives: Option[]
  process_steps: Option[]
  process_constraints: { min_steps: number; max_steps: number; allow_repeated_steps: boolean }
}

export interface SessionView {
  session: SessionSummary
  intro_text: string
  scenes: SceneView[]
  evidence: EvidenceView[]
  npcs: NpcView[]
  known_information: KnownInformation[]
  accusation_options: AccusationOptions
}

export interface CurrentSessionView {
  current_session_id: string | null
  session: SessionView | null
}

/** Details of 409 SAVE_VERSION_UNSUPPORTED: the kept save that a new game may replace. */
export interface UnsupportedSave {
  session_id: string
  state_version: number
}

export interface PlayerOutcome {
  reason_code: string
  summary: string
}

export interface ActionResult<T = unknown> {
  request_id: string
  session_id: string
  business_status: 'COMMITTED' | 'NOOP'
  state_changed: boolean
  state_version_before: number
  result_state_version: number
  phase_after: Phase
  saved_at: string
  data: T
}

export interface StepEvidenceLink {
  step_id: string
  evidence_id: string
}

export interface AccusationContent {
  suspect_character_id: string
  weapon_option_id: string
  motive_option_id: string
  ordered_process_step_ids: string[]
  cited_evidence_ids: string[]
  step_evidence_links: StepEvidenceLink[]
  explanation: string
}

export interface CriterionResult {
  criterion_id: string
  label: string
  matched: boolean
  score: string
  max_score: string
  explanation: string
}

export interface AccusationView {
  content: AccusationContent
  submitted_at: string
  verdict: {
    category: 'CORRECT' | 'PARTIALLY_CORRECT' | 'INCORRECT'
    score: string
    max_score: string
    criteria: CriterionResult[]
  }
}

export interface ReviewEvidence {
  evidence_id: string
  name: string
  content: string
  was_discovered: boolean
}

export interface ReviewView {
  accusation: AccusationView
  truth: { labels: Record<string, string>; explanation: string } & Record<string, unknown>
  evidence_chain: ReviewEvidence[]
  missed_evidence: ReviewEvidence[]
  fixed_review: string
}

export interface RequestRecord {
  request_id: string
  status: 'COMMITTED' | 'NOOP' | 'REJECTED'
  original_http_status: number
  result: ActionResult | null
  error: ApiErrorBody | null
}
