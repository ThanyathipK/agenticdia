// Shared domain types used across the Requirements Engine workspace.
// Extracted from the former monolithic Dashboard.tsx so every split module
// (ChatPanel, PRDEditor, VersionHistory, MarkdownRenderer, DocxExporter,
// useProjectState) can share one source of truth.

export interface UserStory {
  ticket_code: string;
  story_title: string;
  as_a: string;
  i_want_to: string;
  so_that: string;
  acceptance_criteria: string[];
}

export interface RequirementItem {
  id?: string;
  requirement_code: string;
  title: string;
  description?: string;
  user_stories: UserStory[];
  is_locked?: boolean;
  locked_by?: string | null;
  locked_at?: string | null;
}

export interface StructuredRequirements {
  epic_name: string;
  version: number;
  user_stories: UserStory[];
  requirements?: RequirementItem[];
}

export interface ClarificationQuestion {
  checklist_category: string;
  target_user_story_id?: string | null;
  question_text: string;
  user_answer?: string | null;
  is_resolved?: boolean;
}

export interface AuditResult {
  is_valid: boolean;
  audit_version_reviewed: number;
  passed_checks: string[];
  failed_checks: string[];
  clarification_questions?: ClarificationQuestion[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'gatherer' | 'auditor' | 'architect' | string;
  content: string;
  timestamp: string;
  isPendingClarifications?: boolean;
  auditResultSnapshot?: AuditResult;
}

export interface VersionHistory {
  version: number;
  timestamp: string;
  author: string;
  description: string;
  requirementsSnapshot: StructuredRequirements;
}

// PRD Section Types and helper utilities
export interface PRDSection {
  id: string;
  title: string;
  content: string;
}

// Optimistic lock state tracked in the UI for generic artifacts.
export interface ArtifactLockState {
  is_locked: boolean;
  locked_by?: string | null;
  locked_at?: string | null;
  lock_reason?: string | null;
}

// Optimistic lock state tracked in the UI keyed by requirement code.
export interface RequirementLockState {
  is_locked: boolean;
  locked_by?: string | null;
  locked_at?: string | null;
  artifact_id?: string;
}
