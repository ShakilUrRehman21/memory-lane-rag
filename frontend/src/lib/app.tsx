import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, session } from './api';
import type { User } from './types';

export type View = 'home' | 'ask' | 'timeline' | 'library' | 'settings';
export const VIEWS: View[] = ['home', 'ask', 'timeline', 'library', 'settings'];

export type Theme = 'dusk' | 'dawn' | 'auto';
export type Prefs = { theme: Theme; accent: string; motion: 'full' | 'calm' | 'off'; ambient: boolean; density: 'cozy' | 'compact' };
const DEFAULT_PREFS: Prefs = { theme: 'dusk', accent: '#8b9cff', motion: 'full', ambient: true, density: 'cozy' };

type Toast = { id: number; text: string; tone: 'info' | 'success' | 'error'; action?: { label: string; run: () => void } };

type Ctx = {
  user: User | null;
  setUser: (u: User | null) => void;
  refreshUser: () => Promise<void>;
  signIn: (token: string, u: User) => void;
  signOut: () => Promise<void>;
  view: View;
  go: (v: View, param?: string) => void;
  param: string | null;
  prefs: Prefs;
  setPrefs: (p: Partial<Prefs>) => void;
  toast: (text: string, tone?: Toast['tone'], action?: Toast['action']) => void;
  toasts: Toast[];
  dismiss: (id: number) => void;
  openMemory: (id: string | null) => void;
  memoryId: string | null;
  openDocument: (id: string | null) => void;
  documentId: string | null;
  capture: boolean;
  setCapture: (b: boolean) => void;
  palette: boolean;
  setPalette: (b: boolean) => void;
  dataVersion: number;
  bump: () => void;
  chatsVersion: number;
  bumpChats: () => void;
  askDraft: string | null;
  ask: (q: string) => void;
  consumeAskDraft: () => string | null;
};

const AppCtx = createContext<Ctx | null>(null);

function readHash(): { view: View; param: string | null } {
  const [v, p] = window.location.hash.replace(/^#\/?/, '').split('/');
  return { view: (VIEWS.includes(v as View) ? v : 'home') as View, param: p ? decodeURIComponent(p) : null };
}

function loadPrefs(): Prefs {
  try { return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem('ml.prefs') || '{}') }; } catch { return DEFAULT_PREFS; }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [{ view, param }, setRoute] = useState(readHash);
  const [prefs, setPrefsState] = useState<Prefs>(loadPrefs);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [memoryId, openMemory] = useState<string | null>(null);
  const [documentId, openDocument] = useState<string | null>(null);
  const [capture, setCapture] = useState(false);
  const [palette, setPalette] = useState(false);
  const [dataVersion, setDataVersion] = useState(0);
  const [chatsVersion, setChatsVersion] = useState(0);
  const askDraftRef = useRef<string | null>(null);
  const [askDraft, setAskDraft] = useState<string | null>(null);
  const tid = useRef(0);

  useEffect(() => {
    const on = () => setRoute(readHash());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);

  // theme + motion → <html> attributes
  useEffect(() => {
    const root = document.documentElement;
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const apply = () => root.dataset.theme = prefs.theme === 'auto' ? (mq.matches ? 'dawn' : 'dusk') : prefs.theme;
    apply();
    mq.addEventListener('change', apply);
    root.dataset.motion = prefs.motion;
    root.dataset.density = prefs.density;
    root.style.removeProperty('--accent');
    try { localStorage.setItem('ml.prefs', JSON.stringify(prefs)); } catch { /* ignore */ }
    return () => mq.removeEventListener('change', apply);
  }, [prefs]);

  const setPrefs = useCallback((p: Partial<Prefs>) => {
    setPrefsState(prev => {
      const next = { ...prev, ...p };
      if (session.token) api.updateMe({ preferences: next }).catch(() => undefined);
      return next;
    });
  }, []);

  const toast = useCallback((text: string, tone: Toast['tone'] = 'info', action?: Toast['action']) => {
    const id = ++tid.current;
    setToasts(t => [...t.slice(-3), { id, text, tone, action }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), action ? 7000 : 4200);
  }, []);
  const dismiss = useCallback((id: number) => setToasts(t => t.filter(x => x.id !== id)), []);

  const go = useCallback((v: View, p?: string) => {
    window.location.hash = `/${v}${p ? '/' + encodeURIComponent(p) : ''}`;
    setPalette(false);
  }, []);

  const signIn = useCallback((t: string, u: User) => {
    session.set(t);
    setUser(u);
    const remote = (u.preferences || {}) as Partial<Prefs>;
    if (Object.keys(remote).length) setPrefsState(p => ({ ...p, ...remote }));
  }, []);

  const signOut = useCallback(async () => {
    try { await api.logout(); } catch { /* already gone */ }
    session.set(null);
    setUser(null);
    window.location.hash = '';
  }, []);

  const refreshUser = useCallback(async () => {
    try { setUser(await api.me()); } catch { /* handled by 401 hook */ }
  }, []);

  useEffect(() => {
    session.onUnauthorized(() => { session.set(null); setUser(null); });
  }, []);

  const ask = useCallback((q: string) => {
    askDraftRef.current = q;
    setAskDraft(q);
    window.location.hash = '/ask';
    setPalette(false);
  }, []);
  const consumeAskDraft = useCallback(() => {
    const q = askDraftRef.current;
    askDraftRef.current = null;
    setAskDraft(null);
    return q;
  }, []);

  const value = useMemo<Ctx>(() => ({
    user, setUser, refreshUser, signIn, signOut, view, param, go, prefs, setPrefs, toast, toasts, dismiss,
    openMemory, memoryId, openDocument, documentId, capture, setCapture, palette, setPalette,
    dataVersion, bump: () => setDataVersion(v => v + 1), chatsVersion, bumpChats: () => setChatsVersion(v => v + 1),
    askDraft, ask, consumeAskDraft,
  }), [user, refreshUser, signIn, signOut, view, param, go, prefs, setPrefs, toast, toasts, dismiss, memoryId,
    documentId, capture, palette, dataVersion, chatsVersion, askDraft, ask, consumeAskDraft]);

  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp() {
  const c = useContext(AppCtx);
  if (!c) throw new Error('useApp outside provider');
  return c;
}

/** Fetch helper that re-runs when deps or the global data version change. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const { dataVersion } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(() => {
    setLoading(true);
    fnRef.current().then(d => { setData(d); setError(null); }).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(reload, [dataVersion, ...deps]);
  return { data, error, loading, reload, setData };
}
