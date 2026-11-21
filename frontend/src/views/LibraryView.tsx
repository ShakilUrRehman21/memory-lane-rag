import { AnimatePresence, motion } from 'motion/react';
import { CheckCircle2, CircleAlert, Copy, FileText, NotebookPen, Search, Star, UploadCloud, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { useApp, useLoad } from '../lib/app';
import { bytes, cx, fmtDate } from '../lib/format';
import type { UploadResult } from '../lib/types';
import { Card, Empty, Skeleton, Spinner, soft } from '../components/ui';

const ACCEPT = '.txt,.md,.markdown,.pdf,.docx,.html,.htm,.json,.csv,.rtf,.log';

export function LibraryView() {
  const { openDocument, toast, bump, refreshUser } = useApp();
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [tag, setTag] = useState<string | null>(null);
  const layout = 'grid' as 'grid' | 'list';
  const [noteOpen, setNoteOpen] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDq(q), 250); return () => clearTimeout(t); }, [q]);

  const docs = useLoad(() => api.documents({ q: dq || undefined, tag: tag || undefined }), [dq, tag]);
  const tags = useLoad(() => api.tags());


  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="display h1">Library</h1>
          <p>Add journals, notes or any writing. Memory Lane reads and dates each one for you.</p>
        </div>
        <button className="btn" onClick={() => setNoteOpen(o => !o)}><NotebookPen size={16} /> Write a note</button>
      </div>

      <AnimatePresence>{noteOpen && <NoteComposer onDone={() => { setNoteOpen(false); bump(); refreshUser(); }} />}</AnimatePresence>
      <Dropzone onDone={() => { bump(); refreshUser(); }} toast={toast} />

      <div className="row between wrap gap-s mt-l mb">
        <div className="h3">Your documents {docs.data && <span className="faint">· {docs.data.length}</span>}</div>
        <div className="input-icon" style={{ width: 260 }}><Search size={15} /><input className="input" placeholder="Search…" value={q} onChange={e => setQ(e.target.value)} /></div>
      </div>

      {(
        <>
          {tags.data && Object.keys(tags.data).length > 0 && (
            <div className="row wrap gap-s mb">
              {Object.entries(tags.data).map(([t, n]) => <button key={t} className={cx('chip', tag === t && 'on')} onClick={() => setTag(tag === t ? null : t)}># {t} <span className="faint">{String(n)}</span></button>)}
            </div>
          )}
          {docs.loading && !docs.data ? <div className="grid g3">{[0, 1, 2, 3, 4, 5].map(i => <Skeleton key={i} h={170} r={24} />)}</div>
            : !docs.data?.length ? <Empty title={dq || tag ? 'No matches' : 'Your library is empty'}>{dq || tag ? 'Try a different search or filter.' : 'Drop files above, or write your first note.'}</Empty>
              : (
                <motion.div layout className={layout === 'grid' ? 'grid g3' : 'col gap-s'}>
                  <AnimatePresence>
                    {docs.data.map((d, i) => layout === 'grid' ? (
                      <motion.div key={d.id} layout initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }} transition={{ ...soft, delay: Math.min(i, 12) * 0.03 }}>
                        <Card className="doc-card" onClick={() => openDocument(d.id)} hover>
                          <div className="row between">
                            <span className={cx('doc-kind', d.source_type)}>{d.source_type === 'capsule' ? 'Thought' : d.source_type === 'note' ? 'Note' : d.file_type.toUpperCase()}</span>
                          </div>
                          <div className="h3 clamp-2" style={{ display: '-webkit-box', marginTop: 12 }}>{d.title}</div>
                          <div className="small faint clamp-3" style={{ display: '-webkit-box', marginTop: 6 }}>{d.excerpt}</div>
                          <div className="row between tiny faint" style={{ marginTop: 'auto', paddingTop: 14 }}>
                            <span className="mono">{fmtDate(d.document_date, 'month')}</span>
                            <span>{d.memory_count} memories</span>
                          </div>
                        </Card>
                      </motion.div>
                    ) : (
                      <motion.button key={d.id} layout className="doc-row" onClick={() => openDocument(d.id)} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 15) * 0.02 }}>
                        <FileText size={16} className="faint" />
                        <span className="mono tiny faint" style={{ width: 90 }}>{fmtDate(d.document_date, 'month')}</span>
                        <span className="grow truncate" style={{ fontWeight: 600 }}>{d.title}</span>
                        <span className="row gap-s hide-mobile">{d.tags.slice(0, 2).map(t => <span key={t} className="chip tiny">#{t}</span>)}</span>
                        <span className="tiny faint hide-mobile" style={{ width: 90, textAlign: 'right' }}>{d.memory_count} memories</span>
                        <span className="tiny faint hide-mobile" style={{ width: 70, textAlign: 'right' }}>{bytes(d.file_size)}</span>
                        {d.favorite && <Star size={14} fill="var(--amber)" color="var(--amber)" />}
                      </motion.button>
                    ))}
                  </AnimatePresence>
                </motion.div>
              )}
        </>
      )}
    </div>
  );
}

function Dropzone({ onDone, toast }: { onDone: () => void; toast: ReturnType<typeof useApp>['toast'] }) {
  const [over, setOver] = useState(false);
  const [pct, setPct] = useState<number | null>(null);
  const [results, setResults] = useState<UploadResult[]>([]);
  const date = '';
  const tags = '';
  const input = useRef<HTMLInputElement>(null);

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setPct(0); setResults([]);
    try {
      const r = await api.upload(files, { document_date: date || undefined, tags: tags || undefined }, setPct);
      setResults(r.results);
      const ok = r.results.filter(x => x.status === 'ok').length;
      if (ok) { toast(`${ok} document${ok > 1 ? 's' : ''} woven into your lane`, 'success'); onDone(); }
    } catch (e) { toast((e as Error).message, 'error'); } finally { setPct(null); }
  };

  useEffect(() => {
    const onDrag = (e: DragEvent) => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); setOver(true); } };
    const onLeave = (e: DragEvent) => { if (!e.relatedTarget) setOver(false); };
    const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); upload(Array.from(e.dataTransfer?.files || [])); };
    window.addEventListener('dragover', onDrag); window.addEventListener('dragleave', onLeave); window.addEventListener('drop', onDrop);
    return () => { window.removeEventListener('dragover', onDrag); window.removeEventListener('dragleave', onLeave); window.removeEventListener('drop', onDrop); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, tags]);

  return (
    <>
      <motion.div className={cx('dropzone', over && 'over')} onClick={() => input.current?.click()} whileHover={{ scale: 1.005 }}>
        <input ref={input} type="file" multiple accept={ACCEPT} hidden onChange={e => { upload(Array.from(e.target.files || [])); e.target.value = ''; }} />
        <motion.div className="drop-icon" animate={over ? { y: -6, scale: 1.1 } : { y: 0, scale: 1 }}><UploadCloud size={30} /></motion.div>
        <div className="grow">
          <div className="h3">{pct !== null ? `Reading your files… ${pct}%` : over ? 'Let go to add them' : 'Drop files anywhere, or click to browse'}</div>
          <div className="small faint">PDF, Word, text, Markdown and more. Dates are detected automatically.</div>
          {pct !== null && <div className="progress mt"><motion.div animate={{ width: `${pct}%` }} /></div>}
        </div>
      </motion.div>
      <AnimatePresence>
        {results.length > 0 && (
          <motion.div className="col gap-s mt" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
            {results.map(r => (
              <div key={r.file} className="upload-result">
                {r.status === 'ok' ? <CheckCircle2 size={16} style={{ color: 'var(--mint)' }} /> : r.status === 'duplicate' ? <Copy size={16} style={{ color: 'var(--amber)' }} /> : <CircleAlert size={16} style={{ color: 'var(--rose)' }} />}
                <span className="grow truncate">{r.file}</span>
                <span className="tiny faint">{r.status === 'ok' ? `${r.document?.memory_count} memories · dated ${fmtDate(r.document?.document_date)}` : r.detail}</span>
              </div>
            ))}
            <button className="btn ghost sm" style={{ alignSelf: 'flex-end' }} onClick={() => setResults([])}><X size={13} /> Clear</button>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>{over && <motion.div className="drop-veil" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><div className="display h1">Drop to remember</div></motion.div>}</AnimatePresence>
    </>
  );
}

function NoteComposer({ onDone }: { onDone: () => void }) {
  const { toast } = useApp();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const tags = 'journal';
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const d = await api.createNote({ title, content: body, document_date: date, tags: tags.split(',').map(t => t.trim()).filter(Boolean) });
      toast(`Saved “${d.title}” · ${d.memory_count} memories found`, 'success');
      onDone();
    } catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(false); }
  };
  const words = body.trim() ? body.trim().split(/\s+/).length : 0;
  return (
    <motion.div className="glass note-composer" initial={{ opacity: 0, height: 0, marginBottom: 0 }} animate={{ opacity: 1, height: 'auto', marginBottom: 18 }} exit={{ opacity: 0, height: 0, marginBottom: 0 }} transition={soft}>
      <div style={{ padding: 22 }} className="col gap-l">
        <input className="input display" style={{ fontSize: 18, fontWeight: 600, background: 'none', border: 'none', padding: 0 }} placeholder="Title (optional)" value={title} onChange={e => setTitle(e.target.value)} autoFocus />
        <textarea className="textarea" style={{ minHeight: 200, fontSize: 14 }} placeholder="Write as much or as little as you like…" value={body} onChange={e => setBody(e.target.value)} />
        <div className="row wrap gap-s">
          <input type="date" className="input" style={{ width: 170 }} value={date} onChange={e => setDate(e.target.value)} />
          <span className="tiny faint grow">{words} words</span>
          <button className="btn primary" disabled={busy || !body.trim()} onClick={save}>{busy ? <Spinner /> : 'Save to my lane'}</button>
        </div>
      </div>
    </motion.div>
  );
}
