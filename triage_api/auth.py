"""JWT authentication.

Lesson reference: Monday Lessons 5 and 6.
- /token: username + password (form-encoded, OAuth2PasswordRequestForm) -> JWT.
- Authorization: Bearer <token> on every protected route.
- 401 on missing / invalid / expired token.
- 403 on valid token but wrong role.

Production note: JWT_SECRET must be injected at runtime via env. The
Dockerfile never contains a secret. In production, put the API behind
HTTPS so the Bearer token does not travel in cleartext.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from resolve_secrets import resolve

# tokenUrl is what Swagger UI's "Authorize" button calls.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Week 9: no default secret any more. resolve() raises RuntimeError at
# import time when JWT_SECRET is missing - boot fails closed, and the
# message names the key, never a value. tests/conftest.py injects a
# per-session test secret; docker-compose.yml declares ${JWT_SECRET}
# with no default, so the deploy layer fails closed too.
JWT_SECRET = resolve("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "30"))

# Demo credentials. In production these live in a secret manager.
# Env vars are AFIYA_-prefixed: a bare USERNAME collides with the
# Windows/macOS login name and silently breaks the demo users.
USERNAME = os.getenv("AFIYA_USERNAME", "olu")
PASSWORD = os.getenv("AFIYA_PASSWORD", "olu-pass")

# role table for /token -> the user gets one role at login.
_ROLE_FOR_USER: dict[str, str] = {
    USERNAME: "triage_nurse",
    "dispatcher": "dispatcher",
}


# ---------------------------------------------------------------------------
# credential check + token issuance
# ---------------------------------------------------------------------------

def authenticate(username: str, password: str) -> Optional[dict]:
    """Return a token payload dict if creds are valid, else None."""
    # Two demo users - dispatcher has the agent role.
    users = {
        USERNAME: (PASSWORD, "triage_nurse"),
        "dispatcher": ("dispatcher-pass", "dispatcher"),
    }
    record = users.get(username)
    if not record or record[0] != password:
        return None
    return {"sub": username, "role": record[1]}


def create_access_token(subject: str, role: str,
                        expires_minutes: int = JWT_EXPIRES_MINUTES) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Decode and validate the JWT. Raises 401 on any failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token missing subject",
        )
    return payload


def require_role(required: str):
    """Factory: returns a dependency that 403s if the user's role mismatches."""
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") != required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{required}' required, got '{user.get('role')}'",
            )
        return user
    return _dep


# Form dependency alias keeps app.py imports short.
TokenForm = OAuth2PasswordRequestForm