import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import ChatSession, Message, get_db
from app.auth import require_admin, load_users, StaticUser
from app.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------
@router.get("/users")
def list_users(admin: StaticUser = Depends(require_admin)):
    """Returns all users from users.json. Passwords hidden. Admin only."""
    logger.info(f"List users | requested_by={admin.username}")
    users = load_users()
    return [{"username": u["username"], "role": u["role"]} for u in users]


# ---------------------------------------------------------------------------
# GET /admin/sessions
# ---------------------------------------------------------------------------
@router.get("/sessions")
def list_all_sessions(
    db: Session = Depends(get_db),
    admin: StaticUser = Depends(require_admin),
):
    """Returns all sessions from all users. Admin only."""
    logger.info(f"List all sessions | requested_by={admin.username}")

    # Use a JOIN with COUNT to avoid lazy loading s.messages
    results = (
        db.query(
            ChatSession,
            func.count(Message.message_id).label("message_count")
        )
        .outerjoin(Message, Message.session_id == ChatSession.session_id)
        .group_by(ChatSession.session_id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )

    logger.info(f"Returning {len(results)} sessions")

    return [
        {
            "session_id":    str(s.session_id),
            "book_id":       s.book_id,
            "user_id":       str(s.user_id),
            "description":   s.description,
            "created_at":    s.created_at,
            "message_count": count,
        }
        for s, count in results
    ]


# ---------------------------------------------------------------------------
# DELETE /admin/sessions/{session_id}
# ---------------------------------------------------------------------------
@router.delete("/sessions/{session_id}")
def delete_any_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: StaticUser = Depends(require_admin),
):
    """Delete any user's session. Admin only."""
    logger.info(f"Admin delete session | session_id={session_id} | by={admin.username}")

    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    db.delete(session)
    db.commit()
    logger.info(f"Session deleted by admin | session_id={session_id}")
    return {"message": "Session deleted.", "session_id": str(session_id)}