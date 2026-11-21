import { AnimatePresence, motion } from 'motion/react';
import { ArrowRight, CalendarHeart, GitBranch, PenLine, Sparkles, Upload } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useApp, useLoad } from '../lib/app';
import { fmtDate, greeting, yearsAgo } from '../lib/format';
import { Card, Empty, Skeleton } from '../components/ui';

const SUGGESTIONS = [
  'How has my thinking changed over the years?',
  'What were my biggest turning points?',
  'What has always stayed the same about me?',
  'How have I been feeling lately?',
];

export function HomeView() {
  const { user, ask, go, setCapture, openMemory } = useApp();
  const { data, loading } = useLoad(() => api.insights());
  const [q, setQ] = useState('');
  const [ph, setPh] = useState(0);
  useEffect(() => { const t = setInterval(() => setPh(p => (p + 1) % SUGGESTIONS.length), 4200); return () => clearInterval(t); }, []);

  const first = user?.display_name.split(' ')[0] ?? '';
  const empty = data && data.counts.memories === 0;
  const past = data ? (data.on_this_day.length ? data.on_this_day : data.highlights).slice(0, 3) : [];

  return (
    <div className="page" style={{ maxWidth: 980 }}>
      <section className="hero-home">
        <motion.h1 className="display h1" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}>
          {greeting()}, {first}.
        </motion.h1>
        <motion.p className="muted" style={{ marginTop: 6 }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}>
          {data && data.span.start
            ? <>{data.counts.memories} memories from {data.counts.documents} entries, {fmtDate(data.span.start, 'year')}–{fmtDate(data.span.end, 'year')}. What would you like to revisit?</>
            : 'What would you like to remember today?'}
        </motion.p>
        <motion.form className="ask-hero" onSubmit={e => { e.preventDefault(); ask(q.trim() || SUGGESTIONS[ph]); }}
          initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>
          <Sparkles size={20} style={{ color: 'var(--accent)', flexShrink: 0 }} />
          <div className="grow" style={{ position: 'relative' }}>
            <input value={q} onChange={e => setQ(e.target.value)} aria-label="Ask your archive" />
            {!q && (
              <AnimatePresence mode="wait">
                <motion.span key={ph} className="ask-ph" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.35 }}>{SUGGESTIONS[ph]}</motion.span>
              </AnimatePresence>
            )}
          </div>
          <button className="btn primary" type="submit">Ask <ArrowRight size={16} /></button>
        </motion.form>
      </section>

      {loading && !data ? (
        <div className="home-grid mt-l"><Skeleton h={260} r={24} /><Skeleton h={260} r={24} /></div>
      ) : empty ? (
        <Card className="mt-l" hover={false}>
          <Empty title="Let’s start your lane" action={
            <div className="row wrap" style={{ justifyContent: 'center' }}>
              <button className="btn primary" onClick={() => setCapture(true)}><PenLine size={16} /> Write a thought</button>
              <button className="btn" onClick={() => go('library')}><Upload size={16} /> Add journals or documents</button>
            </div>}>
            Add your journals, notes or any writing. Memory Lane dates every thought so you can look back on how you’ve changed.
          </Empty>
        </Card>
      ) : data && (
        <div className="home-grid mt-l">
          <Card delay={0.1}>
            <div className="row gap-s mb"><CalendarHeart size={18} style={{ color: 'var(--rose)' }} /><span className="h3">{data.on_this_day.length ? 'On this day' : 'From your past'}</span></div>
            <div className="col">
              {past.map((m, i) => (
                <motion.button key={m.id} className="otd-item" onClick={() => openMemory(m.id)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 + i * 0.08 }}>
                  <span className="otd-year display">{m.event_date_start?.slice(0, 4)}</span>
                  <span className="grow">
                    <span className="tiny faint">{yearsAgo(m.event_date_start)}</span>
                    <span className="serif clamp-3" style={{ display: '-webkit-box', fontSize: 14, lineHeight: 1.45, marginTop: 2 }}>“{m.statement}”</span>
                  </span>
                </motion.button>
              ))}
            </div>
          </Card>

          <Card delay={0.15}>
            <div className="row gap-s mb"><GitBranch size={18} style={{ color: 'var(--accent)' }} /><span className="h3">How you’ve changed</span></div>
            {data.recent_changes.length ? (
              <div className="col gap-s">
                {data.recent_changes.slice(0, 3).map((c, i) => (
                  <motion.button key={c.id} className="turn" onClick={() => ask(`How did my view on ${c.subject} change, and why?`)} initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.25 + i * 0.06 }}>
                    <div className="row between"><b>{c.subject}</b><span className="tiny faint mono">{fmtDate(c.from_date, 'year')} → {fmtDate(c.to_date, 'year')}</span></div>
                    <div className="turn-line">
                      <span className="small clamp-2 faint">{c.earlier.statement}</span>
                      <span className="turn-arrow">→</span>
                      <span className="small clamp-2">{c.later.statement}</span>
                    </div>
                  </motion.button>
                ))}
              </div>
            ) : <div className="faint small">As you add writing from different years, the ways your views shifted will appear here.</div>}
          </Card>
        </div>
      )}
    </div>
  );
}
