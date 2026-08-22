import { ReactNode, useCallback, useEffect, useRef } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusableIn(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => element.getAttribute('aria-hidden') !== 'true'
  );
}

function useModalFocus(open: boolean, panelRef: React.RefObject<HTMLElement | null>, onClose: () => void) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) {
      return;
    }
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    const first = panel ? focusableIn(panel)[0] : undefined;
    (first ?? panel)?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !panel) {
        return;
      }
      const items = focusableIn(panel);
      if (!items.length) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };

    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      previous?.focus();
    };
  }, [open, panelRef]);
}

interface DialogProps {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  variant: 'drawer' | 'modal';
  children: ReactNode;
}

export function Dialog({ open, onClose, labelledBy, variant, children }: DialogProps) {
  const panelRef = useRef<HTMLElement | null>(null);
  const setPanelRef = useCallback((node: HTMLElement | null) => {
    panelRef.current = node;
  }, []);
  useModalFocus(open, panelRef, onClose);

  if (!open) {
    return null;
  }

  if (variant === 'drawer') {
    return (
      <>
        <div className="drawer-backdrop" onClick={onClose} />
        <aside
          ref={setPanelRef}
          className="drawer"
          role="dialog"
          aria-modal="true"
          aria-labelledby={labelledBy}
          tabIndex={-1}
        >
          {children}
        </aside>
      </>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={setPanelRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
