import type {
  AnswerPayload, BenchmarkRun, ChangePoint, Conversation, DemoAccount, Doc, DocDetail, GraphData, Insights,
  Memory, Message, Relationship, Subject, SystemStatus, UploadResult, User, VersionDiff, MemoryType,
} from './types';

export const API_BASE =
  (import.meta.env.VITE_API_BASE_URL ? String(import.meta.env.VITE_API_BASE_URL).replace(/\/+$/, '') : '') + '/api';

const TOKEN_KEY = 'ml.token';
let token: string | null = (() => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } })();
let onUnauthorized: (() => void) | null = null;

export const session = {
  get token() { return token; },
  set(t: string | null) {
    token = t;
    try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
  },
  onUnauthorized(fn: () => void) { onUnauthorized = fn; },
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

function headers(json = true): HeadersInit {
  const h: Record<string, string> = {};
  if (json) h['Content-Type'] = 'application/json';
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function req<T>(path: string, init: RequestInit = {}, json = true): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...headers(json), ...(init.headers || {}) } });
  } catch {
    throw new ApiError(0, "Can't reach Memory Lane. Is the server running?");
  }
  if (res.status === 401 && onUnauthorized && !path.startsWith('/auth/login')) onUnauthorized();
  if (!res.ok) {
    let detail = res.statusText;
    try { const b = await res.json(); detail = typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail); } catch { /* not json */ }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  const ct = res.headers.get('content-type') || '';
  return (ct.includes('application/json') ? res.json() : res.text()) as Promise<T>;
}

const qs = (o: Record<string, unknown>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export type StreamHandlers = {
  onConversation?: (id: string) => void;
  onMeta?: (meta: { intent: string; citations: AnswerPayload['citations']; provider: string; changes: ChangePoint[]; year_range?: AnswerPayload['year_range']; rewritten_query?: string | null }) => void;
  onToken?: (t: string) => void;
  onDone?: (p: AnswerPayload) => void;
  onError?: (msg: string) => void;
};

export const api = {
  // auth
  demoAccounts: () => req<DemoAccount[]>('/auth/demo-accounts'),
  login: (username_or_email: string, password: string) =>
    req<{ token: string; user: User }>('/auth/login', { method: 'POST', body: JSON.stringify({ username_or_email, password }) }),
  register: (b: { email: string; username: string; password: string; display_name: string; avatar_color?: string }) =>
    req<{ token: string; user: User }>('/auth/register', { method: 'POST', body: JSON.stringify(b) }),
  me: () => req<User>('/auth/me'),
  updateMe: (b: Partial<Pick<User, 'display_name' | 'bio' | 'avatar_color' | 'preferences'>>) =>
    req<User>('/auth/me', { method: 'PATCH', body: JSON.stringify(b) }),
  changePassword: (current_password: string, new_password: string) =>
    req('/auth/password', { method: 'POST', body: JSON.stringify({ current_password, new_password }) }),
  logout: () => req('/auth/logout', { method: 'POST' }),
  deleteAccount: () => req('/auth/me', { method: 'DELETE' }),

  // documents
  documents: (p: { q?: string; tag?: string; favorite?: boolean; sort?: string } = {}) => req<Doc[]>(`/documents${qs(p)}`),
  document: (id: string) => req<DocDetail>(`/documents/${id}`),
  tags: () => req<Record<string, number>>('/documents/tags'),
  series: () => req<Record<string, Doc[]>>('/documents/series'),
  compare: (earlier: string, later: string) => req<VersionDiff>(`/documents/compare${qs({ earlier, later })}`),
  updateDocument: (id: string, b: Partial<Pick<Doc, 'title' | 'document_date' | 'tags' | 'favorite' | 'series_name' | 'version_label'>>) =>
    req<Doc>(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
  deleteDocument: (id: string) => req(`/documents/${id}`, { method: 'DELETE' }),
  createNote: (b: { title: string; content: string; document_date?: string; tags?: string[] }) =>
    req<Doc>('/documents/note', { method: 'POST', body: JSON.stringify(b) }),
  downloadUrl: (id: string) => `${API_BASE}/documents/${id}/download?token=${encodeURIComponent(token || '')}`,
  upload: (files: File[], opts: { document_date?: string; tags?: string } = {},
    onProgress?: (pct: number) => void): Promise<{ results: UploadResult[] }> =>
    new Promise((resolve, reject) => {
      const fd = new FormData();
      files.forEach(f => fd.append('files', f));
      if (opts.document_date) fd.append('document_date', opts.document_date);
      if (opts.tags) fd.append('tags', opts.tags);
      const x = new XMLHttpRequest();
      x.open('POST', `${API_BASE}/documents/upload`);
      if (token) x.setRequestHeader('Authorization', `Bearer ${token}`);
      x.upload.onprogress = e => { if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100)); };
      x.onload = () => {
        try {
          const body = JSON.parse(x.responseText);
          if (x.status >= 400) reject(new ApiError(x.status, body.detail || 'Upload failed')); else resolve(body);
        } catch { reject(new ApiError(x.status, 'Upload failed')); }
      };
      x.onerror = () => reject(new ApiError(0, "Can't reach Memory Lane."));
      x.send(fd);
    }),

  // memories
  memories: (p: { q?: string; memory_type?: string; topic?: string; entity?: string; start_year?: number; end_year?: number; pinned?: boolean; order?: string; limit?: number } = {}) =>
    req<{ items: Memory[]; total: number }>(`/memories${qs(p)}`),
  memory: (id: string) => req<{ memory: Memory; context: string; related: Relationship[]; similar: { memory: Memory; score: number }[] }>(`/memories/${id}`),
  capture: (b: { statement: string; memory_type?: MemoryType; event_date?: string; context_note?: string; tags?: string[] }) =>
    req<Memory>('/memories', { method: 'POST', body: JSON.stringify(b) }),
  updateMemory: (id: string, b: { statement?: string; memory_type?: MemoryType; event_date?: string; pinned?: boolean }) =>
    req<Memory>(`/memories/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
  deleteMemory: (id: string) => req(`/memories/${id}`, { method: 'DELETE' }),
  subjects: () => req<Subject[]>('/memories/subjects'),
  trajectory: (subject: string) => req<{ subject: string; points: { date: string; stance: number; sentiment: number; statement: string; memory_id: string; memory_type: MemoryType }[]; changes: ChangePoint[] }>(`/memories/trajectory${qs({ subject })}`),

  // analysis
  insights: () => req<Insights>('/insights'),
  timeline: (p: { q?: string; memory_type?: string; topic?: string; entity?: string; start_year?: number; end_year?: number } = {}) =>
    req<{ years: { year: string; memories: Memory[] }[]; total: number; change_markers: Record<string, { subject: string; change_type: string }> }>(`/timeline${qs(p)}`),
  changes: (subject?: string) => req<ChangePoint[]>(`/changes${qs({ subject })}`),
  contradictions: () => req<Relationship[]>('/contradictions'),
  graph: () => req<GraphData>('/graph'),
  search: (q: string) => req<{ memories: Memory[]; documents: Doc[] }>(`/search${qs({ q })}`),

  // chat
  conversations: (q?: string) => req<Conversation[]>(`/conversations${qs({ q })}`),
  conversation: (id: string) => req<Conversation & { messages: Message[] }>(`/conversations/${id}`),
  updateConversation: (id: string, b: { title?: string; pinned?: boolean }) =>
    req(`/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
  deleteConversation: (id: string) => req(`/conversations/${id}`, { method: 'DELETE' }),
  feedback: (messageId: string, value: number) =>
    req(`/messages/${messageId}/feedback`, { method: 'POST', body: JSON.stringify({ value }) }),
  exportConversationUrl: (id: string) => `${API_BASE}/conversations/${id}/export?token=${encodeURIComponent(token || '')}`,

  async chatStream(body: { query: string; conversation_id?: string | null; pipeline_mode?: string; filter_start_year?: number | null; filter_end_year?: number | null; top_k?: number },
    h: StreamHandlers, signal?: AbortSignal) {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/chat/stream`, { method: 'POST', headers: headers(), body: JSON.stringify(body), signal });
    } catch (e) {
      if ((e as Error).name === 'AbortError') return;
      h.onError?.("Can't reach Memory Lane. Is the server running?");
      return;
    }
    if (!res.ok || !res.body) {
      let detail = 'Something went wrong.';
      try { detail = (await res.json()).detail; } catch { /* ignore */ }
      if (res.status === 401) onUnauthorized?.();
      h.onError?.(detail);
      return;
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i: number;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const block = buf.slice(0, i);
          buf = buf.slice(i + 2);
          let ev = 'message', data = '';
          for (const line of block.split('\n')) {
            if (line.startsWith('event: ')) ev = line.slice(7);
            else if (line.startsWith('data: ')) data += line.slice(6);
          }
          if (!data) continue;
          const d = JSON.parse(data);
          if (ev === 'conversation') h.onConversation?.(d.conversation_id);
          else if (ev === 'meta') h.onMeta?.(d);
          else if (ev === 'token') h.onToken?.(d.t);
          else if (ev === 'done') h.onDone?.(d);
          else if (ev === 'error') h.onError?.(d.detail);
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') h.onError?.('The connection was interrupted.');
    }
  },

  // system
  status: () => req<SystemStatus>('/system/status'),
  reindex: () => req<{ reindexed: number }>('/system/reindex', { method: 'POST' }),
  exportUrl: () => `${API_BASE}/export?token=${encodeURIComponent(token || '')}`,
  importArchive: (file: File) => {
    const fd = new FormData(); fd.append('file', file);
    return req<{ imported_documents: number }>('/import', { method: 'POST', body: fd }, false);
  },
  runBenchmark: (run_name: string, pipelines: string[]) =>
    req<BenchmarkRun>('/research/benchmark', { method: 'POST', body: JSON.stringify({ run_name, pipelines }) }),
  runs: () => req<BenchmarkRun[]>('/research/runs'),
};
