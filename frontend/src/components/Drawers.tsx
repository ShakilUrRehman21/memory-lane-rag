import { motion } from 'motion/react';
import { Check, Download, Edit3, FileText, Pin, PinOff, Sparkles, Trash2, X } from 'lucide-react';
import { useEffect, useState, type CSSProperties } from 'react';
import { api } from '../lib/api';
import { useApp, useLoad } from '../lib/app';
import { MEMORY_TYPES, TYPE_META, cx, fmtDate, yearsAgo } from '../lib/format';
import type { MemoryType } from '../lib/types';
import { CloseButton, MemoryRow, Overlay, Skeleton, Spinner, TypeBadge } from './ui';

function highlight(passage: string, statement: string) {
  const i = passage.indexOf(statement.slice(0, 40));
  if (i < 0) return <>{passage}</>;
  const end = Math.min(passage.length, i + statement.length);
  return <>{passage.slice(0, i)}<mark className="hl">{passage.slice(i, end)}</mark>{passage.slice(end)}</>;
}

export function MemoryDrawer() {
  const { memoryId, openMemory, openDocument, toast, bump, ask, refreshUser } = useApp();
  const { data, loading, setData } = useLoad(() => memoryId ? api.memory(memoryId) : Promise.resolve(null), [memoryId]);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [date, setDate] = useState('');
  const m = data?.memory;

  useEffect(() => { setEditing(false); }, [memoryId]);

  const patch = async (b: Parameters<typeof api.updateMemory>[1], msg?: string) => {
    if (!m) return;
    try {
      const updated = await api.updateMemory(m.id, b);
      setData(d => d ? { ...d, memory: updated } : d);
      bump();
      if (msg) toast(msg, 'success');
    } catch (e) { toast((e as Error).message, 'error'); }
  };

  const remove = async () => {
    if (!m || !confirm('Delete this memory? The original document stays.')) return;
    await api.deleteMemory(m.id);
    openMemory(null); bump(); refreshUser();
    toast('Memory deleted', 'info');
  };

  return (
    <Overlay open={!!memoryId} onClose={() => openMemory(null)} kind="drawer" label="Memory">
      <div className="drawer-head">
        <div className="eyebrow">Memory</div>
        <div className="row gap-s">
          {m && <button className="btn icon ghost sm" title={m.pinned ? 'Unpin' : 'Pin'} onClick={() => patch({ pinned: !m.pinned }, m.pinned ? 'Unpinned' : 'Pinned to your highlights')}>{m.pinned ? <PinOff size={16} /> : <Pin size={16} />}</button>}
          {m && <button className="btn icon ghost sm" title="Edit" onClick={() => { setDraft(m.statement); setDate(m.event_date_start?.slice(0, 10) || ''); setEditing(true); }}><Edit3 size={16} /></button>}
          {m && <button className="btn icon ghost sm danger" title="Delete" onClick={remove}><Trash2 size={16} /></button>}
          <CloseButton onClick={() => openMemory(null)} />
        </div>
      </div>
      <div style={{ padding: '4px 24px 28px' }}>
        {loading || !m ? <div className="col"><Skeleton h={28} w="40%" /><Skeleton h={90} /><Skeleton h={160} /></div> : (
          <motion.div key={m.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <div className="row wrap gap-s mb">
              <TypeBadge type={m.memory_type} />
              <span className="chip mono">{fmtDate(m.event_date_start, m.date_granularity === 'year' ? 'year' : m.date_granularity === 'month' ? 'month' : 'long')}</span>
              <span className="tiny faint">{yearsAgo(m.event_date_start)}</span>
              {m.pinned && <span className="chip on"><Pin size={12} /> Pinned</span>}
            </div>
            {editing ? (
              <div className="col">
                <textarea className="textarea" value={draft} onChange={e => setDraft(e.target.value)} autoFocus />
                <div className="row wrap gap-s">
                  {MEMORY_TYPES.map(t => <button key={t} className={cx('chip', m.memory_type === t && 'on')} onClick={() => patch({ memory_type: t as MemoryType })}>{TYPE_META[t].glyph} {TYPE_META[t].label}</button>)}
                </div>
                <div className="row">
                  <input type="date" className="input" style={{ width: 180 }} value={date} onChange={e => setDate(e.target.value)} />
                  <div className="grow" />
                  <button className="btn ghost" onClick={() => setEditing(false)}><X size={15} /> Cancel</button>
                  <button className="btn primary" onClick={async () => { await patch({ statement: draft, event_date: date || undefined }, 'Memory updated'); setEditing(false); }}><Check size={15} /> Save</button>
                </div>
              </div>
            ) : (
              <blockquote className="display" style={{ fontSize: 18, lineHeight: 1.45, fontWeight: 500 }}>“{m.statement}”</blockquote>
            )}
            {(m.entities.length > 0 || m.topics.length > 0) && (
              <div className="row wrap gap-s mt-l">
                {m.entities.map(e => <button key={e} className="chip" onClick={() => { openMemory(null); ask(`How has my view of ${e} evolved?`); }}>{e}</button>)}
              </div>
            )}
            <button className="btn mt-l" style={{ width: '100%' }} onClick={() => { openMemory(null); ask(`Tell me more about this: "${m.statement}"`); }}>
              <Sparkles size={16} /> Ask about this moment
            </button>
            {data?.context && data.context.trim() !== m.statement.trim() && (
              <div className="mt-l">
                <div className="eyebrow mb-s">In context</div>
                <div className="inset" style={{ padding: 16, lineHeight: 1.7, color: 'var(--ink-2)' }}>{highlight(data.context, m.statement)}</div>
              </div>
            )}
            <button className="row mt small" style={{ color: 'var(--accent)' }} onClick={() => { openMemory(null); openDocument(m.document_id); }}>
              <FileText size={14} /> From “{m.document_title}”
            </button>
            {data && data.similar.length > 0 && (
              <div className="mt-l">
                <div className="eyebrow mb-s">Related memories</div>
                <div className="col gap-s">{data.similar.slice(0, 3).map((s, i) => <MemoryRow key={s.memory.id} m={s.memory} delay={i * 0.04} onClick={() => openMemory(s.memory.id)} />)}</div>
              </div>
            )}
          </motion.div>
        )}
      </div>
    </Overlay>
  );
}

export function DocumentDrawer() {
  const { documentId, openDocument, toast, bump, refreshUser } = useApp();
  const { data: d, loading, reload } = useLoad(() => documentId ? api.document(documentId) : Promise.resolve(null), [documentId]);
  const [title, setTitle] = useState('');
  const [date, setDate] = useState('');
  const [tags, setTags] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (d) { setTitle(d.title); setDate(d.document_date?.slice(0, 10) || ''); setTags(d.tags.join(', ')); } }, [d]);

  const save = async (extra: Parameters<typeof api.updateDocument>[1] = {}) => {
    if (!d) return;
    setSaving(true);
    try {
      await api.updateDocument(d.id, { title, document_date: date || undefined, tags: tags.split(',').map(t => t.trim()).filter(Boolean), ...extra });
      reload(); bump();
      toast(date !== (d.document_date || '').slice(0, 10) ? 'Saved — memories re-dated' : 'Saved', 'success');
    } catch (e) { toast((e as Error).message, 'error'); } finally { setSaving(false); }
  };

  const remove = async () => {
    if (!d || !confirm(`Delete “${d.title}” and its ${d.memory_count} memories?`)) return;
    await api.deleteDocument(d.id);
    openDocument(null); bump(); refreshUser();
    toast('Document deleted', 'info');
  };

  const dirty = d && (title !== d.title || date !== (d.document_date || '').slice(0, 10) || tags !== d.tags.join(', '));

  return (
    <Overlay open={!!documentId} onClose={() => openDocument(null)} kind="drawer" label="Document">
      <div className="drawer-head">
        <div className="eyebrow">{d?.source_type === 'capsule' ? 'Captured thought' : d?.source_type === 'note' ? 'Note' : 'Document'}</div>
        <div className="row gap-s">
          {d && <a className="btn icon ghost sm" href={api.downloadUrl(d.id)} title="Download"><Download size={16} /></a>}
          {d && <button className="btn icon ghost sm danger" onClick={remove} title="Delete"><Trash2 size={16} /></button>}
          <CloseButton onClick={() => openDocument(null)} />
        </div>
      </div>
      <div style={{ padding: '4px 24px 28px' }}>
        {loading || !d ? <div className="col"><Skeleton h={34} /><Skeleton h={260} /></div> : (
          <motion.div key={d.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="col gap-l">
            <input className="input display" style={{ fontSize: 18, fontWeight: 600, background: 'transparent', border: '1px solid transparent', padding: '6px 8px', marginLeft: -8 }} value={title} onChange={e => setTitle(e.target.value)} />
            <div className="grid" style={{ gap: 12 }}>
              <div className="field"><label>Written on</label><input type="date" className="input" value={date} onChange={e => setDate(e.target.value)} /></div>
            </div>
            {dirty && <button className="btn primary" disabled={saving} onClick={() => save()}>{saving ? <Spinner /> : <><Check size={15} /> Save changes</>}</button>}
            <div className="row wrap gap-s tiny faint">
              <span>{d.word_count.toLocaleString()} words</span>·<span>{d.memory_count} memories</span>
            </div>
            <div className="doc-reader">{d.content}</div>
            {d.memories.length > 0 && (
              <div>
                <div className="eyebrow mb-s">Memories found in this entry</div>
                <div className="col gap-s">
                  {d.memories.map((m, i) => (
                    <div key={m.id} className="row top" style={{ gap: 10 }}>
                      <span className="dot" style={{ marginTop: 9, color: TYPE_META[m.memory_type].color } as CSSProperties} />
                      <MemoryRow m={m} showDoc={false} delay={i * 0.02} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </div>
    </Overlay>
  );
}
