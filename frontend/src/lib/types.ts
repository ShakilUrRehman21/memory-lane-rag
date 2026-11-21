export type MemoryType =
  | 'event' | 'belief' | 'goal' | 'decision' | 'preference'
  | 'knowledge' | 'observation' | 'plan' | 'reflection' | 'feeling';

export interface User {
  id: string;
  username: string;
  display_name: string;
  email?: string | null;
  avatar_color: string;
  bio?: string | null;
  preferences: Record<string, unknown>;
  created_at: string;
  document_count: number;
  memory_count: number;
  earliest_memory_date?: string | null;
  latest_memory_date?: string | null;
}

export interface DemoAccount {
  username: string;
  display_name: string;
  blurb: string;
  avatar_color: string;
  available: boolean;
  password: string;
}

export interface Doc {
  id: string;
  title: string;
  source_type: 'upload' | 'note' | 'capsule' | 'import';
  file_name?: string | null;
  file_type: string;
  file_size: number;
  document_date?: string | null;
  date_confidence: number;
  word_count: number;
  tags: string[];
  favorite: boolean;
  series_name?: string | null;
  version_label?: string | null;
  excerpt: string;
  created_at: string;
  updated_at: string;
  chunk_count: number;
  memory_count: number;
}

export interface Memory {
  id: string;
  document_id: string;
  document_title?: string | null;
  chunk_id?: string | null;
  memory_type: MemoryType;
  statement: string;
  event_date_start?: string | null;
  event_date_end?: string | null;
  date_granularity: string;
  date_confidence: number;
  date_source: string;
  stance_polarity: number;
  sentiment: number;
  importance: number;
  entities: string[];
  topics: string[];
  pinned: boolean;
  created_at: string;
}

export interface DocDetail extends Doc {
  content: string;
  memories: Memory[];
}

export interface ChangePoint {
  id: string;
  subject: string;
  change_type: 'reversal' | 'intensified' | 'softened' | 'new_commitment' | 'direction_shift' | string;
  magnitude: number;
  earlier: Memory;
  later: Memory;
  from_date?: string | null;
  to_date?: string | null;
  uncertainty?: string | null;
}

export interface Relationship {
  id: string;
  source_memory_id: string;
  target_memory_id: string;
  relation_type: 'evolves_from' | 'contradicts' | 'supports' | 'follows' | 'related_to';
  confidence: number;
  rationale?: string | null;
  source?: Memory | null;
  target?: Memory | null;
}

export interface Citation {
  index: number;
  memory_id: string;
  document_id: string;
  document_title: string;
  statement: string;
  date?: string | null;
  memory_type: MemoryType;
  score: number;
}

export interface AnswerPayload {
  message_id?: string;
  query: string;
  intent: string;
  pipeline: string;
  answer: string;
  citations: Citation[];
  used_citations: number[];
  changes: ChangePoint[];
  contradictions: Relationship[];
  uncertainty_notes: string[];
  follow_ups: string[];
  year_range?: [number | null, number | null] | null;
  provider: string;
  timings_ms: Record<string, number>;
}

export interface Conversation {
  id: string;
  title: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  payload: Partial<AnswerPayload>;
  feedback: number;
  created_at: string;
}

export interface Insights {
  counts: Record<'documents' | 'memories' | 'words' | 'years' | 'changes' | 'contradictions' | 'entities', number>;
  span: { start?: string | null; end?: string | null };
  by_type: Record<string, number>;
  topics_by_year: Array<Record<string, number | string>>;
  top_topics: string[];
  top_entities: { name: string; count: number }[];
  mood: { month: string; value: number; count: number }[];
  heatmap: { date: string; count: number }[];
  on_this_day: Memory[];
  highlights: Memory[];
  pinned: Memory[];
  recent_changes: ChangePoint[];
  streak_days: number;
  recent_documents: Doc[];
}

export interface GraphData {
  nodes: Array<{
    id: string; label: string; statement: string; type: MemoryType; date?: string | null;
    document_title?: string; document_id: string; entities: string[]; topics: string[];
    stance: number; importance: number; degree: number;
  }>;
  edges: Array<{ id: string; source: string; target: string; type: Relationship['relation_type'];
    confidence: number; rationale?: string | null }>;
}

export interface Subject { name: string; kind: 'entity' | 'topic'; count: number; years: string[] }

export interface VersionDiff {
  series_name: string;
  earlier_version: string;
  later_version: string;
  earlier_document_id: string;
  later_document_id: string;
  added: string[];
  removed: string[];
  retained: string[];
  semantic_changes: { earlier_statement: string; later_statement: string; similarity: number; stance_delta: number }[];
  line_diff: { op: 'same' | 'added' | 'removed'; text: string }[];
  summary: string;
}

export interface BenchmarkRun {
  id: string;
  run_name: string;
  metrics: Record<string, Record<string, number | string>>;
  summary: string;
  created_at?: string;
}

export interface SystemStatus {
  llm: { provider: string; label: string };
  embeddings: { provider: string | null; notes: string[] };
  version: string;
  max_upload_mb: number;
}

export type UploadResult = { file: string; status: 'ok' | 'duplicate' | 'error'; detail?: string; document?: Doc; document_id?: string };
