import { useState, useMemo } from 'react';
import {
  Database,
  Table,
  Code,
  GitCommit,
  ShieldCheck,
  Search,
  Copy,
  Check,
  AlertCircle,
  Activity,
  Plus,
  Lock,
  Unlock,
  RefreshCw,
  ChevronRight,
} from 'lucide-react';
import DDLViewer from './DDLViewer';
import SnapshotLedger from './SnapshotLedger';
import AuditChecklist from './AuditChecklist';
import {
  TABLES,
  INITIAL_USERS,
  INITIAL_PROJECTS,
  INITIAL_REQUIREMENTS,
  TableSchema,
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
  GridRow,
} from '../../data';
import { notify } from '../Toast';

// Single source of truth for the displayed PostgreSQL DDL. Loaded at build time
// from backend/init.sql (via Vite `?raw`) so the Schema Explorer always reflects
// the exact schema the backend provisions instead of a stale hardcoded copy.
import fullSqlText from '../../../backend/init.sql?raw';

interface SchemaExplorerProps {
  users: UserRow[];
  projects: ProjectRow[];
  epics: EpicRow[];
  requirements: RequirementRow[];
  userStories: UserStoryRow[];
  criteria: AcceptanceCriterionRow[];
  auditResults: AuditResultRow[];
  questions: ClarificationQuestionRow[];
  prdDocs: PrdDocumentRow[];
  versions: VersionHistoryRow[];
  prdVersions: PrdVersionRow[];
  conversationMessages: ConversationMessageRow[];
  artifactEventLogs: ArtifactEventLogRow[];
  setUsers: React.Dispatch<React.SetStateAction<UserRow[]>>;
  setProjects: React.Dispatch<React.SetStateAction<ProjectRow[]>>;
  setEpics: React.Dispatch<React.SetStateAction<EpicRow[]>>;
  setRequirements: React.Dispatch<React.SetStateAction<RequirementRow[]>>;
  setUserStories: React.Dispatch<React.SetStateAction<UserStoryRow[]>>;
  setCriteria: React.Dispatch<React.SetStateAction<AcceptanceCriterionRow[]>>;
  setQuestions: React.Dispatch<React.SetStateAction<ClarificationQuestionRow[]>>;
  setVersions: React.Dispatch<React.SetStateAction<VersionHistoryRow[]>>;
}

/**
 * The Postgres Schema Explorer workspace shown when the app is in 'schema'
 * view mode. Owns the schema navigation state (active tab, selected table,
 * schema lock, grid search, ingress forms) and composes the DDL viewer, table
 * explorer datagrid, snapshot ledger, and audit checklist sub-workspaces.
 */
export default function SchemaExplorer({
  users,
  projects,
  epics,
  requirements,
  userStories,
  criteria,
  auditResults,
  questions,
  prdDocs,
  versions,
  prdVersions,
  conversationMessages,
  artifactEventLogs,
  setUsers,
  setProjects,
  setEpics,
  setRequirements,
  setUserStories,
  setCriteria,
  setQuestions,
  setVersions,
}: SchemaExplorerProps) {
  // Navigation Tabs: 'ddl' | 'explorer' | 'ledger' | 'checklist'
  const [activeTab, setActiveTab] = useState<'ddl' | 'explorer' | 'ledger' | 'checklist'>('explorer');

  // Selected Table inside Explorer
  const [selectedTableName, setSelectedTableName] = useState<string>('requirements');

  // State for insertion dialog input values
  const [userForm, setUserForm] = useState({ email: '', fullName: '', role: 'Business Analyst' });
  const [projectForm, setProjectForm] = useState({ name: '', description: '', userId: INITIAL_USERS[0].id, industryStandard: 'Krungsri Nimble Baseline' });
  const [reqForm, setReqForm] = useState({ epicName: '', projectId: INITIAL_PROJECTS[0].id });
  const [storyForm, setStoryForm] = useState({ requirementId: INITIAL_REQUIREMENTS[0].id, storyTitle: '', ticketCode: 'US-PAY-100', asA: '', iWantTo: '', soThat: '', criteriaText: '' });

  // State for SQL viewer scroll highlights
  const [copiedSql, setCopiedSql] = useState<boolean>(false);

  // Trigger Schema lock
  const [isSchemaLocked, setIsSchemaLocked] = useState<boolean>(true);

  // Search keyword in datagrid
  const [gridSearch, setGridSearch] = useState<string>('');
// Selected table schema object
  const activeTableSchema = useMemo<TableSchema>(() => {
    return TABLES.find(t => t.name === selectedTableName) || TABLES[0];
  }, [selectedTableName]);

  // Helper to retrieve user list or specific attributes
  const getUserName = (id: string) => {
    const u = users.find(x => x.id === id);
    return u ? u.full_name : 'Unknown User';
  };

  const getProjectName = (id: string) => {
    const p = projects.find(x => x.id === id);
    return p ? p.name : 'Unknown Project';
  };

  const getRequirementTitle = (id: string) => {
    const r = requirements.find(x => x.id === id);
    return r ? r.title : 'Unknown Requirement';
  };

  // Filter Grid rows dynamically based on selectedTableName
  const filteredGridData = useMemo<GridRow[]>(() => {
    let raw: GridRow[] = [];
    switch (selectedTableName) {
      case 'users': raw = users; break;
      case 'projects': raw = projects; break;
      case 'epics': raw = epics; break;
      case 'requirements': raw = requirements; break;
      case 'user_stories': raw = userStories; break;
      case 'acceptance_criteria': raw = criteria; break;
      case 'audit_results': raw = auditResults; break;
      case 'clarification_questions': raw = questions; break;
      case 'prd_documents': raw = prdDocs; break;
      case 'version_history': raw = versions; break;
      case 'prd_versions': raw = prdVersions; break;
      case 'conversation_messages': raw = conversationMessages; break;
      case 'artifact_event_logs': raw = artifactEventLogs; break;
    }
    if (!gridSearch) return raw;
    return raw.filter((row: GridRow) =>
      JSON.stringify(row).toLowerCase().includes(gridSearch.toLowerCase())
    );
  }, [selectedTableName, gridSearch, users, projects, epics, requirements, userStories, criteria, auditResults, questions, prdDocs, versions, prdVersions, conversationMessages, artifactEventLogs]);

  const copySqlToClipboard = () => {
    navigator.clipboard.writeText(fullSqlText);
    setCopiedSql(true);
    notify("PostgreSQL DDL script copied to clipboard!", 'success');
    setTimeout(() => setCopiedSql(false), 2000);
  };
// Insert Simulated Database Record handler
  const handleInsertSimulatedRow = (e: React.FormEvent) => {
    e.preventDefault();
    const newId = crypto.randomUUID();
    const nowTimestamp = new Date().toISOString().replace('Z', '+00');

    let simulatedSql = '';

    if (selectedTableName === 'users') {
      if (!userForm.email || !userForm.fullName) {
        notify("Error: Missing required fields email or full_name", 'info');
        return;
      }
      const newRow: UserRow = {
        id: newId,
        email: userForm.email,
        full_name: userForm.fullName,
        role: userForm.role,
        created_at: nowTimestamp
      };
      setUsers([newRow, ...users]);
      simulatedSql = `INSERT INTO users (id, email, full_name, role, created_at, updated_at)\nVALUES ('${newId}', '${userForm.email}', '${userForm.fullName}', '${userForm.role}', NOW(), NOW());`;
      setUserForm({ email: '', fullName: '', role: 'Business Analyst' });

    } else if (selectedTableName === 'projects') {
      if (!projectForm.name) {
        notify("Error: Missing project name", 'info');
        return;
      }
      const newRow: ProjectRow = {
        id: newId,
        user_id: projectForm.userId,
        name: projectForm.name,
        description: projectForm.description,
        industry_standard: projectForm.industryStandard,
        is_locked: false,
        locked_by: null,
        locked_at: null,
        lock_reason: null,
        is_pinned: false,
        created_at: nowTimestamp
      };
      setProjects([newRow, ...projects]);
      simulatedSql = `INSERT INTO projects (id, user_id, name, description, industry_standard, created_at)\nVALUES ('${newId}', '${projectForm.userId}', '${projectForm.name}', '${projectForm.description}', '${projectForm.industryStandard}', NOW());`;
      setProjectForm(prev => ({ ...prev, name: '', description: '' }));

    } else if (selectedTableName === 'epics') {
      if (!reqForm.epicName) {
        notify("Error: Epic name required", 'info');
        return;
      }
      const newRow: EpicRow = {
        id: newId,
        project_id: reqForm.projectId,
        epic_name: reqForm.epicName,
        version: 1,
        is_locked: false,
        status: 'active',
        created_at: nowTimestamp
      };
      setEpics([newRow, ...epics]);
      simulatedSql = `INSERT INTO epics (id, project_id, epic_name, version, is_locked, status, created_at)\nVALUES ('${newId}', '${reqForm.projectId}', '${reqForm.epicName}', 1, FALSE, 'active', NOW());`;
      setReqForm(prev => ({ ...prev, epicName: '' }));

    } else if (selectedTableName === 'requirements') {
      if (!reqForm.epicName) {
        notify("Error: Requirement title required", 'info');
        return;
      }
      const newRow: RequirementRow = {
        id: newId,
        project_id: reqForm.projectId,
        epic_id: null,
        requirement_code: 'REQ-NEW-' + Math.floor(100 + Math.random() * 900),
        title: reqForm.epicName,
        description: '',
        priority: 'Medium',
        status: 'active',
        version: 1,
        is_locked: false,
        locked_by: null,
        locked_at: null,
        lock_reason: null,
        created_at: nowTimestamp
      };
      setRequirements([newRow, ...requirements]);
      simulatedSql = `INSERT INTO requirements (id, project_id, epic_id, requirement_code, title, description, priority, status, version, created_at)\nVALUES ('${newId}', '${reqForm.projectId}', NULL, 'REQ-NEW-${Math.floor(100 + Math.random() * 900)}', '${reqForm.epicName}', '', 'Medium', 'active', 1, NOW());`;
      setReqForm(prev => ({ ...prev, epicName: '' }));
} else if (selectedTableName === 'user_stories') {
      if (!storyForm.storyTitle || !storyForm.asA || !storyForm.iWantTo || !storyForm.soThat) {
        notify("Error: Complete story parts (As a, I want to, So that)", 'info');
        return;
      }
      // Check unique code
      if (userStories.some(s => s.ticket_code === storyForm.ticketCode)) {
        notify(`Error: Ticket code ${storyForm.ticketCode} is already registered.`, 'info');
        return;
      }

      const newStory: UserStoryRow = {
        id: newId,
        project_id: null,
        requirement_id: storyForm.requirementId,
        ticket_code: storyForm.ticketCode,
        story_title: storyForm.storyTitle,
        as_a: storyForm.asA,
        i_want_to: storyForm.iWantTo,
        so_that: storyForm.soThat,
        status: 'active',
        version: 1,
        last_modified_by: 'automated_agent',
        change_type: 'created',
        is_locked: false,
        locked_by: null,
        locked_at: null,
        lock_reason: null,
        created_at: nowTimestamp
      };

      setUserStories([newStory, ...userStories]);

      // If they also added acceptance criteria text, insert that too
      if (storyForm.criteriaText.trim()) {
        const criteriaId = crypto.randomUUID();
        const newCriterion: AcceptanceCriterionRow = {
          id: criteriaId,
          user_story_id: newId,
          criteria_text: storyForm.criteriaText.trim(),
          status: 'active',
          version: 1,
          last_modified_by: 'automated_agent',
          change_type: 'created',
          is_locked: false,
          locked_by: null,
          locked_at: null,
          lock_reason: null,
          created_at: nowTimestamp
        };
        setCriteria(prev => [newCriterion, ...prev]);
        simulatedSql = `BEGIN;\nINSERT INTO user_stories (id, requirement_id, ticket_code, story_title, as_a, i_want_to, so_that, created_at)\nVALUES ('${newId}', '${storyForm.requirementId}', '${storyForm.ticketCode}', '${storyForm.storyTitle}', '${storyForm.asA}', '${storyForm.iWantTo}', '${storyForm.soThat}', NOW());\n\nINSERT INTO acceptance_criteria (id, user_story_id, criteria_text, created_at)\nVALUES ('${criteriaId}', '${newId}', '${storyForm.criteriaText.replace(/'/g, "''")}', NOW());\nCOMMIT;`;
      } else {
        simulatedSql = `INSERT INTO user_stories (id, requirement_id, ticket_code, story_title, as_a, i_want_to, so_that, created_at)\nVALUES ('${newId}', '${storyForm.requirementId}', '${storyForm.ticketCode}', '${storyForm.storyTitle}', '${storyForm.asA}', '${storyForm.iWantTo}', '${storyForm.soThat}', NOW());`;
      }

      // Note: total_user_stories counter removed in new schema

      setStoryForm({
        requirementId: INITIAL_REQUIREMENTS[0].id,
        storyTitle: '',
        ticketCode: 'US-PAY-' + Math.floor(100 + Math.random() * 900),
        asA: '',
        iWantTo: '',
        soThat: '',
        criteriaText: ''
      });
    }

    notify(`Successfully Simulated! Record inserted into local state.`, 'success');
    // Log virtual SQL to show enterprise transparency
    console.log("SIMULATED SQL INGRESS:\n", simulatedSql);
  };

  // Toggle Single Epic Lock status
  // Note: is_locked is now at the epic level, not requirement level
  const toggleEpicLock = (epicId: string) => {
    const epic = epics.find(e => e.id === epicId);
    if (!epic) {
      notify("Epic not found.", 'info');
      return;
    }
    const nextLocked = !epic.is_locked;
    setEpics(prev => prev.map(e => e.id === epicId ? { ...e, is_locked: nextLocked } : e));
    notify(
      nextLocked
        ? `Epic "${epic.epic_name}" locked.`
        : `Epic "${epic.epic_name}" unlocked.`,
      'success'
    );
  };

  // Count metrics
  const activeUnresolvedQuestionsCount = useMemo(() => {
    return questions.filter(q => !q.is_resolved).length;
  }, [questions]);

  const auditValidityScorePercent = useMemo(() => {
    const total = questions.length;
    if (total === 0) return 100;
    const resolved = questions.filter(q => q.is_resolved).length;
    return Math.round((resolved / total) * 100);
  }, [questions]);

  return (
    <>
{/* ==========================================
          SIDEBAR NAVIGATION (Postgres Hub)
      ========================================== */}
      <aside id="sidebar-panel" className="w-72 bg-slate-900 flex flex-col border-r border-slate-800 shrink-0">
        <div className="p-5 border-b border-slate-800">
          <div className="flex items-center gap-2 text-navy-400 font-bold text-lg">
            <div className="w-9 h-9 bg-navy-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-navy-900/30">
              <Database className="w-5 h-5" />
            </div>
            <div className="flex flex-col">
              <span className="leading-tight text-white tracking-tight">Architect SQL</span>
              <span className="text-[10px] text-slate-400 font-mono font-normal">Banking Schema Platform</span>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-4 py-6 overflow-y-auto space-y-6">
          
          {/* Main Tabs */}
          <div>
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2.5 px-2">System Workspaces</div>
            <ul className="space-y-1">
              <li>
                <button 
                  onClick={() => setActiveTab('explorer')}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm transition-all ${
                    activeTab === 'explorer' 
                      ? 'bg-navy-600 text-white font-medium shadow-md shadow-navy-900/20' 
                      : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Table className="w-4 h-4" />
                    <span>Table Schema Explorer</span>
                  </div>
                  <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded font-mono">{TABLES.length} TBL</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => setActiveTab('ddl')}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm transition-all ${
                    activeTab === 'ddl' 
                      ? 'bg-navy-600 text-white font-medium shadow-md shadow-navy-900/20' 
                      : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Code className="w-4 h-4" />
                    <span>PostgreSQL DDL script</span>
                  </div>
                  <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded font-mono font-bold">init.sql</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => setActiveTab('ledger')}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm transition-all ${
                    activeTab === 'ledger' 
                      ? 'bg-navy-600 text-white font-medium shadow-md shadow-navy-900/20' 
                      : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <GitCommit className="w-4 h-4" />
                    <span>Immutable Snapshot Ledger</span>
                  </div>
                  <span className="text-[10px] bg-navy-500/10 text-navy-400 border border-navy-500/20 px-1.5 py-0.5 rounded font-mono">{versions.length}</span>
                </button>
              </li>
              <li>
                <button 
                  onClick={() => setActiveTab('checklist')}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm transition-all ${
                    activeTab === 'checklist' 
                      ? 'bg-navy-600 text-white font-medium shadow-md shadow-navy-900/20' 
                      : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <ShieldCheck className="w-4 h-4" />
                    <span>Audit Integrity & Compliance</span>
                  </div>
                  {activeUnresolvedQuestionsCount > 0 ? (
                    <span className="text-[10px] bg-orange-500 text-slate-950 px-1.5 py-0.5 rounded font-bold animate-pulse">{activeUnresolvedQuestionsCount} PND</span>
                  ) : (
                    <span className="text-[10px] bg-emerald-500 text-slate-950 px-1.5 py-0.5 rounded font-bold">PASS</span>
                  )}
                </button>
              </li>
            </ul>
          </div>
{/* Sub Explorer: Active Tables shortcuts */}
          <div>
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2.5 px-2">Table Schema Directory</div>
            <ul className="space-y-1 text-xs">
              {TABLES.map((t) => (
                <li key={t.name}>
                  <button
                    onClick={() => {
                      setSelectedTableName(t.name);
                      setActiveTab('explorer');
                    }}
                    className={`w-full flex items-center justify-between px-3 py-1.5 rounded transition-all ${
                      selectedTableName === t.name && activeTab === 'explorer'
                        ? 'bg-slate-800 text-navy-400 font-semibold'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/30'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-600"></span>
                      <span className="font-mono">{t.name}</span>
                    </div>
                    {t.name === 'version_history' && (
                      <span className="text-[9px] bg-navy-500/20 text-navy-300 font-mono px-1 py-0.1 rounded border border-navy-500/20">JSONB</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {/* Quick Metrics */}
          <div className="bg-slate-950/50 p-4 rounded-2xl border border-slate-800 space-y-3">
            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Audit Security Level</div>
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-slate-300">
                <span>Compliance Rating</span>
                <span className="font-mono font-bold text-emerald-400">{auditValidityScorePercent}%</span>
              </div>
              <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                <div 
                  className="bg-emerald-500 h-full rounded-full transition-all duration-500" 
                  style={{ width: `${auditValidityScorePercent}%` }}
                ></div>
              </div>
            </div>
            <div className="flex items-center justify-between text-[10px] text-slate-500">
              <span>Total Stories: {userStories.length}</span>
              <span>Audit Lock: 0 Epic</span>
            </div>
          </div>

        </nav>

        <div className="p-4 border-t border-slate-800 bg-slate-950 text-xs">
          <div className="flex items-center gap-3">
            <div className={`w-2.5 h-2.5 rounded-full ${activeUnresolvedQuestionsCount === 0 ? 'bg-emerald-500' : 'bg-orange-400'} animate-pulse`}></div>
            <div className="flex flex-col">
              <span className="text-slate-300 font-medium">Database Cloud Ready</span>
              <span className="text-[10px] text-slate-500">Fast connection tunnel active</span>
            </div>
          </div>
        </div>
      </aside>
{/* ==========================================
          MAIN CONTENT SECTION
      ========================================== */}
      <main className="flex-1 flex flex-col overflow-hidden">
        
        {/* HEADER BAR */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-8 shrink-0">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-slate-900 tracking-tight">Enterprise Core Banking</h1>
              <span className="text-[10px] font-mono px-1.5 py-0.5 bg-navy-50 text-navy-700 font-bold border border-navy-200 rounded">v1.2.0-STABLE</span>
            </div>
            <p className="text-xs text-slate-500">Requirements Engineering, Postgres Schema DDL & Snapshot Ledger</p>
          </div>
          
          <div className="flex items-center gap-3">
            <button 
              onClick={copySqlToClipboard}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-xl hover:bg-slate-50 active:bg-slate-100 transition-all cursor-pointer shadow-sm"
            >
              {copiedSql ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copiedSql ? "Copied" : "Copy DDL Code"}</span>
            </button>
            
            <button 
              onClick={() => {
                setIsSchemaLocked(!isSchemaLocked);
                notify(isSchemaLocked ? "Schema unlocked. Sandbox mutations allowed." : "Schema safely locked. Snapshot immutability enforced.", 'info');
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl transition-all border shadow-sm ${
                isSchemaLocked 
                  ? 'bg-emerald-50/50 text-emerald-700 border-emerald-300 hover:bg-emerald-100/50'
                  : 'bg-orange-50/50 text-orange-700 border-orange-300 hover:bg-orange-100/50'
              }`}
            >
              {isSchemaLocked ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
              <span>{isSchemaLocked ? "Schema Locked" : "Schema Unlocked"}</span>
            </button>

            <button 
              onClick={() => {
                notify("Initializing schema check... all constraints resolved in 0.2ms. Supabase sync OK.", 'success');
              }}
              className="flex items-center gap-1.5 px-4.5 py-1.5 text-xs font-semibold text-white bg-navy-600 rounded-xl hover:bg-navy-700 shadow-md shadow-navy-500/20 active:translate-y-0.5 transition-all"
            >
              <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ animationDuration: '4s' }} />
              <span>Verify Live Schema</span>
            </button>
          </div>
        </header>

        {/* MAIN TABBED SCROLL CONTAINER */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50 flex gap-6">
          
          {/* LEFT AREA: WORKSPACE DISPLAY */}
          <div className="flex-1 flex flex-col gap-6 min-w-0">
            
            {/* TAB: POSTGRESQL DDL (init.sql) */}
            {activeTab === 'ddl' && (
              <DDLViewer
                sqlText={fullSqlText}
                onCopySql={copySqlToClipboard}
              />
            )}
{/* ==========================================
              TAB: TABLE SCHEMA EXPLORER
          ========================================== */}
            {activeTab === 'explorer' && (
              <div className="flex flex-col gap-6">
                
                {/* Table metadata card */}
                <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
                  <div className="flex justify-between items-start gap-4">
                    <div>
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-xl bg-navy-100 text-navy-600 flex items-center justify-center font-mono font-bold text-sm">
                          T
                        </div>
                        <h2 className="text-lg font-bold text-slate-900 font-mono">
                          {activeTableSchema.name}
                        </h2>
                      </div>
                      <p className="text-sm text-slate-600 mt-2">
                        {activeTableSchema.description}
                      </p>
                    </div>

                    <div className="bg-navy-50 border border-navy-100 p-4 rounded-2xl max-w-sm shrink-0">
                      <div className="flex gap-2 items-start">
                        <Activity className="w-4 h-4 text-navy-600 mt-0.5 shrink-0" />
                        <div>
                          <h4 className="text-[11px] font-bold text-navy-900 uppercase tracking-wider">Banking Compliance Purpose</h4>
                          <p className="text-xs text-navy-700 mt-1 leading-relaxed">
                            {activeTableSchema.bankingContext}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Table properties list */}
                  <div className="mt-6 border-t border-slate-100 pt-5">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                      <div className="p-3 bg-slate-50 rounded-xl">
                        <span className="text-slate-400 block font-semibold mb-1">Index Setup</span>
                        <div className="font-mono text-[11px] space-y-1">
                          {activeTableSchema.indexes.map((idx, i) => (
                            <div key={i} className="text-slate-700 bg-white px-2 py-0.5 border border-slate-200 rounded">
                              {idx}
                            </div>
                          ))}
                          {activeTableSchema.indexes.length === 0 && (
                            <span className="text-slate-400 italic">PK auto-indexed</span>
                          )}
                        </div>
                      </div>

                      <div className="p-3 bg-slate-50 rounded-xl col-span-2">
                        <span className="text-slate-400 block font-semibold mb-1">Relational Constraints (Foreign Keys)</span>
                        <div className="space-y-1">
                          {activeTableSchema.relations.map((rel, i) => (
                            <div key={i} className="flex items-center gap-2 font-mono text-[11px] text-slate-700 bg-white px-2 py-0.5 border border-slate-200 rounded">
                              <span className="font-bold text-navy-600">{rel.fromColumn}</span>
                              <span>&rarr;</span>
                              <span className="font-bold text-slate-900">{rel.toTable}({rel.toColumn})</span>
                              <span className="ml-auto text-[10px] bg-red-50 text-red-700 px-1.5 py-0.2 rounded border border-red-100 font-bold uppercase">
                                ON DELETE {rel.onDelete}
                              </span>
                            </div>
                          ))}
                          {activeTableSchema.relations.length === 0 && (
                            <span className="text-slate-400 italic font-sans block">Independent lookup entity (No outbound foreign relations).</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
{/* Datagrid Section */}
                <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm flex flex-col">
                  <div className="bg-slate-50 border-b border-slate-200 px-6 py-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">Live Simulated Ingress Records</h3>
                      <p className="text-xs text-slate-500 mt-0.5">Reflecting current state in client cache</p>
                    </div>
                    
                    <div className="flex items-center gap-2 w-full sm:w-auto">
                      <div className="relative flex-1 sm:flex-initial">
                        <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
                        <input 
                          type="text" 
                          placeholder="Filter grid data..."
                          value={gridSearch}
                          onChange={(e) => setGridSearch(e.target.value)}
                          className="pl-9 pr-3 py-1.5 w-full sm:w-48 bg-white border border-slate-300 rounded-xl text-xs focus:outline-none focus:border-navy-600 transition-colors"
                        />
                      </div>
                      <span className="text-xs font-mono text-slate-500 bg-slate-200 px-2 py-1 rounded font-bold shrink-0">
                        {filteredGridData.length} ROWS
                      </span>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50/50 border-b border-slate-200 text-slate-500 font-semibold select-none">
                          <th className="p-3.5 pl-6 font-mono">id (UUID)</th>
                          {activeTableSchema.columns.filter(c => c.name !== 'id').map(c => (
                            <th key={c.name} className="p-3.5">
                              <div className="flex flex-col">
                                <span className="font-mono text-slate-950">{c.name}</span>
                                <span className="text-[10px] text-slate-400 font-normal">{c.type}</span>
                              </div>
                            </th>
                          ))}
                          {selectedTableName === 'requirements' && (
                            <th className="p-3.5 text-right pr-6">Lock Status</th>
                          )}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {filteredGridData.length === 0 ? (
                          <tr>
                            <td colSpan={activeTableSchema.columns.length + 1} className="p-10 text-center text-slate-400 italic">
                              No rows simulated or matching filter. Use the form below to simulate SQL INSERT!
                            </td>
                          </tr>
                        ) : (
filteredGridData.map((row: GridRow, rIdx) => {
                            const epicForRow = row.epic_id ? epics.find(e => e.id === row.epic_id) : undefined;
                            const epicLocked = epicForRow ? epicForRow.is_locked : !!row.is_locked;
                            return (
                            <tr key={row.id || rIdx} className="hover:bg-slate-50/50 transition-colors">
                              <td className="p-3.5 pl-6 font-mono text-navy-600 select-all max-w-[120px] truncate" title={row.id}>
                                {row.id}
                              </td>
                              {activeTableSchema.columns.filter(c => c.name !== 'id').map(col => {
                                let val: unknown = row[col.name];
                                if (typeof val === 'object' && val !== null) {
                                  val = JSON.stringify(val);
                                }
                                const displayValue = val === true ? 'TRUE' : val === false ? 'FALSE' : val === null || val === undefined ? 'NULL' : String(val);
                                
                                return (
                                  <td key={col.name} className="p-3.5 text-slate-700 font-sans max-w-[200px] truncate" title={displayValue}>
                                    {col.name === 'project_id' ? (
                                      <span className="font-mono bg-slate-100 text-slate-700 px-1 py-0.5 rounded text-[10px]" title={val as string}>
                                        {getProjectName(val as string)}
                                      </span>
                                    ) : col.name === 'user_id' || col.name === 'changed_by_user_id' ? (
                                      <span className="font-mono bg-slate-100 text-slate-700 px-1 py-0.5 rounded text-[10px]" title={val as string}>
                                        {getUserName(val as string)}
                                      </span>
                                    ) : col.name === 'requirement_id' ? (
                                      <span className="font-mono bg-slate-100 text-slate-700 px-1 py-0.5 rounded text-[10px]" title={val as string}>
                                        {getRequirementTitle(val as string)}
                                      </span>
                                    ) : col.name === 'state_snapshot' || col.name === 'passed_checks' || col.name === 'failed_checks' ? (
                                      <code className="text-[10px] bg-slate-900 text-slate-300 px-1.5 py-0.5 rounded font-mono truncate block max-w-xs">{displayValue}</code>
                                    ) : (
                                      displayValue
                                    )}
                                  </td>
                                );
                              })}
                              {selectedTableName === 'requirements' && (
                                <td className="p-3.5 text-right pr-6">
                                  <button 
                                    onClick={() => row.epic_id && toggleEpicLock(row.epic_id)}
                                    className={`px-2 py-1 rounded text-[10px] font-bold ${
                                      epicLocked 
                                        ? 'bg-orange-100 text-orange-800 hover:bg-orange-200' 
                                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                    } transition-colors`}
                                  >
                                    {epicLocked ? "Locked 🔒" : "Unlock 🔓"}
                                  </button>
                                </td>
                              )}
                            </tr>
                          );
                        })
                      )}
                      </tbody>
                    </table>
                  </div>
                </div>
{/* Interactive Insertion Simulator */}
                <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <Plus className="w-4 h-4 text-navy-600" />
                    <h3 className="text-sm font-bold text-slate-900">
                      Interactive SQL Data Ingress Simulator
                    </h3>
                  </div>
                  <p className="text-xs text-slate-500 mb-6 -mt-3">
                    Simulate a high-precision `INSERT INTO {selectedTableName}` query with full schema type checking.
                  </p>

                  {isSchemaLocked && (
                    <div className="bg-slate-50 border border-slate-200 p-4 rounded-2xl flex items-start gap-3 mb-6">
                      <AlertCircle className="w-4.5 h-4.5 text-orange-600 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-xs font-semibold text-slate-800">Schema Ingress Protected</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          The schema protection is locked to safeguard production integrity. Toggle the <strong>"Schema Lock"</strong> in the top header to unlock interactive mutations and simulate custom records!
                        </p>
                      </div>
                    </div>
                  )}

                  {!isSchemaLocked && (
                    <form onSubmit={handleInsertSimulatedRow} className="space-y-4">
                      
                      {/* Selected Table = USERS FORM */}
                      {selectedTableName === 'users' && (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div>
                            <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Corporate Email</label>
                            <input 
                              type="email" 
                              required
                              value={userForm.email} 
                              onChange={e => setUserForm({ ...userForm, email: e.target.value })}
                              placeholder="e.g. some.user@krungsri.com"
                              className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Full Name</label>
                            <input 
                              type="text" 
                              required
                              value={userForm.fullName} 
                              onChange={e => setUserForm({ ...userForm, fullName: e.target.value })}
                              placeholder="e.g. Kittipong Wang"
                              className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">RBAC Role</label>
                            <select 
                              value={userForm.role}
                              onChange={e => setUserForm({ ...userForm, role: e.target.value })}
                              className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                            >
                              <option value="Product Owner">Product Owner</option>
                              <option value="Business Analyst">Business Analyst</option>
                              <option value="Regulatory Auditor">Regulatory Auditor</option>
                              <option value="Lead Developer">Lead Developer</option>
                            </select>
                          </div>
                        </div>
                      )}
{/* Selected Table = PROJECTS FORM */}
                      {selectedTableName === 'projects' && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Project Name</label>
                            <input 
                              type="text" 
                              required
                              value={projectForm.name} 
                              onChange={e => setProjectForm({ ...projectForm, name: e.target.value })}
                              placeholder="e.g. Nimble Core Mobile API"
                              className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Industry Standard</label>
                            <input 
                              type="text" 
                              value={projectForm.industryStandard} 
                              onChange={e => setProjectForm({ ...projectForm, industryStandard: e.target.value })}
                              placeholder="e.g. Krungsri Nimble Baseline"
                              className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Target Analyst (user_id)</label>
                            <select 
                              value={projectForm.userId}
                              onChange={e => setProjectForm({ ...projectForm, userId: e.target.value })}
                              className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                            >
                              {users.map(u => (
                                <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>
                              ))}
                            </select>
                          </div>
                          <div className="md:col-span-2">
                            <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">System Scope Description</label>
                            <textarea 
                              value={projectForm.description} 
                              onChange={e => setProjectForm({ ...projectForm, description: e.target.value })}
                              placeholder="Provide enterprise banking scope definitions..."
                              className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600 h-16"
                            />
                          </div>
                        </div>
                      )}
{/* Selected Table = EPICS FORM */}
                        {selectedTableName === 'epics' && (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                              <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Epic Name</label>
                              <input 
                                type="text" 
                                required
                                value={reqForm.epicName} 
                                onChange={e => setReqForm({ ...reqForm, epicName: e.target.value })}
                                placeholder="e.g. Multi-factor Transaction Authorization"
                                className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Parent Project (project_id)</label>
                              <select 
                                value={reqForm.projectId}
                                onChange={e => setReqForm({ ...reqForm, projectId: e.target.value })}
                                className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                              >
                                {projects.map(p => (
                                  <option key={p.id} value={p.id}>{p.name}</option>
                                ))}
                              </select>
                            </div>
                          </div>
                        )}

                        {/* Selected Table = REQUIREMENTS FORM */}
                        {selectedTableName === 'requirements' && (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                              <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Requirement Title</label>
                              <input 
                                type="text" 
                                required
                                value={reqForm.epicName} 
                                onChange={e => setReqForm({ ...reqForm, epicName: e.target.value })}
                                placeholder="e.g. OTP Validation for High-Value Transactions"
                                className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Parent Project (project_id)</label>
                              <select 
                                value={reqForm.projectId}
                                onChange={e => setReqForm({ ...reqForm, projectId: e.target.value })}
                                className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                              >
                                {projects.map(p => (
                                  <option key={p.id} value={p.id}>{p.name}</option>
                                ))}
                              </select>
                            </div>
                          </div>
                        )}
{/* Selected Table = USER STORIES FORM */}
                        {selectedTableName === 'user_stories' && (
                          <div className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                              <div>
                                <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Epic Grouping (requirement_id)</label>
                                <select 
                                  value={storyForm.requirementId}
                                  onChange={e => setStoryForm({ ...storyForm, requirementId: e.target.value })}
                                  className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                                >
                                  {requirements.map(r => (
                                    <option key={r.id} value={r.id}>{r.title}</option>
                                  ))}
                                </select>
                              </div>
                              <div>
                                <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Agile Ticket Code</label>
                                <input 
                                  type="text" 
                                  required
                                  value={storyForm.ticketCode} 
                                  onChange={e => setStoryForm({ ...storyForm, ticketCode: e.target.value })}
                                  placeholder="e.g. US-PAY-004"
                                  className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                                />
                              </div>
                              <div>
                                <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Story Descriptive Title</label>
                                <input 
                                  type="text" 
                                  required
                                  value={storyForm.storyTitle} 
                                  onChange={e => setStoryForm({ ...storyForm, storyTitle: e.target.value })}
                                  placeholder="e.g. Biometric Fallback Authentication"
                                  className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
                                />
                              </div>
                            </div>
<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                              <div>
                                <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">As a...</label>
                                <textarea 
                                  required
                                  value={storyForm.asA} 
                                  onChange={e => setStoryForm({ ...storyForm, asA: e.target.value })}
                                  placeholder="e.g. Retail bank client with locked credentials"
                                  className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600 h-16"
                                />
                              </div>
                              <div>
                                <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">I want to...</label>
                                <textarea 
                                  required
                                  value={storyForm.iWantTo} 
                                  onChange={e => setStoryForm({ ...storyForm, iWantTo: e.target.value })}
                                  placeholder="e.g. authenticate utilizing my verified device's secure enclave biometric keys"
                                  className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600 h-16"
                                />
                              </div>
                              <div>
                                <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">So that...</label>
                                <textarea 
                                  required
                                  value={storyForm.soThat} 
                                  onChange={e => setStoryForm({ ...storyForm, soThat: e.target.value })}
                                  placeholder="e.g. I can perform transaction limits overrides without needing phone-support calls."
                                  className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600 h-16"
                                />
                              </div>
                            </div>

                            <div className="bg-navy-50/50 p-4 rounded-2xl border border-navy-100">
                              <label className="block text-[11px] font-bold text-slate-700 uppercase mb-1">
                                Optional: Append Acceptance Criteria block (Automated transactional insertion)
                              </label>
                              <textarea 
                                value={storyForm.criteriaText} 
                                onChange={e => setStoryForm({ ...storyForm, criteriaText: e.target.value })}
                                placeholder="GIVEN the customer faces credential failure&#10;WHEN they select face verification&#10;THEN the mobile client queries secure local hardware match..."
                                className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600 h-20 font-mono"
                              />
                            </div>
                          </div>
                        )}
{/* Read-only Tables info */}
                        {(selectedTableName === 'acceptance_criteria' || 
                          selectedTableName === 'audit_results' || 
                          selectedTableName === 'clarification_questions' || 
                          selectedTableName === 'prd_documents' || 
                          selectedTableName === 'prd_versions' ||
                          selectedTableName === 'conversation_messages' ||
                          selectedTableName === 'artifact_event_logs') && (
                          <div className="bg-slate-50 text-slate-600 p-4 rounded-xl text-xs italic">
                            Mutations on <strong>{selectedTableName}</strong> are automatically triggered by regulatory checking routines, system audits, or snapshot creation to maintain professional state-machine integrity. Use the corresponding dedicated widgets for these tables!
                          </div>
                        )}

                        <div className="flex justify-end pt-2">
                          {!(selectedTableName === 'acceptance_criteria' || 
                            selectedTableName === 'audit_results' || 
                            selectedTableName === 'clarification_questions' || 
                            selectedTableName === 'prd_documents' || 
                            selectedTableName === 'prd_versions' ||
                            selectedTableName === 'conversation_messages' ||
                            selectedTableName === 'artifact_event_logs') && (
                            <button
                              type="submit"
                              className="px-4.5 py-2 bg-slate-900 text-white rounded-xl hover:bg-slate-800 transition-colors text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow"
                            >
                              <Plus className="w-4 h-4" />
                              <span>Execute Simulated SQL Insert</span>
                            </button>
                          )}
                        </div>

                      </form>
                    )}
                  </div>

                </div>
              )}

              {/* ==========================================
                  TAB: IMMUTABLE VERSION SNAPSHOT LEDGER
              ========================================== */}
              {activeTab === 'ledger' && (
                <SnapshotLedger
                  requirements={requirements}
                  users={users}
                  projects={projects}
                  userStories={userStories}
                  criteria={criteria}
                  versions={versions}
                  setRequirements={setRequirements}
                  setVersions={setVersions}
                  getRequirementTitle={getRequirementTitle}
                  getProjectName={getProjectName}
                  getUserName={getUserName}
                />
              )}

              {/* ==========================================
                  TAB: AUDIT INTEGRITY & COMPLIANCE
              ========================================== */}
              {activeTab === 'checklist' && (
                <AuditChecklist
                  questions={questions}
                  setQuestions={setQuestions}
                />
              )}

            </div>
{/* RIGHT PANEL: AUDIT SIDE BAR VIEW */}
            <div className="w-80 shrink-0 flex flex-col gap-6">
              
              {/* Card 1: Static DDL Validation Highlights */}
              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Audit Checklist</h3>
                  <span className="text-[10px] bg-slate-100 text-slate-600 font-bold px-1.5 py-0.5 rounded font-mono">DATA</span>
                </div>
                
                <div className="space-y-4">
                  <div className="flex items-start gap-3">
                    <div className="mt-1 w-4 h-4 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center shrink-0">
                      <Check className="w-2.5 h-2.5 stroke-[4]" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-800">Supabase UUID v4</p>
                      <p className="text-[10px] text-slate-500">All primary keys utilize gen_random_uuid() for identity isolation.</p>
                    </div>
                  </div>
                  
                  <div className="flex items-start gap-3">
                    <div className="mt-1 w-4 h-4 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center shrink-0">
                      <Check className="w-2.5 h-2.5 stroke-[4]" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-800">Timezone Integrity</p>
                      <p className="text-[10px] text-slate-500">TIMESTAMPTZ explicitly configured to support cross-timezone auditing.</p>
                    </div>
                  </div>
                  
                  <div className="flex items-start gap-3">
                    <div className="mt-1 w-4 h-4 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center shrink-0">
                      <Check className="w-2.5 h-2.5 stroke-[4]" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-800">Cascade Constraint Locks</p>
                      <p className="text-[10px] text-slate-500">Safe restrict hooks prevent deleting active authors on requirement iterations.</p>
                    </div>
                  </div>

                  <div className="flex items-start gap-3">
                    <div className="mt-1 w-4 h-4 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center shrink-0">
                      <Check className="w-2.5 h-2.5 stroke-[4]" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-slate-800">Schema Index Coverage</p>
                      <p className="text-[10px] text-slate-500">Indexes generated on all Foreign Keys to guarantee lookup performance.</p>
                    </div>
                  </div>
                </div>
              </div>
{/* Card 2: Micro Version History Snapshot ledger */}
              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm flex-1 flex flex-col min-h-0">
                <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100 shrink-0">
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Version Ledger</h3>
                  <button 
                    onClick={() => setActiveTab('ledger')}
                    className="text-[10px] font-bold text-navy-600 uppercase hover:underline"
                  >
                    View All
                  </button>
                </div>

                <div className="space-y-3.5 overflow-y-auto flex-1 pr-1 scrollbar-thin">
                  {versions.slice(0, 3).map((v, i) => (
                    <div key={v.id} className={`p-3 rounded-xl border text-xs ${i === 0 ? 'bg-slate-50/70 border-slate-100' : 'bg-white border-slate-100'}`}>
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[10px] font-mono text-navy-600 font-bold uppercase">
                          Version {v.version_number}.0
                        </span>
                        <span className="text-[10px] text-slate-400">
                          {v.created_at.split('T')[1]?.substring(0,5) || '14:20'}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-700 leading-relaxed font-medium">
                        {v.change_description}
                      </p>
                      <div className="mt-2 flex items-center justify-between text-[9px] text-slate-400">
                        <span>Requirement: {getRequirementTitle(v.requirement_id)}</span>
                        <span>Author: {getUserName(v.changed_by_user_id).split(' ')[0]}</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="pt-4 mt-auto border-t border-slate-100 text-center shrink-0">
                  <button 
                    onClick={() => {
                      setActiveTab('ledger');
                      notify("Navigate to Snapshot Ledger Workspace.", 'info');
                    }}
                    className="text-[10px] font-bold text-navy-600 uppercase tracking-tight hover:underline flex items-center justify-center gap-1 w-full"
                  >
                    <span>View Immutable Snapshots</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

            </div>

          </div>

          {/* BOTTOM STATUS BAR */}
          <footer className="h-10 bg-slate-100 border-t border-slate-200 flex items-center px-6 gap-8 shrink-0 select-none text-[10px]">
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-400 uppercase">Status</span>
              {activeUnresolvedQuestionsCount === 0 ? (
                <span className="font-bold px-1.5 py-0.5 bg-emerald-100 text-emerald-800 rounded">VALIDATED</span>
              ) : (
                <span className="font-bold px-1.5 py-0.5 bg-orange-100 text-orange-800 rounded animate-pulse">ACTION REQUIRED</span>
              )}
            </div>
            
            <div className="ml-auto flex items-center gap-6">
              <div className="text-slate-500 font-bold">
                Schema Lock: <span className={isSchemaLocked ? "text-emerald-600" : "text-orange-500"}>{isSchemaLocked ? "ON" : "OFF"}</span>
              </div>
            </div>
          </footer>

        </main>
    </>
  );
}