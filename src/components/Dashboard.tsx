// Dashboard — workspace shell (formerly a 3000+ line monolith).
// Now composes dedicated modules:
//   - useProjectState   -> all state/effects/handlers (src/hooks/useProjectState.ts)
//   - ChatPanel         -> left conversational panel
//   - PRDEditor         -> PRD Documents tab
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
  GitBranch,
  Clock,
  Download,
  Printer,
  AlertTriangle,
  CheckCircle2,
  LayoutGrid,
  Lock,
  Unlock,
  Pin,
  PinOff,
  Menu,
  ChevronDown,
} from 'lucide-react';
import { useProjectState } from '../hooks/useProjectState';
import type { WorkspaceTab } from '../hooks/useWorkspaceUi';
import { ChatPanel } from './ChatPanel';
import { PRDEditor } from './PRDEditor';
import { ArchitectureFlows } from './ArchitectureFlows';
import { RequirementTraceability } from './RequirementTraceability';
import { VersionHistory } from './VersionHistory';
import { ConfirmationPanel } from './ConfirmationPanel';
import { DocumentLibrary } from './DocumentLibrary';
import { NewProjectModal } from './NewProjectModal';
import { ConfirmModal } from './ConfirmModal';
import { ProjectsDashboard } from './ProjectsDashboard';
import { Tooltip, TooltipBubble } from './Tooltip';
import { highlightMatch } from '../utils/highlight';

// Workspace tabs (PRD Documents / Requirements / Flows / Versions). Declared
// once and shared by both the desktop pill navigation and the tablet/mobile
// dropdown selector so the active-tab behavior can never drift apart.
const TAB_ITEMS: ReadonlyArray<{ id: WorkspaceTab; label: string; icon: typeof FileText }> = [
  { id: 'prd', label: 'PRD Documents', icon: FileText },
  { id: 'trace', label: 'Requirements', icon: GitBranch },
  { id: 'flows', label: 'Flows', icon: Network },
  { id: 'history', label: 'Versions', icon: Clock },
];

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
    activeView,
    setActiveView,
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
    documents,
  } = state;

  // ---- Sidebar project search (pure presentation state) --------------------
  // The query itself lives in useProjects; this only controls whether the
  // search input row is revealed and keeps it focused when opened.
  const [isSearchOpen, setIsSearchOpen] = useState<boolean>(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Mobile drawer: below `lg` the sidebar is hidden and toggled as an overlay
  // drawer via a hamburger button in the top-left, so it never eats horizontal
  // space on small screens.
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState<boolean>(false);
  // Tablet/mobile tab selector (<lg): the horizontal pill is replaced by a compact
  // active-tab dropdown. Selection still routes through the usual setActiveTab
  // handler; this state only owns the dropdown's open/close + outside-click/Escape
  // dismissal (same pattern as the dashboard's dropdowns).
  const [mobileTabsOpen, setMobileTabsOpen] = useState<boolean>(false);
  const mobileTabsRef = useRef<HTMLDivElement>(null);
  const collapsed = historyCollapsed && !mobileSidebarOpen;
  const expanded = !collapsed;

  useEffect(() => {
    if (isSearchOpen) {
      searchInputRef.current?.focus();
    }
  }, [isSearchOpen]);

  // Close the tablet/mobile tab dropdown on outside click or Escape so it never
  // lingers over the document (matches the dashboard dropdown dismissal pattern).
  useEffect(() => {
    if (!mobileTabsOpen) return;
    const handlePointer = (e: MouseEvent) => {
      if (mobileTabsRef.current && !mobileTabsRef.current.contains(e.target as Node)) {
        setMobileTabsOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileTabsOpen(false);
    };
    document.addEventListener('mousedown', handlePointer);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointer);
      document.removeEventListener('keydown', handleKey);
    };
  }, [mobileTabsOpen]);

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
  // Pinned chats sort first; the list below renders them as two clearly
  // separated sections ("Pinned" vs "Recent Projects") instead of one blend.
  const visibleProjects = [...projects].sort((a, b) => Number(!!b.is_pinned) - Number(!!a.is_pinned));

  // Current tab metadata, reused by the tablet/mobile dropdown trigger.
  const currentTab = TAB_ITEMS.find((t) => t.id === activeTab) ?? TAB_ITEMS[0];

  // DOCX/PDF export buttons — shared by the desktop pill and the tablet/mobile
  // bar so both stay identical (same handlers, same style; only sizing varies).
  const exportButtons = (btnCls: string) => (
    <>
      <Tooltip label="Export Word (DOCX)" side="bottom">
        <button
          onClick={handleDownloadDocx}
          aria-label="Export Word (DOCX)"
          className={btnCls}
        >
          <Download className="w-3.5 h-3.5 text-primary shrink-0" />
          <span>DOCX</span>
        </button>
      </Tooltip>

      <Tooltip label="Export PDF" side="bottom">
        <button
          onClick={handlePrintPDF}
          aria-label="Export PDF"
          className={btnCls}
        >
          <Printer className="w-3.5 h-3.5 text-primary shrink-0" />
          <span>PDF</span>
        </button>
      </Tooltip>
    </>
  );

  return (
    <div className="flex-1 flex overflow-hidden h-full">
      {/* Background radial soft light gradient */}
      <div className="absolute inset-0 pointer-events-none z-[-1] overflow-hidden">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-primary/3 blur-[140px] rounded-full"></div>
        <div className="absolute bottom-[10%] right-[-5%] w-[40%] h-[40%] bg-primary/2 blur-[120px] rounded-full"></div>
      </div>

      {/* PROJECT HISTORY SIDEBAR */}
      <aside
        id="project-sidebar"
        className={`${mobileSidebarOpen ? 'mobile-open' : ''} hidden lg:flex lg:flex-col lg:bg-background lg:border-r lg:border-outline lg:shrink-0 lg:transition-[width] lg:duration-200 lg:ease-out ${historyCollapsed ? 'lg:w-[68px]' : 'lg:w-[248px]'}`}
      >
        <div className="p-3 flex items-center justify-between">
          <div className={`flex items-center gap-2 overflow-hidden ${collapsed ? 'w-0 opacity-0' : 'opacity-100'}`}>
            <div className="w-6.5 h-6.5 rounded-lg bg-primary flex items-center justify-center text-on-primary text-[10px] font-bold shrink-0">Ai</div>
            <span className="text-[13px] font-bold text-on-surface whitespace-nowrap">Agentic-AI</span>
          </div>
          <Tooltip label={expanded ? 'Hide sidebar' : 'Show sidebar'} side="right">
            <button
              className="w-8 h-8 rounded-xl border border-outline bg-surface flex items-center justify-center text-on-surface-variant hover:bg-primary/10 hover:text-primary transition-colors shrink-0"
              onClick={() => setHistoryCollapsed((v: boolean) => !v)}
              aria-label={expanded ? 'Hide sidebar' : 'Show sidebar'}
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          </Tooltip>
        </div>

        <div className="px-2">
          <Tooltip label="New Project" side="right" className="w-full">
            <button
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-semibold text-on-surface hover:bg-primary/10 hover:text-primary transition-colors ${collapsed ? 'justify-center' : ''}`}
              aria-label="New Project"
              onClick={() => setIsCreateModalOpen(true)}
            >
              <Plus className="w-4 h-4 shrink-0" />
              {expanded && <span>New Project</span>}
            </button>
          </Tooltip>
          {/* View switcher — the sidebar doubles as the app's navigation: the
              chat/PRD workspace and the projects overview dashboard are the
              two pages, and the active one is highlighted like a nav item. */}
          <Tooltip label="Workspace" side="right" className="w-full">
            <button
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-semibold transition-colors ${collapsed ? 'justify-center' : ''} ${
                activeView === 'workspace'
                  ? 'bg-primary/10 text-primary'
                  : 'text-on-surface-variant hover:bg-primary/10 hover:text-primary'
              }`}
              aria-label="Workspace view"
              aria-current={activeView === 'workspace' ? 'page' : undefined}
              onClick={() => setActiveView('workspace')}
            >
              <MessageSquare className="w-4 h-4 shrink-0" />
              {expanded && <span>Workspace</span>}
            </button>
          </Tooltip>
          <Tooltip label="Dashboard" side="right" className="w-full">
            <button
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-semibold transition-colors ${collapsed ? 'justify-center' : ''} ${
                activeView === 'dashboard'
                  ? 'bg-primary/10 text-primary'
                  : 'text-on-surface-variant hover:bg-primary/10 hover:text-primary'
              }`}
              aria-label="Dashboard view"
              aria-current={activeView === 'dashboard' ? 'page' : undefined}
              onClick={() => setActiveView('dashboard')}
            >
              <LayoutGrid className="w-4 h-4 shrink-0" />
              {expanded && <span>Dashboard</span>}
            </button>
          </Tooltip>
          <Tooltip label="Search Projects" side="right" className="w-full">
            <button
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-semibold transition-colors ${collapsed ? 'justify-center' : ''} ${
                isSearchOpen || projectSearchQuery
                  ? 'bg-primary/10 text-primary'
                  : 'text-on-surface-variant hover:bg-primary/10 hover:text-primary'
              }`}
              aria-label="Search Projects"
              onClick={handleToggleProjectSearch}
            >
              <Search className="w-4 h-4 shrink-0" />
              {expanded && <span>Search Projects</span>}
            </button>
          </Tooltip>
          {isSearchOpen && expanded && (
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
                  className="group/tt absolute right-1.5 p-0.5 text-slate-400 hover:text-slate-600 rounded"
                  aria-label="Clear search"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  <TooltipBubble label="Clear search" side="bottom" />
                </button>
              )}
            </div>
          )}
        </div>

        {/* Section headers ("Pinned" / "Recent Projects") render inside the
            scrollable list below, directly above each group of chats. */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-2 pb-2">
          {projects.length === 0 && expanded && (
            <div className="px-2.5 py-2 text-[12.5px] text-on-surface-variant">No projects yet</div>
          )}
          {projects.length > 0 && visibleProjects.length === 0 && expanded && (
            <div className="px-2.5 py-2 text-[12.5px] text-on-surface-variant">
              No projects or messages matching &quot;{projectSearchQuery.trim()}&quot;
            </div>
          )}
          {visibleProjects.map((p, index) => {
            const isActive = projectId === p.id;
            // Group boundaries: the first pinned chat opens the "Pinned"
            // section and the first unpinned chat opens "Recent Projects", so
            // pinned and unpinned chats stay visually separated instead of
            // blending into a single list. Collapsed mode (icons only) falls
            // back to a thin divider between the two groups.
            const prev = index > 0 ? visibleProjects[index - 1] : null;
            const startsPinnedGroup = !!p.is_pinned && (!prev || !prev.is_pinned);
            const startsUnpinnedGroup = !p.is_pinned && (!prev || !!prev.is_pinned);
            return [
              expanded && startsPinnedGroup && (
                <div
                  key={`${p.id}-pinned-header`}
                  className="px-2.5 pt-4 pb-1.5 flex items-center gap-1.5 text-[11px] font-bold tracking-wide uppercase text-on-surface-variant/70"
                >
                  <Pin className="w-3 h-3 text-primary shrink-0" />
                  Pinned
                </div>
              ),
              startsUnpinnedGroup && index > 0 && (
                <div
                  key={`${p.id}-group-divider`}
                  className="mx-1 mt-2 border-t border-outline/70"
                  aria-hidden="true"
                />
              ),
              expanded && startsUnpinnedGroup && (
                <div
                  key={`${p.id}-recent-header`}
                  className="px-2.5 pt-2 pb-1.5 flex items-center gap-1.5 text-[11px] font-bold tracking-wide uppercase text-on-surface-variant/70"
                >
                  <MessageSquare className="w-3 h-3 shrink-0" />
                  Recent Projects
                </div>
              ),
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
                      maxLength={40}
                      className="flex-1 bg-white border border-primary/30 rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-primary"
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                    />
                    <Tooltip label="Confirm rename" side="left">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRenameProject(p.id, renameProjectName); }}
                        className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                        aria-label="Confirm rename"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                    </Tooltip>
                    <Tooltip label="Cancel rename" side="left">
                      <button
                        onClick={(e) => { e.stopPropagation(); setRenameProjectId(null); }}
                        className="p-1 text-slate-400 hover:bg-slate-100 rounded"
                        aria-label="Cancel rename"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                      </button>
                    </Tooltip>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setProjectId(p.id);
                      // Selecting a project from the sidebar always lands the
                      // user back in the chat/PRD workspace, even if they were
                      // browsing the dashboard view.
                      setActiveView('workspace');
                    }}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setProjectContextMenu({ projectId: p.id, x: e.clientX, y: e.clientY });
                    }}
                    className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] mb-0.5 transition-colors truncate ${collapsed ? 'justify-center' : ''} ${
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
                    {expanded && (
                      <>
                        <span className="truncate flex-1 text-left">{highlightMatch(p.name, projectSearchQuery)}</span>
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5 shrink-0">
                          <Tooltip label={p.is_pinned ? 'Unpin' : 'Pin'} side="left">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleTogglePin(p.id);
                              }}
                              className={`p-1 rounded-lg transition-colors ${p.is_pinned ? 'text-primary hover:bg-primary/10' : 'text-slate-400 hover:text-primary hover:bg-primary/10'}`}
                              aria-label={p.is_pinned ? 'Unpin' : 'Pin'}
                            >
                              {p.is_pinned
                                ? <Pin className="w-3 h-3" />
                                : <PinOff className="w-3 h-3" />}
                            </button>
                          </Tooltip>
                          <Tooltip label="Rename" side="left">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setRenameProjectId(p.id);
                                setRenameProjectName(p.name);
                              }}
                              className="p-1 text-slate-400 hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
                              aria-label="Rename"
                            >
                              <Pencil className="w-3 h-3" />
                            </button>
                          </Tooltip>
                          <Tooltip label="Delete" side="left">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setProjectPendingDelete(p.id);
                              }}
                              className="p-1 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                              aria-label="Delete"
                            >
                              <XCircle className="w-3 h-3" />
                            </button>
                          </Tooltip>
                        </div>
                      </>
                    )}
                  </button>
                )}
                {expanded && renameProjectId !== p.id && p.match_snippet && (
                  <div className="mt-1 px-2.5 flex items-center gap-1.5 text-[11px] leading-snug text-on-surface-variant min-w-0">
                    <MessageSquare className="w-3 h-3 shrink-0 text-on-surface-variant/70" />
                    <span className="truncate flex-1 text-left">
                      {highlightMatch(p.match_snippet, projectSearchQuery)}
                    </span>
                  </div>
                )}
              </div>,
            ];
          })}
        </div>

        {/* Context Menu */}
        {projectContextMenu && (
          <div
            className="fixed z-50 bg-white border border-slate-200 rounded-xl shadow-xl py-1 min-w-[160px] max-w-[calc(100vw-1rem)]"
            style={{
              left: Math.min(projectContextMenu.x, Math.max(8, window.innerWidth - 176)),
              top: Math.min(projectContextMenu.y, Math.max(8, window.innerHeight - 150)),
            }}
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
      {/* MOBILE SIDEBAR DRAWER (below `lg`): hamburger toggle + dimmed backdrop.
          The sidebar itself is re-positioned as an overlay by #project-sidebar.mobile-open. */}
      <button
        type="button"
        className={`group/tt fixed ${mobileSidebarOpen ? 'left-[292px]' : 'left-3'} top-[76px] z-30 w-9 h-9 rounded-xl bg-white border border-outline shadow-md flex items-center justify-center text-on-surface hover:bg-primary/10 hover:text-primary transition-colors lg:hidden`}
        onClick={() => setMobileSidebarOpen((v) => !v)}
        aria-label={mobileSidebarOpen ? 'Close project sidebar' : 'Open project sidebar'}
      >
        {mobileSidebarOpen ? <XCircle className="w-4.5 h-4.5" /> : <Menu className="w-4.5 h-4.5" />}
        <TooltipBubble label={mobileSidebarOpen ? 'Close sidebar' : 'Open sidebar'} side="bottom" />
      </button>
      {mobileSidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setMobileSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* PAGE CONTENT — the workspace (chat + PRD tabs) or the projects
          overview dashboard, switched from the sidebar's view nav. Only the
          content area swaps; the sidebar and its shared project state stay
          mounted so both views always agree. */}
      {activeView === 'dashboard' ? (
        <ProjectsDashboard state={state} />
      ) : (
      <div id="split-container" className="flex-1 flex flex-col lg:flex-row overflow-hidden" ref={splitContainerRef}>
        
        {/* LEFT PANEL: Conversational Timeline & Human-In-The-Loop */}
        <ChatPanel state={state} />

        {/* RESIZABLE DIVIDER */}
        <div
          className={`resize-divider ${isDraggingSplit ? 'is-dragging' : ''}`}
          onMouseDown={() => setIsDraggingSplit(true)}
        />

        {/* RIGHT PANEL: Live Workspace Previews (Tabbed System) */}
        <section className="flex-1 min-w-0 min-h-0 flex flex-col bg-background relative overflow-hidden">
          {/* Tabs bar — warm pill navigation (PRD Documents / Requirements / Flows /
              Versions) modeled on the PRD nav reference; each tab is wired to its
              live workspace panel, and the DOCX/PDF exports sit at the pill's right
              edge (inside it) like the reference's Export button. */}
          <div className="min-h-13 bg-glass-bg border-b border-outline shrink-0 select-none">
            {/* DESKTOP (lg+): the existing horizontal pill navigation — unchanged. */}
            <div className="hidden lg:flex flex flex-col sm:flex-row items-stretch sm:items-center gap-1 px-3 sm:px-4 md:px-6 overflow-x-auto custom-scrollbar">
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-1 p-1 sm:h-[53px] bg-tab-pill border border-tab-pill-border rounded-[10px]">
              {TAB_ITEMS.map((tab) => (
                <Tooltip key={tab.id} label={tab.label} side="bottom">
                  <button
                    onClick={() => setActiveTab(tab.id)}
                    aria-label={`${tab.label} tab`}
                    className={`w-full sm:w-auto h-[43px] px-2.5 sm:px-3.5 rounded-lg font-label-md text-xs font-semibold whitespace-nowrap transition-colors duration-200 flex items-center justify-start gap-1.5 ${
                      activeTab === tab.id
                        ? 'bg-tab-active text-white shadow-sm'
                        : 'text-tab-text hover:bg-tab-hover'
                    }`}
                  >
                    <tab.icon className="w-3.5 h-3.5 shrink-0" />
                    <span>{tab.label}</span>
                  </button>
                </Tooltip>
              ))}

              {/* Export actions — kept inside the pill, pushed to the far right like
                  the reference's Export button. Both compile server-side (LaTeX
                  service), so these only trigger the existing handlers. */}
              <div className="flex items-center gap-1 sm:ml-auto shrink-0 no-print">
                {exportButtons('w-full sm:w-auto h-[39px] px-2.5 sm:px-3.5 rounded-lg bg-white border border-export-border hover:bg-export-hover font-label-md text-xs font-semibold text-export-text transition-colors flex items-center gap-1.5 cursor-pointer whitespace-nowrap')}
              </div>
              </div>
            </div>

            {/* TABLET/MOBILE (<lg): compact dropdown selector showing the active tab.
                The menu is absolutely anchored left/right against this relative bar so
                it spans the content width and can never overflow the viewport. The same
                setActiveTab handler drives it, so active state + navigation are unchanged. */}
            <div ref={mobileTabsRef} className="lg:hidden relative flex items-center gap-1.5 px-3 sm:px-4 md:px-6">
              <div className="flex-1 min-w-0">
                <button
                  type="button"
                  onClick={() => setMobileTabsOpen((v) => !v)}
                  aria-label={`Tab selector (currently ${currentTab.label})`}
                  aria-haspopup="menu"
                  aria-expanded={mobileTabsOpen}
                  className={`w-full h-[43px] rounded-[10px] font-label-md text-xs font-semibold transition-colors duration-200 flex items-center justify-between gap-2 px-2.5 bg-tab-active text-white shadow-sm ${
                    mobileTabsOpen ? 'ring-2 ring-primary/30' : ''
                  }`}
                >
                  <span className="flex items-center gap-1.5 min-w-0">
                    <currentTab.icon className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{currentTab.label}</span>
                  </span>
                  <ChevronDown className={`w-4 h-4 shrink-0 text-white transition-transform duration-200 ${mobileTabsOpen ? 'rotate-180' : ''}`} />
                </button>
              </div>

              <div className="flex items-center gap-1.5 shrink-0 no-print">
                {exportButtons('h-[39px] px-2.5 sm:px-3.5 rounded-lg bg-white border border-export-border hover:bg-export-hover font-label-md text-xs font-semibold text-export-text transition-colors flex items-center gap-1.5 cursor-pointer whitespace-nowrap shrink-0')}
              </div>

              {mobileTabsOpen && (
                <div role="menu" aria-label="Available tabs" className="absolute left-0 right-0 top-full mt-1 z-50 rounded-[10px] bg-surface border border-tab-pill-border shadow-xl py-1">
                  {TAB_ITEMS.map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setActiveTab(tab.id);
                        setMobileTabsOpen(false);
                      }}
                      className={`w-full text-left px-3 py-2.5 rounded-lg text-[13px] font-semibold transition-colors duration-200 flex items-center gap-2.5 ${
                        activeTab === tab.id
                          ? 'bg-tab-active text-white'
                          : 'text-tab-text hover:bg-tab-hover'
                      }`}
                    >
                      <tab.icon className="w-4 h-4 shrink-0" />
                      <span className="flex-1 truncate">{tab.label}</span>
                      {activeTab === tab.id && <Check className="w-4 h-4 shrink-0" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* RIGHT VIEW WINDOW */}
          <div id="printable-document" className="flex-1 min-w-0 overflow-y-auto p-4 md:p-8 lg:p-12 custom-scrollbar">
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
                <div className="flex items-center gap-3 mb-4 relative z-10 min-w-0">
                  <div className="w-10 h-10 rounded-2xl bg-primary/10 flex items-center justify-center text-primary shrink-0">
                    <AlertTriangle className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="font-heading font-bold text-base text-on-surface break-words">
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
                      <div key={idx} className="bg-slate-50 border border-outline/60 p-4 rounded-2xl space-y-2 min-w-0">
                        <div className="flex flex-wrap items-center justify-between gap-1.5">
                          <span className="text-[10px] font-mono font-bold text-primary uppercase bg-primary/10 px-2 py-0.5 rounded break-words">
                            {q.checklist_category}
                          </span>
                          <span className="text-[10px] font-mono text-on-surface-variant font-semibold break-words min-w-0 text-right">
                            Target: {q.target_user_story_id || "General"}
                          </span>
                        </div>
                        <p className="text-sm font-medium text-on-surface break-words">
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


            {/* Requirement Lock Status Panel — only shown on the Requirements tab */}
            {activeTab === 'trace' && structuredRequirements.requirements && structuredRequirements.requirements.length > 0 && (
              <div className="max-w-4xl mx-auto mb-8 p-4.5 bg-white border border-outline rounded-2xl shadow-sm">
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  <Lock className="text-primary w-4 h-4 shrink-0" />
                  <h3 className="font-bold text-sm text-on-surface min-w-0">Requirement Lock Status</h3>
                  <span className="text-[10px] text-on-surface-variant font-mono basis-full sm:basis-auto sm:ml-auto">
                    Locked requirements cannot be updated, deleted, merged, or modified by AI
                  </span>
                </div>
                <div className="space-y-2">
                  {structuredRequirements.requirements.map((req) => {
                    const isLocked = req.is_locked || lockedRequirements[req.requirement_code]?.is_locked;
                    return (
                      <div key={req.requirement_code} className={`flex items-center justify-between gap-2 sm:gap-3 p-3 rounded-xl border ${isLocked ? 'bg-amber-50 border-amber-200' : 'bg-slate-50 border-slate-200'}`}>
                        <div className="flex items-center gap-3 min-w-0">
                          <span className={`w-2 h-2 rounded-full shrink-0 ${isLocked ? 'bg-amber-500' : 'bg-emerald-500'}`}></span>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 min-w-0">
                              <span className="text-xs font-mono font-bold text-on-surface shrink-0">{req.requirement_code}</span>
                              <span className="text-xs text-on-surface break-words min-w-0">{req.title}</span>
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
                          className={`px-3 py-1.5 rounded-xl text-[11px] font-bold transition-all flex items-center gap-1.5 shrink-0 cursor-pointer ${
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
              {activeTab === 'trace' && <RequirementTraceability projectId={projectId} />}
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
      )}

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