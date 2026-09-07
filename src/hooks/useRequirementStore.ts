// useRequirementStore — the requirement-engine domain store extracted from the
// former useProjectState god-hook.
//
// Owns every piece of requirement/PRD state (structured requirements, audit
// result, PRD markdown, sections, diagram source, version ledger, locks, chat
// messages, workflow/agent status) plus their typed setters. It is intentionally
// a "store", not a god-hook: cross-cutting concerns (SSE sync, chat handlers,
// lock actions) live in dedicated hooks that receive this store as a parameter,
// and `useProjectState` composes everything.
import { useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { api } from '../api/client';
import type {
  ArtifactLockState,
  AuditResult,
  ChatMessage,
  PRDSection,
  PrdSectionLockState,
  RequirementLockState,
  StructuredRequirements,
  VersionHistory,
} from '../components/types';
import { handleError } from '../components/Toast';
import {
  formatUserStoriesToMarkdown,
  getSafeSectionContent,
  parsePRDToSections,
  stitchSectionsToPRD,
} from '../utils/markdown';

// ----------------------------------------------------------------------------
// Initial demo state (preserved from the former Dashboard monolith)
// ----------------------------------------------------------------------------

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: 'init-1',
    role: 'system',
    content:
      'Requirements Engine Initialized. Multi-Agent workflow is ready to ingest raw Product Owner specifications.',
    timestamp: '10:24 AM',
  },
  {
    id: 'init-2',
    role: 'assistant',
    content:
      'Hello! I am your Senior Business Analyst AI Agent. Share your raw, conversational, or messy requirement text and I will structure it, run a compliance audit, and compile a formal PRD for you.',
    timestamp: '10:24 AM',
  },
];

// Neutral starting state: the workspace boots EMPTY until real data is loaded
// from the backend or produced by an agent run. Seeding fabricated demo PRDs /
// diagrams here made every fresh project display fake "generated" documents
// before any LLM invocation had ever happened.
const INITIAL_STRUCTURED_REQUIREMENTS: StructuredRequirements = {
  epic_name: '',
  version: 1,
  user_stories: [],
};

const INITIAL_AUDIT_RESULT: AuditResult = {
  is_valid: false,
  audit_version_reviewed: 1,
  passed_checks: [],
  failed_checks: [],
  clarification_questions: [],
};

const INITIAL_PRD_MARKDOWN = '';

const INITIAL_MERMAID = '';

// ----------------------------------------------------------------------------
// Official Krungsri Nimble PRD template
// ----------------------------------------------------------------------------

// One-session cache for the official Krungsri Nimble PRD template served by
// GET /api/prd/template. This is the LATEX template (template-krungsrinimble.tex)
// - the exact structure the Architect agent fills in from project data. The
// right panel shows its normalized preview whenever the project has no
// generated PRD yet, and exports compile this same LaTeX.
let cachedPrdTemplate: string | null = null;

export async function getPrdTemplateMarkdown(): Promise<string> {
  if (cachedPrdTemplate !== null) return cachedPrdTemplate;
  try {
    const resp = await api.getPrdTemplate();
    cachedPrdTemplate = resp.template_latex || '';
  } catch {
    // The template is cosmetic — an unreachable backend surfaces its own errors.
    cachedPrdTemplate = '';
  }
  return cachedPrdTemplate;
}

const INITIAL_VERSION_HISTORY: VersionHistory[] = [];

// ----------------------------------------------------------------------------
// Store interface
// ----------------------------------------------------------------------------

export interface RequirementStore {
  // state
  structuredRequirements: StructuredRequirements;
  auditResult: AuditResult;
  prdMarkdown: string;
  /**
   * Preview copy of the PRD shown in the PRD panel. Generated PRDs are
   * Krungsri LaTeX bodies; this holds their server-normalized GFM form so the
   * markdown renderer never shows raw LaTeX. Markdown documents pass through.
   * Exports keep using the raw `prdMarkdown` so the PDF is still compiled from
   * the original .tex source.
   */
  prdMarkdownDisplay: string;
  sections: PRDSection[];
  editingSectionId: string | null;
  editBuffer: string;
  mermaidDiagram: string;
  versionHistory: VersionHistory[];
  currentVersion: number;
  lockedArtifacts: Record<string, ArtifactLockState>;
  lockedRequirements: Record<string, RequirementLockState>;
  syncStatus: string;
  isProcessing: boolean;
  isLoading: boolean;
  currentAgentNode: string | null;
  clarificationAnswers: Record<string, string>;
  messages: ChatMessage[];
  chatEndRef: React.RefObject<HTMLDivElement | null>;

  // setters
  setStructuredRequirements: Dispatch<SetStateAction<StructuredRequirements>>;
  setAuditResult: Dispatch<SetStateAction<AuditResult>>;
  setPrdMarkdown: Dispatch<SetStateAction<string>>;
  setSections: Dispatch<SetStateAction<PRDSection[]>>;
  setEditingSectionId: Dispatch<SetStateAction<string | null>>;
  setEditBuffer: Dispatch<SetStateAction<string>>;
  setMermaidDiagram: Dispatch<SetStateAction<string>>;
  setVersionHistory: Dispatch<SetStateAction<VersionHistory[]>>;
  setCurrentVersion: Dispatch<SetStateAction<number>>;
  setLockedArtifacts: Dispatch<SetStateAction<Record<string, ArtifactLockState>>>;
  setLockedRequirements: Dispatch<SetStateAction<Record<string, RequirementLockState>>>;
  setSyncStatus: Dispatch<SetStateAction<string>>;
  setIsProcessing: Dispatch<SetStateAction<boolean>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setCurrentAgentNode: Dispatch<SetStateAction<string | null>>;
  setClarificationAnswers: Dispatch<SetStateAction<Record<string, string>>>;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;

  // actions
  resetProjectState: () => void;
  handleSaveSection: (sectionId: string, newContent: string) => Promise<void>;
  /** Fetch the per-part PRD section lock/ownership map from the backend. */
  loadSectionLocks: (projId: string) => Promise<void>;
  /** Lock/unlock ONE PRD part (blocks edits + AI regeneration when locked). */
  handleToggleSectionLock: (sectionId: string) => Promise<void>;
  sectionLocks: Record<string, PrdSectionLockState>;
}

// ----------------------------------------------------------------------------
// Hook
// ----------------------------------------------------------------------------

export function useRequirementStore(projectId: string | null): RequirementStore {
  const [structuredRequirements, setStructuredRequirements] =
    useState<StructuredRequirements>(INITIAL_STRUCTURED_REQUIREMENTS);
  const [auditResult, setAuditResult] = useState<AuditResult>(INITIAL_AUDIT_RESULT);
  const [prdMarkdown, setPrdMarkdown] = useState<string>(INITIAL_PRD_MARKDOWN);
  const [prdMarkdownDisplay, setPrdMarkdownDisplay] = useState<string>(INITIAL_PRD_MARKDOWN);
  const [sections, setSections] = useState<PRDSection[]>([]);
  const [editingSectionId, setEditingSectionId] = useState<string | null>(null);
  const [editBuffer, setEditBuffer] = useState<string>('');
  const [mermaidDiagram, setMermaidDiagram] = useState<string>(INITIAL_MERMAID);
  const [versionHistory, setVersionHistory] =
    useState<VersionHistory[]>(INITIAL_VERSION_HISTORY);
  const [currentVersion, setCurrentVersion] = useState<number>(1);
  const [lockedArtifacts, setLockedArtifacts] =
    useState<Record<string, ArtifactLockState>>({});
  const [lockedRequirements, setLockedRequirements] =
    useState<Record<string, RequirementLockState>>({});
  // Per-part PRD section lock/ownership state (mirrors prd_sections rows).
  const [sectionLocks, setSectionLocks] = useState<Record<string, PrdSectionLockState>>({});
  const [syncStatus, setSyncStatus] = useState<string>('Synced with Local LLM');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [currentAgentNode, setCurrentAgentNode] = useState<string | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Preload the official Krungsri Nimble template once per session so the PRD
  // panel shows the document skeleton immediately. The updater form guarantees
  // a concurrently arriving generated PRD is never clobbered by the skeleton.
  useEffect(() => {
    let cancelled = false;
    getPrdTemplateMarkdown().then((tpl) => {
      if (!cancelled && tpl) setPrdMarkdown((prev) => prev || tpl);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Keep the PREVIEW copy of the PRD in sync with the stored document.
  // Generated PRDs are Krungsri LaTeX bodies: the backend normalizes them into
  // clean GFM (POST /api/prd/convert) so the markdown renderer never shows raw
  // LaTeX. Markdown documents pass through untouched. Exports keep using the
  // raw `prdMarkdown`, so PDFs are still compiled from the original .tex.
  useEffect(() => {
    const src = prdMarkdown;
    if (!src) {
      setPrdMarkdownDisplay('');
      return;
    }
    const looksLikeLatex = /\\(begin|section|documentclass|thispagestyle|newpage|vspace|shortstack)/.test(src);
    if (!looksLikeLatex) {
      setPrdMarkdownDisplay(src);
      return;
    }
    let cancelled = false;
    api
      .convertPrdToMarkdown(src)
      .then((res) => {
        if (!cancelled && res.markdown) setPrdMarkdownDisplay(res.markdown);
      })
      .catch(() => {
        // Preview-only concern: fall back to the raw document, never blank out.
        if (!cancelled) setPrdMarkdownDisplay(src);
      });
    return () => {
      cancelled = true;
    };
  }, [prdMarkdown]);

  // Sync sections whenever the PRD preview or structuredRequirements.user_stories changes
  useEffect(() => {
    setSections(prevSections => {
      const remoteRaw = getSafeSectionContent(prdMarkdownDisplay);
      const remoteSections = parsePRDToSections(remoteRaw);

      if (prevSections.length === 0) {
        return remoteSections;
      }

      let changed = false;
      const updated = prevSections.map(sec => {
        // If this is the active editing section, do not overwrite it with remote updates
        if (editingSectionId === sec.id) {
          return sec;
        }

        // Specially format Section 3 if we have structured user stories
        if (sec.id === 'user_stories' && structuredRequirements.user_stories && structuredRequirements.user_stories.length > 0) {
          const formattedStories = formatUserStoriesToMarkdown(structuredRequirements.user_stories);
          if (sec.content !== formattedStories) {
            changed = true;
            return { ...sec, content: formattedStories };
          }
          return sec;
        }

        const remoteSec = remoteSections.find(rs => rs.id === sec.id);
        if (remoteSec) {
          const safeRemoteContent = getSafeSectionContent(remoteSec.content);
          if (sec.content !== safeRemoteContent) {
            changed = true;
            return { ...sec, content: safeRemoteContent };
          }
        }

        return sec;
      });

      // If any new sections were added remotely that weren't in prevSections, append them
      const missingSections = remoteSections.filter(rs => !prevSections.some(ps => ps.id === rs.id));
      if (missingSections.length > 0) {
        changed = true;
        return [...updated, ...missingSections];
      }

      return changed ? updated : prevSections;
    });
  }, [prdMarkdownDisplay, structuredRequirements.user_stories, editingSectionId]);

  // (Chat auto-scroll moved into ChatPanel — see the note in useChat.ts.)

  const handleSaveSection = async (sectionId: string, newContent: string) => {
    // 1. Update the local sections state
    const updatedSections = sections.map(s =>
      s.id === sectionId ? { ...s, content: newContent } : s
    );
    setSections(updatedSections);

    // 2. Save THE PART to the backend (PATCH one section). The server appends
    // an immutable section version, re-stitches the full document from all
    // parts, and persists it. Falls back to the legacy whole-document save if
    // the section endpoint is unavailable (older backend).
    if (projectId) {
      setSyncStatus('Saving section edit...');
      try {
        const res = await api.updatePrdSection(projectId, sectionId, newContent);
        setPrdMarkdown(res.document_markdown);
        setPrdMarkdownDisplay(res.document_markdown);
        // Refresh per-part lock/version metadata (version_number advanced).
        setSectionLocks(prev => ({
          ...prev,
          [sectionId]: {
            ...(prev[sectionId] ?? {
              review_status: 'draft',
              content_source: 'ai',
              ai_generatable: true,
            }),
            ...(res.section.is_locked !== undefined ? { is_locked: res.section.is_locked } : {}),
            ...(res.section.review_status ? { review_status: res.section.review_status } : {}),
            version_number: res.section.version_number ?? prev[sectionId]?.version_number ?? null,
          },
        }));
        setSyncStatus('Section saved & versioned.');
      } catch {
        // Legacy fallback: stitch all sections and save the whole document.
        try {
          const stitchedMarkdown = stitchSectionsToPRD(updatedSections);
          setPrdMarkdown(stitchedMarkdown);
          setPrdMarkdownDisplay(stitchedMarkdown);
          await api.updateProjectState(projectId, { generated_prd: stitchedMarkdown });
          setSyncStatus('Manual changes saved & synced.');
        } catch (err) {
          handleError('Failed to save manual edits to the database.', err);
          setSyncStatus('Failed to sync manual changes with server.');
        }
      }
    }

    // 3. Reset editing state
    setEditingSectionId(null);
  };

  const loadSectionLocks = async (projId: string) => {
    try {
      const payload = await api.getPrdSections(projId);
      const map: Record<string, PrdSectionLockState> = {};
      for (const s of payload.sections) {
        map[s.section_key] = {
          is_locked: s.is_locked,
          locked_by: s.locked_by,
          review_status: s.review_status,
          content_source: s.content_source,
          ai_generatable: s.ai_generatable,
          version_number: s.version_number ?? null,
        };
      }
      setSectionLocks(map);
    } catch {
      // Cosmetic metadata — never block project loading on it.
    }
  };

  const handleToggleSectionLock = async (sectionId: string) => {
    if (!projectId) return;
    const current = sectionLocks[sectionId];
    const wasLocked = current?.is_locked ?? false;
    // Optimistic update
    setSectionLocks(prev => ({
      ...prev,
      [sectionId]: {
        ...(prev[sectionId] ?? {
          review_status: 'draft',
          content_source: 'ai',
          ai_generatable: true,
        }),
        is_locked: !wasLocked,
        locked_by: wasLocked ? null : 'user',
      },
    }));
    setSyncStatus(wasLocked ? 'Unlocking PRD part...' : 'Locking PRD part...');
    try {
      if (wasLocked) {
        await api.unlockPrdSection(projectId, sectionId);
        setSyncStatus('PRD part unlocked — AI can regenerate it again.');
      } else {
        await api.lockPrdSection(projectId, sectionId);
        setSyncStatus('PRD part locked — protected from edits and AI regeneration.');
      }
    } catch (err) {
      // Revert on failure
      setSectionLocks(prev => ({
        ...prev,
        [sectionId]: { ...(prev[sectionId] as PrdSectionLockState), is_locked: wasLocked },
      }));
      handleError(
        wasLocked ? 'Failed to unlock the PRD part.' : 'Failed to lock the PRD part.',
        err,
      );
      setSyncStatus('Lock action failed.');
    }
  };

  // Legacy helper (kept for parity): clears the requirement-engine domain state.
  // Note: pending-actions reset lives in `useProjects`, which owns that slice.
  const resetProjectState = () => {
    setStructuredRequirements({ epic_name: '', version: 0, user_stories: [] });
    setAuditResult({
      is_valid: false,
      audit_version_reviewed: 0,
      passed_checks: [],
      failed_checks: [],
      clarification_questions: [],
    });
    setPrdMarkdown('');
    setPrdMarkdownDisplay('');
    setMermaidDiagram('');
    setCurrentVersion(1);
    setCurrentAgentNode(null);
    setMessages([]);
    setVersionHistory([]);
    setSyncStatus('Switched project. Loading...');
    setSections([]);
    setSectionLocks({});
    setClarificationAnswers({});
  };

  return {
    structuredRequirements,
    auditResult,
    prdMarkdown,
    prdMarkdownDisplay,
    sections,
    editingSectionId,
    editBuffer,
    mermaidDiagram,
    versionHistory,
    currentVersion,
    lockedArtifacts,
    lockedRequirements,
    syncStatus,
    isProcessing,
    isLoading,
    currentAgentNode,
    clarificationAnswers,
    messages,
    chatEndRef,
    setStructuredRequirements,
    setAuditResult,
    setPrdMarkdown,
    setSections,
    setEditingSectionId,
    setEditBuffer,
    setMermaidDiagram,
    setVersionHistory,
    setCurrentVersion,
    setLockedArtifacts,
    setLockedRequirements,
    setSyncStatus,
    setIsProcessing,
    setIsLoading,
    setCurrentAgentNode,
    setClarificationAnswers,
    setMessages,
    resetProjectState,
    handleSaveSection,
    loadSectionLocks,
    handleToggleSectionLock,
    sectionLocks,
  };
}