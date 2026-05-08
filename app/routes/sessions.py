import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models import ChatSession, get_db
from app.auth import get_current_user, StaticUser
from app.schemas import SessionCreate, SessionResponse
from app.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# POST /sessions
# ---------------------------------------------------------------------------
@router.post("", response_model=SessionResponse)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    current_user: StaticUser = Depends(get_current_user),
):
    """Create a new session tied to the logged-in user."""
    logger.info(f"Create session | book_id={payload.book_id} | user={current_user.username}")
    try:
        session = ChatSession(
            book_id=payload.book_id,
            user_id=current_user.user_id,       # UUID generated from username
            description=payload.description,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info(f"Session created | session_id={session.session_id}")
        return session
    except Exception as e:
        logger.error(f"Create session failed | error={e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------
@router.get("", response_model=list[SessionResponse])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: StaticUser = Depends(get_current_user),
):
    """Returns own sessions only. Admin sees all via GET /admin/sessions."""
    logger.info(f"List sessions | user={current_user.username} | role={current_user.role}")
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.user_id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )
    logger.info(f"Returning {len(sessions)} sessions")
    return sessions


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}
# ---------------------------------------------------------------------------
@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: StaticUser = Depends(get_current_user),
):
    logger.info(f"Get session | session_id={session_id} | user={current_user.username}")

    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Users can only access their own sessions
    if current_user.role != "admin" and session.user_id != current_user.user_id:
        logger.warning(f"Unauthorized session access | user={current_user.username}")
        raise HTTPException(status_code=403, detail="You do not have access to this session.")

    session.messages = sorted(session.messages, key=lambda m: m.created_at)
    return session


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}
# ---------------------------------------------------------------------------
@router.delete("/{session_id}")
def delete_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: StaticUser = Depends(get_current_user),
):
    logger.info(f"Delete session | session_id={session_id} | user={current_user.username}")

    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if current_user.role != "admin" and session.user_id != current_user.user_id:
        logger.warning(f"Unauthorized delete | user={current_user.username}")
        raise HTTPException(status_code=403, detail="You can only delete your own sessions.")

    db.delete(session)
    db.commit()
    logger.info(f"Session deleted | session_id={session_id}")
    return {"message": "Session deleted.", "session_id": str(session_id)}