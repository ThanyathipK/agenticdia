-- ==========================================
-- Enterprise Banking Requirements Engineering System
-- PostgreSQL DDL Script (Optimized for Supabase Cloud)
-- ==========================================

-- Enable modern UUID generation extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- 0. AUTOMATED AUDIT TRIGGER FUNCTION
-- ==========================================
-- Automatically updates the updated_at timestamp when a row is modified.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==========================================
-- 1. USERS TABLE
-- ==========================================
-- Stores information on banking stakeholders, product owners, and business analysts.
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL, -- e.g., 'Product Owner', 'Business Analyst', 'Auditor', 'Developer'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER handle_updated_at_users
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 2. PROJECTS TABLE
-- ==========================================
-- Stores banking systems, digital products, and core-banking project contexts.
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, -- RESTRICT: Prevent user deletion if active projects exist for auditing
    name VARCHAR(255) NOT NULL,
    description TEXT,
    industry_standard VARCHAR(100) NOT NULL, -- e.g., 'Krungsri Nimble', 'ISO-20022', 'PCI-DSS'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER handle_updated_at_projects
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 3. EPICS TABLE
-- ==========================================
DROP TABLE IF EXISTS epics CASCADE;
CREATE TABLE epics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    epic_name VARCHAR(255) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'active'
);

CREATE TRIGGER handle_updated_at_epics
    BEFORE UPDATE ON epics
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 3b. REQUIREMENTS TABLE
-- ==========================================
DROP TABLE IF EXISTS requirements CASCADE;
CREATE TABLE requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    epic_id UUID REFERENCES epics(id) ON DELETE CASCADE,
    requirement_code VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    priority VARCHAR(50),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER handle_updated_at_requirements
    BEFORE UPDATE ON requirements
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 4. USER STORIES TABLE
-- ==========================================
-- Captures Agile user stories formatted according to banking compliance requirements.
CREATE TABLE user_stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    requirement_id UUID NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    ticket_code VARCHAR(50) NOT NULL, -- e.g., 'US-001', 'LN-402'
    story_title VARCHAR(255) NOT NULL,
    as_a TEXT NOT NULL,
    i_want_to TEXT NOT NULL,
    so_that TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    version INTEGER NOT NULL DEFAULT 1,
    last_modified_by VARCHAR(100) NOT NULL DEFAULT 'automated_agent',
    change_type VARCHAR(50) NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Composite unique constraint for project-level ticket_code uniqueness
ALTER TABLE user_stories ADD CONSTRAINT uq_user_stories_project_id_ticket_code UNIQUE (project_id, ticket_code);

CREATE TRIGGER handle_updated_at_user_stories
    BEFORE UPDATE ON user_stories
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 5. ACCEPTANCE CRITERIA TABLE
-- ==========================================
-- Formatted criteria using the standard Given-When-Then specification for banking behavior.
CREATE TABLE acceptance_criteria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_story_id UUID NOT NULL REFERENCES user_stories(id) ON DELETE CASCADE,
    criteria_text TEXT NOT NULL, -- Standardised Given-When-Then criteria block
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    version INTEGER NOT NULL DEFAULT 1,
    last_modified_by VARCHAR(100) NOT NULL DEFAULT 'automated_agent',
    change_type VARCHAR(50) NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER handle_updated_at_acceptance_criteria
    BEFORE UPDATE ON acceptance_criteria
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 6. AUDIT RESULTS TABLE
-- ==========================================
-- Tracks checking runs on requirement drafts, validating banking logic and compliance rules.
CREATE TABLE audit_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requirement_id UUID NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    audit_version_reviewed INT NOT NULL,
    is_valid BOOLEAN NOT NULL DEFAULT FALSE,
    passed_checks JSONB NOT NULL DEFAULT '[]'::jsonb, -- Structured passed rule details
    failed_checks JSONB NOT NULL DEFAULT '[]'::jsonb, -- Structured failed rule details
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER handle_updated_at_audit_results
    BEFORE UPDATE ON audit_results
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 7. CLARIFICATION QUESTIONS TABLE
-- ==========================================
-- Stores clarification, query, and compliance verification dialogues regarding requirements.
CREATE TABLE clarification_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_result_id UUID NOT NULL REFERENCES audit_results(id) ON DELETE CASCADE,
    checklist_category VARCHAR(100) NOT NULL, -- e.g., 'Security', 'Regulatory Compliance', 'Edge Case'
    target_user_story_id UUID REFERENCES user_stories(id) ON DELETE SET NULL, -- Nullable FK for loose coupling
    question_text TEXT NOT NULL,
    user_answer TEXT, -- Nullable until answered by Business Stakeholder
    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER handle_updated_at_clarification_questions
    BEFORE UPDATE ON clarification_questions
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 8. PRD DOCUMENTS TABLE
-- ==========================================
-- Compiled final Production PRDs with markdown explanations and flow visualisations.
CREATE TABLE prd_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version INT NOT NULL,
    prd_markdown TEXT NOT NULL,
    mermaid_diagram TEXT, -- System architecture flowcharts or state diagrams
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER handle_updated_at_prd_documents
    BEFORE UPDATE ON prd_documents
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 9. VERSION HISTORY & SNAPSHOT LEDGER (AUDIT LEDGER)
-- ==========================================
-- Strict audit-trail ledger containing comprehensive historical snapshots of banking requirements.
CREATE TABLE version_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    requirement_id UUID NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    version_number INT NOT NULL,
    changed_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT, -- RESTRICT: Prevent deleting audit author
    change_description TEXT NOT NULL,
    state_snapshot JSONB NOT NULL, -- Stores structural state including nested user_stories and criteria
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER handle_updated_at_version_history
    BEFORE UPDATE ON version_history
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- ==========================================
-- 9b. PRD VERSIONS TABLE (IMMUTABLE VERSION HISTORY)
-- ==========================================
-- Dedicated immutable PRD version repository.
-- Each PRD generation creates a new version record.
-- Never overwrites previous versions.
-- Does NOT store version history inside requirement_states.
CREATE TABLE prd_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version_number INT NOT NULL,
    generated_prd TEXT NOT NULL,
    generated_diagram TEXT,
    generated_by VARCHAR(100) NOT NULL DEFAULT 'automated_agent',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_prd_versions_project_id ON prd_versions(project_id);
CREATE INDEX idx_prd_versions_version_number ON prd_versions(project_id, version_number);

-- ==========================================
-- 10. CONVERSATION MESSAGES TABLE
-- ==========================================
-- Dedicated table for persisting every conversation message per project.
-- Independent from requirement_states storage.
CREATE TABLE conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    workflow_state VARCHAR(50) DEFAULT '',
    intent VARCHAR(50) DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversation_messages_project_id ON conversation_messages(project_id);
CREATE INDEX idx_conversation_messages_conversation_id ON conversation_messages(conversation_id);
CREATE INDEX idx_conversation_messages_created_at ON conversation_messages(created_at);

-- ==========================================
-- 11. INDEXES FOR LOOK-UP OPTIMISATION & CONSTRAINT SPEED
-- ==========================================

-- Primary key lookups are indexed automatically.
-- Foreign Key Indexes (Required to prevent table scans on joins and deletes)
CREATE INDEX idx_projects_user_id ON projects(user_id);
CREATE INDEX idx_epics_project_id ON epics(project_id);
CREATE INDEX idx_requirements_project_id ON requirements(project_id);
CREATE INDEX idx_user_stories_requirement_id ON user_stories(requirement_id);
CREATE INDEX idx_acceptance_criteria_user_story_id ON acceptance_criteria(user_story_id);
CREATE INDEX idx_audit_results_requirement_id ON audit_results(requirement_id);
CREATE INDEX idx_clarification_questions_audit_result_id ON clarification_questions(audit_result_id);
CREATE INDEX idx_clarification_questions_target_user_story_id ON clarification_questions(target_user_story_id);
CREATE INDEX idx_prd_documents_project_id ON prd_documents(project_id);
CREATE INDEX idx_version_history_project_id ON version_history(project_id);
CREATE INDEX idx_version_history_requirement_id ON version_history(requirement_id);
CREATE INDEX idx_version_history_changed_by_user_id ON version_history(changed_by_user_id);

-- Frequently Queried Status & Categories Indexes (To accelerate dashboard metrics and filter runs)
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_epics_is_locked ON epics(is_locked);
CREATE INDEX idx_audit_results_is_valid ON audit_results(is_valid);
CREATE INDEX idx_clarification_questions_is_resolved ON clarification_questions(is_resolved);
CREATE INDEX idx_clarification_questions_category ON clarification_questions(checklist_category);