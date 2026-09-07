// ChatEmptyState — onboarding empty state for a fresh conversation. Gives new
// users a one-click start via banking-domain starter prompts (each sends the
// prompt straight through the normal handleSendMessage flow).
import { Bot, Paperclip, Sparkles } from 'lucide-react';

const STARTER_PROMPTS: string[] = [
  'Draft requirements for a QR payment onboarding flow',
  'Gather requirements for a loan application with document upload',
  'Draft requirements for card issuance with KYC verification',
];

interface ChatEmptyStateProps {
  /** Disabled while no project is selected or an agent run is in flight. */
  disabled?: boolean;
  /** Tooltip shown on the disabled starter chips. */
  disabledReason?: string;
  onPick: (prompt: string) => void;
}

export function ChatEmptyState({ disabled = false, disabledReason, onPick }: ChatEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center text-center pt-14 pb-6 px-4">
      <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
        <Bot className="w-6 h-6 text-primary" />
      </div>
      <h3 className="text-sm font-bold text-on-surface">Turn a brief into audited requirements</h3>
      <p className="text-xs text-on-surface-variant max-w-xs mt-1.5 leading-relaxed">
        Describe a product idea, paste a messy brief, or attach a document — the agents will
        structure it, run the compliance audit, and compile the PRD.
      </p>

      <div className="flex flex-col gap-2 mt-5 w-full max-w-xs">
        {STARTER_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            disabled={disabled}
            title={disabled ? disabledReason : undefined}
            onClick={() => onPick(prompt)}
            className="w-full text-left px-3.5 py-2.5 rounded-xl border border-outline bg-surface hover:border-primary/40 hover:bg-primary/5 text-xs text-on-surface transition-colors flex items-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Sparkles className="w-3.5 h-3.5 text-primary shrink-0" />
            <span className="flex-1">{prompt}</span>
          </button>
        ))}
        <p className="text-[10.5px] text-on-surface-variant/70 font-mono mt-1 flex items-center justify-center gap-1.5">
          <Paperclip className="w-3 h-3 shrink-0" />
          <span>Attach .docx / .pdf / .md / .txt to feed the knowledge base</span>
        </p>
      </div>
    </div>
  );
}