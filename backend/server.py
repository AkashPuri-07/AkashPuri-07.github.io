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
