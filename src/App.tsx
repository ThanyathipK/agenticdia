import { useState } from 'react';
import Dashboard from './components/Dashboard';
import SchemaExplorer from './components/schema/SchemaExplorer';
import { ToastHost } from './components/Toast';
import {
  UserRow,
  ProjectRow,
  EpicRow,
  RequirementRow,
  UserStoryRow,
  AcceptanceCriterionRow,
  AuditResultRow,
  ClarificationQuestionRow,
  PrdDocumentRow,
  VersionHistoryRow,
  PrdVersionRow,
  ConversationMessageRow,
  ArtifactEventLogRow,
  INITIAL_USERS,
  INITIAL_PROJECTS,
  INITIAL_EPICS,
  INITIAL_REQUIREMENTS,
  INITIAL_USER_STORIES,
  INITIAL_ACCEPTANCE_CRITERIA,
  INITIAL_AUDIT_RESULTS,
  INITIAL_QUESTIONS,
  INITIAL_PRD_DOCS,
  INITIAL_VERSION_HISTORY,
  INITIAL_PRD_VERSIONS,
  INITIAL_CONVERSATION_MESSAGES,
  INITIAL_ARTIFACT_EVENT_LOGS,
} from './data';

export default function App() {
  // viewMode: 'agent' (Multi-Agent Requirements Workspace) | 'schema' (Postgres Schema Explorer)
  const [viewMode] = useState<'agent' | 'schema'>('agent');

  // Local Reactive States simulating the live Postgres Database
  const [users, setUsers] = useState<UserRow[]>(INITIAL_USERS);
  const [projects, setProjects] = useState<ProjectRow[]>(INITIAL_PROJECTS);
  const [epics, setEpics] = useState<EpicRow[]>(INITIAL_EPICS);
  const [requirements, setRequirements] = useState<RequirementRow[]>(INITIAL_REQUIREMENTS);
  const [userStories, setUserStories] = useState<UserStoryRow[]>(INITIAL_USER_STORIES);
  const [criteria, setCriteria] = useState<AcceptanceCriterionRow[]>(INITIAL_ACCEPTANCE_CRITERIA);
  const [auditResults] = useState<AuditResultRow[]>(INITIAL_AUDIT_RESULTS);
  const [questions, setQuestions] = useState<ClarificationQuestionRow[]>(INITIAL_QUESTIONS);
  const [prdDocs] = useState<PrdDocumentRow[]>(INITIAL_PRD_DOCS);
  const [versions, setVersions] = useState<VersionHistoryRow[]>(INITIAL_VERSION_HISTORY);
  const [prdVersions] = useState<PrdVersionRow[]>(INITIAL_PRD_VERSIONS);
  const [conversationMessages] = useState<ConversationMessageRow[]>(INITIAL_CONVERSATION_MESSAGES);
  const [artifactEventLogs] = useState<ArtifactEventLogRow[]>(INITIAL_ARTIFACT_EVENT_LOGS);

  return (
    <div id="app-container" className="w-full h-screen bg-background flex flex-col font-sans text-on-surface antialiased overflow-hidden">
      
      {/* Centralized error/warning/system toasts (covers Dashboard & ConfirmationPanel) */}
      <ToastHost />
      
      {/* GLOBAL TOP NAVBAR */}
      <header className="h-16 w-full shrink-0 flex items-center justify-between gap-2 px-4 sm:px-6 bg-surface border-b border-outline z-50">
        {/* Left: Branding & workspace title (same "Ai" mark as the sidebar) */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="w-8 h-8 rounded-xl bg-primary flex items-center justify-center text-on-primary text-[11px] font-bold shrink-0 shadow-sm">
            Ai
          </div>
          <div className="hidden sm:flex items-baseline gap-2.5 min-w-0">
            <h1 className="font-bold text-sm text-on-surface truncate">Agentic-AI</h1>
            <span className="text-xs text-on-surface-variant whitespace-nowrap">Requirements Workspace</span>
          </div>
        </div>
        
        </header>

      {/* MAIN CONTAINER FRAME */}
      <div className="flex-1 flex overflow-hidden">
        {viewMode === 'agent' ? (
          <Dashboard />
        ) : (
          <SchemaExplorer
            users={users}
            projects={projects}
            epics={epics}
            requirements={requirements}
            userStories={userStories}
            criteria={criteria}
            auditResults={auditResults}
            questions={questions}
            prdDocs={prdDocs}
            versions={versions}
            prdVersions={prdVersions}
            conversationMessages={conversationMessages}
            artifactEventLogs={artifactEventLogs}
            setUsers={setUsers}
            setProjects={setProjects}
            setEpics={setEpics}
            setRequirements={setRequirements}
            setUserStories={setUserStories}
            setCriteria={setCriteria}
            setQuestions={setQuestions}
            setVersions={setVersions}
          />
        )}
      </div>
    </div>
  );
}