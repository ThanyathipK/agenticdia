export interface ColumnDefinition {
  name: string;
  type: string;
  constraints: string;
  defaultValue?: string;
  description: string;
}

export interface TableSchema {
  name: string;
  description: string;
  bankingContext: string;
  columns: ColumnDefinition[];
  indexes: string[];
  relations: {
    fromColumn: string;
    toTable: string;
    toColumn: string;
    onDelete: 'CASCADE' | 'RESTRICT' | 'SET NULL' | 'NONE';
  }[];
}

export const TABLES: TableSchema[] = [
  {
    name: 'users',
    description: 'Stores information on banking stakeholders, product owners, and business analysts.',
    bankingContext: 'Maintains digital identity & RBAC (Role-Based Access Control) for audit trail attribution, ensuring clear accountability for requirement changes.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Enterprise unique identifier for the user.' },
      { name: 'email', type: 'VARCHAR(255)', constraints: 'UNIQUE NOT NULL', description: 'Corporate email address for notification routing.' },
      { name: 'full_name', type: 'VARCHAR(255)', constraints: 'NOT NULL', description: 'Legal name of the corporate user.' },
      { name: 'role', type: 'VARCHAR(50)', constraints: 'NOT NULL', description: 'Internal RBAC role: Product Owner, Business Analyst, Auditor, etc.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Audit trail creation date (with timezone info).' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Modified date synced via automation trigger.' }
    ],
    indexes: ['idx_users_role (role)'],
    relations: []
  },
  {
    name: 'projects',
    description: 'Stores banking systems, digital products, and core-banking project contexts.',
    bankingContext: 'Represents the boundary of compliance (e.g., Krungsri Nimble standards). Essential for grouping user stories under regulatory frameworks.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Unique project ID.' },
      { name: 'user_id', type: 'UUID', constraints: 'NOT NULL REFERENCES users(id)', description: 'Lead analyst or owner of the banking product.' },
      { name: 'name', type: 'VARCHAR(255)', constraints: 'NOT NULL', description: 'System or microservice name (e.g., Loan Originator System).' },
      { name: 'description', type: 'TEXT', constraints: 'NULL', description: 'High-level business context and scope definitions.' },
      { name: 'industry_standard', type: 'VARCHAR(100)', constraints: 'NOT NULL', description: 'Compliance guideline baseline (e.g., Krungsri Nimble).' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Timezone-aware initialization timestamp.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'System modification tracker timestamp.' }
    ],
    indexes: ['idx_projects_user_id (user_id)'],
    relations: [
      { fromColumn: 'user_id', toTable: 'users', toColumn: 'id', onDelete: 'RESTRICT' }
    ]
  },
  {
    name: 'requirements',
    description: 'Groups user stories under parent epic structures with version locking.',
    bankingContext: 'Serves as the high-level compliance checkpoint (Epics) that can be locked/unlocked to freeze active requirements during formal internal audits.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Epic unique key.' },
      { name: 'project_id', type: 'UUID', constraints: 'NOT NULL REFERENCES projects(id)', description: 'Parent banking project association.' },
      { name: 'epic_name', type: 'VARCHAR(255)', constraints: 'NOT NULL', description: 'Feature scope name (e.g., Double-entry Ledger Ledger Sync).' },
      { name: 'total_user_stories', type: 'INT', constraints: 'NOT NULL', defaultValue: '0', description: 'Counter metric for agile scope monitoring.' },
      { name: 'current_version', type: 'INT', constraints: 'NOT NULL', defaultValue: '1', description: 'Auto-incrementing requirement iteration number.' },
      { name: 'is_locked', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Audit lock flag. When TRUE, modifications are blocked.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date epic created.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date epic was last edited or locked.' }
    ],
    indexes: ['idx_requirements_project_id (project_id)', 'idx_requirements_is_locked (is_locked)'],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'user_stories',
    description: 'Captures Agile user stories formatted according to banking compliance standards.',
    bankingContext: 'Detailed banking business rules written as "As a / I want to / So that" templates, validating user actions against core security models.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Unique story key.' },
      { name: 'requirement_id', type: 'UUID', constraints: 'NOT NULL REFERENCES requirements(id)', description: 'Epic parent block identifier.' },
      { name: 'ticket_code', type: 'VARCHAR(50)', constraints: 'NOT NULL UNIQUE', description: 'Banking ticketing mapping (e.g. US-001, LN-402).' },
      { name: 'story_title', type: 'VARCHAR(255)', constraints: 'NOT NULL', description: 'Name of user task.' },
      { name: 'as_a', type: 'TEXT', constraints: 'NOT NULL', description: 'Role actor (e.g., Risk Officer, Retail Customer).' },
      { name: 'i_want_to', type: 'TEXT', constraints: 'NOT NULL', description: 'The banking action requested.' },
      { name: 'so_that', type: 'TEXT', constraints: 'NOT NULL', description: 'The compliant banking goal/outcome achieved.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Creation date.' }
    ],
    indexes: ['idx_user_stories_requirement_id (requirement_id)'],
    relations: [
      { fromColumn: 'requirement_id', toTable: 'requirements', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'acceptance_criteria',
    description: 'Given-When-Then specification for verifying banking behavior.',
    bankingContext: 'Direct translation of regulatory guidelines into verifiable, machine-inspectable behavior statements. Eliminates functional ambiguities.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Unique criteria ID.' },
      { name: 'user_story_id', type: 'UUID', constraints: 'NOT NULL REFERENCES user_stories(id)', description: 'Mapped user story.' },
      { name: 'criteria_text', type: 'TEXT', constraints: 'NOT NULL', description: 'Given-When-Then criteria block.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Creation timestamp.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Updated timestamp.' }
    ],
    indexes: ['idx_acceptance_criteria_user_story_id (user_story_id)'],
    relations: [
      { fromColumn: 'user_story_id', toTable: 'user_stories', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'audit_results',
    description: 'Tracks checking runs on requirement drafts, validating compliance.',
    bankingContext: 'Automated/manual verification ledger marking passed rules, failed checks, and identifying issues requiring resolution prior to production release.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Audit report ID.' },
      { name: 'requirement_id', type: 'UUID', constraints: 'NOT NULL REFERENCES requirements(id)', description: 'Audited epic reference.' },
      { name: 'version_reviewed', type: 'INT', constraints: 'NOT NULL', description: 'The Epic version snapshot index analyzed.' },
      { name: 'is_valid', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Whether the requirement matches all regulations.' },
      { name: 'passed_checks', type: 'JSONB', constraints: 'NOT NULL', defaultValue: "\'[]\'::jsonb", description: 'Array of validated compliance checks.' },
      { name: 'failed_checks', type: 'JSONB', constraints: 'NOT NULL', defaultValue: "\'[]\'::jsonb", description: 'Array of failed compliance parameters.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Time audit was compiled.' }
    ],
    indexes: ['idx_audit_results_requirement_id (requirement_id)', 'idx_audit_results_is_valid (is_valid)'],
    relations: [
      { fromColumn: 'requirement_id', toTable: 'requirements', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'clarification_questions',
    description: 'Stores query logs and compliance verification dialogues regarding requirements.',
    bankingContext: 'Closes the loop between banking developers and compliance officers. Ensures unresolved items are formally tracked and resolved.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Unique question ID.' },
      { name: 'audit_result_id', type: 'UUID', constraints: 'NOT NULL REFERENCES audit_results(id)', description: 'Triggering audit report reference.' },
      { name: 'checklist_category', type: 'VARCHAR(100)', constraints: 'NOT NULL', description: 'E.g., Security, Regulatory, Edge Case.' },
      { name: 'target_user_story_id', type: 'UUID', constraints: 'NULL REFERENCES user_stories(id)', description: 'Specific target story queried.' },
      { name: 'question_text', type: 'TEXT', constraints: 'NOT NULL', description: 'System or expert drafted compliance query.' },
      { name: 'user_answer', type: 'TEXT', constraints: 'NULL', description: 'Official stakeholder resolution reply.' },
      { name: 'is_resolved', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Lock resolver status.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date logged.' }
    ],
    indexes: [
      'idx_clarification_questions_audit_result_id (audit_result_id)',
      'idx_clarification_questions_target_user_story_id (target_user_story_id)',
      'idx_clarification_questions_is_resolved (is_resolved)',
      'idx_clarification_questions_category (checklist_category)'
    ],
    relations: [
      { fromColumn: 'audit_result_id', toTable: 'audit_results', toColumn: 'id', onDelete: 'CASCADE' },
      { fromColumn: 'target_user_story_id', toTable: 'user_stories', toColumn: 'id', onDelete: 'SET NULL' }
    ]
  },
  {
    name: 'prd_documents',
    description: 'Compiled final Production PRDs with markdown explanations and system diagrams.',
    bankingContext: 'Official corporate PRD artifacts exported as verified baselines for software architects and compliance review councils.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'PRD Document ID.' },
      { name: 'project_id', type: 'UUID', constraints: 'NOT NULL REFERENCES projects(id)', description: 'Target banking system.' },
      { name: 'version', type: 'INT', constraints: 'NOT NULL', description: 'Target build index.' },
      { name: 'markdown_content', type: 'TEXT', constraints: 'NOT NULL', description: 'Compiled functional specifications in markdown.' },
      { name: 'mermaid_graph', type: 'TEXT', constraints: 'NULL', description: 'Live architecture diagram schema.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Export generation date.' }
    ],
    indexes: ['idx_prd_documents_project_id (project_id)'],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'version_history',
    description: 'Audit-trail ledger containing historical state snapshots of requirements.',
    bankingContext: 'Core integrity component: immutable ledger capturing complete state snapshots (JSONB) of requirements + acceptance criteria on changes. Essential for compliance audits.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Ledger record ID.' },
      { name: 'project_id', type: 'UUID', constraints: 'NOT NULL REFERENCES projects(id)', description: 'Related banking project.' },
      { name: 'requirement_id', type: 'UUID', constraints: 'NOT NULL REFERENCES requirements(id)', description: 'Related epic baseline.' },
      { name: 'version_number', type: 'INT', constraints: 'NOT NULL', description: 'Captured version number.' },
      { name: 'changed_by_user_id', type: 'UUID', constraints: 'NOT NULL REFERENCES users(id)', description: 'Corporate stakeholder author.' },
      { name: 'change_description', type: 'TEXT', constraints: 'NOT NULL', description: 'Reason for requirement iteration.' },
      { name: 'state_snapshot', type: 'JSONB', constraints: 'NOT NULL', description: 'Full recursive state snapshot of user stories & acceptance criteria.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date ledger transaction was posted.' }
    ],
    indexes: [
      'idx_version_history_project_id (project_id)',
      'idx_version_history_requirement_id (requirement_id)',
      'idx_version_history_changed_by_user_id (changed_by_user_id)'
    ],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' },
      { fromColumn: 'requirement_id', toTable: 'requirements', toColumn: 'id', onDelete: 'CASCADE' },
      { fromColumn: 'changed_by_user_id', toTable: 'users', toColumn: 'id', onDelete: 'RESTRICT' }
    ]
  }
];

export interface UserRow {
  id: string;
  email: string;
  full_name: string;
  role: string;
  created_at: string;
}

export interface ProjectRow {
  id: string;
  user_id: string;
  name: string;
  description: string;
  industry_standard: string;
  created_at: string;
}

export interface RequirementRow {
  id: string;
  project_id: string;
  epic_name: string;
  total_user_stories: number;
  current_version: number;
  is_locked: boolean;
  created_at: string;
}

export interface UserStoryRow {
  id: string;
  requirement_id: string;
  ticket_code: string;
  story_title: string;
  as_a: string;
  i_want_to: string;
  so_that: string;
  created_at: string;
}

export interface AcceptanceCriterionRow {
  id: string;
  user_story_id: string;
  criteria_text: string;
  created_at: string;
}

export interface AuditResultRow {
  id: string;
  requirement_id: string;
  version_reviewed: number;
  is_valid: boolean;
  passed_checks: string; // JSON string
  failed_checks: string; // JSON string
  created_at: string;
}

export interface ClarificationQuestionRow {
  id: string;
  audit_result_id: string;
  checklist_category: string;
  target_user_story_id: string | null;
  question_text: string;
  user_answer: string | null;
  is_resolved: boolean;
  created_at: string;
}

export interface PrdDocumentRow {
  id: string;
  project_id: string;
  version: number;
  markdown_content: string;
  mermaid_graph: string;
  created_at: string;
}

export interface VersionHistoryRow {
  id: string;
  project_id: string;
  requirement_id: string;
  version_number: number;
  changed_by_user_id: string;
  change_description: string;
  state_snapshot: string; // JSON string representation
  created_at: string;
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
    created_at: '2026-07-09T10:00:00Z'
  },
  {
    id: 'p2222222-2222-4444-8888-999999999999',
    user_id: 'u1111111-2222-3333-4444-555555555555',
    name: 'Nimble Ledger Hub',
    description: 'Double-entry general ledger service providing near-real-time compliance checks & immutable transaction state.',
    industry_standard: 'ISO-20022 Financial',
    created_at: '2026-07-09T11:30:00Z'
  }
];

export const INITIAL_REQUIREMENTS: RequirementRow[] = [
  {
    id: 'r1111111-3333-4444-9999-aaaaaaaaaaaa',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    epic_name: 'Multi-factor Transaction Authorization',
    total_user_stories: 3,
    current_version: 2,
    is_locked: false,
    created_at: '2026-07-09T10:30:00Z'
  },
  {
    id: 'r2222222-3333-4444-9999-aaaaaaaaaaaa',
    project_id: 'p2222222-2222-4444-8888-999999999999',
    epic_name: 'ISO-20022 Message Validation Engine',
    total_user_stories: 2,
    current_version: 1,
    is_locked: true,
    created_at: '2026-07-09T12:00:00Z'
  }
];

export const INITIAL_USER_STORIES: UserStoryRow[] = [
  {
    id: 'us111111-4444-4444-9999-bbbbbbbbbbbb',
    requirement_id: 'r1111111-3333-4444-9999-aaaaaaaaaaaa',
    ticket_code: 'US-PAY-001',
    story_title: 'Secure OTP Validation',
    as_a: 'Retail Banking Customer initiating a fund transfer over 100,000 THB',
    i_want_to: 'be prompted to verify my transaction with an OTP code generated by my registered Authenticator app',
    so_that: 'the system verifies my active presence and protects my account balance from unauthorized access.',
    created_at: '2026-07-09T10:45:00Z'
  },
  {
    id: 'us222222-4444-4444-9999-bbbbbbbbbbbb',
    requirement_id: 'r1111111-3333-4444-9999-aaaaaaaaaaaa',
    ticket_code: 'US-PAY-002',
    story_title: 'MFA Grace Periods & Caching',
    as_a: 'Corporate Accountant performing batch transfers within a single browser session',
    i_want_to: 'exempt transfers from re-triggering MFA within a 5-minute validated grace period',
    so_that: 'batch execution performance and administrative ergonomics are optimized without exposing the channel to session hijacking.',
    created_at: '2026-07-09T11:00:00Z'
  },
  {
    id: 'us333333-4444-4444-9999-bbbbbbbbbbbb',
    requirement_id: 'r2222222-3333-4444-9999-aaaaaaaaaaaa',
    ticket_code: 'US-LED-001',
    story_title: 'ISO XML Schema Validation',
    as_a: 'Core Clearing Service handling inter-bank messages',
    i_want_to: 'strictly validate all inbound payloads against the pain.001.001.08 XML Schema Definition',
    so_that: 'malformed bank messages are rejected immediately before reaching core ledger queues.',
    created_at: '2026-07-09T12:15:00Z'
  }
];

export const INITIAL_ACCEPTANCE_CRITERIA: AcceptanceCriterionRow[] = [
  {
    id: 'ac111111-5555-4444-9999-cccccccccccc',
    user_story_id: 'us111111-4444-4444-9999-bbbbbbbbbbbb',
    criteria_text: 'GIVEN the customer balance is valid and the transfer amount exceeds 100,000 THB\nWHEN they click "Confirm Transfer"\nTHEN the system suspends transaction execution and dispatches an authenticating challenge modal.',
    created_at: '2026-07-09T10:50:00Z'
  },
  {
    id: 'ac222222-5555-4444-9999-cccccccccccc',
    user_story_id: 'us111111-4444-4444-9999-bbbbbbbbbbbb',
    criteria_text: 'GIVEN the authenticator challenge screen is visible\nWHEN the customer inputs a valid 6-digit dynamic token within 180 seconds\nTHEN the transaction is authorized, submitted to clearance queues, and an audit trail user reference logged.',
    created_at: '2026-07-09T10:52:00Z'
  },
  {
    id: 'ac333333-5555-4444-9999-cccccccccccc',
    user_story_id: 'us333333-4444-4444-9999-bbbbbbbbbbbb',
    criteria_text: 'GIVEN an incoming inter-bank transfer request\nWHEN the payload lacks the <GrpHdr> or <PmtInf> tag\nTHEN the clearing service raises a rejection code "ERR_ISO_SCHEMA_INTEGRITY" and halts internal queue processing.',
    created_at: '2026-07-09T12:20:00Z'
  }
];

export const INITIAL_AUDIT_RESULTS: AuditResultRow[] = [
  {
    id: 'ar111111-6666-4444-9999-dddddddddddd',
    requirement_id: 'r1111111-3333-4444-9999-aaaaaaaaaaaa',
    version_reviewed: 1,
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
    requirement_id: 'r2222222-3333-4444-9999-aaaaaaaaaaaa',
    version_reviewed: 1,
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
    created_at: '2026-07-09T11:25:00Z'
  }
];

export const INITIAL_PRD_DOCS: PrdDocumentRow[] = [
  {
    id: 'prd11111-8888-4444-9999-ffffffffffff',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    version: 2,
    markdown_content: `# SYSTEM REQUIREMENT DOCUMENT\n## Project: Krungsri FastPay Gateway\n\n### 1. Functional Architecture\nThis service provides transaction routing and multi-factor validation hooks. All incoming high-value transactions must validate users against a cryptographically signed mobile Authenticator system.\n\n### 2. State & Integrity Control\nAll transactions are indexed on UUID v4, and state is preserved on time-zone locked tables utilizing automatic audit fields.`,
    mermaid_graph: `sequenceDiagram\n  Customer->>Gateway: Transfer > 100,000 THB\n  Gateway->>AuthService: Request MFA Challenge\n  AuthService->>CustomerDevice: Prompt OTP Verification\n  CustomerDevice-->>AuthService: Submit OTP (6-digits)\n  AuthService-->>Gateway: Authenticity Approved\n  Gateway->>Ledger: Commit Transaction`,
    created_at: '2026-07-09T11:45:00Z'
  }
];

export const INITIAL_VERSION_HISTORY: VersionHistoryRow[] = [
  {
    id: 'vh111111-9999-4444-9999-000000000000',
    project_id: 'p1111111-1111-4444-8888-999999999999',
    requirement_id: 'r1111111-3333-4444-9999-aaaaaaaaaaaa',
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
    requirement_id: 'r1111111-3333-4444-9999-aaaaaaaaaaaa',
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
