from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    EVENT = "event"
    BELIEF = "belief"
    GOAL = "goal"
    DECISION = "decision"
    PREFERENCE = "preference"
    KNOWLEDGE = "knowledge"
    OBSERVATION = "observation"
    PLAN = "plan"
    REFLECTION = "reflection"
    FEELING = "feeling"


class DateGranularity(str, Enum):
    DAY = "day"
    MONTH = "month"
    SEASON = "season"
    YEAR = "year"
    UNRECORDED = "unrecorded"


class DateSource(str, Enum):
    EXPLICIT_IN_TEXT = "explicit_in_text"
    DOC_METADATA = "doc_metadata"
    RELATIVE_INFERRED = "relative_inferred"
    USER_OVERRIDE = "user_override"


class RelationType(str, Enum):
    EVOLVES_FROM = "evolves_from"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    FOLLOWS = "follows"
    RELATED_TO = "related_to"


class QueryIntent(str, Enum):
    FACT_LOOKUP = "FACT_LOOKUP"
    TEMPORAL_LOOKUP = "TEMPORAL_LOOKUP"
    EVOLUTION_ANALYSIS = "EVOLUTION_ANALYSIS"
    TIMELINE_REQUEST = "TIMELINE_REQUEST"
    CHANGE_POINT_ANALYSIS = "CHANGE_POINT_ANALYSIS"
    CONTRADICTION_ANALYSIS = "CONTRADICTION_ANALYSIS"
    VERSION_COMPARISON = "VERSION_COMPARISON"
    STABLE_PATTERN_ANALYSIS = "STABLE_PATTERN_ANALYSIS"
    SUMMARY = "SUMMARY"


# ---------------- Users & auth ----------------
class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    display_name: str = ""
    bio: Optional[str] = None
    avatar_color: str = "#8b9cff"


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    email: Optional[str] = None
    avatar_color: str
    bio: Optional[str] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    document_count: int = 0
    memory_count: int = 0
    earliest_memory_date: Optional[str] = None
    latest_memory_date: Optional[str] = None


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_color: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


# ---------------- Documents ----------------
class NoteCreate(BaseModel):
    title: str = ""
    content: str
    document_date: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    document_date: Optional[str] = None
    tags: Optional[List[str]] = None
    favorite: Optional[bool] = None
    series_name: Optional[str] = None
    version_label: Optional[str] = None


class DocumentOut(BaseModel):
    id: str
    user_id: str
    title: str
    source_type: str
    file_name: Optional[str] = None
    file_type: str
    file_size: int
    document_date: Optional[str] = None
    date_confidence: float = 0
    word_count: int = 0
    tags: List[str] = Field(default_factory=list)
    favorite: bool = False
    series_name: Optional[str] = None
    version_label: Optional[str] = None
    excerpt: str = ""
    created_at: str
    updated_at: str
    chunk_count: int = 0
    memory_count: int = 0


class DocumentDetail(DocumentOut):
    content: str
    memories: List["MemoryOut"] = Field(default_factory=list)


# ---------------- Memories ----------------
class MemoryOut(BaseModel):
    id: str
    user_id: str
    document_id: str
    document_title: Optional[str] = None
    chunk_id: Optional[str] = None
    memory_type: MemoryType
    statement: str
    event_date_start: Optional[str] = None
    event_date_end: Optional[str] = None
    date_granularity: DateGranularity = DateGranularity.UNRECORDED
    date_confidence: float = 0
    date_source: DateSource = DateSource.DOC_METADATA
    stance_polarity: float = 0
    sentiment: float = 0
    importance: float = 0.5
    entities: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    pinned: bool = False
    created_at: str


class MemoryCapture(BaseModel):
    statement: str
    memory_type: Optional[MemoryType] = None
    event_date: Optional[str] = None
    context_note: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class MemoryUpdate(BaseModel):
    statement: Optional[str] = None
    memory_type: Optional[MemoryType] = None
    event_date: Optional[str] = None
    pinned: Optional[bool] = None


class MemoryPage(BaseModel):
    items: List[MemoryOut]
    total: int


# ---------------- Analysis ----------------
class ChangePointOut(BaseModel):
    id: str
    subject: str
    change_type: str
    magnitude: float
    earlier: MemoryOut
    later: MemoryOut
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    uncertainty: Optional[str] = None


class RelationshipOut(BaseModel):
    id: str
    source_memory_id: str
    target_memory_id: str
    relation_type: RelationType
    confidence: float
    rationale: Optional[str] = None
    source: Optional[MemoryOut] = None
    target: Optional[MemoryOut] = None


class VersionDiffOut(BaseModel):
    series_name: str
    earlier_version: str
    later_version: str
    earlier_document_id: str
    later_document_id: str
    added: List[str]
    removed: List[str]
    retained: List[str]
    semantic_changes: List[Dict[str, Any]]
    line_diff: List[Dict[str, Any]]
    summary: str


# ---------------- Chat & query ----------------
class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    pipeline_mode: str = "memory_lane"  # baseline | temporal | memory_lane
    filter_start_year: Optional[int] = None
    filter_end_year: Optional[int] = None
    filter_memory_types: Optional[List[MemoryType]] = None
    top_k: int = 12


class Citation(BaseModel):
    index: int
    memory_id: str
    document_id: str
    document_title: str
    statement: str
    date: Optional[str] = None
    memory_type: str
    score: float = 0


class AnswerPayload(BaseModel):
    query: str
    intent: QueryIntent
    pipeline: str
    answer: str
    citations: List[Citation]
    used_citations: List[int] = Field(default_factory=list)
    changes: List[ChangePointOut] = Field(default_factory=list)
    contradictions: List[RelationshipOut] = Field(default_factory=list)
    uncertainty_notes: List[str] = Field(default_factory=list)
    follow_ups: List[str] = Field(default_factory=list)
    year_range: Optional[List[int]] = None
    provider: str = "offline"
    timings_ms: Dict[str, float] = Field(default_factory=dict)


class ConversationOut(BaseModel):
    id: str
    title: str
    pinned: bool = False
    created_at: str
    updated_at: str
    message_count: int = 0
    preview: str = ""


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    feedback: int = 0
    created_at: str


class ConversationDetail(ConversationOut):
    messages: List[MessageOut]


class BenchmarkRequest(BaseModel):
    run_name: str = "Benchmark Run"
    pipelines: List[str] = ["baseline", "temporal", "memory_lane"]


DocumentDetail.model_rebuild()
