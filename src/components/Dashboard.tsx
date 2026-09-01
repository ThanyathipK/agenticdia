// Dashboard — workspace shell (formerly a 3000+ line monolith).
// Now composes dedicated modules:
//   - useProjectState   -> all state/effects/handlers (src/hooks/useProjectState.ts)
//   - ChatPanel         -> left conversational panel
//   - PRDEditor         -> PRD Document tab
//   - ArchitectureFlows -> System Flows tab
//   - VersionHistory    -> Version Ledger tab
//   - MarkdownRenderer  -> markdown rendering (via PRDEditor)
//   - File exports (PDF/DOCX) are compiled server-side in useProjectState.ts
//     (the browser never re-parses the LaTeX PRD into markdown).
import { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import {
  PanelLeft,
  Plus,
  Search,
  MessageSquare,
  Check,
  XCircle,
  Pencil,
  FileText,
  Network,
  Clock,
  Download,
  Printer,
  AlertTriangle,
  CheckCircle2,
  Lock,
  Unlock,
  Pin,
  PinOff,
} from 'lucide-react';
import { useProjectState } from '../hooks/useProjectState';
import { ChatPanel } from './ChatPanel';
import { PRDEditor } from './PRDEditor';
import { ArchitectureFlows } from './ArchitectureFlows';
import { VersionHistory } from './VersionHistory';
import { ConfirmationPanel } from './ConfirmationPanel';
import { DocumentLibrary } from './DocumentLibrary';
import { NewProjectModal } from './NewProjectModal';
import { ConfirmModal } from './ConfirmModal';

export default function Dashboard() {
  const state = useProjectState();
  const {
    projectId,
    setProjectId,
    projects,
    historyCollapsed,
    setHistoryCollapsed,
    projectContextMenu,
    setProjectContextMenu,
    renameProjectId,
    setRenameProjectId,
    renameProjectName,
    setRenameProjectName,
    handleRenameProject,
    handleDeleteProject,
    handleCreateProject,
    handleTogglePin,
    isCreateModalOpen,
    setIsCreateModalOpen,
    projectPendingDelete,
    setProjectPendingDelete,
    projectSearchQuery,
    setProjectSearchQuery,
    pendingActions,
    setPendingActions,
    loadProjectState,
    isDraggingSplit,
    setIsDraggingSplit,
    splitContainerRef,
    activeTab,
    setActiveTab,
    handleDownloadDocx,
    handlePrintPDF,
    currentAgentNode,
    auditResult,
    handleSubmitClarifications,
    clarificationAnswers,
    handleUpdateAnswerValue,
    structuredRequirements,
    lockedRequirements,
    handleLockRequirement,
    handleUnlockRequirement,
    currentVersion,
    documents,
  } = state;

  // ---- Sidebar project search (pure presentation state) --------------------
  // The query itself lives in useProjects; this only controls whether the
  // search input row is revealed and keeps it focused when opened.
  const [isSearchOpen, setIsSearchOpen] = useState<boolean>(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isSearchOpen) {
      searchInputRef.current?.focus();
    }
  }, [isSearchOpen]);

  const handleToggleProjectSearch = () => {
    // Expanding the sidebar first guarantees the input row is visible.
    if (historyCollapsed) setHistoryCollapsed(false);
    setIsSearchOpen((open) => !open);
  };

  const handleCloseProjectSearch = () => {
    setIsSearchOpen(false);
    setProjectSearchQuery('');
  };

  // Sidebar projects to render. Matching (project names AND conversation
  // message content) happens server-side via GET /api/projects/search — the
  // hook's debounced search effect swaps `projects` for the matching subset.
  // Only the pinned-first presentation ordering is applied here.
  const visibleProjects = [...projects].sort((a, b) => Number(!!b.is_pinned) - Number(!!a.is_pinned));

  return (
    <div className="flex-1 flex overflow-hidden h-full">
      {/* Background radial soft light gradient */}
      <div className="absolute inset-0 pointer-events-none z-[-1] overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-primary/3 blur-[140px] rounded-full"></div>
        <div className="absolute bottom-[10%] right-[-5%] w-[40%] h-[40%] bg-primary/2 blur-[120px] rounded-full"></div>
      </div>

      {/* PROJECT HISTORY SIDEBAR */}
      <aside
        className={`flex flex-col bg-background border-r border-outline shrink-0 transition-[width] duration-200 ease-out ${historyCollapsed ? 'w-[68px]' : 'w-[248px]'}`}
      >
        <div className="p-3 flex items-center justify-between">
          <div className={`flex items-center gap-2 overflow-hidden ${historyCollapsed ? 'w-0 opacity-0' : 'opacity-100'}`}>
            <div className="w-6.5 h-6.5 rounded-lg bg-primary flex items-center justify-center text-on-primary text-[10px] font-bold shrink-0">Ai</div>
            <span className="text-[13px] font-bold text-on-surface whitespace-nowrap">Agentic-AI</span>
          </div>
          <button
            className="w-8 h-8 rounded-xl border border-outline bg-surface flex items-center justify-center text-on-surface-variant hover:bg-primary/10 hover:text-primary transition-colors shrink-0"
            onClick={() => setHistoryCollapsed((v: boolean) => !v)}
            title="Collapse/Expand history panel"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
        </div>

        <div className="px-2">
          <button
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-semibold text-on-surface hover:bg-primary/10 hover:text-primary transition-colors ${historyCollapsed ? 'justify-center' : ''}`}
            title="New Project"
            onClick={() => setIsCreateModalOpen(true)}
          >
            <Plus className="w-4 h-4 shrink-0" />
            {!historyCollapsed && <span>New Project</span>}
          </button>
          <button
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-semibold transition-colors ${historyCollapsed ? 'justify-center' : ''} ${
              isSearchOpen || projectSearchQuery
                ? 'bg-primary/10 text-primary'
                : 'text-on-surface-variant hover:bg-primary/10 hover:text-primary'
            }`}
            title="Search Projects"
            onClick={handleToggleProjectSearch}
          >
            <Search className="w-4 h-4 shrink-0" />
            {!historyCollapsed && <span>Search Projects</span>}
          </button>
          {isSearchOpen && !historyCollapsed && (
            <div className="relative flex items-center mt-1">
              <Search className="absolute left-2.5 w-3.5 h-3.5 text-on-surface-variant pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                value={projectSearchQuery}
                onChange={(e) => setProjectSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    e.stopPropagation();
                    handleCloseProjectSearch();
                  }
                }}
                placeholder="Search projects or messages..."
                className="w-full bg-white border border-outline rounded-xl pl-8 pr-7 py-1.5 text-xs text-on-surface focus:outline-none focus:border-primary"
              />
              {projectSearchQuery && (
                <button
                  onClick={() => {
                    setProjectSearchQuery('');
                    searchInputRef.current?.focus();
                  }}
                  className="absolute right-1.5 p-0.5 text-slate-400 hover:text-slate-600 rounded"
                  title="Clear search"
                >
                  <XCircle className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}
        </div>

        {!historyCollapsed && (
          <div className="px-4 pt-4 pb-1.5 text-[11px] font-bold tracking-wide uppercase text-on-surface-variant/70">
            Recent Projects
          </div>
        )}

        <div className="flex-1 overflow-y-auto custom-scrollbar px-2 pb-2">
          {projects.length === 0 && !historyCollapsed && (
            <div className="px-2.5 py-2 text-[12.5px] text-on-surface-variant">No projects yet</div>
          )}
          {projects.length > 0 && visibleProjects.length === 0 && !historyCollapsed && (
            <div className="px-2.5 py-2 text-[12.5px] text-on-surface-variant">
              No projects or messages matching &quot;{projectSearchQuery.trim()}&quot;
            </div>
          )}
          {visibleProjects.map(p => {
            const isActive = projectId === p.id;
            return (
              <div key={p.id} className="relative group">
                {renameProjectId === p.id ? (
                  <div className="flex items-center gap-1 px-2 py-1">
                    <input
                      type="text"
                      value={renameProjectName}
                      onChange={(e) => setRenameProjectName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRenameProject(p.id, renameProjectName);
                        if (e.key === 'Escape') setRenameProjectId(null);
                      }}
                      className="flex-1 bg-white border border-primary/30 rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-primary"
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                    />
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRenameProject(p.id, renameProjectName); }}
                      className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setRenameProjectId(null); }}
                      className="p-1 text-slate-400 hover:bg-slate-100 rounded"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setProjectId(p.id)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setProjectContextMenu({ projectId: p.id, x: e.clientX, y: e.clientY });
                    }}
                    className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] mb-0.5 transition-colors truncate ${historyCollapsed ? 'justify-center' : ''} ${
                      isActive ? 'bg-primary/10 text-primary font-semibold' : 'text-on-surface hover:bg-surface'
                    }`}
                    title={p.name}
                  >
                    <div className="relative shrink-0">
                      <MessageSquare className={`w-4 h-4 ${isActive ? 'text-primary' : ''}`} />
                      {isActive && (
                        <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-primary rounded-full border-2 border-background"></span>
                      )}
                    </div>
                    {!historyCollapsed && (
                      <>
                        <span className="truncate flex-1 text-left">{p.name}</span>
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5 shrink-0">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleTogglePin(p.id);
                            }}
                            className={`p-1 rounded-lg transition-colors ${p.is_pinned ? 'text-primary hover:bg-primary/10' : 'text-slate-400 hover:text-primary hover:bg-primary/10'}`}
                            title={p.is_pinned ? 'Unpin' : 'Pin'}
                          >
                            {p.is_pinned
                              ? <Pin className="w-3 h-3" />
                              : <PinOff className="w-3 h-3" />}
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setRenameProjectId(p.id);
                              setRenameProjectName(p.name);
                            }}
                            className="p-1 text-slate-400 hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                            title="Rename"
                          >
                            <Pencil className="w-3 h-3" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setProjectPendingDelete(p.id);
                            }}
                            className="p-1 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                            title="Delete"
                          >
                            <XCircle className="w-3 h-3" />
                          </button>
                        </div>
                      </>
                    )}
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Context Menu */}
        {projectContextMenu && (
          <div
            className="fixed z-50 bg-white border border-slate-200 rounded-xl shadow-xl py-1 min-w-[160px]"
            style={{ left: projectContextMenu.x, top: projectContextMenu.y }}
          >
            <button
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 transition-colors"
              onClick={() => {
                handleTogglePin(projectContextMenu.projectId);
              }}
            >
              {(() => {
                const p = projects.find((pr) => pr.id === projectContextMenu.projectId);
                return p && p.is_pinned ? (
                  <>
                    <Pin className="w-3.5 h-3.5 text-primary" />
                    <span>Unpin</span>
                  </>
                ) : (
                  <>
                    <PinOff className="w-3.5 h-3.5" />
                    <span>Pin</span>
                  </>
                );
              })()}
            </button>
            <button
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 transition-colors"
              onClick={() => {
                const p = projects.find((pr) => pr.id === projectContextMenu.projectId);
                if (p) {
                  setRenameProjectId(p.id);
                  setRenameProjectName(p.name);
                }
                setProjectContextMenu(null);
              }}
            >
              <Pencil className="w-3.5 h-3.5" />
              <span>Rename</span>
            </button>
            <button
              className="w-full flex items-center gap-2 px-3 py-2 text-xs text-red-600 hover:bg-red-50 transition-colors"
              onClick={() => {
                const pid = projectContextMenu.projectId;
                setProjectContextMenu(null);
                setProjectPendingDelete(pid);
              }}
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>Delete</span>
            </button>
          </div>
        )}
      </aside>
{/* HORIZONTAL SPLIT GRID WORKSPACE */}
      <div className="flex-1 flex overflow-hidden" ref={splitContainerRef}>
        
        {/* LEFT PANEL: Conversational Timeline & Human-In-The-Loop */}
        <ChatPanel state={state} />

        {/* RESIZABLE DIVIDER */}
        <div
          className={`resize-divider ${isDraggingSplit ? 'is-dragging' : ''}`}
          onMouseDown={() => setIsDraggingSplit(true)}
        />

        {/* RIGHT PANEL: Live Workspace Previews (Tabbed System) */}
        <section className="flex-1 flex flex-col bg-background relative overflow-hidden">
          {/* Tabs bar */}
          <div className="h-13 bg-glass-bg border-b border-outline flex items-center px-6 justify-between shrink-0 select-none">
            <div className="flex bg-black/5 rounded-full p-1 h-9.5 border border-black/5">
              <button 
                onClick={() => setActiveTab('prd')}
                className={`px-5 h-full flex items-center rounded-full font-bold font-label-md text-xs transition-all gap-1.5 ${
                  activeTab === 'prd' 
                    ? 'bg-primary text-on-primary shadow-sm' 
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>PRD Document</span>
              </button>
              
              <button 
                onClick={() => setActiveTab('flows')}
                className={`px-5 h-full flex items-center rounded-full font-bold font-label-md text-xs transition-all gap-1.5 ${
                  activeTab === 'flows' 
                    ? 'bg-primary text-on-primary shadow-sm' 
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
              >
                <Network className="w-3.5 h-3.5" />
                <span>Architecture Flows</span>
              </button>
              
              <button 
                onClick={() => setActiveTab('history')}
                className={`px-5 h-full flex items-center rounded-full font-bold font-label-md text-xs transition-all gap-1.5 ${
                  activeTab === 'history' 
                    ? 'bg-primary text-on-primary shadow-sm' 
                    : 'text-on-surface-variant hover:text-on-surface'
                }`}
              >
                <Clock className="w-3.5 h-3.5" />
                <span>Versions & Docs</span>
              </button>
            </div>

            {/* Quick action buttons */}
            <div className="flex items-center gap-2 no-print shrink-0">
              <button 
                onClick={handleDownloadDocx}
                className="px-3 py-1.5 rounded-xl bg-white border border-outline hover:bg-black/5 font-label-md text-xs text-on-surface transition-all flex items-center gap-1.5 cursor-pointer font-semibold shadow-sm whitespace-nowrap"
              >
                <Download className="w-3.5 h-3.5 text-primary" />
                <span>Export Word (DOCX)</span>
              </button>

              <button 
                onClick={handlePrintPDF}
                className="px-3 py-1.5 rounded-xl bg-primary text-on-primary hover:brightness-110 font-label-md text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-md shadow-primary/15 animate-none whitespace-nowrap"
              >
                <Printer className="w-3.5 h-3.5" />
                <span>Export PDF</span>
              </button>
            </div>
          </div>

          {/* RIGHT VIEW WINDOW */}
          <div id="printable-document" className="flex-1 overflow-y-auto p-8 md:p-12 custom-scrollbar">
{/* Confirmation Panel Area */}
            {pendingActions.map(action => (
                <ConfirmationPanel 
                    key={action.id} 
                    action={action} 
                    onConfirm={() => {
                        setPendingActions(prev => prev.filter(a => a.id !== action.id));
                        if(projectId) loadProjectState(projectId);
                    }}
                    onCancel={() => {
                        setPendingActions(prev => prev.filter(a => a.id !== action.id));
                    }}
                />
            ))}

            {/* Dedicated Clarification Section displayed ONLY when currentAgentNode === WAITING_CLARIFICATION */}
            {currentAgentNode === "WAITING_CLARIFICATION" && auditResult.clarification_questions && auditResult.clarification_questions.some(q => !q.is_resolved) && (
              <motion.div 
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="max-w-4xl mx-auto mb-8 bg-white border-2 border-primary/30 rounded-3xl p-6 shadow-xl relative overflow-hidden"
              >
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent pointer-events-none"></div>
                <div className="flex items-center gap-3 mb-4 relative z-10">
                  <div className="w-10 h-10 rounded-2xl bg-primary/10 flex items-center justify-center text-primary">
                    <AlertTriangle className="w-5 h-5" />
                  </div>
                  <div>
                    <h2 className="font-heading font-bold text-base text-on-surface">
                      Compliance Audit Clarification Required (Waiting Clarification)
                    </h2>
                    <p className="text-xs text-on-surface-variant">
                      Please provide answers to the unresolved clarification questions below to clear the technical audit roadblock.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleSubmitClarifications} className="space-y-4 relative z-10">
                  {auditResult.clarification_questions
                    .map((q, idx) => ({ q, idx }))
                    .filter(({ q }) => !q.is_resolved)
                    .map(({ q, idx }) => (
                      <div key={idx} className="bg-slate-50 border border-outline/60 p-4 rounded-2xl space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-mono font-bold text-primary uppercase bg-primary/10 px-2 py-0.5 rounded">
                            {q.checklist_category}
                          </span>
                          <span className="text-[10px] font-mono text-on-surface-variant font-semibold">
                            Target: {q.target_user_story_id || "General"}
                          </span>
                        </div>
                        <p className="text-sm font-medium text-on-surface">
                          {q.question_text}
                        </p>
                        <input
                          type="text"
                          required
                          value={clarificationAnswers[`q-${idx}`] || ""}
                          onChange={(e) => handleUpdateAnswerValue(`q-${idx}`, e.target.value)}
                          placeholder="Enter your professional resolution or answer here..."
                          className="w-full bg-white border border-outline rounded-xl px-3.5 py-2 text-xs text-on-surface focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all"
                        />
                      </div>
                    ))}

                  <button
                    type="submit"
                    className="w-full bg-primary hover:brightness-110 active:scale-[0.99] text-on-primary py-3 rounded-2xl font-label-md text-xs font-bold shadow-lg shadow-primary/20 flex items-center justify-center gap-2 cursor-pointer transition-all"
                  >
                    <CheckCircle2 className="w-4.5 h-4.5" />
                    <span>Submit Answers & Re-Audit</span>
                  </button>
                </form>
              </motion.div>
            )}
{/* Metadata card preview */}
            <div className="max-w-4xl mx-auto mb-8 p-4.5 bg-white border border-outline rounded-2xl flex flex-wrap gap-4 items-center justify-between shadow-sm">
              <div className="flex items-center gap-3">
                <span className="bg-primary/15 text-primary text-[10.5px] px-2.5 py-1 rounded border border-primary/25 font-bold uppercase tracking-wider font-mono">
                  {projectId}
                </span>
                <div className="flex items-center gap-1.5 text-xs text-on-surface-variant">
                  <span>Version Reviewed:</span>
                  <span className="text-primary font-bold font-mono">v{currentVersion}.0</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className="text-xs text-on-surface-variant font-medium">
                  State: {auditResult.is_valid ? (
                    <span className="text-emerald-600 font-bold">Passed Technical Audit</span>
                  ) : (
                    <span className="text-orange-600 font-bold">Unresolved Queries Pending</span>
                  )}
                </span>
              </div>
            </div>

            {/* Requirement Lock Status Panel */}
            {(structuredRequirements.requirements && structuredRequirements.requirements.length > 0) && (
              <div className="max-w-4xl mx-auto mb-8 p-4.5 bg-white border border-outline rounded-2xl shadow-sm">
                <div className="flex items-center gap-2 mb-3">
                  <Lock className="text-primary w-4 h-4" />
                  <h3 className="font-bold text-sm text-on-surface">Requirement Lock Status</h3>
                  <span className="text-[10px] text-on-surface-variant font-mono ml-auto">
                    Locked requirements cannot be updated, deleted, merged, or modified by AI
                  </span>
                </div>
                <div className="space-y-2">
                  {structuredRequirements.requirements.map((req) => {
                    const isLocked = req.is_locked || lockedRequirements[req.requirement_code]?.is_locked;
                    return (
                      <div key={req.requirement_code} className={`flex items-center justify-between p-3 rounded-xl border ${isLocked ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'}`}>
                        <div className="flex items-center gap-3 min-w-0">
                          <span className={`w-2 h-2 rounded-full shrink-0 ${isLocked ? 'bg-amber-500' : 'bg-emerald-500'}`}></span>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-mono font-bold text-on-surface">{req.requirement_code}</span>
                              <span className="text-xs text-on-surface truncate">{req.title}</span>
                            </div>
                            {isLocked && (
                              <p className="text-[10px] text-amber-700 font-mono mt-0.5">
                                🔒 Locked by {req.locked_by || lockedRequirements[req.requirement_code]?.locked_by || 'user'} 
                                {req.locked_at || lockedRequirements[req.requirement_code]?.locked_at ? ` at ${new Date(req.locked_at || lockedRequirements[req.requirement_code]?.locked_at || '').toLocaleString()}` : ''}
                              </p>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => isLocked ? handleUnlockRequirement(req.requirement_code) : handleLockRequirement(req.requirement_code)}
                          className={`px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                            isLocked 
                              ? 'bg-amber-100 text-amber-800 border border-amber-300 hover:bg-amber-200' 
                              : 'bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20'
                          }`}
                        >
                          {isLocked ? (
                            <>
                              <Unlock className="w-3.5 h-3.5" />
                              <span>Unlock</span>
                            </>
                          ) : (
                            <>
                              <Lock className="w-3.5 h-3.5" />
                              <span>Lock</span>
                            </>
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="max-w-4xl mx-auto">
              {activeTab === 'prd' && <PRDEditor state={state} />}
              {activeTab === 'flows' && <ArchitectureFlows state={state} />}
              {activeTab === 'history' && (
                <>
                  <VersionHistory state={state} />
                  <DocumentLibrary projectId={projectId} docs={documents} />
                </>
              )}
            </div>

          </div>
        </section>

      </div>

      {/* NEW PROJECT MODAL (styled replacement for native prompt()) */}
      <NewProjectModal
        isOpen={isCreateModalOpen}
        onCreate={handleCreateProject}
        onClose={() => setIsCreateModalOpen(false)}
      />

      {/* DELETE PROJECT CONFIRM MODAL (styled replacement for native confirm()) */}
      <ConfirmModal
        isOpen={!!projectPendingDelete}
        title="Delete Project"
        description={`Are you sure you want to delete "${projects.find(p => p.id === projectPendingDelete)?.name ?? 'this project'}"? This action cannot be undone.`}
        confirmLabel="Delete"
        pendingLabel="Deleting..."
        danger
        onConfirm={() => handleDeleteProject(projectPendingDelete as string)}
        onClose={() => setProjectPendingDelete(null)}
      />
    </div>
  );
}