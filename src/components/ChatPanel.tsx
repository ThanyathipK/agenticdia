// ChatPanel — left conversational panel extracted from the former Dashboard.tsx.
// Renders the message timeline (with embedded human-in-the-loop clarification
// forms), the agent execution ticker, and the fixed input + action bar.
import { useEffect, useRef } from 'react';
import type { ChangeEvent } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Network,
  Bot,
  Send,
  RefreshCw,
  Paperclip,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Loader2,
  Square,
} from 'lucide-react';
import { ProjectState } from '../hooks/useProjectState';
import { highlightMatch } from '../utils/highlight';

export function ChatPanel({ state }: { state: ProjectState }) {
  const {
    messages,
    chatEndRef,
    isProcessing,
    isLoading,
    currentAgentNode,
    rawInput,
    setRawInput,
    projectSearchQuery,
    handleSendMessage,
    handleStopGeneration,
    clarificationAnswers,
    handleUpdateAnswerValue,
    handleSubmitClarifications,
    handleValidateRequirements,
    handleGeneratePRD,
    projects,
    projectId,
    syncStatus,
    // Finding #40: the header pill surfaces LLM status; the model name is dynamic.
    lmStudioOnline,
    lmStudioModel,
    documents,
    canRunAgentActions,
  } = state;

  // Clip-icon attach: uploads straight into the project knowledge base
  // (same KNOWLEDGE-ONLY contract as the DocumentLibrary upload control).
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleClipClick = (): void => {
    if (!projectId) return;
    fileInputRef.current?.click();
  };

  const handleFilePicked = async (
    event: ChangeEvent<HTMLInputElement>,
  ): Promise<void> => {
    const file = event.target.files?.[0];
    // Allow re-picking the same file later.
    event.target.value = '';
    if (!file || !projectId) return;
    await documents.handleUploadDocument(file);
  };

  // Agent-action button gating: a brand-new project with no knowledge
  // documents and no gathered requirements has nothing for the Auditor /
  // Architect agents to work with, so Validate Requirements / Generate PRD
  // stay disabled until real content exists.
  const agentActionsDisabled = isLoading || isProcessing || !canRunAgentActions;
  const agentActionHint = !projectId
    ? 'Create or select a project first'
    : 'Add requirements via chat or upload a knowledge document first';

  // ---- Search-driven chat autoscroll --------------------------------------
  // The-sidebar search also matches conversation message content. When a query
  // is active, the chat highlight lights up matching bubbles and this brings
  // the FIRST matching bubble into the center of the chat viewport so the user
  // doesn't have to hunt for it.
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const lastMatchedBubbleIdRef = useRef<string | null>(null);

  useEffect(() => {
    const query = projectSearchQuery.trim().toLowerCase();
    if (!query) {
      lastMatchedBubbleIdRef.current = null;
      return;
    }
    const matchIndex = messages.findIndex(m => (m.content || '').toLowerCase().includes(query));
    if (matchIndex === -1) {
      lastMatchedBubbleIdRef.current = null;
      return;
    }
    const matchId = messages[matchIndex]?.id;
    // Don't re-jump to a bubble that is already the search target: keeps live
    // chat auto-scrolling to the bottom without fighting the search focus.
    if (matchId && lastMatchedBubbleIdRef.current === matchId) return;

    // Deferred so it lands AFTER the store's auto-scroll-to-bottom effect for
    // the same commit (parent effects run last) — the search focus wins.
    const timer = setTimeout(() => {
      const container = chatScrollRef.current;
      if (!container) return;
      const el = container.querySelector(`[data-msg-index="${matchIndex}"]`);
      if (!el) return;
      const containerRect = container.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      const top =
        elRect.top - containerRect.top + container.scrollTop -
        (container.clientHeight / 2) + (elRect.height / 2);
      container.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
      lastMatchedBubbleIdRef.current = matchId;
    }, 60);
    return () => clearTimeout(timer);
  }, [projectSearchQuery, messages]);

  return (
    <section className="chat-panel flex flex-col bg-surface border-r border-outline relative z-10" style={{ flexGrow: 0, flexShrink: 0, flexBasis: `${state.splitPct}%` }}>
      {/* Section Header */}
      <div className="p-3 md:p-4 border-b border-outline flex items-center justify-between bg-glass-bg backdrop-blur-md">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <Network className="text-primary w-4.5 h-4.5" />
          </div>
          <div className="min-w-0">
            <h2 className="font-headline-md text-sm font-bold text-on-surface truncate">
              {projects.find(p => p.id === projectId)?.name || "Conversational Analyst Workspace"}
            </h2>
            <div className="flex items-center gap-1.5 mt-0.5 hidden sm:flex">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shrink-0"></span>
              <p className="text-[10.5px] text-on-surface-variant font-mono truncate">Agent Graph Ready • {syncStatus}</p>
            </div>
          </div>
        </div>

        <span className="text-[10px] bg-primary/10 text-primary border border-primary/20 px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider shrink-0 ml-3 hidden sm:inline-block">
          {lmStudioOnline === false
            ? 'LLM Offline'
            : isProcessing
              ? 'Processing'
              : 'Idle'}
        </span>
      </div>

      {/* Chat Logs scroll list */}
      <div ref={chatScrollRef} className="flex-1 overflow-y-auto p-5 space-y-6 custom-scrollbar pb-32">
        <AnimatePresence initial={false}>
          {messages.map((msg, msgIndex) => {
            const isUser = msg.role === 'user';
            const isSystem = msg.role === 'system';
            // User bubbles sit on the dark brand background, so the highlight
            // needs a light translucent wash instead of the brand-tinted one.
            const bubbleHighlightClass = isUser
              ? 'bg-white/30 text-on-primary font-semibold rounded-[2px] px-0.5'
              : '';

            if (isSystem) {
              return (
                <motion.div 
                  key={msg.id}
                  data-msg-index={msgIndex}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mx-auto max-w-sm text-center py-2"
                >
                  <span className="inline-block px-3 py-1 bg-black/5 rounded-full text-[10.5px] font-mono text-on-surface-variant border border-black/5">
                    {highlightMatch(msg.content, projectSearchQuery)}
                  </span>
                </motion.div>
              );
            }

            return (
              <motion.div
                key={msg.id}
                data-msg-index={msgIndex}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
              >
                {/* Bot avatar */}
                {!isUser && (
                  <div className="w-8.5 h-8.5 rounded-xl bg-primary flex items-center justify-center shrink-0 shadow-md shadow-primary/20">
                    <Bot className="text-on-primary w-5 h-5" />
                  </div>
                )}

                <div className={`flex flex-col gap-1.5 max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
                  {/* Name card */}
                  <span className="font-label-md text-[10px] text-on-surface-variant/70 font-mono">
                    {isUser ? 'Product Owner' : 'Requirements Analyst Node'} • {msg.timestamp}
                  </span>

                  {/* Chat text box */}
                  <div className={`p-4 rounded-2xl shadow-sm border text-sm leading-relaxed ${
                    isUser 
                      ? 'bg-primary text-on-primary border-primary rounded-tr-none' 
                      : 'bg-primary/5 text-on-surface border-primary/15 rounded-tl-none'
                  }`}>
                    <p className="whitespace-pre-line">
                      {highlightMatch(msg.content, projectSearchQuery, bubbleHighlightClass)}
                    </p>
                  </div>

                  {/* Dynamic Pending Clarifications Form Embedded inside the timeline */}
                  {msg.isPendingClarifications && msg.auditResultSnapshot?.clarification_questions && (
                    <motion.div 
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: 0.1 }}
                      className="w-full mt-3 bg-white border-2 border-primary/20 rounded-2xl p-4.5 shadow-lg relative overflow-hidden"
                    >
                      {/* Aureate golden backdrop overlay */}
                      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent pointer-events-none"></div>
                      
                      <div className="flex items-center gap-2 mb-3 relative z-10">
                        <AlertTriangle className="text-primary w-4.5 h-4.5" />
                        <h3 className="font-bold text-xs text-on-surface">Clarification Required</h3>
                      </div>

                      <form
                        onSubmit={handleSubmitClarifications}
                        className="space-y-3 relative z-10"
                      >
                        {msg.auditResultSnapshot.clarification_questions.map((q, idx) => (
                          <div key={idx} className="space-y-1.5 bg-black/5 p-3 rounded-xl border border-black/5">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-mono font-bold text-primary uppercase bg-primary/10 px-1.5 py-0.5 rounded">
                                {q.checklist_category}
                              </span>
                              <span className="text-[10px] font-mono text-on-surface-variant font-semibold">
                                Target: {q.target_user_story_id}
                              </span>
                            </div>
                            <p className="text-[12.5px] font-medium text-on-surface leading-tight">
                              {q.question_text}
                            </p>
                            <input
                              type="text"
                              required
                              value={clarificationAnswers[`q-${idx}`] || ""}
                              onChange={(e) => handleUpdateAnswerValue(`q-${idx}`, e.target.value)}
                              placeholder="e.g. 180 seconds cached via Redis key prefix 'idemp:...'"
                              className="w-full bg-white border border-outline rounded-lg px-3 py-1.5 text-xs text-on-surface focus:ring-1 focus:ring-primary/40 focus:border-primary placeholder:text-on-surface-variant/40 outline-none"
                            />
                          </div>
                        ))}

                        <button
                          type="submit"
                          className="w-full bg-primary hover:brightness-110 active:scale-[0.99] text-on-primary py-2 rounded-xl font-label-md text-xs hover:brightness-110 transition-all font-bold shadow-md shadow-primary/20 flex items-center justify-center gap-1.5"
                        >
                          <CheckCircle2 className="w-4 h-4" />
                          <span>Submit Clarifications & Re-Audit</span>
                        </button>
                      </form>
                    </motion.div>
                  )}
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {/* Simulated execution step ticker */}
        {isProcessing && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-3 pl-12 text-xs text-on-surface-variant/80 italic font-medium"
          >
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-primary" />
            <span>
              {currentAgentNode === 'gatherer_node' && 'Agent: Agile Requirements Gatherer parsing core intent...'}
              {currentAgentNode === 'auditor_node' && 'Agent: Risk Compliance Auditor checking BOT 7-point guidelines...'}
              {currentAgentNode === 'architect_node' && 'Agent: Enterprise CTO Architect building markdown PRD...'}
              {!currentAgentNode && (lmStudioModel ? `Dispatched task to LM Studio Local LLM (${lmStudioModel})...` : 'Dispatched task to LM Studio Local LLM...')}
            </span>
          </motion.div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Conversational Fixed Input Container */}
      <div className="absolute bottom-0 w-full p-4 glass-panel border-t border-outline bg-white/90 z-20 space-y-3">
        {/* Agent Actions Row */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleValidateRequirements}
            disabled={agentActionsDisabled}
            title={agentActionsDisabled ? agentActionHint : 'Run the compliance audit against the current requirements'}
            className="min-w-[160px] flex-1 px-3 py-2 rounded-xl border border-outline hover:bg-black/5 font-label-md text-xs text-on-surface font-bold shadow-sm transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-primary" />
            <span>Validate Requirements</span>
          </button>
          <button
            onClick={handleGeneratePRD}
            disabled={agentActionsDisabled}
            title={agentActionsDisabled ? agentActionHint : 'Compile the formal PRD and architecture diagram'}
            className="min-w-[160px] flex-1 px-3 py-2 rounded-xl bg-primary text-on-primary hover:brightness-110 font-label-md text-xs font-bold shadow-md transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Generate PRD</span>
          </button>
        </div>

        {/* Knowledge-base attach feedback (e.g. scanned-PDF / needs-OCR notice) */}
        {documents.lastDraftMessage && (
          <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
            {documents.lastDraftMessage}
          </p>
        )}

        <div className="flex items-center gap-3 bg-black/5 rounded-full px-4 py-2.5 border border-outline focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/10 transition-all">
          <button
            type="button"
            title={projectId ? 'Attach file (.docx / .pdf / .md / .txt)' : 'Create or select a project first'}
            onClick={handleClipClick}
            disabled={!projectId || isLoading || isProcessing || documents.isUploading}
            className="w-8 h-8 rounded-full flex items-center justify-center text-on-surface-variant hover:bg-primary/10 hover:text-primary transition-colors shrink-0 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {documents.isUploading ? (
              <Loader2 className="w-4.5 h-4.5 animate-spin" />
            ) : (
              <Paperclip className="w-4.5 h-4.5" />
            )}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".docx,.pdf,.md,.txt"
            className="hidden"
            onChange={(e) => void handleFilePicked(e)}
          />
          <input
            type="text"
            value={rawInput}
            disabled={isLoading || isProcessing}
            onChange={(e) => setRawInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
            placeholder={isLoading || isProcessing ? "Processing..." : "Describe a change or write feedback..."}
            className="flex-1 bg-transparent border-none focus:ring-0 font-body-sm text-sm placeholder:text-on-surface-variant/55 text-on-surface outline-none"
          />
          {isLoading || isProcessing ? (
            <button
              type="button"
              title="Stop generating"
              onClick={handleStopGeneration}
              className="w-8.5 h-8.5 rounded-full flex items-center justify-center transition-transform shrink-0 shadow-sm bg-red-600 text-white hover:bg-red-700 hover:scale-105 cursor-pointer"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
            </button>
          ) : (
            <button
              onClick={() => handleSendMessage()}
              disabled={!rawInput.trim()}
              className={`w-8.5 h-8.5 rounded-full flex items-center justify-center transition-transform shrink-0 shadow-sm ${
                rawInput.trim()
                  ? 'bg-primary text-on-primary hover:scale-105 cursor-pointer'
                  : 'bg-black/10 text-on-surface-variant/40 cursor-not-allowed'
              }`}
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </section>
  );
}