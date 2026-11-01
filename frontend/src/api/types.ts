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

export interface InformationRef {
  kind: string
  id: string
}

export interface EvidenceView {
  evidence_id: string
  name: string
  kind: string
  content: string
  source: PublicSource
  credibility: string
  discovered_at: string | null
  key_badge: boolean
  known_conflicts: InformationRef[]
  links: unknown[]
}

export interface KnownInformation {
  information_ref: InformationRef
  content: string
  assertion_kind: string
  source: PublicSource
  credibility: string
  discovered_at: string | null
  known_conflicts: InformationRef[]
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
  known_statements: KnownInformation[]
  topics: TopicView[]
}

export interface RelationshipNode {
  character_id: string
  name: string
  role: string
  public_identity: string
}

export interface RelationshipEdge {
  relationship_id: string
  from_character_id: string
  to_character_id: string
  relationship_type: string
  directed: boolean
  description: string
  assertion_kind: string
  source: PublicSource
  credibility: string
  discovered_at: string | null
  known_conflicts: InformationRef[]
}

export interface RelationshipGraph {
  nodes: RelationshipNode[]
  edges: RelationshipEdge[]
}

export interface TimelineItem {
  timeline_event_id: string
  title: string
  description: string
  scene_id: string | null
  participant_ids: string[]
  time_precision: 'EXACT' | 'RANGE' | 'UNKNOWN'
  time_start_minutes: number | null
  time_end_minutes: number | null
  time_label: string
  assertion_kind: string
  source: PublicSource
  credibility: string
  discovered_at: string | null
  known_conflicts: InformationRef[]
}

export interface TimelineView {
  origin_label: string
  items: TimelineItem[]
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

export interface AccusationContent {
  suspect_character_id: string | null
  weapon_option_id: string | null
  motive_option_id: string | null
  ordered_process_step_ids: string[]
  cited_evidence_ids: string[]
  step_evidence_links: StepEvidenceLink[]
  explanation: string
}

export interface SessionView {
  session: SessionSummary
  intro_text: string
  scenes: SceneView[]
  evidence: EvidenceView[]
  npcs: NpcView[]
  known_information: KnownInformation[]
  relationships: RelationshipGraph
  timeline: TimelineView
  accusation_options: AccusationOptions
  accusation_draft: AccusationContent | null
  pending_conversations: unknown[]
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

export interface ConversationMessageView {
  message_id: string
  sequence_no: number
  speaker: string
  content: string
  origin: string
  validity: string
  created_at: string
  updated_at: string
}

export interface ConversationView {
  conversation_id: string
  conversation_seq: number
  session_id: string
  npc_id: string | null
  request_id: string
  interaction_type: 'CHAT' | 'EVIDENCE_PRESENTATION'
  source_state_version: number
  generation_status: string
  generation_deadline_at: string | null
  deadline_exceeded: boolean
  fixed_reply: string
  messages: ConversationMessageView[]
  fallback_reason: string | null
  can_retry_reply: boolean
  created_at: string
  completed_at: string | null
}

export interface ConversationPage {
  items: ConversationView[]
  next_before_seq: number | null
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
  conversation?: ConversationView | null
}

export interface StepEvidenceLink {
  step_id: string
  evidence_id: string
}

export interface CriterionResult {
  criterion_id: string
  label: string
  matched: boolean
  score: string
  max_score: string
  explanation: string
  missing_evidence_ids: string[]
}

export interface AccusationView {
  content: AccusationContent
  submitted_at: string
  verdict: {
    category: 'CORRECT' | 'PARTIALLY_CORRECT' | 'INCORRECT'
    score: string
    max_score: string
    fixed_explanation: string
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
