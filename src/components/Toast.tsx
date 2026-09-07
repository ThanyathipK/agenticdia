import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { XCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { Tooltip } from './Tooltip';

export type ToastType = 'error' | 'warning' | 'success' | 'info';

export interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

type ToastListener = (toasts: Toast[]) => void;

// ---- Centered, module-level store -----------------------------------------
// Any component can trigger a toast via `notify` / `handleError` / `handleWarning`
// without needing React context or prop drilling. The <ToastHost /> component
// subscribes to this store and renders the visible toasts.
let toasts: Toast[] = [];
const listeners = new Set<ToastListener>();
let nextId = 1;

function emit() {
  const snapshot = [...toasts];
  listeners.forEach((listener) => listener(snapshot));
}

function dismissToast(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

/** Base toast trigger used by all higher-level helpers. */
export function notify(message: string, type: ToastType = 'info', duration = 5000) {
  const id = nextId++;
  toasts = [...toasts, { id, type, message }];
  emit();
  if (duration > 0) {
    setTimeout(() => dismissToast(id), duration);
  }
}

/**
 * Centralized error handler: logs the failure to the console for debugging and
 * surfaces a user-facing error toast so failures are never silent in the UI.
 */
export function handleError(context: string, error?: unknown) {
  console.error(context, error);
  notify(context, 'error');
}

/**
 * Centralized warning handler: logs the failure to the console for debugging and
 * surfaces a user-facing warning toast.
 */
export function handleWarning(context: string, error?: unknown) {
  console.warn(context, error);
  notify(context, 'warning');
}

// ---- Style helpers ---------------------------------------------------------
const TOAST_STYLES: Record<ToastType, { container: string; icon: React.ReactNode }> = {
  error: {
    container: 'border-red-300 bg-red-50 text-red-900',
    icon: <XCircle className="w-5 h-5 text-red-500 shrink-0" />,
  },
  warning: {
    container: 'border-amber-300 bg-amber-50 text-amber-900',
    icon: <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />,
  },
  success: {
    container: 'border-emerald-300 bg-emerald-50 text-emerald-900',
    icon: <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />,
  },
  info: {
    container: 'border-sky-300 bg-sky-50 text-sky-900',
    icon: <Info className="w-5 h-5 text-sky-500 shrink-0" />,
  },
};

/**
 * Renders all active toasts in a fixed top-right stack. Mount once at the app
 * root; it stays in sync with the module-level store automatically.
 */
export const ToastHost: React.FC = () => {
  const [items, setItems] = useState<Toast[]>([]);

  useEffect(() => {
    const listener: ToastListener = (next) => setItems(next);
    listeners.add(listener);
    // Pick up any toasts that may have fired before this host mounted.
    setItems([...toasts]);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-[360px] max-w-[calc(100vw-2rem)] pointer-events-none">
      <AnimatePresence>
        {items.map((t) => (
          <motion.div
            key={t.id}
            layout
            initial={{ opacity: 0, x: 60, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 60, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            role={t.type === 'error' ? 'alert' : 'status'}
            onClick={() => dismissToast(t.id)}
            className={`pointer-events-auto flex items-start gap-2.5 rounded-xl border px-3.5 py-3 shadow-lg cursor-pointer ${TOAST_STYLES[t.type].container}`}
          >
            {TOAST_STYLES[t.type].icon}
            <span className="text-sm font-medium leading-snug flex-1">{t.message}</span>
            <Tooltip label="Dismiss" side="left">
              <button
                className="shrink-0 rounded p-0.5 opacity-60 hover:opacity-100 hover:bg-black/5 transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  dismissToast(t.id);
                }}
                aria-label="Dismiss notification"
              >
                <X className="w-4 h-4" />
              </button>
            </Tooltip>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
};
