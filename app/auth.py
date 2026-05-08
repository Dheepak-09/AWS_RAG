import os
import json
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# HTTP Basic Auth scheme
# — FastAPI shows a username/password popup in /docs automatically
# ---------------------------------------------------------------------------
security = HTTPBasic()

# ---------------------------------------------------------------------------
# Path to users.json at project root
# ---------------------------------------------------------------------------
USERS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "users.json")

# ---------------------------------------------------------------------------
# UUID namespace — uuid5 always gives same UUID for same username
# ---------------------------------------------------------------------------
UUID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")

def username_to_uuid(username: str) -> uuid.UUID:
    return uuid.uuid5(UUID_NAMESPACE, username)


# ---------------------------------------------------------------------------
# StaticUser — simulates a user object, works with all existing route code
# ---------------------------------------------------------------------------
@dataclass
class StaticUser:
    user_id:  uuid.UUID
    username: str
    role:     str

    @property
    def email(self) -> str:
        return self.username


# ---------------------------------------------------------------------------
# Load users from users.json
# ---------------------------------------------------------------------------
def load_users() -> list[dict]:
    if not os.path.exists(USERS_FILE):
        logger.error(f"users.json not found at {USERS_FILE}")
        raise RuntimeError("users.json not found.")
    with open(USERS_FILE, "r") as f:
        return json.load(f).get("users", [])


# ---------------------------------------------------------------------------
# get_current_user — checks username + password on every request
# ---------------------------------------------------------------------------
def get_current_user(credentials: HTTPBasicCredentials = Depends(security)) -> StaticUser:
    """
    Reads username + password from the request.
    Checks against users.json.
    Returns StaticUser with role attached.
    Raises 401 if credentials are wrong.
    """
    users = load_users()

    # Find matching user
    matched = next(
        (u for u in users if u["username"] == credentials.username),
        None
    )

    if not matched or matched["password"] != credentials.password:
        logger.warning(f"Login failed | username={credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.info(f"Authenticated | username={credentials.username} | role={matched['role']}")

    return StaticUser(
        user_id=username_to_uuid(credentials.username),
        username=credentials.username,
        role=matched["role"],
    )


# ---------------------------------------------------------------------------
# require_admin — blocks non-admin users with 403
# ---------------------------------------------------------------------------
def require_admin(current_user: StaticUser = Depends(get_current_user)) -> StaticUser:
    """
    Depends on get_current_user.
    Raises 403 if role is not admin.
    """
    if current_user.role != "admin":
        logger.warning(f"Admin route blocked | username={current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user