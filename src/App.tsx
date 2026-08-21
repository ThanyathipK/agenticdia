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
  const [viewMode, setViewMode] = useState<'agent' | 'schema'>('agent');

  // Local Reactive States simulating the live Postgres Database
  const [users, setUsers] = useState<UserRow[]>(INITIAL_USERS);
  const [projects, setProjects] = useState<ProjectRow[]>(INITIAL_PROJECTS);
  const [epics, setEpics] = useState<EpicRow[]>(INITIAL_EPICS);
  const [requirements, setRequirements] = useState<RequirementRow[]>(INITIAL_REQUIREMENTS);
  const [userStories, setUserStories] = useState<UserStoryRow[]>(INITIAL_USER_STORIES);
  const [criteria, setCriteria] = useState<AcceptanceCriterionRow[]>(INITIAL_ACCEPTANCE_CRITERIA);
  const [auditResults, setAuditResults] = useState<AuditResultRow[]>(INITIAL_AUDIT_RESULTS);
  const [questions, setQuestions] = useState<ClarificationQuestionRow[]>(INITIAL_QUESTIONS);
  const [prdDocs, setPrdDocs] = useState<PrdDocumentRow[]>(INITIAL_PRD_DOCS);
  const [versions, setVersions] = useState<VersionHistoryRow[]>(INITIAL_VERSION_HISTORY);
  const [prdVersions, setPrdVersions] = useState<PrdVersionRow[]>(INITIAL_PRD_VERSIONS);
  const [conversationMessages, setConversationMessages] = useState<ConversationMessageRow[]>(INITIAL_CONVERSATION_MESSAGES);
  const [artifactEventLogs, setArtifactEventLogs] = useState<ArtifactEventLogRow[]>(INITIAL_ARTIFACT_EVENT_LOGS);

  return (
    <div id="app-container" className="w-full h-screen bg-slate-100 flex flex-col font-sans text-slate-800 antialiased overflow-hidden">
      
      {/* Centralized error/warning/system toasts (covers Dashboard & ConfirmationPanel) */}
      <ToastHost />
      
      {/* GLOBAL TOP NAVBAR (Matching Stitch Header precisely) */}
      <header className="h-16 w-full shrink-0 flex items-center justify-between px-6 bg-white border-b border-black/5 z-50">
        {/* Left: Branding & Project Title */}
        <div className="flex items-center gap-4 min-w-[280px]">
          <span className="material-symbols-outlined text-brand text-2xl font-bold">Agentic-AI</span>
          <div className="flex items-center cursor-pointer group">
            <h1 className="font-bold text-slate-900 text-sm">For PRD</h1>
          </div>
        </div>
        
        {/* Right actions: User Avatar */}
        <div className="w-8 h-8 rounded-full overflow-hidden cursor-pointer border border-brand/30">
            <img className="w-full h-full object-cover" referrerPolicy="no-referrer" src="https://lh3.googleusercontent.com/aida-public/AB6AXuBDlAC0DOS6EdgtoiiblRYSq4kovm0aGBgk0J0--3PR3DjY3GRR1MSXxugEHy6Z8hnEcHWXmlcYG_KCT2Tzf3RSjEJ_sS6mj0h8OhQRZXWOaNxhjNMAvrg3TB9jZP5Xf2rG1f_yqj9jQelGFRgrZyqoQuf34EIYP3Vkbvpkm0oruz-4pWwgPSZc9V3DcXA-qq_ufzqZc5GCob0H1QKqJcC7AAnES2wcw3fJ6hiY1iVgYEUWrmCkJbVe"/>
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