# B-Chat — Book Intelligence Platform

A full-stack RAG (Retrieval Augmented Generation) application that lets users upload PDF books and chat with them using AI. Built with FastAPI, PostgreSQL + pgvector, Amazon Bedrock, and a ChatGPT-style frontend.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Authentication](#authentication)
- [API Reference](#api-reference)
- [Database Schema](#database-schema)
- [How RAG Works](#how-rag-works)
- [Role Based Access Control](#role-based-access-control)
- [Streaming](#streaming)
- [Logging](#logging)
- [Database Migrations](#database-migrations)

---

## Overview

B-Chat allows users to upload PDF books and have intelligent conversations about their content. The system extracts text from PDFs, splits it into chunks, generates vector embeddings using Amazon Titan, stores them in PostgreSQL with pgvector, and retrieves relevant context using hybrid search (vector + keyword) when a user asks a question.

Answers are generated using Amazon Bedrock LLMs and streamed token by token to the frontend in real time.

---

## Architecture

```
User
 │
 ▼
Frontend (HTML/CSS/JS)
 │  HTTP Basic Auth on every request
 ▼
FastAPI Backend
 ├── Auth       → users.json (static RBAC)
 ├── Books      → upload, index, search, stream chat
 ├── Sessions   → conversation management
 └── Admin      → user and session management
 │
 ├── Amazon Bedrock
 │   ├── Titan Embeddings v2  → generates vector embeddings
 │   └── LLM (Llama4)         → generates answers
 │
 └── PostgreSQL + pgvector
     ├── rag_documents  → embeddings + full-text search index
     ├── sessions       → conversation sessions
     └── messages       → chat history
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.11+ |
| Database | PostgreSQL 15+ with pgvector extension |
| ORM | SQLAlchemy (sessions/messages) + psycopg2 (RAG table) |
| Embeddings | Amazon Titan Text Embeddings v2 (via Bedrock) |
| LLM | Meta Llama 4 Maverick (via Bedrock) |
| PDF Processing | PyMuPDF (fitz) |
| Text Splitting | LangChain RecursiveCharacterTextSplitter |
| Auth | HTTP Basic Auth + static users.json |
| Migrations | Alembic |
| Frontend | Vanilla HTML, CSS, JavaScript |
| Logging | Python logging with RotatingFileHandler |

---

## Project Structure

```
rag_backend/
│
├── start.py                   # One command startup script
├── main.py                    # FastAPI app, routers, middleware
├── frontend.html              # ChatGPT style frontend
├── users.json                 # Static user credentials and roles
├── .env                       # Environment variables
├── requirements.txt           # Python dependencies
├── alembic.ini                # Alembic migration config
│
├── logs/                      # Auto-created on first run
│   └── app.log                # Rotating log file
│
├── migrations/                # Alembic migration files
│   ├── env.py
│   └── versions/
│
└── app/
    ├── __init__.py
    ├── auth.py                # HTTP Basic Auth + role dependencies
    ├── database.py            # psycopg2 connection config
    ├── models.py              # SQLAlchemy ORM + pgvector DDL
    ├── schemas.py             # Pydantic request/response models
    ├── services.py            # RAG pipeline (embed, index, search, stream)
    ├── logger.py              # Logging setup (file + console)
    │
    └── routes/
        ├── __init__.py
        ├── auth.py            # GET /auth/me
        ├── books.py           # Upload, list, chat/stream, delete
        ├── sessions.py        # Create, list, get, delete sessions
        └── admin.py           # Admin only routes
```

---

## Prerequisites

Before running this project make sure you have:

- Python 3.11 or higher
- PostgreSQL 15+ with the pgvector extension installed
- An AWS account with Amazon Bedrock access enabled
- Access to the following Bedrock models in your AWS region:
  - `amazon.titan-embed-text-v2:0`
  - `us.meta.llama4-maverick-17b-instruct-v1:0`
- AWS credentials configured via `aws configure` or environment variables

---

## Setup & Installation

**Step 1 — Clone the repository**

```bash
git clone <your-repo-url>
cd rag_backend
```

**Step 2 — Create and activate a virtual environment**

```bash
# Windows
python -m venv env
env\Scripts\activate

# Mac/Linux
python -m venv env
source env/bin/activate
```

**Step 3 — Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 4 — Set up PostgreSQL**

Make sure PostgreSQL is running and the pgvector extension is available. Create your database:

```sql
CREATE DATABASE ragdb;
\c ragdb
CREATE EXTENSION vector;
```

**Step 5 — Configure environment variables**

Copy the `.env` file and fill in your values:

```bash
cp .env .env.local
```

See the [Configuration](#configuration) section for all required variables.

**Step 6 — Run database migrations**

```bash
alembic upgrade head
```

**Step 7 — Configure users**

Edit `users.json` to set your usernames, passwords, and roles:

```json
{
  "users": [
    { "username": "admin", "password": "your_admin_password", "role": "admin" },
    { "username": "john",  "password": "your_user_password",  "role": "user"  }
  ]
}
```

---

## Configuration

All configuration lives in the `.env` file at the project root.

```env
# PostgreSQL connection
PG_HOST=localhost
PG_PORT=5432
PG_DB=ragdb
PG_USER=postgres
PG_PASSWORD=your_password

# AWS Bedrock
AWS_REGION=us-east-1

# Embedding dimension — must match the pgvector column (256, 512, or 1024)
EMBEDDING_DIM=1024

# LLM model ID
MODEL_ID=us.meta.llama4-maverick-17b-instruct-v1:0

# Max PDF upload size in MB
MAX_UPLOAD_SIZE_MB=50

# JWT settings
JWT_SECRET=change_this_to_a_long_random_string
JWT_EXPIRE_HOURS=24
```

AWS credentials are read from `aws configure` (recommended) or from environment variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

---

## Running the Application

**Start everything with one command:**

```bash
python start.py
```

This will:
- Start the FastAPI backend on `http://127.0.0.1:8000`
- Start the frontend static server on `http://127.0.0.1:3000`
- Automatically open the browser at `http://127.0.0.1:3000/frontend.html`

**Or start the backend only:**

```bash
uvicorn main:app --reload
```

**API documentation** is available at `http://127.0.0.1:8000/docs` once the server is running.

---

## Authentication

Authentication uses HTTP Basic Auth with credentials defined in `users.json`. No registration is needed — users are statically configured.

**To login via the frontend:** open the app, enter your username and password on the login screen.

**To authenticate via API (Swagger UI):** click the Authorize button at the top of `/docs` and enter your username and password.

**To add a new user:** edit `users.json` and add a new entry. No restart needed — credentials are read on every request.

```json
{ "username": "newuser", "password": "password123", "role": "user" }
```

---

## API Reference

### Auth

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/auth/me` | Any | Returns currently authenticated user info |

### Books

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/books/upload` | Admin | Upload a PDF and start background indexing |
| GET | `/books/` | Any | List all indexed books |
| GET | `/books/status/{book_id}` | Any | Poll indexing progress |
| POST | `/books/chat/stream` | Any | Stream chat response token by token |
| DELETE | `/books/{book_id}` | Admin | Delete a book and all its chunks |

### Sessions

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/sessions` | Any | Create a new conversation session |
| GET | `/sessions` | Any | List your own sessions |
| GET | `/sessions/{session_id}` | Any | Get session with full message history |
| DELETE | `/sessions/{session_id}` | Any | Delete your own session |

### Admin

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/admin/users` | Admin | List all users from users.json |
| GET | `/admin/sessions` | Admin | List all sessions from all users |
| DELETE | `/admin/sessions/{session_id}` | Admin | Delete any session |

---

## Database Schema

### sessions

| Column | Type | Description |
|---|---|---|
| session_id | UUID | Primary key |
| book_id | TEXT | Which book this session is about |
| user_id | UUID | UUID derived from username |
| description | VARCHAR(255) | Optional session label |
| created_at | TIMESTAMP | Creation time |

### messages

| Column | Type | Description |
|---|---|---|
| message_id | UUID | Primary key |
| session_id | UUID | Foreign key to sessions |
| role | VARCHAR(20) | "user" or "assistant" |
| content | TEXT | Message content |
| created_at | TIMESTAMP | Creation time |

### rag_documents (managed by psycopg2, not ORM)

| Column | Type | Description |
|---|---|---|
| id | SERIAL | Primary key |
| book_id | TEXT | Which book this chunk belongs to |
| content | TEXT | The text chunk |
| embedding | vector(1024) | pgvector embedding |
| tsv | TSVECTOR | Auto-generated full-text search index |
| metadata | JSONB | book name, page number, book_id |

---

## How RAG Works

**Indexing (when a book is uploaded):**

1. PDF text is extracted page by page using PyMuPDF
2. Each page is split into overlapping chunks (500 tokens, 100 overlap)
3. Each chunk is embedded using Amazon Titan Text Embeddings v2
4. Chunks + embeddings are stored in the `rag_documents` table in PostgreSQL

**Retrieval (when a user asks a question):**

1. The query is embedded using the same Titan model
2. Vector search finds the most semantically similar chunks using cosine similarity
3. Keyword search finds chunks matching exact terms using PostgreSQL tsvector
4. Both results are merged and deduplicated (hybrid search)

**Generation:**

1. Retrieved chunks are formatted as context with book name and page numbers
2. Full conversation history from the session is loaded
3. Context + history + query are sent to the Bedrock LLM
4. The response streams back token by token

---

## Role Based Access Control

Users are defined in `users.json` with one of two roles:

**admin** can:
- Upload and delete books
- View all books
- Chat with books
- Create and manage their own sessions
- View all users and all sessions via admin panel
- Delete any session

**user** can:
- View all books
- Chat with books
- Create and manage their own sessions only

---

## Streaming

Chat responses are streamed token by token using Server Sent Events (SSE).

The backend uses `StreamingResponse` with `media_type="text/event-stream"`. Each token from Bedrock is yielded as:

```
data: {"token": "The"}
data: {"token": " book"}
data: {"token": " mentions"}
...
data: {"done": true, "answer": "The full response text"}
```

The frontend reads each SSE line, parses the JSON payload, and appends tokens to the message bubble in real time. The final `done` event triggers DB saving of the full response.

---

## Logging

Logs are written to both the console and `logs/app.log`.

The log file rotates automatically at 5MB and keeps the last 3 backup files.

Log format:
```
2026-05-08 10:23:01 | INFO     | app.routes.books | → POST /books/upload
2026-05-08 10:23:05 | INFO     | app.services     | Indexing complete | book_id=abc-123 | total_chunks=342
2026-05-08 10:25:12 | ERROR    | app.services     | Bedrock API error | error=...
```

---

## Database Migrations

This project uses Alembic for schema migrations.

**Apply all pending migrations:**
```bash
alembic upgrade head
```

**Generate a new migration after changing models.py:**
```bash
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

**Check current migration version:**
```bash
alembic current
```

**Undo the last migration:**
```bash
alembic downgrade -1
```
