// ============================================================================
// Frontend data layer for the Schema Explorer.
//
// `TABLES` (the schema metadata the explorer renders) is DERIVED from the single
// source of truth, backend/init.sql, which Vite imports via the `?raw` suffix
// (the same import the DDL viewer uses). ./schema/parseDdl parses the table /
// column / index / relation structure out of that DDL, and ./schema/annotations
// attaches the human-authored descriptions & banking context that are not part
// of the DDL. This guarantees the explorer can never display a schema that has
// drifted from the deployed Postgres DDL.
//
// The `*Row` types + `INITIAL_*` constants below are the simulated seed / state
// projections used by the in-browser datagrid (they are DATA, not schema).
// ============================================================================

import initSqlText from '../backend/init.sql?raw';
import { parseDdl } from './schema/parseDdl';
import { SCHEMA_ANNOTATIONS, enrichSchema } from './schema/annotations';
import type { TableSchema } from './schema/types';

// Re-export schema type contracts so existing consumers keep working
// (e.g. `import { TableSchema } from '../../data'`).
export type { ColumnDefinition, TableSchema } from './schema/types';

/**
 * Schema metadata shown by the Table Schema Explorer.
 * Structure is parsed from backend/init.sql (canonical); human-authored
 * descriptions & banking context are merged in from SCHEMA_ANNOTATIONS.
 */
export const TABLES: TableSchema[] = enrichSchema(parseDdl(initSqlText), SCHEMA_ANNOTATIONS);

export type UserRow = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  created_at: string;
}

export type ProjectRow = {
  id: string;
  user_id: string;
  name: string;
  description: string;
  industry_standard: string;
  is_locked: boolean;
  locked_by: string | null;
  locked_at: string | null;
  lock_reason: string | null;
  created_at: string;
}

export type EpicRow = {
  id: string;
  project_id: string;
  epic_name: string;
  version: number;
  is_locked: boolean;
  status: string;
  created_at: string;
}

export type RequirementRow = {
  id: string;
  project_id: string;
  epic_id: string | null;
  requirement_code: string;
  title: string;
  description: string;
  priority: string | null;
  status: string;
  version: number;
  is_locked: boolean;
  locked_by: string | null;
  locked_at: string | null;
  lock_reason: string | null;
  created_at: string;
}

export type UserStoryRow = {
  id: string;
  project_id: string | null;
  requirement_id: string;
  ticket_code: string;
  story_title: string;
  as_a: string;
  i_want_to: string;
  so_that: string;
  status: string;
  version: number;
  last_modified_by: string;
  change_type: string;
  is_locked: boolean;
  locked_by: string | null;
  locked_at: string | null;
  lock_reason: string | null;
  created_at: string;
}

export type AcceptanceCriterionRow = {
  id: string;
  user_story_id: string;
  criteria_text: string;
  status: string;
  version: number;
  last_modified_by: string;
  change_type: string;
  is_locked: boolean;
  locked_by: string | null;
  locked_at: string | null;
  lock_reason: string | null;
  created_at: string;
}

export type AuditResultRow = {
  id: string;
  requirement_id: string;
  audit_version_reviewed: number;
  is_valid: boolean;
  passed_checks: string; // JSON string
  failed_checks: string; // JSON string
  created_at: string;
}

export type ClarificationQuestionRow = {
  id: string;
  audit_result_id: string;
  checklist_category: string;
  target_user_story_id: string | null;
  question_text: string;
  user_answer: string | null;
  is_resolved: boolean;
  is_locked: boolean;
  locked_by: string | null;
  locked_at: string | null;
  lock_reason: string | null;
  created_at: string;
}

export type PrdDocumentRow = {
  id: string;
  project_id: string;
  version: number;
  prd_markdown: string;
  mermaid_diagram: string | null;
  is_locked: boolean;
  locked_by: string | null;
  locked_at: string | null;
  lock_reason: string | null;
  created_at: string;
}

export type VersionHistoryRow = {
  id: string;
  project_id: string;
  requirement_id: string;
  version_number: number;
  changed_by_user_id: string;
  change_description: string;
  state_snapshot: string; // JSON string representation
  created_at: string;
}

export type PrdVersionRow = {
  id: string;
  project_id: string;
  version_number: number;
  generated_prd: string;
  generated_diagram: string | null;
  generated_by: string;
  created_at: string;
}

export type ConversationMessageRow = {
  id: string;
  conversation_id: string | null;
  project_id: string;
  role: string;
  message: string;
  workflow_state: string;
  intent: string;
  created_at: string;
}

export type ArtifactEventLogRow = {
  event_id: string;
  artifact_type: string;
  artifact_id: string;
  action: string;
  old_value: string | null; // JSON string
  new_value: string | null; // JSON string
  performed_by: string;
  timestamp: string;
}

/**
 * Generic shape used by the Schema Explorer's simulated datagrid.
 *
 * The grid renders rows across many heterogeneous tables and reads arbitrary
 * columns dynamically (`row[col.name]`), so an index signature is included.
 * The explicit optional fields cover the columns shared across several tables
 * that the grid accesses directly. Note that not every table has an `id`
 * (e.g. `ArtifactEventLogRow` uses `event_id`), hence `id` is optional.
 *
 * Every concrete row type (`UserRow`, `ProjectRow`, ...) is structurally
 * assignable to this shape, which lets the datagrid drop the previous `any`
 * typing while keeping the code type-safe.
 */
export interface GridRow {
  id?: string;
  epic_id?: string | null;
  is_locked?: boolean;
  [key: string]: unknown;
}

export const INITIAL_USERS: UserRow[] = [
  { id: 'u1111111-2222-3333-4444-555555555555', email: 'anond.k@krungsri-nimble.com', full_name: 'Anond Kittisiri', role: 'Business Analyst Lead', created_at: '2026-07-09T08:00:00Z' },
  { id: 'u2222222-2222-3333-4444-555555555555', email: 'siriporn.t@krungsri.com', full_name: 'Siriporn Thanakit', role: 'Product Owner', created_at: '2026-07-09T08:15:00Z' },
  { id: 'u3333333-2222-3333-4444-555555555555', email: 'compliance.auditor@sec.or.th', full_name: 'Dr. Thana Viroj', role: 'Regulatory Auditor', created_at: '2026-07-09T09:00:00Z' }
];

export const INITIAL_PROJECTS: ProjectRow[] = [
  {
    id: 'p1111111-1111-4444-8888-999999999999',
    user_id: 'u2222222-2222-3333-4444-555555555555',
    name: 'Krungsri FastPay Gateway',
    description: 'High-throughput payment gateway conforming to national instant settlement protocols and PCI-DSS standards.',
    industry_standard: 'Krungsri Nimble Baseline',
    is_locked: false,
    locked_by: null,
    locked_at: null,
    lock_reason: null,
    created_at: '2026-07-09T10:00:00Z'
  },
  {
    id: 'p2222222-2222-4444-8888-999999999999',
    user_id: 'u1111111-2222-3333-4444-555555555555',
    name: 'Nimble Ledger Hub',
    description: 'Double-entry general ledger service providing near-real-time compliance checks & immutable transaction state.',
    industry_standard: 'ISO-20022 Financial',
    is_locked: true,
    locked_by: 'compliance.auditor@sec.or.th',
    locked_at: '2026-07-09T11:35:00Z',
    lock_reason: 'Pending ISO-20022 certification audit',
    created_at: '2026-07-09T11:30:00Z'
  }
];

export const INITIAL_EPICS: EpicRow[] = [
  {
    id: 'e1111111-3333-4444-9999-aaaaaaaaaaaa',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    epic_name: 'Multi-factor Transaction Authorization',
    version: 2,
    is_locked: false,
    status: 'active',
    created_at: '2026-07-09T10:30:00Z'
  },
  {
    id: 'e2222222-3333-4444-9999-aaaaaaaaaaaa',
    project_id: 'p2222222-2222-4444-8888-999999999999',
    epic_name: 'ISO-20022 Message Validation Engine',
    version: 1,
    is_locked: true,
    status: 'active',
    created_at: '2026-07-09T12:00:00Z'
  }
];

export const INITIAL_REQUIREMENTS: RequirementRow[] = [
  {
    id: 'r1111111-3333-4444-9999-bbbbbbbbbbbb',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    epic_id: 'e1111111-3333-4444-9999-aaaaaaaaaaaa',
    requirement_code: 'REQ-PAY-001',
    title: 'Multi-factor Transaction Authorization',
    description: 'All high-value transactions must validate users via OTP or biometric authentication before execution.',
    priority: 'Critical',
    status: 'active',
    version: 2,
    is_locked: false,
    locked_by: null,
    locked_at: null,
    lock_reason: null,
    created_at: '2026-07-09T10:30:00Z'
  },
  {
    id: 'r2222222-3333-4444-9999-bbbbbbbbbbbb',
    project_id: 'p2222222-2222-4444-8888-999999999999',
    epic_id: 'e2222222-3333-4444-9999-aaaaaaaaaaaa',
    requirement_code: 'REQ-LED-001',
    title: 'ISO-20022 Message Validation Engine',
    description: 'Validate all inbound inter-bank messages against the pain.001.001.08 XML Schema Definition.',
    priority: 'High',
    status: 'active',
    version: 1,
    is_locked: true,
    locked_by: 'compliance.auditor@sec.or.th',
    locked_at: '2026-07-09T12:05:00Z',
    lock_reason: 'External audit in progress',
    created_at: '2026-07-09T12:00:00Z'
  }
];

export const INITIAL_USER_STORIES: UserStoryRow[] = [
  {
    id: 'us111111-4444-4444-9999-bbbbbbbbbbbb',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    requirement_id: 'r1111111-3333-4444-9999-bbbbbbbbbbbb',
    ticket_code: 'US-PAY-001',
    story_title: 'Secure OTP Validation',
    as_a: 'Retail Banking Customer initiating a fund transfer over 100,000 THB',
    i_want_to: 'be prompted to verify my transaction with an OTP code generated by my registered Authenticator app',
    so_that: 'the system verifies my active presence and protects my account balance from unauthorized access.',
    status: 'active',
    version: 1,
    last_modified_by: 'automated_agent',
    change_type: 'created',
    is_locked: false,
    locked_by: null,
    locked_at: null,
    lock_reason: null,
    created_at: '2026-07-09T10:45:00Z'
  },
  {
    id: 'us222222-4444-4444-9999-bbbbbbbbbbbb',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    requirement_id: 'r1111111-3333-4444-9999-bbbbbbbbbbbb',
    ticket_code: 'US-PAY-002',
    story_title: 'MFA Grace Periods & Caching',
    as_a: 'Corporate Accountant performing batch transfers within a single browser session',
    i_want_to: 'exempt transfers from re-triggering MFA within a 5-minute validated grace period',
    so_that: 'batch execution performance and administrative ergonomics are optimized without exposing the channel to session hijacking.',
    status: 'active',
    version: 1,
    last_modified_by: 'automated_agent',
    change_type: 'created',
    is_locked: false,
    locked_by: null,
    locked_at: null,
    lock_reason: null,
    created_at: '2026-07-09T11:00:00Z'
  },
  {
    id: 'us333333-4444-4444-9999-bbbbbbbbbbbb',
    project_id: 'p2222222-2222-4444-8888-999999999999',
    requirement_id: 'r2222222-3333-4444-9999-bbbbbbbbbbbb',
    ticket_code: 'US-LED-001',
    story_title: 'ISO XML Schema Validation',
    as_a: 'Core Clearing Service handling inter-bank messages',
    i_want_to: 'strictly validate all inbound payloads against the pain.001.001.08 XML Schema Definition',
    so_that: 'malformed bank messages are rejected immediately before reaching core ledger queues.',
    status: 'active',
    version: 1,
    last_modified_by: 'automated_agent',
    change_type: 'created',
    is_locked: true,
    locked_by: 'compliance.auditor@sec.or.th',
    locked_at: '2026-07-09T12:20:00Z',
    lock_reason: 'Pending ISO validation',
    created_at: '2026-07-09T12:15:00Z'
  }
];

export const INITIAL_ACCEPTANCE_CRITERIA: AcceptanceCriterionRow[] = [
  {
    id: 'ac111111-5555-4444-9999-cccccccccccc',
    user_story_id: 'us111111-4444-4444-9999-bbbbbbbbbbbb',
    criteria_text: 'GIVEN the customer balance is valid and the transfer amount exceeds 100,000 THB\nWHEN they click "Confirm Transfer"\nTHEN the system suspends transaction execution and dispatches an authenticating challenge modal.',
    status: 'active',
    version: 1,
    last_modified_by: 'automated_agent',
    change_type: 'created',
    is_locked: false,
    locked_by: null,
    locked_at: null,
    lock_reason: null,
    created_at: '2026-07-09T10:50:00Z'
  },
  {
    id: 'ac222222-5555-4444-9999-cccccccccccc',
    user_story_id: 'us111111-4444-4444-9999-bbbbbbbbbbbb',
    criteria_text: 'GIVEN the authenticator challenge screen is visible\nWHEN the customer inputs a valid 6-digit dynamic token within 180 seconds\nTHEN the transaction is authorized, submitted to clearance queues, and an audit trail user reference logged.',
    status: 'active',
    version: 1,
    last_modified_by: 'automated_agent',
    change_type: 'created',
    is_locked: false,
    locked_by: null,
    locked_at: null,
    lock_reason: null,
    created_at: '2026-07-09T10:52:00Z'
  },
  {
    id: 'ac333333-5555-4444-9999-cccccccccccc',
    user_story_id: 'us333333-4444-4444-9999-bbbbbbbbbbbb',
    criteria_text: 'GIVEN an incoming inter-bank transfer request\nWHEN the payload lacks the <GrpHdr> or <PmtInf> tag\nTHEN the clearing service raises a rejection code "ERR_ISO_SCHEMA_INTEGRITY" and halts internal queue processing.',
    status: 'active',
    version: 1,
    last_modified_by: 'automated_agent',
    change_type: 'created',
    is_locked: true,
    locked_by: 'compliance.auditor@sec.or.th',
    locked_at: '2026-07-09T12:25:00Z',
    lock_reason: 'Awaiting ISO compliance sign-off',
    created_at: '2026-07-09T12:20:00Z'
  }
];

export const INITIAL_AUDIT_RESULTS: AuditResultRow[] = [
  {
    id: 'ar111111-6666-4444-9999-dddddddddddd',
    requirement_id: 'r1111111-3333-4444-9999-bbbbbbbbbbbb',
    audit_version_reviewed: 1,
    is_valid: false,
    passed_checks: JSON.stringify([
      { rule: 'PRIMARY_KEY_UUID', message: 'All stories and criteria are correctly referenced using UUID v4 keys.' },
      { rule: 'TICKET_CODE_COMPLIANCE', message: 'Ticketing keys match standard US-[PROD]-000 formats.' }
    ]),
    failed_checks: JSON.stringify([
      { rule: 'MFA_FAILSAFE_FALLBACK', message: 'Story US-PAY-002 lacks fallback criteria if the primary authenticator app is offline.' },
      { rule: 'CRITERIA_FORMATTING', message: 'Acceptance criteria for story US-PAY-002 are missing Given-When-Then structured blocks.' }
    ]),
    created_at: '2026-07-09T11:15:00Z'
  },
  {
    id: 'ar222222-6666-4444-9999-dddddddddddd',
    requirement_id: 'r2222222-3333-4444-9999-bbbbbbbbbbbb',
    audit_version_reviewed: 1,
    is_valid: true,
    passed_checks: JSON.stringify([
      { rule: 'PRIMARY_KEY_UUID', message: 'All tables verified on UUID v4.' },
      { rule: 'ISO_MAPPING_VERIFIED', message: 'UML diagram and XML patterns verified against ISO guidelines.' },
      { rule: 'LEDGER_INTEGRITY_CHECK', message: 'Meets double-entry regulatory frameworks.' }
    ]),
    failed_checks: JSON.stringify([]),
    created_at: '2026-07-09T12:30:00Z'
  }
];

export const INITIAL_QUESTIONS: ClarificationQuestionRow[] = [
  {
    id: 'q1111111-7777-4444-9999-eeeeeeeeeeee',
    audit_result_id: 'ar111111-6666-4444-9999-dddddddddddd',
    checklist_category: 'Security & Compliance',
    target_user_story_id: 'us222222-4444-4444-9999-bbbbbbbbbbbb',
    question_text: 'Are grace periods for corporate transfers compliant with Krungsri Nimble standards? SEC audit guidelines usually mandate re-authorization for single-transfer requests exceeding 1,000,000 THB regardless of grace window.',
    user_answer: 'Verified. We will add a threshold constraint: transfers exceeding 1M THB bypass the grace period cache and always prompt.',
    is_resolved: true,
    is_locked: false,
    locked_by: null,
    locked_at: null,
    lock_reason: null,
    created_at: '2026-07-09T11:20:00Z'
  },
  {
    id: 'q2222222-7777-4444-9999-eeeeeeeeeeee',
    audit_result_id: 'ar111111-6666-4444-9999-dddddddddddd',
    checklist_category: 'Failsafe & Redundancy',
    target_user_story_id: 'us111111-4444-4444-9999-bbbbbbbbbbbb',
    question_text: 'If the customer loses cellular signal during active transfer, what is the fallback method? SMS OTP backup, or physical token token-generator?',
    user_answer: null,
    is_resolved: false,
    is_locked: true,
    locked_by: 'compliance.auditor@sec.or.th',
    locked_at: '2026-07-09T11:30:00Z',
    lock_reason: 'Pending failsafe review',
    created_at: '2026-07-09T11:25:00Z'
  }
];

export const INITIAL_PRD_DOCS: PrdDocumentRow[] = [
  {
    id: 'prd11111-8888-4444-9999-ffffffffffff',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    version: 2,
    prd_markdown: `# SYSTEM REQUIREMENT DOCUMENT\n## Project: Krungsri FastPay Gateway\n\n### 1. Functional Architecture\nThis service provides transaction routing and multi-factor validation hooks. All incoming high-value transactions must validate users against a cryptographically signed mobile Authenticator system.\n\n### 2. State & Integrity Control\nAll transactions are indexed on UUID v4, and state is preserved on time-zone locked tables utilizing automatic audit fields.`,
    mermaid_diagram: `sequenceDiagram\n  Customer->>Gateway: Transfer > 100,000 THB\n  Gateway->>AuthService: Request MFA Challenge\n  AuthService->>CustomerDevice: Prompt OTP Verification\n  CustomerDevice-->>AuthService: Submit OTP (6-digits)\n  AuthService-->>Gateway: Authenticity Approved\n  Gateway->>Ledger: Commit Transaction`,
    is_locked: false,
    locked_by: null,
    locked_at: null,
    lock_reason: null,
    created_at: '2026-07-09T11:45:00Z'
  }
];

export const INITIAL_VERSION_HISTORY: VersionHistoryRow[] = [
  {
    id: 'vh111111-9999-4444-9999-000000000000',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    requirement_id: 'r1111111-3333-4444-9999-bbbbbbbbbbbb',
    version_number: 1,
    changed_by_user_id: 'u1111111-2222-3333-4444-555555555555',
    change_description: 'Initial draft for Multi-factor Transaction Authorization.',
    state_snapshot: JSON.stringify({
      user_stories: [
        { ticket: 'US-PAY-001', title: 'Secure OTP Validation' }
      ],
      criteria: [
        { story_ticket: 'US-PAY-001', text: 'Prompt challenge screen above 100K THB.' }
      ]
    }),
    created_at: '2026-07-09T10:45:00Z'
  },
  {
    id: 'vh222222-9999-4444-9999-000000000000',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    requirement_id: 'r1111111-3333-4444-9999-bbbbbbbbbbbb',
    version_number: 2,
    changed_by_user_id: 'u2222222-2222-3333-4444-555555555555',
    change_description: 'Added grace period story for batch transfers and fixed checklist queries.',
    state_snapshot: JSON.stringify({
      user_stories: [
        { ticket: 'US-PAY-001', title: 'Secure OTP Validation' },
        { ticket: 'US-PAY-002', title: 'MFA Grace Periods & Caching' }
      ],
      criteria: [
        { story_ticket: 'US-PAY-001', text: 'Prompt challenge screen above 100K THB.' },
        { story_ticket: 'US-PAY-002', text: 'Grace period verified in 5-minute session.' }
      ]
    }),
    created_at: '2026-07-09T11:40:00Z'
  }
];

export const INITIAL_PRD_VERSIONS: PrdVersionRow[] = [
  {
    id: 'pv111111-aaaa-4444-9999-cccccccccccc',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    version_number: 1,
    generated_prd: '# FastPay Gateway PRD v1\nInitial draft generated by Architect Agent.',
    generated_diagram: 'sequenceDiagram\n  Customer->>Gateway: Initiate Transfer',
    generated_by: 'architect_agent',
    created_at: '2026-07-09T10:00:00Z'
  },
  {
    id: 'pv222222-aaaa-4444-9999-cccccccccccc',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    version_number: 2,
    generated_prd: '# FastPay Gateway PRD v2\nAdded OTP fallback and grace period logic.',
    generated_diagram: 'sequenceDiagram\n  Customer->>Gateway: Transfer > 100K\n  Gateway->>Auth: MFA',
    generated_by: 'architect_agent',
    created_at: '2026-07-09T11:00:00Z'
  }
];

export const INITIAL_CONVERSATION_MESSAGES: ConversationMessageRow[] = [
  {
    id: 'cm111111-bbbb-4444-9999-dddddddddddd',
    conversation_id: 'conv-001',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    role: 'user',
    message: 'We need to support corporate batch transfers with a grace period for MFA.',
    workflow_state: 'gather',
    intent: 'functional_requirement',
    created_at: '2026-07-09T09:00:00Z'
  },
  {
    id: 'cm222222-bbbb-4444-9999-dddddddddddd',
    conversation_id: 'conv-001',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    role: 'assistant',
    message: 'Understood. I will add a 5-minute grace window for batch transfers under 1M THB.',
    workflow_state: 'confirm',
    intent: 'acknowledgement',
    created_at: '2026-07-09T09:01:00Z'
  }
];

export const INITIAL_ARTIFACT_EVENT_LOGS: ArtifactEventLogRow[] = [
  {
    event_id: 'ael111111-cccc-4444-9999-eeeeeeeeeeee',
    artifact_type: 'user_story',
    artifact_id: 'us222222-4444-4444-9999-bbbbbbbbbbbb',
    action: 'CREATE',
    old_value: null,
    new_value: JSON.stringify({ ticket_code: 'US-PAY-002', title: 'MFA Grace Periods & Caching' }),
    performed_by: 'automated_agent',
    timestamp: '2026-07-09T11:00:00Z'
  },
  {
    event_id: 'ael222222-cccc-4444-9999-eeeeeeeeeeee',
    artifact_type: 'user_story',
    artifact_id: 'us222222-4444-4444-9999-bbbbbbbbbbbb',
    action: 'LOCK',
    old_value: JSON.stringify({ is_locked: false }),
    new_value: JSON.stringify({ is_locked: true, lock_reason: 'Regulatory clarification pending' }),
    performed_by: 'compliance.auditor@sec.or.th',
    timestamp: '2026-07-09T11:10:00Z'
  }
];