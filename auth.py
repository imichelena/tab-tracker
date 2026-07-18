"""Session-based auth using Starlette SessionMiddleware + passlib."""
import hmac
import hashlib
from starlette.requests import Request
from config import SECRET_KEY, SESSION_COOKIE_NAME


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), stored_hash)


def get_current_user(request: Request) -> dict | None:
    """Read user info from session."""
    session = request.session if hasattr(request, "session") else {}
    if session.get("user_id"):
        return {
            "id": session["user_id"],
            "username": session["username"],
            "display_name": session["display_name"],
            "is_admin": session.get("is_admin", False),
        }
    return None
