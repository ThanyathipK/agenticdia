// useModalBehavior — shared modal UX behavior for the app's dialog components
// (ConfirmModal, NewProjectModal, ...):
//   - Escape closes the dialog via a document-level listener, so it works no
//     matter which element currently holds focus (per-button onKeyDown Escape
//     handlers only fired while that one button happened to be focused).
//   - Tab / Shift+Tab are trapped inside the dialog so keyboard focus can't
//     escape into the page behind the blurred overlay.
//   - Focus returns to the element that opened the dialog when it closes.
//   - Background scroll is locked while the dialog is open.
import { useEffect, useRef } from 'react';
import type { RefObject } from 'react';

interface UseModalBehaviorOptions {
  isOpen: boolean;
  /** Close callback (Escape key). Overlay click handling stays in the component. */
  onClose: () => void;
  /** When false (e.g. a request is in flight), Escape is ignored. */
  dismissible?: boolean;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export function useModalBehavior({
  isOpen,
  onClose,
  dismissible = true,
}: UseModalBehaviorOptions): { dialogRef: RefObject<HTMLDivElement | null> } {
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Track the latest onClose without re-subscribing the listeners on every
  // render (components pass fresh inline closures each render).
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!isOpen) return;

    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (dismissible) {
          event.stopPropagation();
          onCloseRef.current();
        }
        return;
      }
      if (event.key !== 'Tab') return;

      // Focus trap: cycle Tab / Shift+Tab within the dialog card.
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => el.getClientRects().length > 0);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const inside = active instanceof HTMLElement && dialog.contains(active);
      if (!event.shiftKey && (active === last || !inside)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && (active === first || !inside)) {
        event.preventDefault();
        last.focus();
      }
    };

    // Capture phase: win races against other document-level key handlers.
    document.addEventListener('keydown', handleKeyDown, true);

    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [isOpen, dismissible]);

  return { dialogRef };
}