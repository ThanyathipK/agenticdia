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
      { name: 'is_locked', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Audit lock flag. When TRUE, project-level mutations are blocked.' },
      { name: 'locked_by', type: 'VARCHAR(100)', constraints: 'NULL', description: 'Corporate stakeholder or agent that applied the lock.' },
      { name: 'locked_at', type: 'TIMESTAMPTZ', constraints: 'NULL', description: 'UTC timestamp when the lock was applied.' },
      { name: 'lock_reason', type: 'VARCHAR(255)', constraints: 'NULL', description: 'Justification for the lock (e.g., External Audit, Migration).' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Timezone-aware initialization timestamp.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'System modification tracker timestamp.' }
    ],
    indexes: ['idx_projects_user_id (user_id)'],
    relations: [
      { fromColumn: 'user_id', toTable: 'users', toColumn: 'id', onDelete: 'RESTRICT' }
    ]
  },
  {
    name: 'epics',
    description: 'High-level business capabilities or features that group related requirements.',
    bankingContext: 'Serves as the primary compliance checkpoint for banking features. Can be locked/unlocked to freeze active requirements during formal internal audits.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Epic unique identifier.' },
      { name: 'project_id', type: 'UUID', constraints: 'NOT NULL REFERENCES projects(id)', description: 'Parent banking project association.' },
      { name: 'epic_name', type: 'VARCHAR(255)', constraints: 'NOT NULL', description: 'Feature scope name (e.g., Multi-factor Transaction Authorization).' },
      { name: 'version', type: 'INT', constraints: 'NOT NULL', defaultValue: '1', description: 'Auto-incrementing epic iteration number.' },
      { name: 'is_locked', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Audit lock flag. When TRUE, modifications are blocked.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date epic created.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date epic was last edited or locked.' },
      { name: 'status', type: 'VARCHAR(50)', constraints: 'NOT NULL', defaultValue: 'active', description: 'Lifecycle status: active, archived, deprecated.' }
    ],
    indexes: ['idx_epics_project_id (project_id)', 'idx_epics_is_locked (is_locked)'],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'requirements',
    description: 'Detailed functional and non-functional requirements derived from epics.',
    bankingContext: 'Granular compliance units that map to specific regulatory needs. Each requirement is versioned and traceable to an epic for audit purposes.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Requirement unique identifier.' },
      { name: 'project_id', type: 'UUID', constraints: 'NOT NULL REFERENCES projects(id)', description: 'Parent banking project association.' },
      { name: 'epic_id', type: 'UUID', constraints: 'NULL REFERENCES epics(id)', description: 'Parent epic reference for hierarchical organization.' },
      { name: 'requirement_code', type: 'VARCHAR(50)', constraints: 'NOT NULL', description: 'Unique requirement identifier (e.g., REQ-001).' },
      { name: 'title', type: 'VARCHAR(255)', constraints: 'NOT NULL', description: 'Short descriptive title of the requirement.' },
      { name: 'description', type: 'TEXT', constraints: 'NULL', description: 'Detailed functional or non-functional specification.' },
      { name: 'priority', type: 'VARCHAR(50)', constraints: 'NULL', description: 'Business priority: High, Medium, Low, Critical.' },
      { name: 'status', type: 'VARCHAR(50)', constraints: 'NOT NULL', defaultValue: 'active', description: 'Lifecycle status: active, deprecated, superseded.' },
      { name: 'version', type: 'INT', constraints: 'NOT NULL', defaultValue: '1', description: 'Current version number for change tracking.' },
      { name: 'is_locked', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Audit lock flag. When TRUE, modifications are blocked.' },
      { name: 'locked_by', type: 'VARCHAR(100)', constraints: 'NULL', description: 'Corporate stakeholder or agent that applied the lock.' },
      { name: 'locked_at', type: 'TIMESTAMPTZ', constraints: 'NULL', description: 'UTC timestamp when the lock was applied.' },
      { name: 'lock_reason', type: 'VARCHAR(255)', constraints: 'NULL', description: 'Justification for the lock (e.g., External Audit, Migration).' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date requirement was created.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date requirement was last modified.' }
    ],
    indexes: ['idx_requirements_project_id (project_id)'],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' },
      { fromColumn: 'epic_id', toTable: 'epics', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'user_stories',
    description: 'Captures Agile user stories formatted according to banking compliance standards.',
    bankingContext: 'Detailed banking business rules written as "As a / I want to / So that" templates, validating user actions against core security models.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Unique story key.' },
      { name: 'project_id', type: 'UUID', constraints: 'NULL REFERENCES projects(id)', description: 'Project association for multi-tenant filtering.' },
      { name: 'requirement_id', type: 'UUID', constraints: 'NOT NULL REFERENCES requirements(id)', description: 'Parent requirement identifier.' },
      { name: 'ticket_code', type: 'VARCHAR(50)', constraints: 'NOT NULL', description: 'Banking ticketing mapping (e.g. US-001, LN-402).' },
      { name: 'story_title', type: 'VARCHAR(255)', constraints: 'NOT NULL', description: 'Name of user task.' },
      { name: 'as_a', type: 'TEXT', constraints: 'NOT NULL', description: 'Role actor (e.g., Risk Officer, Retail Customer).' },
      { name: 'i_want_to', type: 'TEXT', constraints: 'NOT NULL', description: 'The banking action requested.' },
      { name: 'so_that', type: 'TEXT', constraints: 'NOT NULL', description: 'The compliant banking goal/outcome achieved.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Creation date.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Last modification timestamp.' },
      { name: 'status', type: 'VARCHAR(50)', constraints: 'NOT NULL', defaultValue: 'active', description: 'Lifecycle status: active, archived, deprecated.' },
      { name: 'version', type: 'INT', constraints: 'NOT NULL', defaultValue: '1', description: 'Current version for change tracking.' },
      { name: 'last_modified_by', type: 'VARCHAR(100)', constraints: 'NOT NULL', defaultValue: 'automated_agent', description: 'Entity that last modified this record.' },
      { name: 'change_type', type: 'VARCHAR(50)', constraints: 'NOT NULL', defaultValue: 'created', description: 'Type of last change: created, updated, deleted.' },
      { name: 'is_locked', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Audit lock flag. When TRUE, modifications are blocked.' },
      { name: 'locked_by', type: 'VARCHAR(100)', constraints: 'NULL', description: 'Corporate stakeholder or agent that applied the lock.' },
      { name: 'locked_at', type: 'TIMESTAMPTZ', constraints: 'NULL', description: 'UTC timestamp when the lock was applied.' },
      { name: 'lock_reason', type: 'VARCHAR(255)', constraints: 'NULL', description: 'Justification for the lock (e.g., External Audit, Migration).' }
    ],
    indexes: ['idx_user_stories_requirement_id (requirement_id)', 'uq_user_stories_project_id_ticket_code (project_id, ticket_code)'],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' },
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
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Last modification timestamp.' },
      { name: 'status', type: 'VARCHAR(50)', constraints: 'NOT NULL', defaultValue: 'active', description: 'Lifecycle status: active, archived, deprecated.' },
      { name: 'version', type: 'INT', constraints: 'NOT NULL', defaultValue: '1', description: 'Current version for change tracking.' },
      { name: 'last_modified_by', type: 'VARCHAR(100)', constraints: 'NOT NULL', defaultValue: 'automated_agent', description: 'Entity that last modified this record.' },
      { name: 'change_type', type: 'VARCHAR(50)', constraints: 'NOT NULL', defaultValue: 'created', description: 'Type of last change: created, updated, deleted.' },
      { name: 'is_locked', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Audit lock flag. When TRUE, modifications are blocked.' },
      { name: 'locked_by', type: 'VARCHAR(100)', constraints: 'NULL', description: 'Corporate stakeholder or agent that applied the lock.' },
      { name: 'locked_at', type: 'TIMESTAMPTZ', constraints: 'NULL', description: 'UTC timestamp when the lock was applied.' },
      { name: 'lock_reason', type: 'VARCHAR(255)', constraints: 'NULL', description: 'Justification for the lock (e.g., External Audit, Migration).' }
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
      { name: 'requirement_id', type: 'UUID', constraints: 'NOT NULL REFERENCES requirements(id)', description: 'Audited requirement reference.' },
      { name: 'audit_version_reviewed', type: 'INT', constraints: 'NOT NULL', description: 'The requirement version snapshot index analyzed.' },
      { name: 'is_valid', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Whether the requirement matches all regulations.' },
      { name: 'passed_checks', type: 'JSONB', constraints: 'NOT NULL', defaultValue: "\'[]\'::jsonb", description: 'Array of validated compliance checks.' },
      { name: 'failed_checks', type: 'JSONB', constraints: 'NOT NULL', defaultValue: "\'[]\'::jsonb", description: 'Array of failed compliance parameters.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Time audit was compiled.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Time audit was last modified.' }
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
      { name: 'is_locked', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Audit lock flag. When TRUE, modifications are blocked.' },
      { name: 'locked_by', type: 'VARCHAR(100)', constraints: 'NULL', description: 'Corporate stakeholder or agent that applied the lock.' },
      { name: 'locked_at', type: 'TIMESTAMPTZ', constraints: 'NULL', description: 'UTC timestamp when the lock was applied.' },
      { name: 'lock_reason', type: 'VARCHAR(255)', constraints: 'NULL', description: 'Justification for the lock (e.g., External Audit, Migration).' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date logged.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date last modified.' }
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
      { name: 'prd_markdown', type: 'TEXT', constraints: 'NOT NULL', description: 'Compiled functional specifications in markdown.' },
      { name: 'mermaid_diagram', type: 'TEXT', constraints: 'NULL', description: 'Live architecture diagram schema.' },
      { name: 'is_locked', type: 'BOOLEAN', constraints: 'NOT NULL', defaultValue: 'FALSE', description: 'Audit lock flag. When TRUE, modifications are blocked.' },
      { name: 'locked_by', type: 'VARCHAR(100)', constraints: 'NULL', description: 'Corporate stakeholder or agent that applied the lock.' },
      { name: 'locked_at', type: 'TIMESTAMPTZ', constraints: 'NULL', description: 'UTC timestamp when the lock was applied.' },
      { name: 'lock_reason', type: 'VARCHAR(255)', constraints: 'NULL', description: 'Justification for the lock (e.g., External Audit, Migration).' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Export generation date.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Last modification timestamp.' }
    ],
    indexes: ['idx_prd_documents_project_id (project_id)'],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'version_history',
    description: 'Audit-trail ledger containing historical state snapshots of requirements.',
    bankingContext: 'Core integrity component: immutable ledger capturing complete state snapshots (JSONB) of requirements on changes. Essential for compliance audits.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Ledger record ID.' },
      { name: 'project_id', type: 'UUID', constraints: 'NOT NULL REFERENCES projects(id)', description: 'Related banking project.' },
      { name: 'requirement_id', type: 'UUID', constraints: 'NOT NULL REFERENCES requirements(id)', description: 'Related requirement baseline.' },
      { name: 'version_number', type: 'INT', constraints: 'NOT NULL', description: 'Captured version number.' },
      { name: 'changed_by_user_id', type: 'UUID', constraints: 'NOT NULL REFERENCES users(id)', description: 'Corporate stakeholder author.' },
      { name: 'change_description', type: 'TEXT', constraints: 'NOT NULL', description: 'Reason for requirement iteration.' },
      { name: 'state_snapshot', type: 'JSONB', constraints: 'NOT NULL', description: 'Full recursive state snapshot of requirements.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Date ledger transaction was posted.' },
      { name: 'updated_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Last modification timestamp.' }
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
  },
  {
    name: 'prd_versions',
    description: 'Immutable version history for generated PRDs. Each PRD generation creates a new record; previous versions are never overwritten.',
    bankingContext: 'Provides immutable traceability for every PRD artifact produced by the system, satisfying immutable-audit requirements.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'PRD version record ID.' },
      { name: 'project_id', type: 'UUID', constraints: 'NOT NULL REFERENCES projects(id)', description: 'Related banking project.' },
      { name: 'version_number', type: 'INT', constraints: 'NOT NULL', description: 'Sequential PRD version for this project.' },
      { name: 'generated_prd', type: 'TEXT', constraints: 'NOT NULL', description: 'Full generated PRD markdown at this version.' },
      { name: 'generated_diagram', type: 'TEXT', constraints: 'NULL', description: 'Generated architecture diagram at this version.' },
      { name: 'generated_by', type: 'VARCHAR(100)', constraints: 'NOT NULL', defaultValue: 'automated_agent', description: 'Agent or user that produced this version.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Timestamp this version was created.' }
    ],
    indexes: [
      'idx_prd_versions_project_id (project_id)',
      'idx_prd_versions_version_number (project_id, version_number)'
    ],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'conversation_messages',
    description: 'Persists every conversation message per project for chat/voice audit and replay.',
    bankingContext: 'Supports regulatory replay and customer-interaction audit trails by storing every inbound and outbound message with workflow context.',
    columns: [
      { name: 'id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Message unique identifier.' },
      { name: 'conversation_id', type: 'UUID', constraints: 'NULL', description: 'Groups messages into a single conversation thread.' },
      { name: 'project_id', type: 'UUID', constraints: 'NOT NULL REFERENCES projects(id)', description: 'Project context for multi-tenant isolation.' },
      { name: 'role', type: 'VARCHAR(50)', constraints: 'NOT NULL', description: 'Speaker role: user, assistant, system.' },
      { name: 'message', type: 'TEXT', constraints: 'NOT NULL', description: 'Full message content.' },
      { name: 'workflow_state', type: 'VARCHAR(50)', constraints: 'NULL', defaultValue: "''", description: 'Current workflow or FSM state at time of message.' },
      { name: 'intent', type: 'VARCHAR(50)', constraints: 'NULL', defaultValue: "''", description: 'Detected user intent classification.' },
      { name: 'created_at', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'Timestamp the message was recorded.' }
    ],
    indexes: [
      'idx_conversation_messages_project_id (project_id)',
      'idx_conversation_messages_conversation_id (conversation_id)',
      'idx_conversation_messages_created_at (created_at)'
    ],
    relations: [
      { fromColumn: 'project_id', toTable: 'projects', toColumn: 'id', onDelete: 'CASCADE' }
    ]
  },
  {
    name: 'artifact_event_logs',
    description: 'Immutable append-only event log tracking every artifact mutation across the platform.',
    bankingContext: 'Provides tamper-evident traceability for all CREATE/UPDATE/DELETE/ARCHIVE/LOCK/UNLOCK actions on banking artifacts.',
    columns: [
      { name: 'event_id', type: 'UUID', constraints: 'PRIMARY KEY', defaultValue: 'gen_random_uuid()', description: 'Unique event log entry ID.' },
      { name: 'artifact_type', type: 'VARCHAR(50)', constraints: 'NOT NULL', description: 'Type of artifact mutated: epic, requirement, user_story, acceptance_criteria, prd.' },
      { name: 'artifact_id', type: 'VARCHAR(36)', constraints: 'NOT NULL', description: 'UUID of the artifact that was mutated.' },
      { name: 'action', type: 'VARCHAR(20)', constraints: 'NOT NULL', description: 'CREATE, UPDATE, DELETE, ARCHIVE, LOCK, UNLOCK.' },
      { name: 'old_value', type: 'JSONB', constraints: 'NULL', description: 'Full artifact snapshot before the change.' },
      { name: 'new_value', type: 'JSONB', constraints: 'NULL', description: 'Full artifact snapshot after the change.' },
      { name: 'performed_by', type: 'VARCHAR(100)', constraints: 'NOT NULL', defaultValue: 'automated_agent', description: 'User or agent that triggered the change.' },
      { name: 'timestamp', type: 'TIMESTAMPTZ', constraints: 'NOT NULL', defaultValue: 'NOW()', description: 'When the mutation occurred.' }
    ],
    indexes: [
      'idx_artifact_event_logs_artifact (artifact_type, artifact_id)',
      'idx_artifact_event_logs_action (action)',
      'idx_artifact_event_logs_timestamp (timestamp)'
    ],
    relations: []
  }
];

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