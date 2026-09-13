// ============================================================================
// API wire types — the typed contract between the React frontend and the
// FastAPI backend (`backend/app/schemas.py`).
//
// These mirror the Pydantic response models so API payloads are never handled
// as `any`. The domain state shapes consumed by components live in
// `src/components/types.ts`; `src/api/transforms.ts` converts wire payloads
// into those domain shapes at the hook boundary.
// ============================================================================

// ----------------------------------------------------------------------------
// Projects
// ----------------------------------------------------------------------------

export interface ProjectSummary {
  id: string;
  name: string;
  description: string | null;
  industry_standard: string;
  is_pinned?: boolean;
  /** Dashboard ★ flag marker; independent of the sidebar pin. */
  is_flagged?: boolean;
  /** User-editable workflow status ('draft' | 'in_review_hpo' | 'in_review_po' | 'approved' | 'revised') shown on the dashboard table. */
  status?: string;
  /** ISO-8601 timestamp of the last project update (dashboard 'Updated' column). */
  updated_at?: string | null;
  /** Short excerpt of a matching conversation message, present only when the project matched via message content. */
  match_snippet?: string | null;
}

/** Request body for setting a project's user-editable workflow status (dashboard table). */
export interface ProjectStatusRequest {
  status: ProjectStatus;
}

/** Workflow statuses editable from the dashboard projects table. */
export type ProjectStatus = 'draft' | 'in_review_hpo' | 'in_review_po' | 'approved' | 'revised';

export interface ProjectCreated {
  id: string;
  name: string;
}

export interface ProjectDeleteResponse {
  status: string;
  project_id: string;
}

// ----------------------------------------------------------------------------
// User stories (as serialized by backend `serialize_user_story` + enrichment)
// ----------------------------------------------------------------------------

export interface UserStoryPayload {
  id?: string;
  project_id?: string;
  ticket_code: string;
  story_title: string;
  as_a: string;
  i_want_to: string;
  so_that: string;
  acceptance_criteria?: string[];
  status?: string;
  version?: number;
  last_modified_by?: string | null;
  change_type?: string | null;
  is_locked?: boolean;
  locked_by?: string | null;
  locked_at?: string | null;
}

// ----------------------------------------------------------------------------
// Requirements
// ----------------------------------------------------------------------------

export interface RequirementPayload {
  id?: string;
  project_id?: string;
  epic_id?: string | null;
  requirement_code: string;
  title: string;
  description?: string;
  status?: string;
  is_locked?: boolean;
  locked_by?: string | null;
  locked_at?: string | null;
  user_stories?: UserStoryPayload[];
}

// ----------------------------------------------------------------------------
// Clarification questions / audit results
// ----------------------------------------------------------------------------

export interface ClarificationQuestionPayload {
  id?: string;
  project_id?: string;
  checklist_category: string;
  target_user_story_id?: string | null;
  question_text: string;
  user_answer?: string | null;
  is_resolved?: boolean;
}

export interface AuditResultPayload {
  id?: string;
  project_id?: string;
  is_valid: boolean;
  audit_version_reviewed?: number;
  passed_checks: string[];
  failed_checks: string[];
  clarification_questions?: ClarificationQuestionPayload[];
}

// ----------------------------------------------------------------------------
// Conversation history
// ----------------------------------------------------------------------------

export interface ConversationMessagePayload {
  id: string;
  project_id?: string;
  role: string;
  message?: string;
  content?: string;
  workflow_state?: string;
  intent?: string;
  created_at: string;
  /** Legacy display timestamp used by the chat UI when created_at is missing. */
  timestamp?: string;
}

// ----------------------------------------------------------------------------
// Pending (merge) actions awaiting human confirmation
// ----------------------------------------------------------------------------

export interface PendingActionPayload {
  id: string;
  project_id: string;
  action_type: string;
  target_requirement_id?: string | null;
  original_user_message: string;
  /** Proposed merged requirement state. */
  proposed_changes?: Record<string, unknown>;
  affected_user_story_ids?: string[];
  affected_acceptance_criteria_ids?: string[];
  workflow_stage?: string;
  status?: string;
  expires_at?: string;
}

// ----------------------------------------------------------------------------
// Flattened requirement-state payload (`GET/PUT /api/project/{id}`,
// `POST /api/clarification/submit`)
// ----------------------------------------------------------------------------

/**
 * `requirements` is normally an array, but a few legacy code paths still emit a
 * single `{ epic_name }` object — the field type reflects that defensive shape.
 */
export type RequirementsField =
  | RequirementPayload[]
  | { epic_name?: string }
  | null
  | undefined;

export interface RequirementStatePayload {
  project_id?: string;
  project_name?: string | null;
  requirements?: RequirementsField;
  business_goals?: Array<string | Record<string, unknown>>;
  actors?: Array<string | Record<string, unknown>>;
  user_stories?: UserStoryPayload[];
  acceptance_criteria?: Array<string | Record<string, unknown>>;
  clarification_questions?: ClarificationQuestionPayload[];
  validation_status?: string | null;
  generated_prd?: string;
  generated_diagrams?: string;
  current_workflow_state?: string | null;
  version_number?: number;
  updated_at?: string | null;
  conversation_history?: ConversationMessagePayload[];
}

// ----------------------------------------------------------------------------
// `POST /api/process-requirements`
// ----------------------------------------------------------------------------

export interface ProcessRequirementsRequest {
  project_id: string;
  raw_input?: string;
  current_version?: number;
  version_history_summaries?: string;
  target_agent?: string;
  structured_requirements?: Record<string, unknown>;
}

export interface GatheredRequirementsPayload {
  epic_name?: string;
  version?: number;
  user_stories?: UserStoryPayload[];
  requirements?: RequirementPayload[];
  [key: string]: unknown;
}

export interface ProcessRequirementsResponse {
  status: string;
  detected_intent?: string | null;
  workflow_routing?: Record<string, unknown> | null;
  structured_requirements?: GatheredRequirementsPayload | null;
  audit_result?: AuditResultPayload | null;
  prd_markdown?: string | null;
  mermaid_diagram?: string | null;
  message?: string | null;
  pending_merge?: boolean | null;
  pending_action_id?: string | null;
  conversation_history?: ConversationMessagePayload[];
  [key: string]: unknown;
}

// ----------------------------------------------------------------------------
// Locks
// ----------------------------------------------------------------------------

export interface ArtifactLockMetadata {
  id?: string;
  artifact_type?: string;
  artifact_id?: string;
  is_locked: boolean;
  locked_by?: string | null;
  locked_at?: string | null;
}

export interface ArtifactLockResponse {
  status: string;
  artifact: ArtifactLockMetadata | Record<string, unknown>;
}

// ----------------------------------------------------------------------------
// Health probe (`GET /api/health`)
// ----------------------------------------------------------------------------

export interface HealthPayload {
  status: string;
  app_name: string;
  local_inference_gateway: string;
  macbook_context_window_budget: string;
  lm_studio_online: boolean;
  lm_studio_model?: string | null;
  lm_studio_model_loaded: boolean;
  lm_studio_loaded_models: string[];
  lm_studio_latency_ms?: number | null;
  lm_studio_error?: string | null;
  lm_studio_last_checked?: string | null;
}

// ----------------------------------------------------------------------------
// Action confirmation responses
// ----------------------------------------------------------------------------

export interface ConfirmActionResponse {
  status: string;
  requirement_state?: RequirementStatePayload;
}

export interface ActionStatusResponse {
  status: string;
}

// ----------------------------------------------------------------------------
// Uploaded documents (`/api/project/{id}/documents/*`)
//
// Uploading ONLY adds knowledge-base source material; extraction is a separate,
// explicit action whose output stays a DRAFT pending_action until confirmed.
// ----------------------------------------------------------------------------

export type DocumentFormat = 'docx' | 'pdf' | 'md' | 'txt';

export interface UploadedDocumentPayload {
  id: string;
  project_id: string;
  original_filename: string;
  original_format: DocumentFormat | string;
  mime_type?: string | null;
  content_markdown?: string | null;
  file_size_bytes: number;
  token_count: number;
  status: 'processed' | 'failed' | string;
  uploaded_by: string;
  extraction_status: 'not_extracted' | 'extraction_pending' | 'extraction_applied' | string;
  created_at: string;
  updated_at: string;
  /** Present on scanned-PDF failures: explicit needs-OCR message. */
  message?: string | null;
}

export interface DocumentMarkdownPayload extends UploadedDocumentPayload {
  content_markdown: string;
}

export interface ProcessDocumentResponse {
  status: 'draft_ready' | 'failed' | string;
  mode: 'full' | 'chunked' | string;
  chunk_count: number;
  processed_tokens: number;
  pending_action_id?: string | null;
  excluded_anything: boolean;
  document_id: string;
  message?: string | null;
}

export interface DocumentDeleteResponse {
  status: string;
  document_id: string;
  project_id: string;
  original_filename: string;
}

// ----------------------------------------------------------------------------
// PRD preview normalization (`POST /api/prd/convert`)
//
// Generated PRDs are Krungsri LaTeX bodies; this endpoint turns them (or a
// legacy Markdown PRD) into clean GFM markdown so the on-screen preview never
// renders raw LaTeX.
// ----------------------------------------------------------------------------

export interface ConvertedPrdMarkdownPayload {
  markdown: string;
  source_kind: 'latex' | 'markdown' | string;
}

// ----------------------------------------------------------------------------
// PRD sections (`/api/project/{id}/prd/sections/*`)
//
// The PRD is a COLLECTION of editable, lockable, versioned PARTS (the nine
// preview parts). `section_key` matches the preview section ids produced by
// `parsePRDToSections` ('title', 'stakeholders', 'version_history', 'reviews',
// 'contents', 'business_overview', 'product_scope', 'tech_ops', 'appendix').
// ----------------------------------------------------------------------------

export interface PrdSectionPayload {
  id: string;
  project_id: string;
  section_key: string;
  title: string;
  content: string;
  section_order: number;
  /** 'template' | 'ai' | 'human' — who owns the content. */
  content_source: 'template' | 'ai' | 'human' | string;
  /** False => the Architect agent never regenerates this part. */
  ai_generatable: boolean;
  /** 'draft' | 'satisfied' | 'approved'. */
  review_status: string;
  is_locked: boolean;
  locked_by?: string | null;
  locked_at?: string | null;
  /** Latest version number in prd_section_versions. */
  version_number?: number | null;
  created_at: string;
  updated_at: string;
}

export interface PrdSectionListPayload {
  project_id: string;
  sections: PrdSectionPayload[];
}

export interface PrdSectionUpdateResponse {
  section: PrdSectionPayload;
  /** Full PRD markdown stitched from ALL parts after the edit. */
  document_markdown: string;
}


// ----------------------------------------------------------------------------
// PRD version ledger (`/api/project/{id}/prd-versions*`)
//
// EVERY document change — an AI regeneration or a manual part edit/revert —
// appends an immutable `prd_versions` snapshot. The version ALWAYS advances,
// and each snapshot carries `change_type` ('ai' | 'manual'), a change summary
// and the per-section change records (incl. `locked_preserved` markers proving
// the lock contract was honoured).
// ----------------------------------------------------------------------------

export interface PrdVersionChangedSection {
  section_key: string;
  title: string;
  /** 'created' | 'updated' | 'unchanged' | 'removed' | 'locked_preserved'. */
  change_kind: string;
  changed: boolean;
}

export interface PrdVersionPayload {
  version_id: string;
  project_id: string;
  version_number: number;
  /** Semantic Version (MAJOR.MINOR.PATCH): MAJOR = sections created/removed,
   *  MINOR = AI content updates, PATCH = manual edits / no-change advances. */
  semver: string;
  /** Full PRD markdown snapshot at this version (used for diffing / restore). */
  generated_prd: string;
  generated_by: string;
  /** 'ai' | 'manual' — origin of the snapshot. */
  change_type: string;
  change_summary: string | null;
  changed_sections: PrdVersionChangedSection[] | null;
  created_at: string;
}

export interface PrdVersionDiffSectionPayload {
  section_key: string;
  title: string;
  change_kind: string;
  changed: boolean;
  added: number;
  removed: number;
  /** Diff lines: [['add'|'del'|'context', line], ...]. */
  diff_lines: [string, string][];
}

export interface PrdVersionDiffPayload {
  project_id: string;
  to_version: number;
  base_version: number;
  sections: PrdVersionDiffSectionPayload[];
}

export interface PrdVersionRestorePayload {
  /** Ledger version number the document was restored from. */
  restored_from_version: number;
  /** The NEW version number appended for this restore (append-only ledger). */
  new_version_number: number;
  /** Semantic version of the NEW appended snapshot. */
  semver: string;
  /** Full PRD markdown after the restore (locked sections preserved). */
  document_markdown: string;
  restored_sections: number;
  preserved_locked_sections: number;
}


// ============================================================================
// Requirement Traceability Matrix (derived, read-only)
// GET /api/project/{id}/traceability — links Requirements <-> User Stories
// <-> Acceptance Criteria <-> PRD sections <-> diagrams via FKs + REQ-/US- code
// references inside section content and mermaid source. See
// backend/app/traceability_service.py for how links are derived.
// ============================================================================
export interface TraceabilityRequirementInfo {
  id: string;
  requirement_code: string;
  title: string;
  description: string;
  epic_name?: string | null;
  status?: string | null;
  version?: number | null;
  is_locked: boolean;
}

export interface TraceabilityStory {
  id?: string | null;
  ticket_code?: string | null;
  story_title?: string | null;
  as_a?: string | null;
  i_want_to?: string | null;
  so_that?: string | null;
  acceptance_criteria: string[];
  is_locked: boolean;
}

export interface TraceabilityRow {
  requirement: TraceabilityRequirementInfo;
  user_stories: TraceabilityStory[];
  /** PRD section keys referencing this requirement (or its stories). */
  prd_sections: string[];
  /** Diagram labels referencing this requirement (e.g. 'PRD v3'). */
  diagrams: string[];
  /** True when the requirement has stories with criteria AND a section reference. */
  traced: boolean;
}

export interface TraceabilityDiagram {
  label: string;
  version: number;
}

export interface StaleCodeReference {
  code: string;
  section_keys?: string[];
  diagrams?: string[];
}

export interface TraceabilityCoverage {
  total_requirements: number;
  total_user_stories: number;
  total_acceptance_criteria: number;
  traced_requirements: number;
  requirements_without_stories: string[];
  requirements_without_prd_sections: string[];
  requirements_without_diagram: string[];
  stories_without_criteria: string[];
  stories_without_prd_sections: string[];
  stale_section_references: StaleCodeReference[];
  stale_diagram_references: StaleCodeReference[];
}

export interface TraceabilityPayload {
  project_id: string;
  rows: TraceabilityRow[];
  diagrams: TraceabilityDiagram[];
  coverage: TraceabilityCoverage;
}

