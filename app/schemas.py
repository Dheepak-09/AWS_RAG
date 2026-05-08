from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid


# ---------------------------------------------------------------------------
# Book schemas
# ---------------------------------------------------------------------------

class BookUploadResponse(BaseModel):
    message: str
    book_id: str
    book_name: str
    total_chunks: int


class IndexingStatusResponse(BaseModel):
    book_id: str
    status: str       # "processing" | "done" | "failed: ..."
    chunks: int


class BookItem(BaseModel):
    book_id: str
    book_name: Optional[str]
    chunks: int


class DeleteResponse(BaseModel):
    message: str
    book_id: str


# ---------------------------------------------------------------------------
# Session schemas
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    book_id: str
    description: Optional[str] = None


class MessageResponse(BaseModel):
    message_id: uuid.UUID
    session_id: uuid.UUID
    role: str           # "user" or "assistant"
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    session_id: uuid.UUID
    book_id: str
    description: Optional[str]
    created_at: datetime
    messages: list[MessageResponse] = []

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Chat schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: uuid.UUID   # session carries book_id — no need to pass book_id separately
    query: str


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    book_id: str
    query: str
    answer: str