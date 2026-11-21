import { AnimatePresence, motion } from 'motion/react';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { api, session } from './lib/api';
import { AppProvider, useApp, type View } from './lib/app';
import { cx } from './lib/format';
import { Ambient } from './components/Ambient';
import { DocumentDrawer, MemoryDrawer } from './components/Drawers';
import { Logo } from './components/Logo';
import { CaptureModal, CommandPalette } from './components/Overlays';
import { Sidebar, Toasts, Topbar } from './components/Shell';
import { AuthView } from './views/AuthView';
import { HomeView } from './views/HomeView';

const lazyView = (load: () => Promise<Record<string, () => React.ReactElement>>, name: string) =>
  lazy(() => load().then(m => ({ default: m[name] })));
const AskView = lazyView(() => import('./views/AskView'), 'AskView');
const TimelineView = lazyView(() => import('./views/TimelineView'), 'TimelineView');
const LibraryView = lazyView(() => import('./views/LibraryView'), 'LibraryView');
const SettingsView = lazyView(() => import('./views/SettingsView'), 'SettingsView');

const VIEWS: Record<View, React.ComponentType> = {
  home: HomeView, ask: AskView, timeline: TimelineView, library: LibraryView, settings: SettingsView,
};
const JUMP: Record<string, View> = { h: 'home', a: 'ask', t: 'timeline', l: 'library', s: 'settings' };

function Shell() {
  const { view, go, setPalette, setCapture, palette, capture } = useApp();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('ml.collapsed') === '1');
  const [mobileOpen, setMobileOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const pendingG = useRef(0);

  useEffect(() => { localStorage.setItem('ml.collapsed', collapsed ? '1' : '0'); }, [collapsed]);
  useEffect(() => { mainRef.current?.scrollTo({ top: 0 }); setMobileOpen(false); }, [view]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = /input|textarea|select/i.test((e.target as HTMLElement)?.tagName) || (e.target as HTMLElement)?.isContentEditable;
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(!palette); return; }
      if (mod && e.key.toLowerCase() === 'j') { e.preventDefault(); setCapture(!capture); return; }
      if (typing || mod || e.altKey) return;
      if (e.key === '/') { e.preventDefault(); setPalette(true); return; }
      if (e.key === 'g') { pendingG.current = Date.now(); return; }
      if (Date.now() - pendingG.current < 900 && JUMP[e.key]) { go(JUMP[e.key]); pendingG.current = 0; }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [palette, capture, setPalette, setCapture, go]);

  const ViewComp = VIEWS[view];
  return (
    <div className={cx('shell', collapsed && 'collapsed', mobileOpen && 'mobile-open')}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} onNavigate={() => setMobileOpen(false)} />
      {mobileOpen && <div className="overlay show-mobile" style={{ zIndex: 40 }} onClick={() => setMobileOpen(false)} />}
      <main className={cx('main', view === 'ask' && 'main-fixed')} ref={mainRef}>
        <Topbar onMenu={() => setMobileOpen(true)} />
        <AnimatePresence mode="wait">
          <motion.div key={view} className="view-wrap" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}>
            <Suspense fallback={<div className="page"><div className="skel" style={{ height: 120, borderRadius: 24, marginTop: 30 }} /></div>}><ViewComp /></Suspense>
          </motion.div>
        </AnimatePresence>
      </main>
      <CommandPalette />
      <CaptureModal />
      <MemoryDrawer />
      <DocumentDrawer />
    </div>
  );
}

function Root() {
  const { user, signIn } = useApp();
  const [booting, setBooting] = useState(!!session.token);

  useEffect(() => {
    if (!session.token) return;
    api.me().then(u => signIn(session.token!, u)).catch(() => session.set(null)).finally(() => setBooting(false));
  }, [signIn]);

  return (
    <>
      <Ambient />
      <AnimatePresence mode="wait">
        {booting ? (
          <motion.div key="boot" className="boot" exit={{ opacity: 0, scale: 1.04 }} transition={{ duration: 0.5 }}>
            <Logo size={36} /><div className="brand-name">Memory Lane</div>
          </motion.div>
        ) : user ? (
          <motion.div key="app" style={{ height: '100%' }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}><Shell /></motion.div>
        ) : (
          <motion.div key="auth" style={{ height: '100%' }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.5 }}><AuthView /></motion.div>
        )}
      </AnimatePresence>
      <Toasts />
    </>
  );
}

export default function App() {
  return <AppProvider><Root /></AppProvider>;
}
