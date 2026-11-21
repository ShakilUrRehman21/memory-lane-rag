/** Memory Lane mark: a winding path with three points in time, on an accent tile. */
export function Logo({ size = 28 }: { size?: number; animated?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <path d="M7 24c4-1 4.5-6 8.5-7.3S22 18 24.5 14 25.5 8 26 7" stroke="white" strokeOpacity="0.95" strokeWidth="2" strokeLinecap="round" />
      <circle cx="7" cy="24" r="1.9" fill="white" />
      <circle cx="15.5" cy="16.7" r="1.7" fill="white" />
      <circle cx="25.6" cy="7.4" r="2" fill="white" />
    </svg>
  );
}

/** Quiet icon tile for empty states. */
export function Orb({ size = 44 }: { size?: number }) {
  return (
    <div style={{ width: size, height: size, borderRadius: 12, display: 'grid', placeItems: 'center', background: 'var(--surface-2)', border: '1px solid var(--line)' }}>
      <Logo size={size * 0.55} />
    </div>
  );
}
