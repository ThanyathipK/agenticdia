// AuthPanel — the sign-in / signed-in user chip pinned to the BOTTOM-LEFT of
// the project sidebar (#project-sidebar in Dashboard.tsx).
//
// Signed out  -> a "Sign in" button that opens AuthModal.
// Signed in   -> avatar + name/role chip with a "Log out" button.
//
// The sidebar collapses to a 68px icon rail, so both states have a compact
// rendering (icon-only, tooltips on the right) and a full one. All session
// state comes from useAuth; this component is presentation + the two callbacks.
import { LogIn, LogOut, ShieldCheck } from 'lucide-react';
import type { AuthUserPayload } from '../api/types';
import { authInitials } from '../hooks/useAuth';
import { Tooltip } from './Tooltip';

interface AuthPanelProps {
  user: AuthUserPayload | null;
  /** True while signing in / out (disables the triggers). */
  isAuthenticating: boolean;
  /** Sidebar icon-rail mode (68px) instead of the expanded 248px width. */
  collapsed: boolean;
  onOpenAuth: () => void;
  onLogout: () => void;
}

export function AuthPanel({
  user,
  isAuthenticating,
  collapsed,
  onOpenAuth,
  onLogout,
}: AuthPanelProps) {
  if (!user) {
    return (
      <div className="p-2 border-t border-outline">
        <Tooltip label="Sign in" side="right" className="w-full">
          <button
            type="button"
            onClick={onOpenAuth}
            disabled={isAuthenticating}
            aria-label="Sign in"
            className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-[13px] font-semibold text-on-surface-variant hover:bg-primary/10 hover:text-primary transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
              collapsed ? 'justify-center' : ''
            }`}
          >
            <LogIn className="w-4 h-4 shrink-0" />
            {!collapsed && <span>Sign in</span>}
          </button>
        </Tooltip>
      </div>
    );
  }

  const initials = authInitials(user);

  if (collapsed) {
    return (
      <div className="p-2 border-t border-outline flex flex-col items-center gap-1.5">
        <Tooltip label={`${user.full_name} · ${user.role}`} side="right">
          <div
            className="w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center text-[11px] font-bold shrink-0"
            aria-label={`Signed in as ${user.full_name}`}
          >
            {initials}
          </div>
        </Tooltip>
        <Tooltip label="Log out" side="right">
          <button
            type="button"
            onClick={onLogout}
            disabled={isAuthenticating}
            aria-label="Log out"
            className="w-8 h-8 rounded-xl flex items-center justify-center text-on-surface-variant hover:bg-red-50 hover:text-red-600 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </Tooltip>
      </div>
    );
  }

  return (
    <div className="p-2 border-t border-outline">
      <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-xl">
        <div
          className="w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center text-[11px] font-bold shrink-0"
          aria-hidden="true"
        >
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] font-semibold text-on-surface truncate" title={user.full_name}>
            {user.full_name}
          </div>
          <div className="flex items-center gap-1 text-[11px] text-on-surface-variant truncate">
            <ShieldCheck className="w-3 h-3 shrink-0 text-primary/70" />
            <span className="truncate" title={`${user.role} · ${user.email}`}>{user.role}</span>
          </div>
        </div>
        <Tooltip label="Log out" side="left">
          <button
            type="button"
            onClick={onLogout}
            disabled={isAuthenticating}
            aria-label="Log out"
            className="p-1.5 rounded-lg text-on-surface-variant hover:bg-red-50 hover:text-red-600 transition-colors shrink-0 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </Tooltip>
      </div>
    </div>
  );
}