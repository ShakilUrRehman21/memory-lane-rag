import { AnimatePresence, motion } from 'motion/react';
import { ArrowRight, Eye, EyeOff } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import { useApp } from '../lib/app';
import type { DemoAccount } from '../lib/types';
import { Logo } from '../components/Logo';
import { Avatar, Seg, Spinner } from '../components/ui';

const COLORS = ['#6e6af0', '#14b8a6', '#ec4899', '#f59e0b', '#0ea5e9', '#ef4444'];

export function AuthView() {
  const { signIn, toast } = useApp();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [demo, setDemo] = useState<DemoAccount[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [show, setShow] = useState(false);
  const [f, setF] = useState({ id: '', email: '', username: '', name: '', password: '' });

  useEffect(() => {
    let tries = 0;
    const load = () => api.demoAccounts().then(setDemo).catch(() => undefined);
    load();
    const t = setInterval(() => { if (++tries > 10) clearInterval(t); else load(); }, 2500); // demo data may still be loading
    return () => clearInterval(t);
  }, []);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    setError(null); setBusy('form');
    try {
      const r = mode === 'login'
        ? await api.login(f.id.trim(), f.password)
        : await api.register({ email: f.email, username: f.username, password: f.password, display_name: f.name,
          avatar_color: COLORS[Math.floor(Math.random() * COLORS.length)] });
      signIn(r.token, r.user);
      if (mode === 'register') toast('Welcome! Start by adding a journal entry or note.', 'success');
    } catch (err) { setError((err as Error).message); } finally { setBusy(null); }
  };

  const demoLogin = async (a: DemoAccount) => {
    setBusy(a.username); setError(null);
    try { const r = await api.login(a.username, a.password); signIn(r.token, r.user); }
    catch (err) { setError((err as Error).message); } finally { setBusy(null); }
  };

  return (
    <div className="auth">
      <motion.div className="auth-card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <div className="row" style={{ gap: 10 }}><Logo size={28} /><span className="brand-name">Memory Lane</span></div>
        <p className="muted small" style={{ margin: '14px 0 20px' }}>Ask questions about your own journals and notes, and see how your thinking changed over time.</p>

        <Seg value={mode} onChange={m => { setMode(m); setError(null); }} options={[{ value: 'login', label: 'Sign in' }, { value: 'register', label: 'Create account' }]} />

        <form onSubmit={submit} className="col mt" style={{ gap: 12 }}>
          {mode === 'login' ? (
            <div className="field"><label>Username or email</label><input className="input" value={f.id} onChange={e => setF({ ...f, id: e.target.value })} autoComplete="username" required /></div>
          ) : (
            <>
              <div className="field"><label>Name</label><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required /></div>
              <div className="grid g2" style={{ gap: 10 }}>
                <div className="field"><label>Username</label><input className="input" value={f.username} onChange={e => setF({ ...f, username: e.target.value })} autoComplete="username" required minLength={3} /></div>
                <div className="field"><label>Email</label><input type="email" className="input" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} autoComplete="email" required /></div>
              </div>
            </>
          )}
          <div className="field"><label>Password</label>
            <div className="input-icon right">
              <input type={show ? 'text' : 'password'} className="input" value={f.password} onChange={e => setF({ ...f, password: e.target.value })}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'register' ? 8 : 1}
                placeholder={mode === 'register' ? 'At least 8 characters' : undefined} />
              <button type="button" className="eye" onClick={() => setShow(s => !s)} aria-label="Show password">{show ? <EyeOff size={15} /> : <Eye size={15} />}</button>
            </div>
          </div>
          <AnimatePresence>{error && <motion.div className="form-error" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>{error}</motion.div>}</AnimatePresence>
          <button className="btn primary" disabled={busy === 'form'} style={{ marginTop: 4 }}>
            {busy === 'form' ? <Spinner /> : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        {demo.length > 0 && (
          <div className="mt-l">
            <div className="divider-label"><span>or try a demo account</span></div>
            <div className="col" style={{ gap: 6 }}>
              {demo.map(a => (
                <button key={a.username} className="demo-account" disabled={!a.available || !!busy} onClick={() => demoLogin(a)}>
                  <Avatar name={a.display_name} color={a.avatar_color} size={28} />
                  <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}>
                    <span className="small" style={{ fontWeight: 600, display: 'block' }}>{a.display_name}</span>
                    <span className="tiny faint truncate" style={{ display: 'block' }}>{a.available ? a.blurb : 'Preparing…'}</span>
                  </span>
                  {busy === a.username ? <Spinner size={14} /> : <ArrowRight size={14} className="faint" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}
