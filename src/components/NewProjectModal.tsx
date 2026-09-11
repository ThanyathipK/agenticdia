import { useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { useModalBehavior } from '../hooks/useModalBehavior';

interface NewProjectModalProps {
  isOpen: boolean;
  /**
   * Creates the project. Resolves to null on success (modal closes only then)
   * or to a user-facing error message — e.g. the backend's duplicate-name
   * conflict — which is rendered inline below the input.
   */
  onCreate: (name: string) => Promise<string | null>;
  onClose: () => void;
}

// NewProjectModal — styled replacement for the former native prompt() dialog,
// following the app's design language: rounded-2xl card on a blurred overlay,
// outline-border inputs, primary CTA.
export function NewProjectModal({ isOpen, onCreate, onClose }: NewProjectModalProps) {
  const [name, setName] = useState<string>('');
  const [isCreating, setIsCreating] = useState<boolean>(false);
  // Inline validation error (e.g. "name already exists" from the backend's
  // 409 duplicate check) — cleared as soon as the user edits the input.
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Shared modal behavior: Escape-anywhere-to-close, focus trap, focus restore
  // on close, and background scroll lock. Escape stays disabled while the
  // create request is in flight (same guard as the overlay click below).
  const { dialogRef } = useModalBehavior({
    isOpen,
    onClose: () => {
      if (!isCreating) onClose();
    },
  });

  // Fresh, focused input every time the modal opens.
  useEffect(() => {
    if (!isOpen) return;
    setName('');
    setIsCreating(false);
    setError(null);
    const timer = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(timer);
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    const trimmed = name.trim();
    if (!trimmed || isCreating) return;
    setIsCreating(true);
    setError(null);
    try {
      const failure = await onCreate(trimmed);
      if (failure === null) {
        onClose();
      } else {
        setError(failure);
      }
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={() => { if (!isCreating) onClose(); }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="w-[320px] bg-white border border-outline rounded-2xl shadow-xl p-5 focus:outline-none"
        role="dialog"
        aria-modal="true"
        aria-label="Create new project"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <Plus className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h3 className="text-[13px] font-bold text-on-surface">New Project</h3>
            <p className="text-[11px] text-on-surface-variant">Name your project to get started</p>
          </div>
        </div>

        <input
          ref={inputRef}
          type="text"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSubmit();
          }}
          placeholder="Project name"
          maxLength={40}
          aria-invalid={!!error}
          className={`w-full bg-white border rounded-xl px-3 py-2 text-xs text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none transition-colors ${
            error
              ? 'border-red-400 focus:border-red-500'
              : 'border-outline focus:border-primary'
          }`}
        />
        {error && (
          <p role="alert" className="mt-2 text-[11px] font-medium text-red-600 leading-snug">
            {error}
          </p>
        )}

        <div className="flex items-center justify-end gap-2 mt-4">
          <button
            onClick={() => { if (!isCreating) onClose(); }}
            disabled={isCreating}
            className="px-3 py-2 rounded-xl bg-primary/5 text-on-surface-variant hover:bg-primary/10 hover:text-on-surface transition-colors text-xs font-semibold cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || isCreating}
            className="px-4 py-2 rounded-xl bg-primary text-on-primary hover:brightness-110 active:scale-[0.99] transition-all text-xs font-bold shadow-md shadow-primary/20 flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:brightness-100"
          >
            <Plus className="w-3.5 h-3.5" />
            {isCreating ? 'Creating...' : 'Create Project'}
          </button>
        </div>
      </div>
    </div>
  );
}