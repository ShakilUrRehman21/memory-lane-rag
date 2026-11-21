import { AnimatePresence, motion } from 'motion/react';
import { ArrowRight, CalendarDays, CornerDownLeft, FileText, Moon, PenLine, Search, Sparkles, Sun } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api } from '../lib/api';
import { useApp } from '../lib/app';
import { TYPE_META, cx, fmtDate } from '../lib/format';
import type { Doc, Memory, MemoryType } from '../lib/types';
import { NAV } from './Shell';
import { Overlay, Spinner, TypeBadge } from './ui';

type Item = { id: string; group: string; label: ReactNode; sub?: ReactNode; icon: ReactNode; run: () => void };

export function CommandPalette() {
  const { palette, setPalette, go, openMemory, openDocument, ask, setCapture, prefs, setPrefs } = useApp();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const [res, setRes] = useState<{ memories: Memory[]; documents: Doc[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (palette) { setQ(''); setRes(null); setSel(0); } }, [palette]);
  useEffect(() => {
    if (!q.trim()) { setRes(null); return; }
    setLoading(true);
    const t = setTimeout(() => api.search(q).then(setRes).catch(() => setRes(null)).finally(() => setLoading(false)), 180);
    return () => clearTimeout(t);
  }, [q]);

  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    const ql = q.trim().toLowerCase();
    if (ql) out.push({ id: 'ask', group: 'Ask', icon: <Sparkles size={16} />, label: <>Ask Memory Lane: <b>“{q}”</b></>, run: () => ask(q) });
    res?.memories.forEach(m => out.push({ id: m.id, group: 'Memories', icon: <span style={{ color: TYPE_META[m.memory_type].color }}>{TYPE_META[m.memory_type].glyph}</span>,
      label: <span className="clamp-2">{m.statement}</span>, sub: `${fmtDate(m.event_date_start, 'month')} · ${m.document_title ?? ''}`,
      run: () => { setPalette(false); openMemory(m.id); } }));
    res?.documents.slice(0, 5).forEach(d => out.push({ id: d.id, group: 'Documents', icon: <FileText size={16} />, label: d.title,
      sub: fmtDate(d.document_date), run: () => { setPalette(false); openDocument(d.id); } }));
    const actions: Item[] = [
      { id: 'capture', group: 'Actions', icon: <PenLine size={16} />, label: 'Capture a thought', sub: 'Ctrl+J', run: () => { setPalette(false); setCapture(true); } },
      { id: 'theme', group: 'Actions', icon: prefs.theme === 'dawn' ? <Moon size={16} /> : <Sun size={16} />, label: `Switch to ${prefs.theme === 'dawn' ? 'Dusk' : 'Dawn'} theme`, run: () => setPrefs({ theme: prefs.theme === 'dawn' ? 'dusk' : 'dawn' }) },
      ...NAV.map(n => ({ id: `go-${n.view}`, group: 'Go to', icon: n.icon, label: n.label, sub: n.hint, run: () => go(n.view) })),
    ];
    out.push(...actions.filter(a => !ql || String(a.label).toLowerCase().includes(ql) || a.sub?.toString().toLowerCase().includes(ql)));
    return out;
  }, [q, res, ask, setPalette, openMemory, openDocument, setCapture, prefs.theme, setPrefs, go]);

  useEffect(() => { setSel(0); }, [items.length]);
  useEffect(() => { listRef.current?.querySelector('.palette-item.on')?.scrollIntoView({ block: 'nearest' }); }, [sel]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(items.length - 1, s + 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(0, s - 1)); }
    if (e.key === 'Enter') { e.preventDefault(); items[sel]?.run(); }
  };

  let lastGroup = '';
  return (
    <Overlay open={palette} onClose={() => setPalette(false)} className="palette" label="Command palette">
      <div className="palette-input">
        {loading ? <Spinner size={18} /> : <Search size={18} className="faint" />}
        <input autoFocus value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey} placeholder="Search your life, or ask a question…" />
        <span className="kbd">esc</span>
      </div>
      <div className="palette-list" ref={listRef}>
        {items.map((it, i) => {
          const head = it.group !== lastGroup ? <div className="palette-group eyebrow" key={`g-${it.group}`}>{it.group}</div> : null;
          lastGroup = it.group;
          return (
            <div key={it.id + i}>
              {head}
              <button className={cx('palette-item', i === sel && 'on')} onMouseEnter={() => setSel(i)} onClick={it.run}>
                <span style={{ width: 20, display: 'grid', placeItems: 'center' }}>{it.icon}</span>
                <span className="grow"><span style={{ display: 'block' }}>{it.label}</span>{it.sub && <span className="tiny faint">{it.sub}</span>}</span>
                {i === sel && <CornerDownLeft size={14} className="faint" />}
              </button>
            </div>
          );
        })}
      </div>
    </Overlay>
  );
}

const PROMPTS = [
  'What is on your mind right now?', 'What did you decide today?', 'What do you believe that you didn’t a year ago?',
  'What are you grateful for?', 'What are you hoping for next?', 'What surprised you this week?',
];

export function CaptureModal() {
  const { capture, setCapture, toast, bump, refreshUser, openMemory } = useApp();
  const [text, setText] = useState('');
  const [type, setType] = useState<MemoryType | 'auto'>('auto');
  const [date, setDate] = useState('');
  const [busy, setBusy] = useState(false);
  const prompt = useMemo(() => PROMPTS[Math.floor(Math.random() * PROMPTS.length)], [capture]);

  useEffect(() => { if (capture) { setText(''); setType('auto'); setDate(''); } }, [capture]);

  const save = async () => {
    if (text.trim().length < 3) return;
    setBusy(true);
    try {
      const m = await api.capture({ statement: text.trim(), memory_type: type === 'auto' ? undefined : type, event_date: date || undefined });
      setCapture(false);
      bump(); refreshUser();
      toast(`Saved as a ${TYPE_META[m.memory_type].label.toLowerCase()} for ${fmtDate(m.event_date_start)}`, 'success', { label: 'Open', run: () => openMemory(m.id) });
    } catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(false); }
  };

  return (
    <Overlay open={capture} onClose={() => setCapture(false)} label="Capture a thought">
      <div style={{ padding: 26 }}>
        <div className="eyebrow">Capture</div>
        <AnimatePresence mode="wait">
          <motion.div key={prompt} className="display h2" style={{ margin: '6px 0 16px' }} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>{prompt}</motion.div>
        </AnimatePresence>
        <textarea className="textarea" autoFocus value={text} onChange={e => setText(e.target.value)} placeholder="Write freely. One honest sentence is enough."
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save(); }} style={{ minHeight: 120, fontSize: 14 }} />
        <div className="row between mt" style={{ flexWrap: 'wrap', gap: 12, marginTop: 16 }}>
          <label className="row small faint" style={{ gap: 8 }}>
            <CalendarDays size={15} /> When did this happen?
            <input type="date" className="input" style={{ width: 170, padding: '7px 10px' }} value={date} onChange={e => setDate(e.target.value)} />
          </label>
          <div className="row">
            <span className="tiny faint hide-mobile"><span className="kbd">Ctrl</span> + <span className="kbd">Enter</span></span>
            <button className="btn primary" disabled={busy || text.trim().length < 3} onClick={save}>{busy ? <Spinner /> : <>Save memory <ArrowRight size={16} /></>}</button>
          </div>
        </div>
      </div>
    </Overlay>
  );
}

export { TypeBadge };
