// useProjectState — slim composition root.
//
// The former 1,421-line "god-hook" has been decomposed into focused modules,
// each owning one concern and flowing through the typed `src/api` client so no
// payload is ever handled as `any`:
//
//   - src/api/{types,client,transforms}  -> typed backend contract + conversions
//   - useProjects                        -> project list, selection, CRUD, pending actions
//   - useWorkspaceUi                     -> split pane, tabs, diagram/version UI state
//   - useRequirementStore                -> requirement/PRD domain state + typed setters
//   - useArtifactLocks                   -> optimistic lock/unlock actions
//   - useProjectSync                     -> loadProjectState + SSE live sync
//   - useChat                            -> conversational / multi-agent handlers
//   - useLmStudioHealth                  -> LLM connectivity health polling (unchanged)
//
// This hook keeps exposing the same `ProjectState` interface so the presentational
// components (Dashboard, ChatPanel, PRDEditor, ArchitectureFlows, VersionHistory)
// are unaffected.
import type { Dispatch, SetStateAction } from 'react';
import type {
  AuditResult,
  ChatMessage,
  PRDSection,
  RequirementLockState,
  StructuredRequirements,
  VersionHistory,
} from '../components/types';
import type { PendingActionPayload, ProjectSummary } from '../api/types';
import { api, detailFromBlobError } from '../api/client';
import { handleError } from '../components/Toast';
import type { UseDocumentsResult } from './useDocuments';
import type { WorkspaceTab } from './useWorkspaceUi';
import { useArtifactLocks } from './useArtifactLocks';
import { useChat } from './useChat';
import { useDocuments } from './useDocuments';
import { useLmStudioHealth } from './useLmStudioHealth';
import { useProjectSync } from './useProjectSync';
import { useProjects } from './useProjects';
import { useRequirementStore } from './useRequirementStore';
import { useWorkspaceUi } from './useWorkspaceUi';

export interface ProjectState {
  // Project/chrome state
  projectId: string | null;
  setProjectId: Dispatch<SetStateAction<string | null>>;
  projects: ProjectSummary[];
  setProjects: Dispatch<SetStateAction<ProjectSummary[]>>;
  currentVersion: number;
  pendingActions: PendingActionPayload[];
  setPendingActions: Dispatch<SetStateAction<PendingActionPayload[]>>;
  historyCollapsed: boolean;
  setHistoryCollapsed: Dispatch<SetStateAction<boolean>>;
  projectContextMenu: { projectId: string; x: number; y: number } | null;
  setProjectContextMenu: Dispatch<SetStateAction<{ projectId: string; x: number; y: number } | null>>;
  renameProjectId: string | null;
  setRenameProjectId: Dispatch<SetStateAction<string | null>>;
  renameProjectName: string;
  setRenameProjectName: Dispatch<SetStateAction<string>>;
  handleRenameProject: (projectId: string, newName: string) => Promise<void>;
  /** Deletes a project; resolves to true on success. */
  handleDeleteProject: (projIdToDelete: string) => Promise<boolean>;
  /** Creates a project with the given name; resolves to true on success. */
  handleCreateProject: (name: string) => Promise<boolean>;
  handleTogglePin: (projectId: string) => Promise<void>;
  /** Whether the styled "New Project" modal is shown (replaces native prompt()). */
  isCreateModalOpen: boolean;
  setIsCreateModalOpen: Dispatch<SetStateAction<boolean>>;
  /** Project awaiting delete confirmation in the styled ConfirmModal (replaces native confirm()). */
  projectPendingDelete: string | null;
  setProjectPendingDelete: Dispatch<SetStateAction<string | null>>;
  /** Sidebar search filter — case-insensitively filters visible projects by name. */
  projectSearchQuery: string;
  setProjectSearchQuery: Dispatch<SetStateAction<string>>;

  // Chat / split layout
  messages: ChatMessage[];
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  rawInput: string;
  setRawInput: Dispatch<SetStateAction<string>>;
  splitPct: number;
  setSplitPct: Dispatch<SetStateAction<number>>;
  isDraggingSplit: boolean;
  setIsDraggingSplit: Dispatch<SetStateAction<boolean>>;
  splitContainerRef: React.RefObject<HTMLDivElement | null>;
  chatEndRef: React.RefObject<HTMLDivElement | null>;
  isProcessing: boolean;
  isLoading: boolean;
  currentAgentNode: string | null;
  syncStatus: string;
  // Finding #40: LM Studio connectivity health (polled via GET /api/health)
  backendOnline: boolean | null;
  lmStudioOnline: boolean | null;
  lmStudioModel: string | null;
  lmStudioModelLoaded: boolean;
  lmStudioLoadedModels: string[];
  lmStudioLatencyMs: number | null;
  lmStudioLastCheckedAt: string | null;
  lmStudioError: string | null;
  checkLmStudioHealth: () => Promise<void>;
  clarificationAnswers: Record<string, string>;
  handleUpdateAnswerValue: (key: string, value: string) => void;
  handleSubmitClarifications: (e: React.FormEvent) => Promise<void>;
  handleSendMessage: (textToSend?: string) => Promise<void>;
  handleValidateRequirements: () => Promise<void>;
  handleGeneratePRD: () => Promise<void>;
  /**
   * Gate shared by the agent action buttons (Validate Requirements / Generate
   * PRD): true only when the active project exists AND holds real content —
   * at least one uploaded knowledge document, user story, or requirement item.
   */
  canRunAgentActions: boolean;
  /** Aborts the in-flight agent request (Stop button). No-op when idle. */
  handleStopGeneration: () => void;
  handleDownloadDocx: () => Promise<void>;
  handlePrintPDF: () => void;
  loadProjectState: (projId: string, retries?: number, delay?: number) => Promise<void>;
  // Uploaded-document knowledge base + DRAFT-only extraction handlers
  documents: UseDocumentsResult;

  // PRD / requirements state
  structuredRequirements: StructuredRequirements;
  auditResult: AuditResult;
  prdMarkdown: string;
  sections: PRDSection[];
  editingSectionId: string | null;
  setEditingSectionId: Dispatch<SetStateAction<string | null>>;
  editBuffer: string;
  setEditBuffer: Dispatch<SetStateAction<string>>;
  handleSaveSection: (sectionId: string, newContent: string) => Promise<void>;
  lockedRequirements: Record<string, RequirementLockState>;
  handleLockRequirement: (requirementCode: string) => Promise<void>;
  handleUnlockRequirement: (requirementCode: string) => Promise<void>;

  // Tabs / flows / history (document library lives inside the history tab)
  activeTab: WorkspaceTab;
  setActiveTab: (tab: WorkspaceTab) => void;
  mermaidDiagram: string;
  versionHistory: VersionHistory[];
  selectedHistVersion: number;
  setSelectedHistVersion: Dispatch<SetStateAction<number>>;
  diffBaseVersion: number | null;
  setDiffBaseVersion: Dispatch<SetStateAction<number | null>>;
  diagramZoom: number;
  setDiagramZoom: Dispatch<SetStateAction<number>>;
  hoverNode: string | null;
  setHoverNode: Dispatch<SetStateAction<string | null>>;
  activePacketFlow: boolean;
  setActivePacketFlow: Dispatch<SetStateAction<boolean>>;
}

// ----------------------------------------------------------------------------
// Hook — composes the focused sub-hooks back into one `ProjectState`.
// ----------------------------------------------------------------------------

export function useProjectState(): ProjectState {
  const projectsApi = useProjects();
  const ui = useWorkspaceUi();
  const store = useRequirementStore(projectsApi.projectId);
  const locks = useArtifactLocks(store, projectsApi.projectId);
  const { loadProjectState } = useProjectSync(
    store,
    projectsApi.projectId,
    projectsApi.setPendingActions,
    ui.setActiveTab,
  );
  const lm = useLmStudioHealth();
  // Documents must be composed BEFORE useChat so the agent-action gate below
  // can consider the knowledge base when it is injected into the chat deps.
  const documents = useDocuments({
    projectId: projectsApi.projectId,
    pendingActions: projectsApi.pendingActions,
    setPendingActions: projectsApi.setPendingActions,
  });

  // Agent-action gating (Validate Requirements / Generate PRD): a brand-new
  // project with NO knowledge documents and NO gathered requirements has
  // nothing for the Auditor/Architect agents to work with, so those actions
  // stay blocked until real content exists (uploaded docs, user stories, or
  // requirement items).
  const hasRequirementContent =
    (store.structuredRequirements.user_stories?.length ?? 0) > 0 ||
    (store.structuredRequirements.requirements?.length ?? 0) > 0;
  const hasKnowledgeContent = documents.documents.length > 0;
  const canRunAgentActions =
    Boolean(projectsApi.projectId) && (hasRequirementContent || hasKnowledgeContent);

  const chat = useChat(store, {
    projectId: projectsApi.projectId,
    projects: projectsApi.projects,
    currentVersion: store.currentVersion,
    setPendingActions: projectsApi.setPendingActions,
    setActiveTab: ui.setActiveTab,
    loadProjectState,
    canRunAgentActions,
  });


  // Shared plumbing for the two file exports. The generated PRD is LaTeX
  // (template-krungsrinimble.tex), so the finished PDF/DOCX is COMPILED
  // server-side (Tectonic / Pandoc) — the browser never re-parses it as
  // markdown, which is what previously made exports follow template.md.
  const exportCompiledFile = async (fmt: 'pdf' | 'docx') => {
    const pid = projectsApi.projectId;
    if (!pid) {
      store.setSyncStatus('Select a project before exporting.');
      return;
    }
    const projectName =
      projectsApi.projects.find(p => p.id === pid)?.name || 'Krungsri Nimble PRD';

    store.setSyncStatus(
      fmt === 'pdf'
        ? 'Compiling the Krungsri Nimble LaTeX PRD to PDF (Tectonic)...'
        : 'Converting the Krungsri Nimble LaTeX PRD to Word (Pandoc)...',
    );

    try {
      const blob =
        fmt === 'pdf'
          ? await api.exportPrdPdf(pid, store.prdMarkdown, store.currentVersion, projectName)
          : await api.exportPrdDocx(pid, store.prdMarkdown, store.currentVersion, projectName);

      const stem = `PRD-${projectName.replace(/[^A-Za-z0-9._-]+/g, '-').slice(0, 48)}`;
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${stem}-V${store.currentVersion}.${fmt}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);

      store.setSyncStatus(
        fmt === 'pdf' ? 'PRD PDF exported from the .tex template.' : 'PRD Word Document (.docx) exported from the .tex template.',
      );
    } catch (err) {
      const detail = await detailFromBlobError(err);
      if (detail) {
        handleError(detail, err);
        store.setSyncStatus(`Failed to generate ${fmt.toUpperCase()} document.`);
      } else if (fmt === 'pdf') {
        handleError('Failed to generate the PDF document.', err);
        store.setSyncStatus('Failed to generate PDF document.');
      } else {
        handleError('Failed to generate the DOCX document.', err);
        store.setSyncStatus('Failed to generate DOCX document.');
      }
    }
  };

  const handleDownloadDocx = async () => {
    await exportCompiledFile('docx');
  };

  const handlePrintPDF = async () => {
    await exportCompiledFile('pdf');
  };

  return {
    projectId: projectsApi.projectId,
    setProjectId: projectsApi.setProjectId,
    projects: projectsApi.projects,
    setProjects: projectsApi.setProjects,
    pendingActions: projectsApi.pendingActions,
    setPendingActions: projectsApi.setPendingActions,
    currentVersion: store.currentVersion,
    rawInput: chat.rawInput,
    setRawInput: chat.setRawInput,
    splitPct: ui.splitPct,
    setSplitPct: ui.setSplitPct,
    isDraggingSplit: ui.isDraggingSplit,
    setIsDraggingSplit: ui.setIsDraggingSplit,
    historyCollapsed: ui.historyCollapsed,
    setHistoryCollapsed: ui.setHistoryCollapsed,
    splitContainerRef: ui.splitContainerRef,
    messages: chat.messages,
    setMessages: chat.setMessages,
    projectContextMenu: projectsApi.projectContextMenu,
    setProjectContextMenu: projectsApi.setProjectContextMenu,
    renameProjectId: projectsApi.renameProjectId,
    setRenameProjectId: projectsApi.setRenameProjectId,
    renameProjectName: projectsApi.renameProjectName,
    setRenameProjectName: projectsApi.setRenameProjectName,
    handleRenameProject: projectsApi.handleRenameProject,
    handleDeleteProject: projectsApi.handleDeleteProject,
    handleCreateProject: projectsApi.handleCreateProject,
    handleTogglePin: projectsApi.handleTogglePin,
    isCreateModalOpen: projectsApi.isCreateModalOpen,
    setIsCreateModalOpen: projectsApi.setIsCreateModalOpen,
    projectPendingDelete: projectsApi.projectPendingDelete,
    setProjectPendingDelete: projectsApi.setProjectPendingDelete,
    projectSearchQuery: projectsApi.projectSearchQuery,
    setProjectSearchQuery: projectsApi.setProjectSearchQuery,
    structuredRequirements: store.structuredRequirements,
    auditResult: store.auditResult,
    prdMarkdown: store.prdMarkdown,
    sections: store.sections,
    editingSectionId: store.editingSectionId,
    setEditingSectionId: store.setEditingSectionId,
    editBuffer: store.editBuffer,
    setEditBuffer: store.setEditBuffer,
    handleSaveSection: store.handleSaveSection,
    lockedRequirements: locks.lockedRequirements,
    handleLockRequirement: locks.handleLockRequirement,
    handleUnlockRequirement: locks.handleUnlockRequirement,
    activeTab: ui.activeTab,
    setActiveTab: ui.setActiveTab,
    mermaidDiagram: store.mermaidDiagram,
    versionHistory: store.versionHistory,
    selectedHistVersion: ui.selectedHistVersion,
    setSelectedHistVersion: ui.setSelectedHistVersion,
    diffBaseVersion: ui.diffBaseVersion,
    setDiffBaseVersion: ui.setDiffBaseVersion,
    diagramZoom: ui.diagramZoom,
    setDiagramZoom: ui.setDiagramZoom,
    hoverNode: ui.hoverNode,
    setHoverNode: ui.setHoverNode,
    activePacketFlow: ui.activePacketFlow,
    setActivePacketFlow: ui.setActivePacketFlow,
    clarificationAnswers: chat.clarificationAnswers,
    handleUpdateAnswerValue: chat.handleUpdateAnswerValue,
    handleSubmitClarifications: chat.handleSubmitClarifications,
    isProcessing: chat.isProcessing,
    isLoading: chat.isLoading,
    currentAgentNode: chat.currentAgentNode,
    syncStatus: chat.syncStatus,
    chatEndRef: chat.chatEndRef,
    handleSendMessage: chat.handleSendMessage,
    handleValidateRequirements: chat.handleValidateRequirements,
    handleGeneratePRD: chat.handleGeneratePRD,
    canRunAgentActions,
    handleStopGeneration: chat.handleStopGeneration,
    handleDownloadDocx,
    handlePrintPDF,
    loadProjectState,
    documents,
    // Finding #40: LM Studio connectivity health
    backendOnline: lm.backendOnline,
    lmStudioOnline: lm.lmStudioOnline,
    lmStudioModel: lm.lmStudioModel,
    lmStudioModelLoaded: lm.lmStudioModelLoaded,
    lmStudioLoadedModels: lm.lmStudioLoadedModels,
    lmStudioLatencyMs: lm.lmStudioLatencyMs,
    lmStudioLastCheckedAt: lm.lmStudioLastCheckedAt,
    lmStudioError: lm.lmStudioError,
    checkLmStudioHealth: lm.checkLmStudioHealth,
  };
}