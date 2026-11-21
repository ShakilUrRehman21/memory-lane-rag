import type { MemoryType } from './types';

export const TYPE_META: Record<MemoryType, { label: string; color: string; glyph: string }> = {
  belief: { label: 'Belief', color: 'var(--c-belief)', glyph: '◆' },
  goal: { label: 'Goal', color: 'var(--c-goal)', glyph: '✦' },
  decision: { label: 'Decision', color: 'var(--c-decision)', glyph: '◉' },
  preference: { label: 'Preference', color: 'var(--c-preference)', glyph: '♡' },
  plan: { label: 'Plan', color: 'var(--c-plan)', glyph: '▸' },
  reflection: { label: 'Reflection', color: 'var(--c-reflection)', glyph: '◌' },
  feeling: { label: 'Feeling', color: 'var(--c-feeling)', glyph: '❍' },
  knowledge: { label: 'Knowledge', color: 'var(--c-knowledge)', glyph: '▤' },
  observation: { label: 'Observation', color: 'var(--c-observation)', glyph: '◎' },
  event: { label: 'Moment', color: 'var(--c-event)', glyph: '•' },
};

export const MEMORY_TYPES = Object.keys(TYPE_META) as MemoryType[];

export const CHANGE_META: Record<string, { label: string; tone: string }> = {
  reversal: { label: 'Reversal', tone: 'var(--rose)' },
  intensified: { label: 'Strengthened', tone: 'var(--mint)' },
  softened: { label: 'Softened', tone: 'var(--amber)' },
  new_commitment: { label: 'New commitment', tone: 'var(--accent)' },
  direction_shift: { label: 'Change of direction', tone: 'var(--lilac)' },
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function fmtDate(d?: string | null, mode: 'short' | 'long' | 'month' | 'year' = 'short'): string {
  if (!d) return 'Undated';
  const [y, m, day] = d.slice(0, 10).split('-').map(Number);
  if (!y) return d;
  if (mode === 'year') return String(y);
  if (mode === 'month' || !day) return m ? `${MONTHS[m - 1]} ${y}` : String(y);
  if (mode === 'long') return `${MONTHS[m - 1]} ${day}, ${y}`;
  return `${MONTHS[m - 1]} ${day}, ${y}`;
}

export function relTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return fmtDate(iso.slice(0, 10));
}

export function yearsAgo(d?: string | null): string {
  if (!d) return '';
  const y = new Date().getFullYear() - Number(d.slice(0, 4));
  return y <= 0 ? 'this year' : y === 1 ? '1 year ago' : `${y} years ago`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return 'Still up';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  if (h < 22) return 'Good evening';
  return 'Good night';
}

export function stanceLabel(s: number): string {
  if (s >= 0.5) return 'embracing';
  if (s > 0.1) return 'leaning in';
  if (s <= -0.5) return 'resisting';
  if (s < -0.1) return 'doubtful';
  return 'neutral';
}

export const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(s => s[0]?.toUpperCase()).join('') || '·';

export const cx = (...c: Array<string | false | null | undefined>) => c.filter(Boolean).join(' ');
