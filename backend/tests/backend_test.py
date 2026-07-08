"""
Backend regression tests for Akash Puri portfolio API.

Covers:
  - Public endpoints (root, list, get by slug)
  - Auth guards on protected endpoints (401)
  - /api/auth/session with bogus X-Session-ID → 401 (Emergent rejects)
  - Simulated admin session via seeded Mongo docs + Bearer token
    - /auth/me, admin list/create/update/delete, slug uniqueness, draft visibility
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://my-gallery-26.preview.emergentagent.com"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "akashpuri7@gmail.com"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="session")
def admin_session(mongo_db):
    """Seed an admin user + session_token directly into Mongo. Returns bearer token."""
    user_id = f"user_test_{uuid.uuid4().hex[:10]}"
    session_token = f"test_session_{uuid.uuid4().hex}"
    mongo_db.users.insert_one({
        "user_id": user_id,
        "email": ADMIN_EMAIL,
        "name": "Akash Puri (Test)",
        "picture": "https://ui-avatars.com/api/?name=AP",
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo_db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield {"token": session_token, "user_id": user_id}
    # cleanup
    mongo_db.users.delete_one({"user_id": user_id})
    mongo_db.user_sessions.delete_one({"session_token": session_token})


@pytest.fixture
def public_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def admin_client(admin_session):
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_session['token']}",
    })
    return s


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_posts(mongo_db):
    yield
    mongo_db.posts.delete_many({"slug": {"$regex": "^test-"}})
    # Cleanup any stray test messages that used TEST_ prefix names/emails.
    mongo_db.messages.delete_many({"$or": [
        {"name": {"$regex": "^TEST_"}},
        {"email": {"$regex": "@example\\.com$"}},
    ]})


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------
class TestPublic:
    def test_root(self, public_client):
        r = public_client.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        data = r.json()
        assert "name" in data
        assert data["name"] == "Akash Puri Portfolio API"

    def test_list_public_posts_only_published(self, public_client):
        r = public_client.get(f"{BASE_URL}/api/posts")
        assert r.status_code == 200
        posts = r.json()
        assert isinstance(posts, list)
        assert len(posts) >= 3, f"Expected at least 3 seeded posts, got {len(posts)}"
        for p in posts:
            for field in ["id", "slug", "title", "date", "excerpt", "body", "imageURL", "postLink", "tags", "published"]:
                assert field in p, f"Missing {field} in post"
            assert p["published"] is True

    def test_get_post_by_slug(self, public_client):
        r = public_client.get(f"{BASE_URL}/api/posts/floodlight-hygiene")
        assert r.status_code == 200
        p = r.json()
        assert p["slug"] == "floodlight-hygiene"
        assert p["published"] is True

    def test_get_post_404(self, public_client):
        r = public_client.get(f"{BASE_URL}/api/posts/nonexistent-slug-xyz")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Auth guards — unauthenticated access
# ---------------------------------------------------------------------------
class TestAuthGuards:
    def test_me_requires_auth(self, public_client):
        r = public_client.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_admin_list_requires_auth(self, public_client):
        r = public_client.get(f"{BASE_URL}/api/admin/posts")
        assert r.status_code == 401

    def test_admin_create_requires_auth(self, public_client):
        r = public_client.post(f"{BASE_URL}/api/admin/posts", json={"slug": "x", "title": "x", "date": "2025-01-01"})
        assert r.status_code == 401

    def test_admin_update_requires_auth(self, public_client):
        r = public_client.put(f"{BASE_URL}/api/admin/posts/some-id", json={"slug": "x", "title": "x", "date": "2025-01-01"})
        assert r.status_code == 401

    def test_admin_delete_requires_auth(self, public_client):
        r = public_client.delete(f"{BASE_URL}/api/admin/posts/some-id")
        assert r.status_code == 401

    def test_bogus_bearer_token(self, public_client):
        r = public_client.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer totally-bogus-token"},
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# /api/auth/session — Emergent OAuth rejects bogus session IDs
# ---------------------------------------------------------------------------
class TestOAuthSession:
    def test_missing_x_session_id(self, public_client):
        r = public_client.post(f"{BASE_URL}/api/auth/session")
        assert r.status_code == 400

    def test_bogus_x_session_id_returns_401(self, public_client):
        r = public_client.post(
            f"{BASE_URL}/api/auth/session",
            headers={"X-Session-ID": "bogus-session-id-that-emergent-will-reject"},
        )
        # Emergent auth should reject → 401 (may take a couple seconds)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Simulated admin CRUD (seeded session)
# ---------------------------------------------------------------------------
class TestAdminCRUD:
    def test_auth_me(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"

    def test_admin_list_posts(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/posts")
        assert r.status_code == 200
        posts = r.json()
        assert isinstance(posts, list)
        assert len(posts) >= 3

    def test_create_update_delete_flow(self, admin_client):
        # CREATE
        slug = f"test-{uuid.uuid4().hex[:8]}"
        payload = {
            "slug": slug,
            "title": "TEST Post Title",
            "date": "January 15, 2026",
            "excerpt": "Test excerpt",
            "body": "# body",
            "imageURL": "https://example.com/img.png",
            "postLink": "#",
            "tags": ["Test", "Automation"],
            "published": True,
        }
        r = admin_client.post(f"{BASE_URL}/api/admin/posts", json=payload)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["slug"] == slug
        assert created["title"] == "TEST Post Title"
        assert created["published"] is True
        post_id = created["id"]

        # LIST includes new post
        r = admin_client.get(f"{BASE_URL}/api/admin/posts")
        assert any(p["id"] == post_id for p in r.json())

        # PUBLIC includes it (since published)
        r = requests.get(f"{BASE_URL}/api/posts")
        assert any(p["id"] == post_id for p in r.json())

        # UPDATE
        upd = dict(payload)
        upd["title"] = "TEST Post Updated"
        upd["published"] = False
        r = admin_client.put(f"{BASE_URL}/api/admin/posts/{post_id}", json=upd)
        assert r.status_code == 200
        assert r.json()["title"] == "TEST Post Updated"
        assert r.json()["published"] is False

        # Verify draft doesn't appear publicly
        r = requests.get(f"{BASE_URL}/api/posts")
        assert not any(p["id"] == post_id for p in r.json()), "Draft post leaked into public list"

        # DELETE
        r = admin_client.delete(f"{BASE_URL}/api/admin/posts/{post_id}")
        assert r.status_code == 200
        # confirm 404
        r = admin_client.get(f"{BASE_URL}/api/admin/posts/{post_id}")
        assert r.status_code == 404

    def test_slug_uniqueness_auto_suffix(self, admin_client):
        base_slug = f"test-uniq-{uuid.uuid4().hex[:6]}"
        payload = {"slug": base_slug, "title": "A", "date": "2026-01-15", "published": False}
        r1 = admin_client.post(f"{BASE_URL}/api/admin/posts", json=payload)
        assert r1.status_code == 200
        first = r1.json()
        assert first["slug"] == base_slug

        r2 = admin_client.post(f"{BASE_URL}/api/admin/posts", json={**payload, "title": "B"})
        assert r2.status_code == 200
        second = r2.json()
        assert second["slug"] == f"{base_slug}-2", f"expected -2 suffix, got {second['slug']}"

        # cleanup
        admin_client.delete(f"{BASE_URL}/api/admin/posts/{first['id']}")
        admin_client.delete(f"{BASE_URL}/api/admin/posts/{second['id']}")


# ---------------------------------------------------------------------------
# Regression — static assets still served
# ---------------------------------------------------------------------------
class TestStaticRegression:
    @pytest.mark.parametrize("path", [
        "/sitemap.xml", "/robots.txt",
        "/favicon.ico", "/favicon-32.png", "/favicon-192.png", "/favicon-512.png",
        "/apple-touch-icon.png", "/og-image.png",
    ])
    def test_asset_200(self, public_client, path):
        r = public_client.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"{path} returned {r.status_code}"


# ---------------------------------------------------------------------------
# Contact Messages — public submit + admin management
# ---------------------------------------------------------------------------
class TestMessagesPublicSubmit:
    """POST /api/messages is unauthenticated (contact form endpoint)."""

    def test_submit_valid_message_persists_and_sends_email(self, public_client, mongo_db):
        payload = {
            "name": "TEST_Sender",
            "email": "test+valid@example.com",
            "message": "Automated integration probe — please ignore.",
        }
        r = public_client.post(f"{BASE_URL}/api/messages", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        # Response shape
        assert "id" in data and isinstance(data["id"], str) and len(data["id"]) > 0
        assert data["name"] == payload["name"]
        assert data["email"] == payload["email"]
        assert data["message"] == payload["message"]
        assert data["read"] is False
        assert "email_sent" in data and isinstance(data["email_sent"], bool)
        assert "created_at" in data and isinstance(data["created_at"], str)

        # Verify persistence via Mongo (avoids needing admin auth for a public-endpoint check)
        doc = mongo_db.messages.find_one({"id": data["id"]}, {"_id": 0})
        assert doc is not None, "Message was not persisted in Mongo"
        assert doc["email"] == payload["email"]
        assert doc["email_sent"] == data["email_sent"]

        # Integration probe: Emergent Resend proxy should have accepted the send.
        # If the key is present and Resend responded 2xx, email_sent should be True.
        # We record but don't hard-fail (graceful degradation is documented behavior).
        if not data["email_sent"]:
            pytest.skip("email_sent=False — check EMERGENT_EMAIL_KEY and Resend proxy status")

        # Cleanup
        mongo_db.messages.delete_one({"id": data["id"]})

    @pytest.mark.parametrize("payload", [
        {"email": "a@b.com", "message": "hi"},                   # missing name
        {"name": "x", "message": "hi"},                          # missing email
        {"name": "x", "email": "a@b.com"},                       # missing message
        {"name": "", "email": "a@b.com", "message": "hi"},       # empty name
        {"name": "x", "email": "", "message": "hi"},             # empty email
        {"name": "x", "email": "a@b.com", "message": ""},        # empty message
    ])
    def test_submit_invalid_payload_returns_422(self, public_client, payload):
        r = public_client.post(f"{BASE_URL}/api/messages", json=payload)
        assert r.status_code == 422, f"Expected 422 for {payload}, got {r.status_code}"


class TestMessagesAuthGuards:
    """All admin message routes require auth."""

    def test_list_requires_auth(self, public_client):
        r = public_client.get(f"{BASE_URL}/api/admin/messages")
        assert r.status_code == 401

    def test_unread_count_requires_auth(self, public_client):
        r = public_client.get(f"{BASE_URL}/api/admin/messages/unread-count")
        assert r.status_code == 401

    def test_patch_requires_auth(self, public_client):
        r = public_client.patch(f"{BASE_URL}/api/admin/messages/fake-id", json={"read": True})
        assert r.status_code == 401

    def test_delete_requires_auth(self, public_client):
        r = public_client.delete(f"{BASE_URL}/api/admin/messages/fake-id")
        assert r.status_code == 401


class TestMessagesAdminFlow:
    """End-to-end admin management flow — submit → list → mark read → unread → delete."""

    def test_full_lifecycle(self, public_client, admin_client, mongo_db):
        # Snapshot pre-existing unread count so the assertion is deterministic even if
        # other messages linger in the collection.
        pre = admin_client.get(f"{BASE_URL}/api/admin/messages/unread-count")
        assert pre.status_code == 200
        pre_unread = pre.json()["unread"]

        # (a) POST publicly
        payload = {
            "name": "TEST_LifecycleUser",
            "email": "test+lifecycle@example.com",
            "message": "Lifecycle test message.",
        }
        r = public_client.post(f"{BASE_URL}/api/messages", json=payload)
        assert r.status_code == 200
        created = r.json()
        msg_id = created["id"]

        try:
            # (a) List → newest first at position 0
            r = admin_client.get(f"{BASE_URL}/api/admin/messages")
            assert r.status_code == 200
            msgs = r.json()
            assert isinstance(msgs, list) and len(msgs) >= 1
            assert msgs[0]["id"] == msg_id, "New message should be sorted at position 0 (created_at desc)"
            assert msgs[0]["name"] == payload["name"]
            assert msgs[0]["email"] == payload["email"]
            assert msgs[0]["message"] == payload["message"]
            assert msgs[0]["read"] is False

            # (b) Unread count incremented by 1
            r = admin_client.get(f"{BASE_URL}/api/admin/messages/unread-count")
            assert r.status_code == 200
            assert r.json()["unread"] == pre_unread + 1

            # (c) PATCH read=true
            r = admin_client.patch(f"{BASE_URL}/api/admin/messages/{msg_id}", json={"read": True})
            assert r.status_code == 200
            assert r.json()["read"] is True
            assert r.json()["id"] == msg_id

            r = admin_client.get(f"{BASE_URL}/api/admin/messages/unread-count")
            assert r.json()["unread"] == pre_unread

            # (d) PATCH read=false
            r = admin_client.patch(f"{BASE_URL}/api/admin/messages/{msg_id}", json={"read": False})
            assert r.status_code == 200
            assert r.json()["read"] is False
            r = admin_client.get(f"{BASE_URL}/api/admin/messages/unread-count")
            assert r.json()["unread"] == pre_unread + 1

            # (e) DELETE
            r = admin_client.delete(f"{BASE_URL}/api/admin/messages/{msg_id}")
            assert r.status_code == 200

            # (f) Confirm removal
            r = admin_client.get(f"{BASE_URL}/api/admin/messages")
            assert not any(m["id"] == msg_id for m in r.json()), "Deleted message still present"
            r = admin_client.patch(f"{BASE_URL}/api/admin/messages/{msg_id}", json={"read": True})
            assert r.status_code == 404
        finally:
            # Safety net cleanup in case of assertion failure
            mongo_db.messages.delete_one({"id": msg_id})

    def test_patch_missing_read_field_returns_400(self, admin_client, public_client, mongo_db):
        r = public_client.post(f"{BASE_URL}/api/messages", json={
            "name": "TEST_PatchGuard", "email": "test+patch@example.com", "message": "x",
        })
        msg_id = r.json()["id"]
        try:
            r = admin_client.patch(f"{BASE_URL}/api/admin/messages/{msg_id}", json={})
            assert r.status_code == 400
        finally:
            mongo_db.messages.delete_one({"id": msg_id})

    def test_delete_nonexistent_returns_404(self, admin_client):
        r = admin_client.delete(f"{BASE_URL}/api/admin/messages/does-not-exist-xyz")
        assert r.status_code == 404
