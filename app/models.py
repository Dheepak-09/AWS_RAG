import os
import uuid
from datetime import datetime

from sqlalchemy import (
    create_engine, Column, String, Text, DateTime, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from dotenv import load_dotenv

from app.database import get_connection

load_dotenv()

# ---------------------------------------------------------------------------
# SQLAlchemy engine
# ---------------------------------------------------------------------------
PG_HOST     = os.getenv("PG_HOST", "localhost")
PG_PORT     = os.getenv("PG_PORT", "5432")
PG_DB       = os.getenv("PG_DB", "ragdb")
PG_USER     = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

engine       = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base         = declarative_base()


# ---------------------------------------------------------------------------
# ChatSession model
# ---------------------------------------------------------------------------
class ChatSession(Base):
    """
    One row per conversation session.
    Tied to one book (book_id) and one user (user_id).
    user_id is a UUID derived from the username in users.json.
    No FK to users table since users are static JSON, not DB rows.
    """
    __tablename__ = "sessions"

    session_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id     = Column(String, nullable=False)
    user_id     = Column(UUID(as_uuid=True), nullable=False)  # no FK — users are in JSON
    description = Column(String(255), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Message model
# ---------------------------------------------------------------------------
class Message(Base):
    """One row per chat message (user or assistant)."""
    __tablename__ = "messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False)
    role       = Column(String(20), nullable=False)   # "user" or "assistant"
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


# ---------------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Create all tables on startup
# ---------------------------------------------------------------------------
def create_tables():
    """
    Creates:
    1. sessions, messages via SQLAlchemy ORM
    2. rag_documents + pgvector indexes via raw psycopg2
    Fully idempotent.
    """
    Base.metadata.create_all(bind=engine)
    print("SQLAlchemy tables ready: sessions, messages")

    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
    TABLE = "rag_documents"

    conn = get_connection()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id        SERIAL PRIMARY KEY,
                    book_id   TEXT   NOT NULL,
                    content   TEXT   NOT NULL,
                    embedding vector({EMBEDDING_DIM}),
                    tsv       TSVECTOR GENERATED ALWAYS AS
                              (to_tsvector('english', content)) STORED,
                    metadata  JSONB  NOT NULL DEFAULT '{{}}'::jsonb
                );
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {TABLE}_book_id_idx
                ON {TABLE} (book_id);
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {TABLE}_emb_idx
                ON {TABLE}
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {TABLE}_tsv_idx
                ON {TABLE} USING GIN (tsv);
            """)
        print(f"pgvector table ready: {TABLE}")
    finally:
        conn.close()