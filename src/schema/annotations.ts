// ============================================================================
// annotations.ts — human-authored schema documentation.
//
// Everything structurally derivable from the canonical DDL (backend/init.sql)
// lives in the parser output (see ./parseDdl.ts). What does NOT live in the DDL
// — the business-facing table `description`, `bankingContext`, and per-column
// descriptions — lives here so that the single source of truth stays the DDL
// while the Explorer keeps its rich, human-written copy.
//
// `enrichSchema(...)` merges these annotations onto the parsed structure to
// produce the `TableSchema[]` that the Schema Explorer renders.
// ============================================================================

import type { ParsedTableSchema, TableSchema } from './types';

export interface TableAnnotations {
  description: string;
  bankingContext: string;
  columns: Record<string, string>;
}

/**
 * Human-authored documentation keyed by table name.
 */
export const SCHEMA_ANNOTATIONS: Record<string, TableAnnotations> = {
  users: {
    description: `Stores information on banking stakeholders, product owners, and business analysts.`,
    bankingContext: `Maintains digital identity & RBAC (Role-Based Access Control) for audit trail attribution, ensuring clear accountability for requirement changes.`,
    columns: {
      id: `Enterprise unique identifier for the user.`,
      email: `Corporate email address for notification routing.`,
      full_name: `Legal name of the corporate user.`,
      role: `Internal RBAC role: Product Owner, Business Analyst, Auditor, etc.`,
      created_at: `Audit trail creation date (with timezone info).`,
      updated_at: `Modified date synced via automation trigger.`,
    },
  },
  projects: {
    description: `Stores banking systems, digital products, and core-banking project contexts.`,
    bankingContext: `Represents the boundary of compliance (e.g., Krungsri Nimble standards). Essential for grouping user stories under regulatory frameworks.`,
    columns: {
      id: `Unique project ID.`,
      user_id: `Lead analyst or owner of the banking product.`,
      name: `System or microservice name (e.g., Loan Originator System).`,
      description: `High-level business context and scope definitions.`,
      industry_standard: `Compliance guideline baseline (e.g., Krungsri Nimble).`,
      is_locked: `Audit lock flag. When TRUE, project-level mutations are blocked.`,
      locked_by: `Corporate stakeholder or agent that applied the lock.`,
      locked_at: `UTC timestamp when the lock was applied.`,
      lock_reason: `Justification for the lock (e.g., External Audit, Migration).`,
      created_at: `Timezone-aware initialization timestamp.`,
      updated_at: `System modification tracker timestamp.`,
    },
  },
  epics: {
    description: `High-level business capabilities or features that group related requirements.`,
    bankingContext: `Serves as the primary compliance checkpoint for banking features. Can be locked/unlocked to freeze active requirements during formal internal audits.`,
    columns: {
      id: `Epic unique identifier.`,
      project_id: `Parent banking project association.`,
      epic_name: `Feature scope name (e.g., Multi-factor Transaction Authorization).`,
      version: `Auto-incrementing epic iteration number.`,
      is_locked: `Audit lock flag. When TRUE, modifications are blocked.`,
      locked_by: `Corporate stakeholder or agent that applied the lock.`,
      locked_at: `UTC timestamp when the lock was applied.`,
      lock_reason: `Justification for the lock (e.g., External Audit, Migration).`,
      created_at: `Date epic created.`,
      updated_at: `Date epic was last edited or locked.`,
      status: `Lifecycle status: active, archived, deprecated.`,
    },
  },
  requirements: {
    description: `Detailed functional and non-functional requirements derived from epics.`,
    bankingContext: `Granular compliance units that map to specific regulatory needs. Each requirement is versioned and traceable to an epic for audit purposes.`,
    columns: {
      id: `Requirement unique identifier.`,
      project_id: `Parent banking project association.`,
      epic_id: `Parent epic reference for hierarchical organization.`,
      requirement_code: `Unique requirement identifier (e.g., REQ-001).`,
      title: `Short descriptive title of the requirement.`,
      description: `Detailed functional or non-functional specification.`,
      status: `Lifecycle status: active, deprecated, superseded.`,
      version: `Current version number for change tracking.`,
      is_locked: `Audit lock flag. When TRUE, modifications are blocked.`,
      locked_by: `Corporate stakeholder or agent that applied the lock.`,
      locked_at: `UTC timestamp when the lock was applied.`,
      lock_reason: `Justification for the lock (e.g., External Audit, Migration).`,
      created_at: `Date requirement was created.`,
      updated_at: `Date requirement was last modified.`,
    },
  },
  user_stories: {
    description: `Captures Agile user stories formatted according to banking compliance standards.`,
    bankingContext: `Detailed banking business rules written as "As a / I want to / So that" templates, validating user actions against core security models.`,
    columns: {
      id: `Unique story key.`,
      project_id: `Project association for multi-tenant filtering.`,
      requirement_id: `Parent requirement identifier.`,
      ticket_code: `Banking ticketing mapping (e.g. US-001, LN-402).`,
      story_title: `Name of user task.`,
      as_a: `Role actor (e.g., Risk Officer, Retail Customer).`,
      i_want_to: `The banking action requested.`,
      so_that: `The compliant banking goal/outcome achieved.`,
      status: `Lifecycle status: active, archived, deprecated.`,
      version: `Current version for change tracking.`,
      last_modified_by: `Entity that last modified this record.`,
      change_type: `Type of last change: created, updated, deleted.`,
      is_locked: `Audit lock flag. When TRUE, modifications are blocked.`,
      locked_by: `Corporate stakeholder or agent that applied the lock.`,
      locked_at: `UTC timestamp when the lock was applied.`,
      lock_reason: `Justification for the lock (e.g., External Audit, Migration).`,
      created_at: `Creation date.`,
      updated_at: `Last modification timestamp.`,
    },
  },
  acceptance_criteria: {
    description: `Given-When-Then specification for verifying banking behavior.`,
    bankingContext: `Direct translation of regulatory guidelines into verifiable, machine-inspectable behavior statements. Eliminates functional ambiguities.`,
    columns: {
      id: `Unique criteria ID.`,
      user_story_id: `Mapped user story.`,
      criteria_text: `Given-When-Then criteria block.`,
      status: `Lifecycle status: active, archived, deprecated.`,
      version: `Current version for change tracking.`,
      last_modified_by: `Entity that last modified this record.`,
      change_type: `Type of last change: created, updated, deleted.`,
      is_locked: `Audit lock flag. When TRUE, modifications are blocked.`,
      locked_by: `Corporate stakeholder or agent that applied the lock.`,
      locked_at: `UTC timestamp when the lock was applied.`,
      lock_reason: `Justification for the lock (e.g., External Audit, Migration).`,
      created_at: `Creation timestamp.`,
      updated_at: `Last modification timestamp.`,
    },
  },

audit_results: {
    description: `Tracks checking runs on requirement drafts, validating compliance.`,
    bankingContext: `Automated/manual verification ledger marking passed rules, failed checks, and identifying issues requiring resolution prior to production release.`,
    columns: {
      id: `Audit report ID.`,
      requirement_id: `Audited requirement reference.`,
      audit_version_reviewed: `The requirement version snapshot index analyzed.`,
      is_valid: `Whether the requirement matches all regulations.`,
      passed_checks: `Array of validated compliance checks.`,
      failed_checks: `Array of failed compliance parameters.`,
      created_at: `Time audit was compiled.`,
      updated_at: `Time audit was last modified.`,
    },
  },
  clarification_questions: {
    description: `Stores query logs and compliance verification dialogues regarding requirements.`,
    bankingContext: `Closes the loop between banking developers and compliance officers. Ensures unresolved items are formally tracked and resolved.`,
    columns: {
      id: `Unique question ID.`,
      audit_result_id: `Triggering audit report reference.`,
      checklist_category: `E.g., Security, Regulatory, Edge Case.`,
      target_user_story_id: `Specific target story queried.`,
      question_text: `System or expert drafted compliance query.`,
      user_answer: `Official stakeholder resolution reply.`,
      is_resolved: `Lock resolver status.`,
      is_locked: `Audit lock flag. When TRUE, modifications are blocked.`,
      locked_by: `Corporate stakeholder or agent that applied the lock.`,
      locked_at: `UTC timestamp when the lock was applied.`,
      lock_reason: `Justification for the lock (e.g., External Audit, Migration).`,
      created_at: `Date logged.`,
      updated_at: `Date last modified.`,
    },
  },
  prd_documents: {
    description: `Compiled final Production PRDs with markdown explanations and system diagrams.`,
    bankingContext: `Official corporate PRD artifacts exported as verified baselines for software architects and compliance review councils.`,
    columns: {
      id: `PRD Document ID.`,
      project_id: `Target banking system.`,
      version: `Target build index.`,
      prd_markdown: `Compiled functional specifications in markdown.`,
      mermaid_diagram: `Live architecture diagram schema.`,
      is_locked: `Audit lock flag. When TRUE, modifications are blocked.`,
      locked_by: `Corporate stakeholder or agent that applied the lock.`,
      locked_at: `UTC timestamp when the lock was applied.`,
      lock_reason: `Justification for the lock (e.g., External Audit, Migration).`,
      created_at: `Export generation date.`,
      updated_at: `Last modification timestamp.`,
    },
  },
  prd_versions: {
    description: `Immutable version history for generated PRDs. Each PRD generation creates a new record; previous versions are never overwritten.`,
    bankingContext: `Provides immutable traceability for every PRD artifact produced by the system, satisfying immutable-audit requirements.`,
    columns: {
      id: `PRD version record ID.`,
      project_id: `Related banking project.`,
      version_number: `Sequential PRD version for this project.`,
      generated_prd: `Full generated PRD markdown at this version.`,
      generated_by: `Agent or user that produced this version.`,
      created_at: `Timestamp this version was created.`,
    },
  },
  conversation_messages: {
    description: `Persists every conversation message per project for chat/voice audit and replay.`,
    bankingContext: `Supports regulatory replay and customer-interaction audit trails by storing every inbound and outbound message with workflow context.`,
    columns: {
      id: `Message unique identifier.`,
      project_id: `Project context for multi-tenant isolation.`,
      role: `Speaker role: user, assistant, system.`,
      message: `Full message content.`,
      workflow_state: `Current workflow or FSM state at time of message.`,
      intent: `Detected user intent classification.`,
      created_at: `Timestamp the message was recorded.`,
    },
  },
  artifact_event_logs: {
    description: `Immutable append-only event log tracking every artifact mutation across the platform.`,
    bankingContext: `Provides tamper-evident traceability for all CREATE/UPDATE/DELETE/ARCHIVE/LOCK/UNLOCK actions on banking artifacts.`,
    columns: {
      event_id: `Unique event log entry ID.`,
      artifact_type: `Type of artifact mutated: epic, requirement, user_story, acceptance_criteria, prd.`,
      artifact_id: `UUID of the artifact that was mutated.`,
      action: `CREATE, UPDATE, DELETE, ARCHIVE, LOCK, UNLOCK.`,
      old_value: `Full artifact snapshot before the change.`,
      new_value: `Full artifact snapshot after the change.`,
      performed_by: `User or agent that triggered the change.`,
      timestamp: `When the mutation occurred.`,
    },
  },
};


/**
 * Merge parsed (canonical, DDL-derived) schema structure with the human-authored
 * annotations to produce the enriched `TableSchema[]` the Explorer renders.
 *
 * Any table/column missing an annotation falls back to an empty string rather
 * than dropping out, so the explorer always shows every column the DDL declares.
 */
export function enrichSchema(
  parsed: ParsedTableSchema[],
  annotations: Record<string, TableAnnotations>,
): TableSchema[] {
  return parsed.map((table) => {
    const meta = annotations[table.name];
    return {
      name: table.name,
      description: meta?.description ?? '',
      bankingContext: meta?.bankingContext ?? '',
      columns: table.columns.map((col) => ({
        name: col.name,
        type: col.type,
        constraints: col.constraints,
        ...(col.defaultValue !== undefined ? { defaultValue: col.defaultValue } : {}),
        description: meta?.columns?.[col.name] ?? '',
      })),
      indexes: table.indexes,
      relations: table.relations,
    };
  });
}

