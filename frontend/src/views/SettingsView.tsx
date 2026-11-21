import { Download, KeyRound, Palette, ShieldAlert, Upload, User as UserIcon } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '../lib/api';
import { useApp, useLoad, type Prefs } from '../lib/app';
import { Avatar, Card, Seg, Spinner } from '../components/ui';

const ACCENTS = ['#8b9cff', '#5eead4', '#f0abfc', '#fbbf77', '#7dd3fc', '#fda4af', '#a3e635'];

function Section({ icon, title, sub, children, delay = 0 }: { icon: ReactNode; title: string; sub?: string; children: ReactNode; delay?: number }) {
  return (
    <Card hover={false} delay={delay}>
      <div className="row gap-s mb"><span className="section-icon">{icon}</span><div><div className="h3">{title}</div>{sub && <div className="small faint">{sub}</div>}</div></div>
      {children}
    </Card>
  );
}

export function SettingsView() {
  const { user, setUser, prefs, setPrefs, toast, signOut, bump, refreshUser } = useApp();
  const status = useLoad(() => api.status());
  const [name, setName] = useState(user?.display_name || '');
  const [bio, setBio] = useState(user?.bio || '');
  const [color, setColor] = useState(user?.avatar_color || ACCENTS[0]);
  const [pw, setPw] = useState({ cur: '', next: '' });
  const [busy, setBusy] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (user) { setName(user.display_name); setBio(user.bio || ''); setColor(user.avatar_color); } }, [user]);

  const saveProfile = async () => {
    setBusy('profile');
    try { setUser(await api.updateMe({ display_name: name, bio, avatar_color: color })); toast('Profile saved', 'success'); }
    catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(null); }
  };
  const changePw = async () => {
    setBusy('pw');
    try { await api.changePassword(pw.cur, pw.next); setPw({ cur: '', next: '' }); toast('Password changed', 'success'); }
    catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(null); }
  };
  const doImport = async (f: File) => {
    setBusy('import');
    try { const r = await api.importArchive(f); toast(`Imported ${r.imported_documents} documents`, 'success'); bump(); refreshUser(); }
    catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(null); }
  };
  const del = async () => {
    if (prompt('This permanently deletes your account and every memory. Type DELETE to confirm.') !== 'DELETE') return;
    await api.deleteAccount(); toast('Account deleted', 'info'); signOut();
  };

  return (
    <div className="page" style={{ maxWidth: 900 }}>
      <div className="page-head"><div><h1 className="display h1">Settings</h1></div></div>
      <div className="col gap-l">
        <Section icon={<Palette size={17} />} title="Appearance">
          <div className="col gap-l">
            <div className="row between wrap gap-s"><span>Theme</span>
              <Seg<Prefs['theme']> value={prefs.theme} onChange={t => setPrefs({ theme: t })} options={[{ value: 'dusk', label: '🌙 Dusk' }, { value: 'dawn', label: '☀️ Dawn' }, { value: 'auto', label: 'System' }]} /></div>
          </div>
        </Section>

        <Section icon={<UserIcon size={17} />} title="Profile" delay={0.05}>
          <div className="row gap-l top wrap">
            <Avatar name={name || '?'} color={color} size={72} />
            <div className="col grow" style={{ minWidth: 260 }}>
              <div className="grid g2" style={{ gap: 12 }}>
                <div className="field"><label>Display name</label><input className="input" value={name} onChange={e => setName(e.target.value)} /></div>
                <div className="field"><label>Username</label><input className="input" value={user?.username || ''} disabled /></div>
              </div>
              <div className="field"><label>About you</label><input className="input" value={bio} onChange={e => setBio(e.target.value)} placeholder="A line about your story" /></div>
              <div className="row between wrap">
                <div className="row gap-s">{ACCENTS.map(c => <button key={c} onClick={() => setColor(c)} style={{ width: 22, height: 22, borderRadius: '50%', background: c, boxShadow: color === c ? `0 0 0 2px var(--bg), 0 0 0 4px ${c}` : 'none' }} aria-label={c} />)}</div>
                <button className="btn primary" onClick={saveProfile} disabled={busy === 'profile'}>{busy === 'profile' ? <Spinner /> : 'Save profile'}</button>
              </div>
            </div>
          </div>
        </Section>


        <Section icon={<Download size={17} />} title="Backup" sub="Download everything, or restore from a backup" delay={0.15}>
          <div className="row wrap gap-s">
            <a className="btn" href={api.exportUrl()}><Download size={15} /> Download backup</a>
            <button className="btn" onClick={() => fileRef.current?.click()} disabled={busy === 'import'}>{busy === 'import' ? <Spinner /> : <Upload size={15} />} Restore a backup</button>
            <input ref={fileRef} type="file" accept=".json" hidden onChange={e => { const f = e.target.files?.[0]; if (f) doImport(f); e.target.value = ''; }} />
          </div>
        </Section>

        <Section icon={<KeyRound size={17} />} title="Password" delay={0.2}>
          <div className="grid g2" style={{ gap: 12 }}>
            <input type="password" className="input" placeholder="Current password" value={pw.cur} onChange={e => setPw({ ...pw, cur: e.target.value })} autoComplete="current-password" />
            <input type="password" className="input" placeholder="New password (8+ characters)" value={pw.next} onChange={e => setPw({ ...pw, next: e.target.value })} autoComplete="new-password" />
          </div>
          <button className="btn mt" onClick={changePw} disabled={!pw.cur || pw.next.length < 8 || busy === 'pw'}>{busy === 'pw' ? <Spinner /> : 'Change password'}</button>
        </Section>

        <Section icon={<ShieldAlert size={17} />} title="Danger zone" delay={0.25}>
          <div className="row between wrap gap-s"><span className="small faint">Permanently delete your account, documents, memories and conversations.</span><button className="btn danger" onClick={del}>Delete account</button></div>
        </Section>
        <div className="tiny faint" style={{ textAlign: 'center' }}>Answers written by {status.data?.llm.label ?? '…'} · <span className="kbd">Ctrl K</span> search · <span className="kbd">Ctrl J</span> new thought</div>
      </div>
    </div>
  );
}
