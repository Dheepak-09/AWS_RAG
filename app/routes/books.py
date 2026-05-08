import os
import json
import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.services import rag_service
from app.models import ChatSession, Message, get_db
from app.auth import get_current_user, require_admin, StaticUser
from app.logger import get_logger
from app.schemas import (
    BookUploadResponse,
    BookItem,
    ChatRequest,
    DeleteResponse,
    IndexingStatusResponse,
)

load_dotenv()

router = APIRouter()
logger = get_logger(__name__)

MAX_UPLOAD_SIZE_MB    = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ---------------------------------------------------------------------------
# In-memory indexing status tracker
# { book_id: "processing" | "done" | "failed: ..." }
# ---------------------------------------------------------------------------
indexing_status: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Background indexing task
# ---------------------------------------------------------------------------
def run_indexing(pdf_path: str, book_id: str, tmp_dir: str):
    try:
        indexing_status[book_id] = "processing"
        logger.info(f"Background indexing started | book_id={book_id}")
        rag_service.index_book(pdf_path, book_id)
        indexing_status[book_id] = "done"
        logger.info(f"Background indexing complete | book_id={book_id}")
    except Exception as e:
        indexing_status[book_id] = f"failed: {str(e)}"
        logger.error(f"Background indexing failed | book_id={book_id} | error={e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# POST /books/upload — ADMIN ONLY
# ---------------------------------------------------------------------------
@router.post("/upload", response_model=BookUploadResponse)
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    admin: StaticUser = Depends(require_admin),
):
    """Upload a PDF book. Admin only."""
    logger.info(f"Upload request | filename='{file.filename}' | admin={admin.username}")

    if not file.filename.endswith(".pdf"):
        logger.warning(f"Rejected non-PDF | filename='{file.filename}'")
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    tmp_dir  = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, file.filename)

    try:
        content = await file.read()

        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            size_mb = len(content) / (1024 * 1024)
            logger.warning(f"Rejected oversized file | size={size_mb:.1f}MB | limit={MAX_UPLOAD_SIZE_MB}MB")
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {size_mb:.1f}MB. Maximum allowed is {MAX_UPLOAD_SIZE_MB}MB.",
            )

        with open(tmp_path, "wb") as f:
            f.write(content)
        logger.info(f"File saved | size={len(content)/(1024*1024):.1f}MB")

    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.error(f"File save failed | error={e}")
        raise HTTPException(status_code=500, detail=f"File save failed: {str(e)}")

    book_id   = rag_service.generate_book_id()
    book_name = os.path.splitext(file.filename)[0]

    indexing_status[book_id] = "processing"
    background_tasks.add_task(run_indexing, tmp_path, book_id, tmp_dir)

    logger.info(f"Upload accepted | book='{book_name}' | book_id={book_id}")

    return BookUploadResponse(
        message="Book uploaded. Indexing running in background. Poll GET /books/status/{book_id}.",
        book_id=book_id,
        book_name=book_name,
        total_chunks=0,
    )


# ---------------------------------------------------------------------------
# GET /books/status/{book_id} — ANY LOGGED IN USER
# ---------------------------------------------------------------------------
@router.get("/status/{book_id}", response_model=IndexingStatusResponse)
def get_indexing_status(
    book_id: str,
    current_user: StaticUser = Depends(get_current_user),
):
    logger.info(f"Status check | book_id={book_id} | user={current_user.username}")

    status = indexing_status.get(book_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"No indexing job found for book_id '{book_id}'.")

    chunks = rag_service.get_chunk_count(book_id) if status == "done" else 0
    return IndexingStatusResponse(book_id=book_id, status=status, chunks=chunks)


# ---------------------------------------------------------------------------
# GET /books/ — ANY LOGGED IN USER
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[BookItem])
def list_books(current_user: StaticUser = Depends(get_current_user)):
    logger.info(f"List books | user={current_user.username} | role={current_user.role}")
    try:
        return rag_service.list_books()
    except Exception as e:
        logger.error(f"list_books failed | error={e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /books/chat/stream — ANY LOGGED IN USER
# Streams tokens from Bedrock token by token via SSE
# ---------------------------------------------------------------------------
@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: StaticUser = Depends(get_current_user),
):
    """
    Streaming chat endpoint.
    Returns tokens one by one as Server Sent Events (SSE).
    Each event: data: {"token": "..."}
    Final event: data: {"done": true, "answer": "full answer"}
    Saves user message + full assistant answer to DB after streaming.
    """
    logger.info(f"Stream chat | session_id={request.session_id} | user={current_user.username}")

    # Load session
    session = db.query(ChatSession).filter(
        ChatSession.session_id == request.session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Users can only chat in their own sessions
    if current_user.role != "admin" and session.user_id != current_user.user_id:
        logger.warning(f"Unauthorized session access | user={current_user.username}")
        raise HTTPException(status_code=403, detail="You do not have access to this session.")

    book_id = session.book_id

    # Check indexing status
    status = indexing_status.get(book_id, "done")
    if status == "processing":
        raise HTTPException(status_code=400, detail="Book is still being indexed.")
    if status.startswith("failed"):
        raise HTTPException(status_code=500, detail=f"Indexing failed: {status}")

    if not rag_service.book_exists(book_id):
        raise HTTPException(status_code=404, detail="Book not found in vector DB.")

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # Load conversation history
    past_messages = (
        db.query(Message)
        .filter(Message.session_id == request.session_id)
        .order_by(Message.created_at)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in past_messages]

    # Save user message to DB before streaming starts
    db.add(Message(session_id=request.session_id, role="user", content=request.query))
    db.commit()
    logger.info(f"User message saved | session={request.session_id}")

    def generate():
        full_answer = ""
        try:
            for sse_line in rag_service.stream_query_with_history(
                query=request.query,
                book_id=book_id,
                history=history,
            ):
                # Parse to check for done signal
                if sse_line.startswith("data: "):
                    payload_str = sse_line[6:].strip()
                    try:
                        payload = json.loads(payload_str)
                        if payload.get("done"):
                            full_answer = payload.get("answer", "")
                    except Exception:
                        pass
                # Forward every SSE line to the client
                yield sse_line

        finally:
            # Save full assistant answer to DB after stream ends
            if full_answer:
                db.add(Message(
                    session_id=request.session_id,
                    role="assistant",
                    content=full_answer,
                ))
                db.commit()
                logger.info(f"Assistant message saved | session={request.session_id} | length={len(full_answer)}")

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# DELETE /books/{book_id} — ADMIN ONLY
# ---------------------------------------------------------------------------
@router.delete("/{book_id}", response_model=DeleteResponse)
def delete_book(
    book_id: str,
    admin: StaticUser = Depends(require_admin),
):
    logger.info(f"Delete book | book_id={book_id} | admin={admin.username}")

    if not rag_service.book_exists(book_id):
        raise HTTPException(status_code=404, detail=f"No book found with book_id '{book_id}'.")

    try:
        rag_service.delete_book(book_id)
        indexing_status.pop(book_id, None)
        logger.info(f"Book deleted | book_id={book_id}")
        return DeleteResponse(message="Book deleted successfully.", book_id=book_id)
    except Exception as e:
        logger.error(f"Delete failed | book_id={book_id} | error={e}")
        raise HTTPException(status_code=500, detail=str(e))