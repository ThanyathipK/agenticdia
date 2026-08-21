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
import { downloadDocx, printPDF } from '../utils/docx';
import { useArtifactLocks } from './useArtifactLocks';
import { useChat } from './useChat';
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
  handleDeleteProject: (projIdToDelete: string) => Promise<void>;
  handleCreateProject: () => Promise<void>;
  handleTogglePin: (projectId: string) => Promise<void>;

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
  handleDownloadDocx: () => Promise<void>;
  handlePrintPDF: () => void;
  loadProjectState: (projId: string, retries?: number, delay?: number) => Promise<void>;

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

  // Tabs / flows / history
  activeTab: 'prd' | 'flows' | 'history';
  setActiveTab: (tab: 'prd' | 'flows' | 'history') => void;
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
  const chat = useChat(store, {
    projectId: projectsApi.projectId,
    projects: projectsApi.projects,
    currentVersion: store.currentVersion,
    setPendingActions: projectsApi.setPendingActions,
    setActiveTab: ui.setActiveTab,
    loadProjectState,
  });
  const lm = useLmStudioHealth();

  const handleDownloadDocx = async () => {
    await downloadDocx({
      projectId: projectsApi.projectId,
      projectName:
        projectsApi.projects.find(p => p.id === projectsApi.projectId)?.name ||
        'PromptPay Merchant Settlement Engine',
      epicName: store.structuredRequirements.epic_name || 'PromptPay Real-Time Merchant Settlement Engine',
      userStories: store.structuredRequirements.user_stories || [],
      currentVersion: store.currentVersion,
      prdMarkdown: store.prdMarkdown,
      setSyncStatus: store.setSyncStatus,
    });
  };

  const handlePrintPDF = () => {
    printPDF({
      projectId: projectsApi.projectId,
      projectName:
        projectsApi.projects.find(p => p.id === projectsApi.projectId)?.name ||
        'PromptPay Merchant Settlement Engine',
      epicName: store.structuredRequirements.epic_name || 'PromptPay Real-Time Merchant Settlement Engine',
      userStories: store.structuredRequirements.user_stories || [],
      currentVersion: store.currentVersion,
      prdMarkdown: store.prdMarkdown,
      setSyncStatus: store.setSyncStatus,
    });
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
    handleDownloadDocx,
    handlePrintPDF,
    loadProjectState,
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