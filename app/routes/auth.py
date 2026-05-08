from fastapi import APIRouter, Depends
from app.auth import get_current_user, StaticUser

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /auth/me
# Returns who is currently logged in
# ---------------------------------------------------------------------------
@router.get("/me")
def get_me(current_user: StaticUser = Depends(get_current_user)):
    """
    Returns the currently authenticated user's info.
    Use this to verify your credentials are working.
    """
    return {
        "username": current_user.username,
        "role":     current_user.role,
        "user_id":  str(current_user.user_id),
    }