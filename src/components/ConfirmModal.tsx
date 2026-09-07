import { useEffect, useRef, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { useModalBehavior } from '../hooks/useModalBehavior';

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  pendingLabel?: string;
  /** Renders the destructive (red) styling when true. */
  danger?: boolean;
  /** Action to run; resolves to true on success (modal closes only then). */
  onConfirm: () => Promise<boolean>;
  onClose: () => void;
}

// ConfirmModal — styled replacement for native confirm() dialogs, following
// the app's design language: rounded-2xl card on a blurred overlay with a
// warning icon chip; red CTA for destructive actions.
export function ConfirmModal({
  isOpen,
  title,
  description,
  confirmLabel = 'Confirm',
  pendingLabel = 'Working...',
  danger = false,
  onConfirm,
  onClose,
}: ConfirmModalProps) {
  const [isWorking, setIsWorking] = useState<boolean>(false);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  // Shared modal behavior: Escape-anywhere-to-close, focus trap, focus restore
  // on close, and background scroll lock. Escape stays disabled while a request
  // is in flight (same guard as the overlay click below).
  const { dialogRef } = useModalBehavior({
    isOpen,
    onClose: () => {
      if (!isWorking) onClose();
    },
  });

  // Reset transient state and focus the confirm button whenever opened.
  useEffect(() => {
    if (!isOpen) return;
    setIsWorking(false);
    const timer = setTimeout(() => confirmBtnRef.current?.focus(), 30);
    return () => clearTimeout(timer);
  }, [isOpen]);

  if (!isOpen) return null;

  const handleConfirm = async () => {
    if (isWorking) return;
    setIsWorking(true);
    try {
      const ok = await onConfirm();
      if (ok) onClose();
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={() => { if (!isWorking) onClose(); }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="w-[320px] bg-white border border-outline rounded-2xl shadow-xl p-5 focus:outline-none"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-2.5 mb-4">
          <div className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${danger ? 'bg-red-50' : 'bg-primary/10'}`}>
            <AlertTriangle className={`w-4 h-4 ${danger ? 'text-red-500' : 'text-primary'}`} />
          </div>
          <div>
            <h3 className="text-[13px] font-bold text-on-surface">{title}</h3>
            <p className="text-[11px] text-on-surface-variant mt-0.5 leading-relaxed">{description}</p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 mt-4">
          <button
            onClick={() => { if (!isWorking) onClose(); }}
            disabled={isWorking}
            className="px-3 py-2 rounded-xl bg-primary/5 text-on-surface-variant hover:bg-primary/10 hover:text-on-surface transition-colors text-xs font-semibold cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            ref={confirmBtnRef}
            onClick={handleConfirm}
            disabled={isWorking}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
              danger
                ? 'bg-red-500 text-white hover:bg-red-600 shadow-md shadow-red-500/20'
                : 'bg-primary text-on-primary hover:brightness-110 active:scale-[0.99] shadow-md shadow-primary/20'
            }`}
          >
            {isWorking ? pendingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}