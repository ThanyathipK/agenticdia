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
      'Krungsri Nimble Requirements Engine Initialized. Multi-Agent workflow is ready to ingest raw Product Owner specifications.',
    timestamp: '10:24 AM',
  },
  {
    id: 'init-2',
    role: 'assistant',
    content:
      'Hello! I am your Senior Business Analyst AI Agent. Please provide your raw, conversational, or messy requirement text for the PromptPay integration or core banking upgrade, and I will extract it, run a full compliance audit, and design a pristine PRD for you.',
    timestamp: '10:24 AM',
  },
];

const INITIAL_STRUCTURED_REQUIREMENTS: StructuredRequirements = {
  epic_name: 'PromptPay Real-Time Merchant Settlement Engine',
  version: 1,
  user_stories: [
    {
      ticket_code: 'US-001',
      story_title: 'Real-time Fund Settlement via QR Scan',
      as_a: 'Corporate Merchant Retailer',
      i_want_to:
        'receive instant notifications and settlement when a customer scans my PromptPay QR code',
      so_that: 'I can verify payment immediately and dispense goods without settlement delay',
      acceptance_criteria: [
        'Given a customer has scanned a valid static PromptPay QR code, When the transaction is approved by the national switch, Then the funds are instantly credited to the corporate account.',
        'Given the system detects a network timeout during national switch callback, When the transaction is retried, Then an explicit idempotency key must be checked to prevent double posting.',
      ],
    },
  ],
};

const INITIAL_AUDIT_RESULT: AuditResult = {
  is_valid: false,
  audit_version_reviewed: 1,
  passed_checks: ['Financial Regulatory Compliance', 'Security & Data Masking'],
  failed_checks: ['Idempotency & De-duplication', 'Network Timeouts & Retry Strategies'],
  clarification_questions: [
    {
      checklist_category: 'Idempotency & De-duplication',
      target_user_story_id: 'US-001',
      question_text:
        'The settlement workflow for US-001 does not specify how back-to-back duplicate transaction payloads are caught. Please define an explicit Idempotency Key mechanism (e.g. key duration, field source).',
    },
    {
      checklist_category: 'Network Timeouts & Retry Strategies',
      target_user_story_id: 'US-001',
      question_text:
        'What is the designated timeout ceiling and circuit-breaker retry pattern for dependent 3rd-party node queries when contacting the PromptPay national switch?',
    },
  ],
};
const INITIAL_PRD_MARKDOWN = `# Product Requirement Document (PRD)

## 1. Executive Summary
This document specifies the functional, non-functional, and technical requirements for integrating the PromptPay real-time payment network into our core banking ecosystem. It targets robust, high-throughput transactions with compliance audits enforced.

## 2. Technical Architecture & Constraints
- **Inbound Gateways:** mTLS with Bank of Thailand national switch
- **Message Standard:** ISO 20022 real-time pain.001 / pain.002 settlement envelopes
- **Data Guardrails:** Strict AES-256 field-level encryption for corporate merchant routing configurations

## 3. Scope of Requirements (User Stories)
- **REQ-PP-001:** Real-time settlement notifications with dynamic webhook routing
- **REQ-PP-002:** Automated end-of-day reconciliation with zero general ledger discrepancies`;

const INITIAL_MERMAID = `sequenceDiagram
  autonumber
  Client Browser->>FastAPI Backend: HTTP POST /api/transaction
  FastAPI Backend->>Security Module: Validate Signature & Token
  Security Module->>National Switch API: Dispatch ISO 20022 payload
  National Switch API-->>FastAPI Backend: Confirm Settlement Status
  FastAPI Backend->>Supabase DB: Persist Ledger & Update Idempotency`;

const INITIAL_VERSION_HISTORY: VersionHistory[] = [
  {
    version: 1,
    timestamp: '2026-07-10 10:24',
    author: 'Thanyathip (Product Owner)',
    description: 'Initial raw draft of PromptPay QR scan integration specifications.',
    requirementsSnapshot: {
      epic_name: 'PromptPay Real-Time Merchant Settlement Engine',
      version: 1,
      user_stories: [
        {
          ticket_code: 'US-001',
          story_title: 'Real-time Fund Settlement via QR Scan',
          as_a: 'Corporate Merchant Retailer',
          i_want_to:
            'receive instant notifications and settlement when a customer scans my PromptPay QR code',
          so_that: 'I can verify payment immediately and dispense goods without settlement delay',
          acceptance_criteria: [
            'Given a customer scanned a PromptPay QR, When transaction approved, Then credit funds.',
          ],
        },
      ],
    },
  },
];

// ----------------------------------------------------------------------------
// Store interface
// ----------------------------------------------------------------------------

export interface RequirementStore {
  // state
  structuredRequirements: StructuredRequirements;
  auditResult: AuditResult;
  prdMarkdown: string;
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
}

// ----------------------------------------------------------------------------
// Hook
// ----------------------------------------------------------------------------

export function useRequirementStore(projectId: string | null): RequirementStore {
  const [structuredRequirements, setStructuredRequirements] =
    useState<StructuredRequirements>(INITIAL_STRUCTURED_REQUIREMENTS);
  const [auditResult, setAuditResult] = useState<AuditResult>(INITIAL_AUDIT_RESULT);
  const [prdMarkdown, setPrdMarkdown] = useState<string>(INITIAL_PRD_MARKDOWN);
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
  const [syncStatus, setSyncStatus] = useState<string>('Synced with Local LLM');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [currentAgentNode, setCurrentAgentNode] = useState<string | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Sync sections whenever prdMarkdown or structuredRequirements.user_stories changes
  useEffect(() => {
    setSections(prevSections => {
      const remoteRaw = getSafeSectionContent(prdMarkdown);
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
  }, [prdMarkdown, structuredRequirements.user_stories, editingSectionId]);

  // Keep the chat scrolled to the latest message
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isProcessing]);

  const handleSaveSection = async (sectionId: string, newContent: string) => {
    // 1. Update the local sections state
    const updatedSections = sections.map(s =>
      s.id === sectionId ? { ...s, content: newContent } : s
    );
    setSections(updatedSections);

    // 2. Stitch back to a single prdMarkdown block
    const stitchedMarkdown = stitchSectionsToPRD(updatedSections);
    setPrdMarkdown(stitchedMarkdown);

    // 3. Save to backend database
    if (projectId) {
      setSyncStatus('Saving manual section edits...');
      try {
        await api.updateProjectState(projectId, { generated_prd: stitchedMarkdown });
        setSyncStatus('Manual changes saved & synced.');
      } catch (err) {
        handleError('Failed to save manual edits to the database.', err);
        setSyncStatus('Failed to sync manual changes with server.');
      }
    }

    // 4. Reset editing state
    setEditingSectionId(null);
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
    setMermaidDiagram('');
    setCurrentVersion(1);
    setCurrentAgentNode(null);
    setMessages([]);
    setVersionHistory([]);
    setSyncStatus('Switched project. Loading...');
    setSections([]);
    setClarificationAnswers({});
  };

  return {
    structuredRequirements,
    auditResult,
    prdMarkdown,
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
  };
}