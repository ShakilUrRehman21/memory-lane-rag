"""Password hashing, session tokens, auth dependency and a small login rate limiter."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import Depends, Header, HTTPException, Query, Request

ITERATIONS = 200_000
LEGACY_ITERATIONS = 100_000  # accounts created before v2


def hash_password(password: str, salt: Optional[bytes] = None, iterations: int = ITERATIONS) -> Tuple[str, str]:
    salt = salt or os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return key.hex(), salt.hex()


def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    return password_check(password, stored_hash, stored_salt) is not None


def password_check(password: str, stored_hash: str, stored_salt: str) -> Optional[int]:
    """Returns the iteration count that matched (so legacy hashes can be upgraded), or None."""
    try:
        salt = bytes.fromhex(stored_salt)
        for it in (ITERATIONS, LEGACY_ITERATIONS):
            if hmac.compare_digest(hash_password(password, salt, it)[0], stored_hash):
                return it
    except Exception:
        pass
    return None


def generate_token() -> str:
    return secrets.token_urlsafe(32)


class RateLimiter:
    """Sliding-window limiter keyed by client address."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s
        self.hits: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        from app.core.config import settings
        if settings.TESTING:
            return
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")
        q.append(now)


login_limiter = RateLimiter(limit=12, window_s=60)


def _token_from(authorization: Optional[str], token_q: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return token_q


def current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None, include_in_schema=False),
):
    """Resolve the signed-in user from the bearer token (or ?token= for download links)."""
    from app.storage.repo import Users

    tok = _token_from(authorization, token)
    if not tok:
        raise HTTPException(401, "Please sign in.")
    user = Users.by_session(tok)
    if not user:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    request.state.token = tok
    return user


CurrentUser = Depends(current_user)
