import { AnimatePresence, motion } from 'motion/react';
import { BookOpen, ChevronsLeft, ChevronsRight, Home, LogOut, Menu, MessageSquarePlus, Moon, PenLine, Search, Settings, Sparkles, Sun, Trash2, Waypoints, X } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { api } from '../lib/api';
import type { Conversation } from '../lib/types';
import { useApp, type View } from '../lib/app';
import { cx } from '../lib/format';
import { Logo } from './Logo';
import { Avatar, spring } from './ui';

export const NAV: { view: View; label: string; icon: ReactNode; hint: string }[] = [
  { view: 'home', label: 'Today', icon: <Home size={18} />, hint: 'Your overview' },
  { view: 'ask', label: 'Ask', icon: <Sparkles size={18} />, hint: 'Ask your past self anything' },
  { view: 'timeline', label: 'Timeline', icon: <Waypoints size={18} />, hint: 'Every memory in order' },
  { view: 'library', label: 'Library', icon: <BookOpen size={18} />, hint: 'Add & manage your writing' },
  { view: 'settings', label: 'Settings', icon: <Settings size={18} />, hint: 'Profile, theme & data' },
];

export function Sidebar({ collapsed, onToggle, onNavigate }: { collapsed: boolean; onToggle: () => void; onNavigate?: () => void }) {
  const { view, go, user, signOut, setCapture } = useApp();
  return (
    <aside className="sidebar">
      <div className="brand">
        <Logo size={26} />
        <span className="brand-name">Memory Lane</span>
      </div>
      <motion.button className="btn" style={{ marginBottom: 8, justifyContent: collapsed ? 'center' : 'flex-start' }}
        onClick={() => { setCapture(true); onNavigate?.(); }} whileTap={{ scale: 0.97 }} title="Capture a thought (Ctrl+J)">
        <PenLine size={15} /> <span className="nav-label">New thought</span>
      </motion.button>
      <nav className="col" style={{ gap: 2 }}>
        {NAV.map(n => (
          <div key={n.view}>
            <button className={cx('nav-item', view === n.view && 'active')} style={{ width: '100%' }} title={collapsed ? n.label : undefined}
              onClick={() => { go(n.view); onNavigate?.(); }}>
              {view === n.view && <motion.span layoutId="nav-pill" className="pill" transition={spring} />}
              {n.icon}<span className="nav-label">{n.label}</span>
            </button>
          </div>
        ))}
      </nav>
      {!collapsed && <RecentChats onNavigate={onNavigate} />}
      <div className="sidebar-foot">
        {user && (
          <div className="sidebar-card row">
            <Avatar name={user.display_name} color={user.avatar_color} size={26} />
            <div className="grow">
              <div className="truncate" style={{ fontWeight: 600 }}>{user.display_name}</div>
              <div className="tiny faint truncate">{user.memory_count} memories</div>
            </div>
            <button className="btn icon ghost sm" onClick={signOut} title="Sign out"><LogOut size={15} /></button>
          </div>
        )}
        <button className="nav-item hide-mobile" onClick={onToggle} title={collapsed ? 'Expand' : 'Collapse'}>
          {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}<span className="nav-label">Collapse</span>
        </button>
      </div>
    </aside>
  );
}

function RecentChats({ onNavigate }: { onNavigate?: () => void }) {
  const { chatsVersion, view, param, go, user } = useApp();
  const [chats, setChats] = useState<Conversation[]>([]);
  useEffect(() => { api.conversations().then(setChats).catch(() => undefined); }, [chatsVersion, user?.id]);

  const remove = async (c: Conversation) => {
    await api.deleteConversation(c.id);
    setChats(cs => cs.filter(x => x.id !== c.id));
    if (view === 'ask' && param === c.id) go('ask');
  };

  return (
    <div className="recent-chats">
      <div className="row between recent-head">
        <span className="eyebrow">Chats</span>
        <button className="btn icon ghost sm" title="New chat" onClick={() => { go('ask'); onNavigate?.(); }}><MessageSquarePlus size={15} /></button>
      </div>
      <div className="recent-list">
        <AnimatePresence initial={false}>
          {chats.map(c => (
            <motion.div key={c.id} className={cx('recent-item', view === 'ask' && param === c.id && 'on')} layout
              initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, height: 0 }}>
              <button className="grow truncate" onClick={() => { go('ask', c.id); onNavigate?.(); }} title={c.title}>{c.title}</button>
              <button className="recent-del" title="Delete chat" onClick={() => remove(c)}><Trash2 size={13} /></button>
            </motion.div>
          ))}
        </AnimatePresence>
        {chats.length === 0 && <div className="tiny faint" style={{ padding: '6px 12px' }}>Your chats will appear here.</div>}
      </div>
    </div>
  );
}

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { setPalette, prefs, setPrefs, user, go } = useApp();
  const dark = prefs.theme !== 'dawn';
  return (
    <header className="topbar">
      <button className="btn icon ghost show-mobile" onClick={onMenu} aria-label="Menu"><Menu size={18} /></button>
      <button className="search-trigger" onClick={() => setPalette(true)}>
        <Search size={16} /> <span>Search your memories…</span>
        <span className="kbd hide-mobile">{navigator.platform.includes('Mac') ? '⌘' : 'Ctrl'} K</span>
      </button>
      <div className="grow" />
      <motion.button className="btn icon ghost" whileTap={{ rotate: 90, scale: 0.9 }} title="Toggle light / dark"
        onClick={() => setPrefs({ theme: dark ? 'dawn' : 'dusk' })}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.span key={dark ? 'moon' : 'sun'} initial={{ y: -10, opacity: 0, rotate: -40 }} animate={{ y: 0, opacity: 1, rotate: 0 }} exit={{ y: 10, opacity: 0, rotate: 40 }} transition={{ duration: 0.25 }} style={{ display: 'grid' }}>
            {dark ? <Moon size={18} /> : <Sun size={18} />}
          </motion.span>
        </AnimatePresence>
      </motion.button>
      {user && <button onClick={() => go('settings')} title="Settings"><Avatar name={user.display_name} color={user.avatar_color} size={26} /></button>}
    </header>
  );
}

export function Toasts() {
  const { toasts, dismiss } = useApp();
  const tone = { info: 'var(--accent)', success: 'var(--mint)', error: 'var(--rose)' };
  return (
    <div className="toasts" aria-live="polite">
      <AnimatePresence>
        {toasts.map(t => (
          <motion.div key={t.id} className="toast" layout initial={{ opacity: 0, y: 20, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40, scale: 0.95 }} transition={spring}>
            <span className="t-dot" style={{ color: tone[t.tone] }} />
            <span className="grow">{t.text}</span>
            {t.action && <button className="btn sm" onClick={() => { t.action!.run(); dismiss(t.id); }}>{t.action.label}</button>}
            <button className="btn icon ghost sm" onClick={() => dismiss(t.id)} aria-label="Dismiss"><X size={14} /></button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

export function useMobileNav() {
  const [open, setOpen] = useState(false);
  return { open, setOpen };
}
