import { AnimatePresence, animate, motion, useInView, useMotionValue, useTransform } from 'motion/react';
import { useEffect, useId, useRef, type CSSProperties, type MouseEvent, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { TYPE_META, cx, fmtDate, initials } from '../lib/format';
import type { Memory, MemoryType } from '../lib/types';
import { Orb } from './Logo';
import { useApp } from '../lib/app';

export const spring = { type: 'spring', stiffness: 380, damping: 32 } as const;
export const soft = { duration: 0.3, ease: [0.22, 1, 0.36, 1] } as const;

/** Spotlight card: radial glow follows the cursor. */
export function Card({ children, className, style, onClick, hover = true, delay = 0, as = 'div' }: {
  children: ReactNode; className?: string; style?: CSSProperties; onClick?: () => void; hover?: boolean; delay?: number; as?: 'div' | 'button';
}) {
  const onMove = (e: MouseEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`);
    e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`);
  };
  const Comp = as === 'button' ? motion.button : motion.div;
  return (
    <Comp className={cx('card spot', hover && 'hover', className)} style={{ ...style, textAlign: as === 'button' ? 'left' : undefined }}
      onMouseMove={onMove} onClick={onClick}
      initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      transition={{ ...soft, delay }}>
      {children}
    </Comp>
  );
}

export function Seg<T extends string>({ value, options, onChange, size }: {
  value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; size?: 'sm';
}) {
  const id = useId();
  return (
    <div className="seg" role="tablist" style={size === 'sm' ? { fontSize: 12 } : undefined}>
      {options.map(o => (
        <button key={o.value} role="tab" aria-selected={value === o.value} className={cx(value === o.value && 'on')} onClick={() => onChange(o.value)}>
          {value === o.value && <motion.span layoutId={`seg-${id}`} className="seg-pill" transition={spring} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function TypeBadge({ type }: { type: MemoryType }) {
  const m = TYPE_META[type] || TYPE_META.event;
  return <span className="type-badge" style={{ '--t': m.color } as CSSProperties}><span>{m.glyph}</span>{m.label}</span>;
}

export function Avatar({ name, color, size = 36 }: { name: string; color: string; size?: number }) {
  return <div className="avatar" style={{ width: size, height: size, fontSize: size * 0.38, '--c': color } as CSSProperties}>{initials(name)}</div>;
}

export function Skeleton({ h = 16, w = '100%', r, style }: { h?: number; w?: number | string; r?: number; style?: CSSProperties }) {
  return <div className="skel" style={{ height: h, width: w, borderRadius: r, ...style }} />;
}

export function SkeletonCards({ n = 3, h = 120 }: { n?: number; h?: number }) {
  return <>{Array.from({ length: n }, (_, i) => <Skeleton key={i} h={h} r={24} style={{ opacity: 1 - i * 0.18 }} />)}</>;
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <motion.div className="empty" initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={soft}>
      <Orb />
      <div className="display h2" style={{ color: 'var(--ink)' }}>{title}</div>
      {children && <div style={{ maxWidth: 440 }}>{children}</div>}
      {action}
    </motion.div>
  );
}

/** Number that counts up when it scrolls into view. */
export function Counter({ value, format = (n: number) => Math.round(n).toLocaleString() }: { value: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const mv = useMotionValue(0);
  const text = useTransform(mv, v => format(v));
  useEffect(() => {
    if (!inView) return;
    const c = animate(mv, value, { duration: 1.4, ease: [0.22, 1, 0.36, 1] });
    return c.stop;
  }, [inView, value, mv]);
  return <motion.span ref={ref}>{text}</motion.span>;
}

export function Overlay({ open, onClose, children, kind = 'modal', className, label }: {
  open: boolean; onClose: () => void; children: ReactNode; kind?: 'modal' | 'drawer'; className?: string; label?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="overlay" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }} />
          <motion.div role="dialog" aria-modal aria-label={label} className={cx(kind, className)}
            initial={kind === 'drawer' ? { x: 60, opacity: 0 } : { y: 24, opacity: 0, scale: 0.97 }}
            animate={kind === 'drawer' ? { x: 0, opacity: 1 } : { y: 0, opacity: 1, scale: 1 }}
            exit={kind === 'drawer' ? { x: 60, opacity: 0 } : { y: 16, opacity: 0, scale: 0.98 }}
            transition={spring}>
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

export function CloseButton({ onClick }: { onClick: () => void }) {
  return <button className="btn icon ghost" onClick={onClick} aria-label="Close"><X size={18} /></button>;
}

/** Compact memory row used across views. */
export function MemoryRow({ m, onClick, showDoc = true, delay = 0 }: { m: Memory; onClick?: () => void; showDoc?: boolean; delay?: number }) {
  const { openMemory } = useApp();
  return (
    <motion.button className="memory-row" onClick={onClick || (() => openMemory(m.id))}
      initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ ...soft, delay }}
      whileHover={{ x: 0 }}>
      <span className="memory-row-bar" style={{ background: TYPE_META[m.memory_type]?.color }} />
      <span className="grow">
        <span className="row gap-s small faint" style={{ marginBottom: 4 }}>
          <span className="mono">{fmtDate(m.event_date_start, 'month')}</span>
          {showDoc && m.document_title && <><span>·</span><span className="truncate">{m.document_title}</span></>}
        </span>
        <span className="clamp-2" style={{ display: '-webkit-box' }}>{m.statement}</span>
      </span>
    </motion.button>
  );
}

export function Stagger({ children, className, style }: { children: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <motion.div className={className} style={style} initial="hidden" animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05 } } }}>
      {children}
    </motion.div>
  );
}
export const staggerItem = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0, transition: soft } };

export function Spinner({ size = 16 }: { size?: number }) {
  return <svg className="spin" width={size} height={size} viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" /><path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /></svg>;
}

export function Thinking({ label = 'Thinking' }: { label?: string }) {
  return <span className="row small faint"><span className="thinking-dots"><span /><span /><span /></span>{label}</span>;
}
