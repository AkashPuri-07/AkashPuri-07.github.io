"""
FastAPI backend for Akash Puri's portfolio.

Provides:
  - Emergent-managed Google OAuth (session_id → httpOnly session_token cookie)
  - Admin allow-list (env var ADMIN_EMAILS)
  - Public + admin CRUD endpoints for Journal posts
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Cookie, Depends, FastAPI, Header, HTTPException, Request, Response, status
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
EMERGENT_AUTH_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
SESSION_COOKIE = "session_token"
SESSION_TTL_DAYS = 7

# Emergent-managed Resend email (constants — do NOT read base URL from env)
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Akash Puri")
CONTACT_INBOX = os.environ.get("CONTACT_INBOX", "akashpuri7@gmail.com")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Akash Puri Portfolio API")
api = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: str = ""
    role: str = "viewer"  # "admin" or "viewer"


class Post(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    slug: str
    title: str
    date: str  # ISO date "YYYY-MM-DD" or human-friendly
    excerpt: str = ""
    body: str = ""  # markdown
    imageURL: str = ""
    postLink: str = ""
    tags: List[str] = Field(default_factory=list)
    published: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PostInput(BaseModel):
    slug: str
    title: str
    date: str
    excerpt: str = ""
    body: str = ""
    imageURL: str = ""
    postLink: str = ""
    tags: List[str] = Field(default_factory=list)
    published: bool = False


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    message: str
    read: bool = False
    email_sent: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MessageInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
async def _get_session_token(request: Request, authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    """Session token from httpOnly cookie first, Authorization header fallback."""
    tok = request.cookies.get(SESSION_COOKIE)
    if tok:
        return tok
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


async def get_current_user(request: Request, authorization: Optional[str] = Header(default=None)) -> User:
    token = await _get_session_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    return User(**user_doc)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
@api.post("/auth/session")
async def create_session(response: Response, x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID")):
    """Exchange Emergent session_id for our own session_token cookie."""
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Missing X-Session-ID header")

    async with httpx.AsyncClient(timeout=15.0) as hc:
        r = await hc.get(EMERGENT_AUTH_URL, headers={"X-Session-ID": x_session_id})
    if r.status_code != 200:
        logger.warning("Emergent auth failed: %s %s", r.status_code, r.text[:200])
        raise HTTPException(status_code=401, detail="OAuth session invalid")

    data = r.json()
    email = data.get("email", "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="No email in session data")

    role = "admin" if email in ADMIN_EMAILS else "viewer"
    if role != "admin":
        # Enforce allow-list: block non-admin sign-in entirely for this app.
        raise HTTPException(status_code=403, detail="Access restricted to site owner")

    # Upsert user
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": data.get("name", existing.get("name", "")),
                      "picture": data.get("picture", existing.get("picture", "")),
                      "role": role}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": data.get("name", ""),
            "picture": data.get("picture", ""),
            "role": role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # Create session
    session_token = data.get("session_token") or uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    return {"email": email, "name": data.get("name", ""), "picture": data.get("picture", ""), "role": role}


@api.get("/auth/me", response_model=User)
async def me(user: User = Depends(get_current_user)):
    return user


@api.post("/auth/logout")
async def logout(request: Request, response: Response, authorization: Optional[str] = Header(default=None)):
    token = await _get_session_token(request, authorization)
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="none", secure=True)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Journal posts — public endpoints
# ---------------------------------------------------------------------------
async def _next_available_slug(slug: str, exclude_id: Optional[str] = None) -> str:
    """Ensure slug is unique. Suffix -2, -3 if needed."""
    base = slug or f"post-{uuid.uuid4().hex[:6]}"
    candidate = base
    i = 2
    while True:
        q = {"slug": candidate}
        if exclude_id:
            q["id"] = {"$ne": exclude_id}
        existing = await db.posts.find_one(q, {"_id": 0, "id": 1})
        if not existing:
            return candidate
        candidate = f"{base}-{i}"
        i += 1


@api.get("/posts", response_model=List[Post])
async def list_public_posts():
    docs = await db.posts.find({"published": True}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Post(**d) for d in docs]


@api.get("/posts/{slug}", response_model=Post)
async def get_public_post(slug: str):
    doc = await db.posts.find_one({"slug": slug, "published": True}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return Post(**doc)


# ---------------------------------------------------------------------------
# Journal posts — admin endpoints
# ---------------------------------------------------------------------------
@api.get("/admin/posts", response_model=List[Post])
async def admin_list_posts(_: User = Depends(require_admin)):
    docs = await db.posts.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [Post(**d) for d in docs]


@api.get("/admin/posts/{post_id}", response_model=Post)
async def admin_get_post(post_id: str, _: User = Depends(require_admin)):
    doc = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return Post(**doc)


@api.post("/admin/posts", response_model=Post)
async def admin_create_post(payload: PostInput, _: User = Depends(require_admin)):
    slug = await _next_available_slug(payload.slug)
    post = Post(slug=slug, **{k: v for k, v in payload.model_dump().items() if k != "slug"})
    await db.posts.insert_one(post.model_dump())
    return post


@api.put("/admin/posts/{post_id}", response_model=Post)
async def admin_update_post(post_id: str, payload: PostInput, _: User = Depends(require_admin)):
    existing = await db.posts.find_one({"id": post_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")
    slug = await _next_available_slug(payload.slug, exclude_id=post_id)
    updates = payload.model_dump()
    updates["slug"] = slug
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.posts.update_one({"id": post_id}, {"$set": updates})
    doc = await db.posts.find_one({"id": post_id}, {"_id": 0})
    return Post(**doc)


@api.delete("/admin/posts/{post_id}")
async def admin_delete_post(post_id: str, _: User = Depends(require_admin)):
    result = await db.posts.delete_one({"id": post_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"ok": True, "id": post_id}


# ---------------------------------------------------------------------------
# Contact messages — public submit + admin management
# ---------------------------------------------------------------------------
def _build_contact_email_html(name: str, email: str, message: str, created_at: str) -> str:
    safe_message = (message or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    return f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f6f4ef;font-family:'Helvetica Neue',Arial,sans-serif;color:#14130f;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f6f4ef;padding:40px 20px;">
    <tr><td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 12px 32px -12px rgba(120,100,60,0.2);">
        <tr><td style="background:linear-gradient(135deg,#d4b47a,#8f7443);padding:24px 32px;">
          <div style="color:#fff;font-size:12px;letter-spacing:0.24em;text-transform:uppercase;font-weight:600;">Portfolio · New message</div>
          <div style="color:#fff;font-family:Georgia,serif;font-size:24px;font-weight:600;margin-top:8px;">You have a new inquiry</div>
        </td></tr>
        <tr><td style="padding:32px;">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
            <tr><td style="padding:8px 0;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:#8a857b;">From</td></tr>
            <tr><td style="padding:0 0 16px;font-size:16px;color:#14130f;font-weight:600;">{name}<br>
              <a href="mailto:{email}" style="color:#8f7443;font-weight:500;text-decoration:none;font-size:14px;">{email}</a>
            </td></tr>
            <tr><td style="padding:8px 0;font-size:12px;letter-spacing:0.14em;text-transform:uppercase;color:#8a857b;border-top:1px solid rgba(20,19,15,0.08);">Message</td></tr>
            <tr><td style="padding:0 0 16px;font-size:15px;line-height:1.6;color:#4a4740;">{safe_message}</td></tr>
            <tr><td style="padding:16px 0 0;border-top:1px solid rgba(20,19,15,0.08);font-size:12px;color:#8a857b;">Received {created_at}</td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:20px 32px;background:#f6f4ef;text-align:center;font-size:12px;color:#8a857b;">
          Sent from your portfolio contact form · <a href="mailto:{email}" style="color:#8f7443;text-decoration:none;">Reply directly</a>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


async def _send_contact_email(msg: Message) -> bool:
    if not EMAIL_KEY:
        logger.warning("EMERGENT_EMAIL_KEY not set — skipping email send")
        return False
    payload = {
        "to": [CONTACT_INBOX],
        "subject": f"New portfolio message from {msg.name}",
        "html": _build_contact_email_html(msg.name, msg.email, msg.message, msg.created_at),
        "from_name": EMAIL_FROM_NAME,
        "contact_email": msg.email,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as hc:
            r = await hc.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json=payload,
            )
        r.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        logger.error("Email send failed: %s %s", e.response.status_code, e.response.text[:200])
        return False
    except Exception as e:
        logger.error("Email send error: %s", e)
        return False


@api.post("/messages", response_model=Message)
async def submit_message(payload: MessageInput):
    msg = Message(**payload.model_dump())
    doc = msg.model_dump()
    await db.messages.insert_one(doc)

    # Try to send the email; update the row with the outcome but never fail the request on email trouble.
    email_ok = await _send_contact_email(msg)
    if email_ok:
        await db.messages.update_one({"id": msg.id}, {"$set": {"email_sent": True}})
        msg.email_sent = True
    return msg


@api.get("/admin/messages", response_model=List[Message])
async def admin_list_messages(_: User = Depends(require_admin)):
    docs = await db.messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [Message(**d) for d in docs]


@api.get("/admin/messages/unread-count")
async def admin_unread_count(_: User = Depends(require_admin)):
    count = await db.messages.count_documents({"read": False})
    return {"unread": count}


@api.patch("/admin/messages/{msg_id}", response_model=Message)
async def admin_toggle_read(msg_id: str, payload: dict, _: User = Depends(require_admin)):
    if "read" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'read' field")
    result = await db.messages.update_one({"id": msg_id}, {"$set": {"read": bool(payload["read"])}})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Message not found")
    doc = await db.messages.find_one({"id": msg_id}, {"_id": 0})
    return Message(**doc)


@api.delete("/admin/messages/{msg_id}")
async def admin_delete_message(msg_id: str, _: User = Depends(require_admin)):
    result = await db.messages.delete_one({"id": msg_id})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True, "id": msg_id}


# ---------------------------------------------------------------------------
# Health + seed
# ---------------------------------------------------------------------------
@api.get("/")
async def root():
    return {"name": "Akash Puri Portfolio API", "status": "ok"}


DEFAULT_POSTS = [
    {
        "slug": "under-pacing-diagnostic-not-bid",
        "title": "Why Under-Pacing Is a Diagnostic Problem, Not a Bid Problem",
        "date": "March 12, 2025",
        "excerpt": "Everyone reaches for bid multipliers first. In most cases, the fix is upstream — in inventory, frequency caps or creative rotation. Here's the audit I run before I touch a single bid.",
        "body": "# Full article body\n\nAdd markdown content here.",
        "imageURL": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=900&auto=format&fit=crop&q=75",
        "postLink": "#",
        "tags": ["DV360", "Pacing", "Diagnostics"],
        "published": True,
    },
    {
        "slug": "reading-dv360-report-as-media-planner",
        "title": "Reading a DV360 Report Like a Media Planner, Not an Ops Person",
        "date": "February 4, 2025",
        "excerpt": "The default columns tell you the campaign ran. The right columns tell you whether it worked. A short guide to the seven views I keep on my second monitor.",
        "body": "# Full article body\n\nAdd markdown content here.",
        "imageURL": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=900&auto=format&fit=crop&q=75",
        "postLink": "#",
        "tags": ["DV360", "Reporting"],
        "published": True,
    },
    {
        "slug": "floodlight-hygiene",
        "title": "The Quiet Discipline of Floodlight Hygiene",
        "date": "January 18, 2025",
        "excerpt": "Bad tags don't announce themselves. They just quietly attribute the wrong conversions to the wrong campaigns until someone gets fired. A short primer on keeping your tracking house in order.",
        "body": "# Full article body\n\nAdd markdown content here.",
        "imageURL": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=900&auto=format&fit=crop&q=75",
        "postLink": "#",
        "tags": ["Floodlight", "Tracking"],
        "published": True,
    },
]


@app.on_event("startup")
async def seed_if_empty():
    count = await db.posts.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc)
        docs = []
        for i, p in enumerate(DEFAULT_POSTS):
            post = Post(**p)
            d = post.model_dump()
            # Preserve chronological insertion so listing sorted by created_at desc is stable.
            d["created_at"] = (now - timedelta(seconds=i)).isoformat()
            d["updated_at"] = d["created_at"]
            docs.append(d)
        await db.posts.insert_many(docs)
        logger.info("Seeded %d default posts", len(docs))


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# ---------------------------------------------------------------------------
# Wire up
# ---------------------------------------------------------------------------
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
