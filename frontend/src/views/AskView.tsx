import { AnimatePresence, motion } from 'motion/react';
import { ArrowUp, Check, Copy, RotateCcw, Square, TriangleAlert } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../lib/api';
import { useApp } from '../lib/app';
import { cx, fmtDate } from '../lib/format';
import type { AnswerPayload, Citation } from '../lib/types';
import { Orb } from '../components/Logo';
import { Thinking, soft } from '../components/ui';

type Turn = { id: string; role: 'user' | 'assistant'; content: string; payload?: Partial<AnswerPayload>; streaming?: boolean; error?: string; feedback?: number };

const STARTERS = [
  { t: 'How has my thinking changed over the years?', k: 'Change' },
  { t: 'What were the biggest turning points in my life?', k: 'Turning points' },
  { t: 'What has stayed constant about me?', k: 'Patterns' },
  { t: 'How have I been feeling lately?', k: 'Feelings' },
]

function withCiteLinks(md: string) {
  return md.replace(/\[(\d{1,2})\](?!\()/g, '[$1](#cite-$1)');
}

function Answer({ text, citations, streaming, hot, setHot }: { text: string; citations: Citation[]; streaming?: boolean; hot: number | null; setHot: (n: number | null) => void }) {
  const { openMemory } = useApp();
  const md = useMemo(() => withCiteLinks(text), [text]);
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        a: ({ href, children }) => {
          if (href?.startsWith('#cite-')) {
            const n = Number(href.slice(6));
            const c = citations.find(x => x.index === n);
            return (
              <button className={cx('cite', hot === n && 'hot')} onMouseEnter={() => setHot(n)} onMouseLeave={() => setHot(null)}
                onClick={() => c && openMemory(c.memory_id)} title={c ? `${fmtDate(c.date, 'month')} · ${c.statement}` : undefined}>{n}</button>
            );
          }
          return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
        },
      }}>{md}</ReactMarkdown>
      {streaming && <span className="caret" />}
    </div>
  );
}

function Sources({ citations, used, hot, setHot }: { citations: Citation[]; used: number[]; hot: number | null; setHot: (n: number | null) => void }) {
  const { openMemory } = useApp();
  const [open, setOpen] = useState(false);
  const shown = used.length ? citations.filter(c => used.includes(c.index)) : citations;
  if (!shown.length) return null;
  return (
    <div className="inline-sources">
      <button className="chip" onClick={() => setOpen(o => !o)}>{open ? '▾' : '▸'} {shown.length} source{shown.length > 1 ? 's' : ''}</button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div className="grid g2 sources-grid" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={soft}>
            {shown.map(c => (
              <button key={c.index} className={cx('evi-card', hot === c.index && 'hot')} onMouseEnter={() => setHot(c.index)} onMouseLeave={() => setHot(null)} onClick={() => openMemory(c.memory_id)}>
                <div className="row between"><span className="cite" style={{ pointerEvents: 'none' }}>{c.index}</span><span className="tiny faint mono">{fmtDate(c.date, 'month')}</span></div>
                <div className="small clamp-3" style={{ display: '-webkit-box', marginTop: 8 }}>{c.statement}</div>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function AskView() {
  const { param, go, consumeAskDraft, askDraft, toast, bumpChats } = useApp();
  const [convId, setConvId] = useState<string | null>(param);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [hot, setHot] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stick = useRef(true);

  // load a conversation from the URL
  useEffect(() => {
    if (param === convId && turns.length) return;
    setConvId(param);
    if (!param) { setTurns([]); return; }
    api.conversation(param).then(c => setTurns(c.messages.map(m => ({ id: m.id, role: m.role, content: m.content, payload: m.payload, feedback: m.feedback }))))
      .catch(() => { toast('That conversation no longer exists', 'error'); go('ask'); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [param]);

  const scrollDown = useCallback((force = false) => {
    const el = scrollRef.current;
    if (el && (force || stick.current)) el.scrollTo({ top: el.scrollHeight, behavior: force ? 'smooth' : 'auto' });
  }, []);

  const send = useCallback(async (text: string, replaceLast = false) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput('');
    setBusy(true);
    stick.current = true;
    const uid = `u${Date.now()}`, aid = `a${Date.now()}`;
    setTurns(t => [...(replaceLast ? t.slice(0, -2) : t), { id: uid, role: 'user', content: q }, { id: aid, role: 'assistant', content: '', streaming: true }]);
    setTimeout(() => scrollDown(true), 50);
    const ac = new AbortController();
    abortRef.current = ac;
    const patch = (fn: (t: Turn) => Turn) => setTurns(ts => ts.map(t => t.id === aid ? fn(t) : t));
    let newConv: string | null = null;
    await api.chatStream({
      query: q, conversation_id: convId,
    }, {
      onConversation: id => { newConv = id; },
      onMeta: m => patch(t => ({ ...t, payload: { ...t.payload, citations: m.citations, intent: m.intent, provider: m.provider, changes: m.changes } })),
      onToken: tok => { patch(t => ({ ...t, content: t.content + tok })); requestAnimationFrame(() => scrollDown()); },
      onDone: p => { patch(t => ({ ...t, id: p.message_id || t.id, content: p.answer, payload: p, streaming: false })); },
      onError: msg => patch(t => ({ ...t, streaming: false, error: msg })),
    }, ac.signal);
    patch(t => ({ ...t, streaming: false }));
    setBusy(false);
    abortRef.current = null;
    if (newConv && newConv !== convId) {
      setConvId(newConv);
      go('ask', newConv);
    }
    bumpChats();
    setTimeout(() => inputRef.current?.focus(), 30);
  }, [busy, convId, scrollDown, go, bumpChats]);

  // a question handed over from elsewhere (home, palette, drawers)
  useEffect(() => {
    if (!askDraft) return;
    const q = consumeAskDraft();
    if (q) {
      setConvId(null); setTurns([]);
      window.history.replaceState(null, '', '#/ask');
      setTimeout(() => send(q), 60);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askDraft]);

  const stop = () => abortRef.current?.abort();
  return (
    <div className="ask-layout">
      <section className="chat">
        <div className="chat-scroll" ref={scrollRef} onScroll={e => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120; }}>
          {turns.length === 0 ? (
            <div className="chat-empty">
              <Orb size={44} />
              <motion.h2 className="display h1" style={{ textAlign: 'center' }} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={soft}>
                What would you like to know?
              </motion.h2>
              <p className="muted small" style={{ textAlign: 'center', maxWidth: 460 }}>Answers come from your own entries, with the source for every line.</p>
              <div className="grid g2 starters">
                {STARTERS.map((s, i) => (
                  <motion.button key={s.t} className="card spot hover starter" onClick={() => send(s.t)}
                    initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ...soft, delay: 0.15 + i * 0.06 }}>
                    <span className="eyebrow">{s.k}</span><span className="serif" style={{ fontSize: 14, lineHeight: 1.35 }}>{s.t}</span>
                  </motion.button>
                ))}
              </div>
            </div>
          ) : (
            <div className="turns">
              {turns.map((t, idx) => t.role === 'user' ? (
                <motion.div key={t.id} className="turn-user" initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={soft}>{t.content}</motion.div>
              ) : (
                <motion.div key={t.id} className="turn-ai" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={soft}>
                  {t.error ? (
                    <div className="form-error row"><TriangleAlert size={16} /> {t.error}<button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => send(turns[idx - 1].content, true)}><RotateCcw size={13} /> Retry</button></div>
                  ) : !t.content && t.streaming ? (
                    <Thinking label={t.payload?.citations ? `Reading ${t.payload.citations.length} memories…` : 'Searching your lane…'} />
                  ) : (
                    <Answer text={t.content} citations={t.payload?.citations || []} streaming={t.streaming} hot={hot} setHot={setHot} />
                  )}
                  {!t.streaming && !t.error && <Sources citations={t.payload?.citations || []} used={t.payload?.used_citations || []} hot={hot} setHot={setHot} />}
                  {!t.streaming && (t.payload?.uncertainty_notes?.length ?? 0) > 0 && (
                    <div className="note-soft">{t.payload!.uncertainty_notes!.map(n => <div key={n}>◌ {n}</div>)}</div>
                  )}
                  {!t.streaming && !t.error && t.content && (
                    <div className="row wrap gap-s mt">
                      <CopyButton text={t.content} />
                    </div>
                  )}
                  {!t.streaming && idx === turns.length - 1 && (t.payload?.follow_ups?.length ?? 0) > 0 && (
                    <div className="row wrap gap-s mt">
                      {t.payload!.follow_ups!.map((f, i) => (
                        <motion.button key={f} className="chip followup" onClick={() => send(f)} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.07 }}>↳ {f}</motion.button>
                      ))}
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          )}
        </div>

        <div className="composer-wrap">
          <form className={cx('composer', busy && 'busy')} onSubmit={e => { e.preventDefault(); send(input); }}>
            <textarea ref={inputRef} rows={1} value={input} placeholder="Ask about any moment, belief, goal or feeling…" autoFocus
              onChange={e => { setInput(e.target.value); e.target.style.height = 'auto'; e.target.style.height = `${Math.min(180, e.target.scrollHeight)}px`; }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }} />
            {busy ? (
              <motion.button type="button" className="btn icon" onClick={stop} title="Stop" initial={{ scale: 0.8 }} animate={{ scale: 1 }}><Square size={15} fill="currentColor" /></motion.button>
            ) : (
              <motion.button type="submit" className="btn icon primary" disabled={!input.trim()} whileTap={{ scale: 0.9 }} title="Send"><ArrowUp size={18} /></motion.button>
            )}
          </form>
          <div className="tiny faint" style={{ textAlign: 'center', marginTop: 8 }}>Answers come only from your own writing. Click a number to see the source.</div>
        </div>
      </section>

    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button className="btn ghost sm" onClick={() => { navigator.clipboard?.writeText(text.replace(/\[(\d+)\]/g, '')).then(() => { setOk(true); setTimeout(() => setOk(false), 1600); }); }}>
      {ok ? <><Check size={13} /> Copied</> : <><Copy size={13} /> Copy</>}
    </button>
  );
}
