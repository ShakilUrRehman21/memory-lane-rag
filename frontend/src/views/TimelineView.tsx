import { motion } from 'motion/react';
import { GitBranch, Pin, Search, X } from 'lucide-react';
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { api } from '../lib/api';
import { useApp, useLoad } from '../lib/app';
import { CHANGE_META, TYPE_META, cx, fmtDate } from '../lib/format';
import { Empty, Skeleton, TypeBadge } from '../components/ui';

export function TimelineView() {
  const { openMemory, param } = useApp();
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [entity, setEntity] = useState<string | null>(param);
  const [activeYear, setActiveYear] = useState<string | null>(null);
  const refs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => { const t = setTimeout(() => setDebounced(q), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => { setEntity(param); }, [param]);

  const { data, loading } = useLoad(() => api.timeline({ q: debounced || undefined, entity: entity || undefined }), [debounced, entity]);
  const subjects = useLoad(() => api.subjects());

  const years = (data?.years || []).filter(y => y.memories.length);
  const ordered = years;
  const total = years.reduce((s, y) => s + y.memories.length, 0);

  // track the year in view for the minimap
  useEffect(() => {
    const io = new IntersectionObserver(es => { es.forEach(e => { if (e.isIntersecting) setActiveYear((e.target as HTMLElement).dataset.year || null); }); }, { rootMargin: '-30% 0px -60% 0px' });
    Object.values(refs.current).forEach(el => el && io.observe(el));
    return () => io.disconnect();
  }, [ordered.length]);


  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="display h1">Timeline</h1>
          <p>{total} moments{entity ? <> about <b>{entity}</b></> : ''}, in the order they happened. Click any one to open it.</p>
        </div>
      </div>

      <div className="glass filters">
        <div className="input-icon grow" style={{ minWidth: 220 }}><Search size={16} /><input className="input" placeholder="Search…" value={q} onChange={e => setQ(e.target.value)} /></div>
        <select className="select" style={{ width: 220 }} value={entity || ''} onChange={e => setEntity(e.target.value || null)}>
          <option value="">All topics</option>
          {subjects.data?.filter(s => s.kind === 'entity').map(s => <option key={s.name} value={s.name}>{s.name} ({s.count})</option>)}
        </select>
        {(entity || q) && <button className="chip" onClick={() => { setEntity(null); setQ(''); }}><X size={12} /> Clear</button>}
      </div>

      {loading && !data ? <div className="col mt-l">{[0, 1, 2, 3].map(i => <Skeleton key={i} h={90} r={20} />)}</div>
        : !total ? <Empty title="Nothing here yet">Try clearing filters, or add more writing to your library.</Empty>
          : (
            <div className="river-wrap">
              <div className="river">
                <div className="river-line" />
                {ordered.map(y => (
                  <div key={y.year} className="river-year" data-year={y.year} ref={el => { refs.current[y.year] = el; }}>
                    <motion.div className="year-mark" initial={{ opacity: 0, scale: 0.8 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true, margin: '-80px' }}>
                      <span className="display">{y.year}</span><span className="tiny faint">{y.memories.length} moments</span>
                    </motion.div>
                    {y.memories.map((m, i) => {
                      const change = data?.change_markers[m.id];
                      const side = i % 2 === 0 ? 'left' : 'right';
                      return (
                        <motion.div key={m.id} className={cx('river-item', side)} style={{ '--t': TYPE_META[m.memory_type].color } as CSSProperties}
                          initial={{ opacity: 0, y: 6 }} whileInView={{ opacity: 1, y: 0 }}
                          viewport={{ once: true, margin: '-40px' }} transition={{ duration: 0.3 }}>
                          <span className="river-node" />
                          <button className="card spot hover river-card" onClick={() => openMemory(m.id)}
                            onMouseMove={e => { const r = e.currentTarget.getBoundingClientRect(); e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`); e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`); }}>
                            <div className="row between gap-s">
                              <span className="mono tiny faint">{fmtDate(m.event_date_start, m.date_granularity === 'year' ? 'year' : m.date_granularity === 'month' ? 'month' : 'short')}</span>
                              <div className="row gap-s">{m.pinned && <Pin size={12} style={{ color: 'var(--accent)' }} />}{m.memory_type !== 'event' && <TypeBadge type={m.memory_type} />}</div>
                            </div>
                            <div className="serif" style={{ fontSize: 14, lineHeight: 1.45, margin: '10px 0 8px' }}>{m.statement}</div>
                            <div className="row wrap gap-s">
                              {change && <span className="chip tiny" style={{ color: CHANGE_META[change.change_type]?.tone }}><GitBranch size={11} /> {CHANGE_META[change.change_type]?.label} · {change.subject}</span>}
                              {m.entities.slice(0, 3).map(e => <span key={e} className="chip tiny">{e}</span>)}
                              <span className="tiny faint truncate" style={{ marginLeft: 'auto', maxWidth: 200 }}>{m.document_title}</span>
                            </div>
                          </button>
                        </motion.div>
                      );
                    })}
                  </div>
                ))}
              </div>
              <nav className="minimap hide-mobile">
                {ordered.map(y => (
                  <button key={y.year} className={cx(activeYear === y.year && 'on')} onClick={() => refs.current[y.year]?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
                    <span className="mm-bar" style={{ width: `${Math.min(100, 20 + y.memories.length * 8)}%` }} />{y.year}
                  </button>
                ))}
              </nav>
            </div>
          )}
    </div>
  );
}
