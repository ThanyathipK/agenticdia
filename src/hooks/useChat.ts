// useChat — the conversational / multi-agent handlers extracted from the former
// useProjectState god-hook. Owns `rawInput` and the agent actions
// (send, validate, generate PRD, clarifications). Domain state lives in the
// shared `RequirementStore`; project info and pending-actions are injected
// through `deps`.
import { useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import axios from 'axios';
import { api } from '../api/client';
import type { PendingActionPayload, ProjectSummary } from '../api/types';
import {
  toAuditResultFromPayload,
  toGatheredRequirementsPayload,
  toStructuredRequirementsFromGathered,
} from '../api/transforms';
import type { VersionHistory } from '../components/types';
import { handleError } from '../components/Toast';
import type { RequirementStore } from './useRequirementStore';
import type { WorkspaceTab } from './useWorkspaceUi';

export interface ChatDeps {
  projectId: string | null;
  projects: ProjectSummary[];
  currentVersion: number;
  setPendingActions: Dispatch<SetStateAction<PendingActionPayload[]>>;
  setActiveTab: (tab: WorkspaceTab) => void;
  loadProjectState: (projId: string, retries?: number, delay?: number) => Promise<void>;
  /**
   * Gate shared with the ChatPanel action buttons: false while the project has
   * neither knowledge documents nor gathered requirements, so the agent
   * handlers refuse to run on an empty project (defense-in-depth parity with
   * the disabled Validate / Generate PRD buttons).
   */
  canRunAgentActions: boolean;
}

export interface UseChatResult {
  messages: RequirementStore['messages'];
  setMessages: RequirementStore['setMessages'];
  rawInput: string;
  setRawInput: Dispatch<SetStateAction<string>>;
  isProcessing: boolean;
  isLoading: boolean;
  currentAgentNode: string | null;
  syncStatus: string;
  chatEndRef: RequirementStore['chatEndRef'];
  clarificationAnswers: Record<string, string>;
  handleSendMessage: (textToSend?: string) => Promise<void>;
  handleValidateRequirements: () => Promise<void>;
  handleGeneratePRD: () => Promise<void>;
  /** Aborts the in-flight agent request (Stop button). No-op when idle. */
  handleStopGeneration: () => void;
  handleSubmitClarifications: (e: React.FormEvent) => Promise<void>;
  handleUpdateAnswerValue: (key: string, value: string) => void;
}

const nowTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

// --- Rate-limit (HTTP 429) awareness ---------------------------------------
// A 429 from the backend is a transient "slow down" signal (Finding #39), NOT a
// backend outage. These helpers let callers distinguish the two so they surface
// a "please wait" notice instead of the automatic local-sandbox fallback.

const isRateLimitError = (err: unknown): boolean => {
  if (!err || typeof err !== 'object') return false;
  return (err as { response?: { status?: number } }).response?.status === 429;
};

const extractRetryAfter = (err: unknown): number | null => {
  if (!err || typeof err !== 'object') return null;
  const headers = (err as { response?: { headers?: Record<string, unknown> & { get?: (k: string) => unknown } } }).response?.headers;
  const raw =
    headers?.['retry-after'] ??
    headers?.['Retry-After'] ??
    (typeof headers?.get === 'function' ? headers.get('retry-after') : undefined);
  if (raw === undefined || raw === null) return null;
  const seconds = Number(raw);
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : null;
};

const rateLimitedContent = (err: unknown): string => {
  const wait = extractRetryAfter(err);
  const suffix = wait === null
    ? 'A short time window will restore access.'
    : `Please wait about **${wait} second(s)** before continuing.`;
  return `⏳ **Rate Limit Reached:** Too many requests in a short window. ${suffix}`;
};

// --- Stop-button (request abort) awareness ----------------------------------
// When the user presses Stop we cancel the axios request. Axios then rejects
// with a CanceledError — that is an intentional user action, NOT a failure, so
// every handler surfaces a neutral "stopped" notice instead of an error toast.
const isAbortError = (err: unknown): boolean =>
  axios.isCancel(err) || (err as { code?: string })?.code === 'ERR_CANCELED';

export function useChat(store: RequirementStore, deps: ChatDeps): UseChatResult {
  const [rawInput, setRawInput] = useState<string>('');

  // Abort controller for whichever agent request is currently in flight.
  // The Stop button aborts it; each handler creates a fresh controller per run.
  const abortRef = useRef<AbortController | null>(null);

  // (Chat auto-scroll moved into ChatPanel, which owns the scroll container:
  // it only follows the timeline while the user is near the bottom and shows a
  // "jump to latest" pill otherwise.)

  // Build a truthful change-history digest for the backend prompt context.
  // Every agent call used to hardcode 'No previous history.', which defeated
  // the Architect node's incremental-regeneration logic (it could never see
  // what had already been approved). Returning undefined lets the backend's
  // documented default ("No previous history.") apply for genuinely new
  // projects instead of duplicating that string here.
  const buildVersionHistorySummaries = (): string | undefined => {
    const history = store.versionHistory || [];
    if (history.length === 0) return undefined;
    return history
      .map(h => `- v${h.version} (${h.timestamp}, ${h.author}): ${h.description}`)
      .join('\n');
  };

  // Handle Raw Conversational Input Submission
  const handleSendMessage = async (textToSend?: string) => {
    if (!deps.projectId) {
      store.setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: '⚠️ **No Project Selected:** Please select or create a project before interacting.',
        timestamp: nowTime(),
      }]);
      return;
    }
    const projectId = deps.projectId;
    const inputMsg = textToSend || rawInput;
    if (!inputMsg.trim()) return;

    // Clear main input if sent from main input box
    if (!textToSend) setRawInput('');

    // Append User message to UI
    store.setMessages(prev => [...prev, {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputMsg,
      timestamp: nowTime(),
    }]);

    // Set Loading State - show neutral loading indicator until intent is determined
    store.setIsLoading(true);
    store.setIsProcessing(true);
    store.setSyncStatus('Detecting intent...');
    store.setCurrentAgentNode(null);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      // The backend handles intent detection internally and routes accordingly:
      //   - GENERAL_CHAT: returns conversational response directly (no agent workflow)
      //   - REQUIREMENT_REQUEST: proceeds to Gatherer workflow
      const data = await api.processRequirements({
        project_id: projectId,
        raw_input: inputMsg,
        current_version: deps.currentVersion,
        version_history_summaries: 'No previous history.',
        target_agent: 'gatherer',
        structured_requirements: toGatheredRequirementsPayload(store.structuredRequirements),
      }, controller.signal);

      const detectedIntent = data.detected_intent || 'GENERAL_CHAT';

      if (detectedIntent === 'GENERAL_CHAT') {
        // Do NOT modify requirements, user stories, version history, or any project artifacts
        store.setSyncStatus('Synced with Supabase Cloud');
        store.setCurrentAgentNode(null);
        const chatResponse = data.message || 'I understood your message. How can I help you further?';
        store.setMessages(prev => [...prev, {
          id: `general-chat-${Date.now()}`,
          role: 'assistant',
          content: chatResponse,
          timestamp: nowTime(),
        }]);
      } else {
        store.setSyncStatus('Gathering specifications...');
        store.setCurrentAgentNode('gatherer_node');

        const receivedReqs = data.structured_requirements || null;
        const pendingActionId = data.pending_action_id;
        const isPendingMerge = data.pending_merge === true;

        if (isPendingMerge && pendingActionId) {
          // Store the pending merge for confirmation
          deps.setPendingActions(prev => [...prev, {
            id: pendingActionId,
            project_id: projectId,
            action_type: 'MERGE',
            original_user_message: inputMsg,
            proposed_changes: (receivedReqs ?? undefined) as Record<string, unknown> | undefined,
          }]);

          store.setMessages(prev => [...prev, {
            id: `merge-preview-${Date.now()}`,
            role: 'assistant',
            content: `📋 **Merge Preview Ready**\nI have analyzed your input and prepared the merged requirements. Please review the changes below and **Confirm** or **Cancel**.\n\n> *"${inputMsg}"*`,
            timestamp: nowTime(),
          }]);
        } else if (receivedReqs && receivedReqs.epic_name) {
          // Fallback: if no pending merge (e.g. direct update), apply immediately
          const nextVer = deps.currentVersion + 1;
          const nextStructured = toStructuredRequirementsFromGathered(receivedReqs, nextVer);
          store.setStructuredRequirements(nextStructured);
          store.setCurrentVersion(nextVer);

          const newHist: VersionHistory = {
            version: nextVer,
            timestamp: new Date().toISOString().replace('T', ' ').substring(0, 16),
            author: 'Product Owner',
            description: inputMsg.substring(0, 70) + (inputMsg.length > 70 ? '...' : ''),
            requirementsSnapshot: nextStructured,
          };
          store.setVersionHistory(prev => [newHist, ...prev]);
          store.setSyncStatus(`State updated to Version ${nextVer}.0`);
        }

        if (!isPendingMerge) {
          store.setMessages(prev => [...prev, {
            id: `gatherer-passed-${Date.now()}`,
            role: 'assistant',
            content: '📥 **Requirements Gathered & Updated!**\nI have successfully structured your input into the Agile Requirements board.\n\nTo run compliance validation on these updated specifications, please click the **Validate Requirements** button. Or click **Generate PRD** to build the technical documentation.',
            timestamp: nowTime(),
          }]);
        }
      }
    } catch (err) {
      if (isAbortError(err)) {
        store.setMessages(prev => [...prev, {
          id: `stopped-${Date.now()}`,
          role: 'assistant',
          content: '⏹️ **Stopped.**\nYou cancelled this request — the server-side run was terminated and no requirement changes were applied.',
          timestamp: nowTime(),
        }]);
        store.setSyncStatus('Request stopped by user.');
        return;
      }
      if (isRateLimitError(err)) {
        store.setMessages(prev => [...prev, {
          id: `rate-limited-${Date.now()}`,
          role: 'assistant',
          content: rateLimitedContent(err),
          timestamp: nowTime(),
        }]);
        store.setSyncStatus('Rate limited — please wait before continuing.');
        return;
      }
      handleError('The requirement engine could not complete your request.', err);
      const errorContent = `⚠️ **Request Failed — Nothing Was Saved.**\n\nThe requirement engine could not complete your message (${(err as Error)?.message || err}).\n\nYour input was **not** recorded as a user story, and no requirement state was changed.`;
      store.setMessages(prev => [...prev, {
        id: `api-error-${Date.now()}`,
        role: 'assistant',
        content: errorContent,
        timestamp: nowTime(),
      }]);
      store.setSyncStatus('Request failed. Nothing was saved.');
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      store.setIsLoading(false);
      store.setIsProcessing(false);
      store.setCurrentAgentNode(null);
    }
  };

  // Handle On-Demand Audit Execution
  const handleValidateRequirements = async () => {
    if (!deps.projectId) return;
    if (!deps.canRunAgentActions) {
      // Nothing to audit yet — mirror the disabled button instead of running
      // the auditor agent against an empty project.
      store.setSyncStatus('Nothing to validate yet — add requirements or upload a knowledge document.');
      return;
    }
    const projectId = deps.projectId;
    store.setIsLoading(true);
    store.setIsProcessing(true);
    store.setSyncStatus('Running Technical Audit...');
    store.setCurrentAgentNode('auditor_node');

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const data = await api.processRequirements({
        project_id: projectId,
        raw_input: '',
        target_agent: 'auditor',
        structured_requirements: toGatheredRequirementsPayload(store.structuredRequirements),
        current_version: deps.currentVersion,
        version_history_summaries: 'No previous history.',
      }, controller.signal);

      const receivedAudit = toAuditResultFromPayload(data.audit_result);
      const pendingActionId = data.pending_action_id;
      const isPendingMerge = data.pending_merge === true;

      // Handle pending merge for audit results (if applicable)
      if (isPendingMerge && pendingActionId) {
        deps.setPendingActions(prev => [...prev, {
          id: pendingActionId,
          project_id: projectId,
          action_type: 'MERGE',
          original_user_message: 'Audit validation',
          proposed_changes: (data.audit_result ?? {}) as Record<string, unknown>,
        }]);
      }

      const isValid = receivedAudit.is_valid;
      if (isValid === false) {
        const questions = receivedAudit.clarification_questions || [];
        const questionTexts = questions.map(q => `• ${q.question_text}`).join('\n');
        const warningContent = `⚠️ **Compliance Audit Alert (Auditor Agent):**\nTechnical gaps or missing security constraints were detected in your specifications against our checklist.\n\n**Pending Clarifications:**\n${questionTexts || 'None specified'}`;

        store.setMessages(prev => [...prev, {
          id: `audit-failed-${Date.now()}`,
          role: 'assistant',
          content: warningContent,
          timestamp: nowTime(),
          isPendingClarifications: true,
          auditResultSnapshot: receivedAudit,
        }]);

        store.setSyncStatus('Audit Pending. Clarifications required.');
      } else {
        const successContent = `✅ **Compliance Audit Passed!**\nRequirements have successfully validated against all retail banking security and regulatory checks. Ready for PRD compilation.`;
        store.setMessages(prev => [...prev, {
          id: `audit-passed-${Date.now()}`,
          role: 'assistant',
          content: successContent,
          timestamp: nowTime(),
        }]);

        store.setSyncStatus('Completed. Zero compliance violations.');
      }

      store.setAuditResult(receivedAudit);

      if (receivedAudit.clarification_questions) {
        const initialAnswers: Record<string, string> = {};
        receivedAudit.clarification_questions.forEach((_q, idx) => {
          initialAnswers[`q-${idx}`] = '';
        });
        store.setClarificationAnswers(initialAnswers);
      }
    } catch (err) {
      if (isAbortError(err)) {
        store.setMessages(prev => [...prev, {
          id: `stopped-${Date.now()}`,
          role: 'assistant',
          content: '⏹️ **Stopped.**\nYou cancelled this request — the audit was terminated and no validation verdict was applied.',
          timestamp: nowTime(),
        }]);
        store.setSyncStatus('Validation stopped by user.');
        return;
      }
      if (isRateLimitError(err)) {
        store.setMessages(prev => [...prev, {
          id: `rate-limited-${Date.now()}`,
          role: 'assistant',
          content: rateLimitedContent(err),
          timestamp: nowTime(),
        }]);
        store.setSyncStatus('Rate limited — please wait before continuing.');
        return;
      }
      handleError('Compliance audit did not complete.', err);
      store.setMessages(prev => [...prev, {
        id: `audit-error-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ **Audit Failed — No Validation Was Saved.**\n\nThe audit could not complete against the requirement engine (${(err as Error)?.message || err}).\n\nNo validation verdict was applied and no requirements were changed.`,
        timestamp: nowTime(),
      }]);
      store.setSyncStatus('Audit failed. No changes were saved.');
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      store.setIsLoading(false);
      store.setIsProcessing(false);
      store.setCurrentAgentNode(null);
    }
  };

  // Handle On-Demand PRD & Architecture Diagram Generation
  const handleGeneratePRD = async () => {
    if (!deps.projectId) return;
    if (!deps.canRunAgentActions) {
      // Nothing to compile yet — mirror the disabled button instead of asking
      // the architect agent to build a PRD from an empty project.
      store.setSyncStatus('Nothing to compile yet — add requirements or upload a knowledge document.');
      return;
    }
    const projectId = deps.projectId;
    store.setIsLoading(true);
    store.setIsProcessing(true);
    store.setSyncStatus('Compiling enterprise PRD document...');
    store.setCurrentAgentNode('architect_node');

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const data = await api.processRequirements({
        project_id: projectId,
        raw_input: '',
        target_agent: 'architect',
        structured_requirements: toGatheredRequirementsPayload(store.structuredRequirements),
        current_version: deps.currentVersion,
        version_history_summaries: buildVersionHistorySummaries(),
      }, controller.signal);

      const generatedPrd = data.prd_markdown || '';
      const generatedMermaid = data.mermaid_diagram || '';

      if (generatedPrd) store.setPrdMarkdown(generatedPrd);
      if (generatedMermaid) store.setMermaidDiagram(generatedMermaid);

      store.setMessages(prev => [...prev, {
        id: `prd-generated-${Date.now()}`,
        role: 'assistant',
        content: '📄 **Enterprise PRD Compiled Successfully!**\nThe CTO Architect Agent has generated the formal PRD and interactive system sequence flows in the preview panel.',
        timestamp: nowTime(),
      }]);

      store.setSyncStatus('PRD and sequence diagram updated.');
      deps.setActiveTab('prd'); // switch tab automatically to PRD
    } catch (err) {
      if (isAbortError(err)) {
        store.setMessages(prev => [...prev, {
          id: `stopped-${Date.now()}`,
          role: 'assistant',
          content: '⏹️ **Stopped.**\nYou cancelled this request — PRD generation was terminated server-side; no document was produced.',
          timestamp: nowTime(),
        }]);
        store.setSyncStatus('Generation stopped by user.');
        return;
      }
      if (isRateLimitError(err)) {
        store.setMessages(prev => [...prev, {
          id: `rate-limited-${Date.now()}`,
          role: 'assistant',
          content: rateLimitedContent(err),
          timestamp: nowTime(),
        }]);
        store.setSyncStatus('Rate limited — please wait before continuing.');
        return;
      }
      handleError('PRD generation did not complete.', err);
      store.setMessages(prev => [...prev, {
        id: `prd-error-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ **PRD Generation Failed — No Document Saved.**\n\nThe document could not be generated (${(err as Error)?.message || err}).\n\nNo PRD or diagram was produced.`,
        timestamp: nowTime(),
      }]);
      store.setSyncStatus('PRD generation failed. No document saved.');
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      store.setIsLoading(false);
      store.setIsProcessing(false);
      store.setCurrentAgentNode(null);
    }
  };

  // Stop button — terminates generation on BOTH sides: asks the backend to
  // hard-cancel the running workflow task (best-effort), then aborts the local
  // axios request so the UI unlocks immediately instead of waiting for the LLM
  // workflow to finish.
  const handleStopGeneration = () => {
    const controller = abortRef.current;
    if (!controller) return;
    const projectId = deps.projectId;
    if (projectId) {
      void api.cancelProcessRequirements(projectId).catch(() => {
        // Best-effort only: if this loses a race with completion (or fails),
        // the local abort below still unblocks the UI instantly.
      });
    }
    controller.abort();
    abortRef.current = null;
    store.setSyncStatus('Stopping generation...');
  };

  // (Removed) The former `simulateAgentWorkflowFallback` fabricated a fake user
  // story + version bump locally whenever any backend call failed. It silently
  // "saved" data the backend never saw and drove the misleading "(Local
  // Fallback)" messages. All failure paths now surface a truthful error instead.

  // Submit Answer to Clarifications Form
  const handleSubmitClarifications = async (e: React.FormEvent) => {
    e.preventDefault();
    if (Object.keys(store.clarificationAnswers).length === 0) return;

    try {
      store.setSyncStatus('Submitting clarifications...');
      const res = await api.submitClarifications(deps.projectId ?? '', store.clarificationAnswers);
      if (res) {
        store.setClarificationAnswers({});
        if (res.current_workflow_state) {
          store.setCurrentAgentNode(res.current_workflow_state);
        }
        if (res.clarification_questions) {
          store.setAuditResult(prev => ({
            ...prev,
            is_valid: res.validation_status === 'valid',
            clarification_questions: res.clarification_questions,
          }));
        }
        if (deps.projectId) deps.loadProjectState(deps.projectId);
        store.setSyncStatus('Clarifications submitted successfully');
      }
    } catch (err) {
      handleError('Failed to submit clarifications.', err);
      store.setSyncStatus('Failed to submit clarifications');
    }
  };

  const handleUpdateAnswerValue = (key: string, value: string) => {
    store.setClarificationAnswers(prev => ({
      ...prev,
      [key]: value,
    }));
  };

  return {
    messages: store.messages,
    setMessages: store.setMessages,
    rawInput,
    setRawInput,
    isProcessing: store.isProcessing,
    isLoading: store.isLoading,
    currentAgentNode: store.currentAgentNode,
    syncStatus: store.syncStatus,
    chatEndRef: store.chatEndRef,
    clarificationAnswers: store.clarificationAnswers,
    handleSendMessage,
    handleValidateRequirements,
    handleGeneratePRD,
    handleStopGeneration,
    handleSubmitClarifications,
    handleUpdateAnswerValue,
  };
}