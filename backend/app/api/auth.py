import re

from fastapi import APIRouter, HTTPException, Request

from app.core.security import ITERATIONS, CurrentUser, hash_password, login_limiter, password_check, verify_password
from app.models.schemas import AuthResponse, LoginRequest, PasswordChange, ProfileUpdate, RegisterRequest, UserOut
from app.storage.repo import Users

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_ACCOUNTS = [
    {"username": "alex_chen", "display_name": "Alex Chen", "blurb": "Systems engineer → AI researcher, 2019–2026",
     "avatar_color": "#8b9cff"},
    {"username": "sophia_taylor", "display_name": "Dr. Sophia Taylor", "blurb": "Wet-lab biologist → genomic AI lead, 2020–2026",
     "avatar_color": "#5eead4"},
    {"username": "marcus_vance", "display_name": "Marcus Vance", "blurb": "SaaS PM → AI venture founder, 2018–2026",
     "avatar_color": "#f0abfc"},
]
DEMO_PASSWORD = "password123"


@router.get("/demo-accounts")
def demo_accounts():
    return [{**a, "available": Users.raw_by_identifier(a["username"]) is not None, "password": DEMO_PASSWORD}
            for a in DEMO_ACCOUNTS]


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, request: Request):
    login_limiter.check(f"reg:{request.client.host if request.client else '?'}")
    username = re.sub(r"[^a-z0-9_.]", "_", req.username.strip().lower())
    email = req.email.strip().lower()
    if len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Please enter a valid email address.")
    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    if Users.raw_by_identifier(username):
        raise HTTPException(409, "That username is taken.")
    if Users.raw_by_identifier(email):
        raise HTTPException(409, "An account with that email already exists.")
    h, s = hash_password(req.password)
    user = Users.create(username, req.display_name.strip() or username, email, h, s, req.avatar_color,
                        (req.bio or "").strip() or None)
    return AuthResponse(token=Users.create_session(user.id), user=user)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request):
    login_limiter.check(f"login:{request.client.host if request.client else '?'}")
    raw = Users.raw_by_identifier(req.username_or_email.strip())
    matched = password_check(req.password, raw["password_hash"], raw["password_salt"]) \
        if raw and raw.get("password_hash") else None
    if matched is None:
        raise HTTPException(401, "That username/email and password don't match.")
    if matched != ITERATIONS:  # upgrade a legacy hash transparently
        h, s = hash_password(req.password)
        from app.core.database import get_db
        with get_db() as c:
            c.execute("UPDATE users SET password_hash=?, password_salt=? WHERE id=?", (h, s, raw["id"]))
    return AuthResponse(token=Users.create_session(raw["id"]), user=Users.get(raw["id"]))


@router.get("/me", response_model=UserOut)
def me(user=CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user=CurrentUser):
    if body.avatar_color and not re.match(r"^#[0-9a-fA-F]{6}$", body.avatar_color):
        raise HTTPException(400, "Colour must look like #a1b2c3.")
    return Users.update(user.id, display_name=(body.display_name or "").strip() or None, bio=body.bio,
                        avatar_color=body.avatar_color, preferences=body.preferences)


@router.post("/password")
def change_password(body: PasswordChange, user=CurrentUser):
    raw = Users.raw(user.id)
    if not verify_password(body.current_password, raw["password_hash"], raw["password_salt"]):
        raise HTTPException(400, "Current password is incorrect.")
    if len(body.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters.")
    h, s = hash_password(body.new_password)
    from app.core.database import get_db
    with get_db() as c:
        c.execute("UPDATE users SET password_hash=?, password_salt=? WHERE id=?", (h, s, user.id))
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, user=CurrentUser):
    Users.delete_session(request.state.token)
    return {"ok": True}


@router.delete("/me")
def delete_account(user=CurrentUser):
    Users.delete(user.id)
    return {"ok": True}
