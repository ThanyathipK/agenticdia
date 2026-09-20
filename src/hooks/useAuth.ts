// useAuth — the client-side authentication session.
//
// Owns the JWT session for the whole app so the sidebar's user chip (sign in /
// log out, bottom-left) has one source of truth, and exposes it to any other
// consumer that needs to know who is signed in.
//
// Backend contract (backend/app/routes/auth.py — repository-backed):
//   POST /api/auth/login    OAuth2 password flow -> access token + user
//   GET  /api/auth/me       re-resolves the token against the users table
//   POST /api/auth/register self-service signup (gated by SIGNUP_ENABLED)
//   POST /api/auth/logout   audit-log only; the JWT itself is stateless
//   GET  /api/auth/config   unauthenticated capabilities probe
//
// Persistence: the token is kept in localStorage so a reload does not sign the
// user out. That is deliberate for this internal banking workspace talking to a
// same-origin (Vite-proxied) API; HTTP-only cookies are the hardening step for
// a public deployment.
import { useCallback, useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { api, detailFromJsonError, setAuthToken } from '../api/client';
import type { AuthConfigPayload, AuthUserPayload } from '../api/types';
import { notify } from '../components/Toast';

export const AUTH_TOKEN_STORAGE_KEY = 'agenticdia.auth.token';

/**
 * The browser's localStorage, or null when it is unavailable (SSR / Node test
 * runs, private mode, storage disabled by policy). Every accessor below treats
 * null as "no persistence" instead of throwing.
 */
function tokenStorage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
}

/** Read the persisted token, tolerating a blocked/unavailable localStorage. */
export function readStoredToken(): string | null {
  return tokenStorage()?.getItem(AUTH_TOKEN_STORAGE_KEY) ?? null;
}

export function writeStoredToken(token: string | null): void {
  const storage = tokenStorage();
  if (!storage) return;
  if (token) storage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  else storage.removeItem(AUTH_TOKEN_STORAGE_KEY);
}

/** Initials for the sidebar avatar ('Ada Lovelace' -> 'AL'). */
export function authInitials(user: Pick<AuthUserPayload, 'full_name' | 'email'>): string {
  const source = (user.full_name || user.email || '').trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export interface UseAuthResult {
  /** The signed-in user's public profile, or null when signed out. */
  user: AuthUserPayload | null;
  token: string | null;
  /** True while a login / register / logout request is in flight. */
  isAuthenticating: boolean;
  /** False when the backend reports SIGNUP_ENABLED=false (hides the sign-up UI). */
  signupEnabled: boolean;
  /** Sign in with email + password. Resolves to a user-facing error, or null on success. */
  login: (email: string, password: string) => Promise<string | null>;
  /** Create an account and sign in. Resolves to a user-facing error, or null on success. */
  register: (
    email: string,
    password: string,
    fullName: string,
    role?: string,
  ) => Promise<string | null>;
  /** Clear the session (the server audit call is best-effort). */
  logout: () => Promise<void>;
  /** Controls the sign-in / sign-up dialog rendered by Dashboard. */
  isAuthModalOpen: boolean;
  setIsAuthModalOpen: Dispatch<SetStateAction<boolean>>;
}

export function useAuth(): UseAuthResult {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUserPayload | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState<boolean>(false);
  const [signupEnabled, setSignupEnabled] = useState<boolean>(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);

  // ---- Public auth capabilities (unauthenticated) --------------------------
  useEffect(() => {
    let cancelled = false;
    api
      .authConfig()
      .then((config: AuthConfigPayload) => {
        if (!cancelled) setSignupEnabled(Boolean(config.signup_enabled));
      })
      .catch((err: unknown) => {
        // Fail CLOSED: if we cannot confirm signup is enabled, do not offer it.
        console.warn('GET /api/auth/config failed; sign-up stays hidden', err);
        if (!cancelled) setSignupEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ---- Restore a persisted session ----------------------------------------
  // The stored token is NOT trusted on its own: GET /api/auth/me re-resolves it
  // against the users table, so a token for a deleted account (or one signed
  // with a different secret after a backend restart) is discarded instead of
  // leaving the UI in a fake signed-in state.
  useEffect(() => {
    const stored = readStoredToken();
    if (!stored) return;

    setAuthToken(stored);
    setToken(stored);

    let cancelled = false;
    api
      .authMe(stored)
      .then((profile) => {
        if (!cancelled) setUser(profile);
      })
      .catch(() => {
        if (cancelled) return;
        console.warn('Stored session is no longer valid; signing out locally');
        setAuthToken(null);
        writeStoredToken(null);
        setToken(null);
        setUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const clearSession = useCallback(() => {
    setAuthToken(null);
    writeStoredToken(null);
    setToken(null);
    setUser(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setIsAuthenticating(true);
    try {
      const session = await api.authLogin(email.trim(), password);
      setAuthToken(session.access_token);
      writeStoredToken(session.access_token);
      setToken(session.access_token);
      setUser(session.user);
      notify(`Signed in as ${session.user.full_name}`, 'success');
      return null;
    } catch (err: unknown) {
      // The backend answers an identical "Invalid credentials" for both an
      // unknown email and a wrong password (by design), so surface it as-is.
      return (
        detailFromJsonError(err) ??
        'Login failed — check your email and password, and that the backend is running.'
      );
    } finally {
      setIsAuthenticating(false);
    }
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string, role?: string) => {
      setIsAuthenticating(true);
      try {
        await api.authRegister({
          email: email.trim(),
          password,
          full_name: fullName.trim(),
          ...(role ? { role } : {}),
        });
      } catch (err: unknown) {
        return detailFromJsonError(err) ?? 'Registration failed. Please try again.';
      } finally {
        setIsAuthenticating(false);
      }

      // Registration returns no token, so sign the new account in with the very
      // credentials just created (one less round-trip for the user).
      const signInError = await login(email, password);
      if (signInError) {
        notify('Account created — please sign in.', 'success');
      }
      return null;
    },
    [login],
  );

  const logout = useCallback(async () => {
    setIsAuthenticating(true);
    try {
      // Best-effort: the server writes an audit-log line, but the JWT is
      // stateless, so the client-side clear below is what actually signs out.
      if (token) {
        try {
          await api.authLogout(token);
        } catch (err: unknown) {
          console.warn('Server-side logout call failed; clearing session locally', err);
        }
      }
    } finally {
      clearSession();
      setIsAuthenticating(false);
      notify('Signed out', 'info');
    }
  }, [clearSession, token]);

  return {
    user,
    token,
    isAuthenticating,
    signupEnabled,
    login,
    register,
    logout,
    isAuthModalOpen,
    setIsAuthModalOpen,
  };
}