"""
Iteration 6 — Static blog file + sitemap generation regression suite.

Covers:
  - Startup: /app/frontend/public/blog/ exists with a folder per published post
  - Sitemap has 6 static anchors + 1 <loc> per published post
  - CRUD from /api/admin/posts writes/removes /blog/{slug}/index.html
  - Rename slug removes old folder, creates new
  - Unpublish removes the file
  - Delete removes the file
  - HTTP GET /blog/{slug}/ returns 200 with correct SEO surface (title, meta description,
    canonical, og:type=article, og:image, og:url, twitter:card, JSON-LD Article).
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://my-gallery-26.preview.emergentagent.com"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "akashpuri7@gmail.com"
BLOG_ROOT = Path("/app/frontend/public/blog")
SITEMAP = Path("/app/frontend/public/sitemap.xml")


# -------- fixtures --------
@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def admin_session(mongo_db):
    user_id = f"user_test_{uuid.uuid4().hex[:10]}"
    session_token = f"test_session_{uuid.uuid4().hex}"
    mongo_db.users.insert_one({
        "user_id": user_id, "email": ADMIN_EMAIL, "name": "Akash Puri (Test)",
        "picture": "https://ui-avatars.com/api/?name=AP", "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo_db.user_sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield session_token
    mongo_db.users.delete_one({"user_id": user_id})
    mongo_db.user_sessions.delete_one({"session_token": session_token})


@pytest.fixture
def admin_client(admin_session):
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_session}",
    })
    return s


# -------- Startup filesystem invariants --------
class TestStartupState:
    def test_blog_root_exists(self):
        assert BLOG_ROOT.exists() and BLOG_ROOT.is_dir()

    def test_seeded_slugs_have_index_html(self):
        r = requests.get(f"{BASE_URL}/api/posts")
        assert r.status_code == 200
        slugs = [p["slug"] for p in r.json()]
        assert len(slugs) >= 3
        for slug in slugs:
            f = BLOG_ROOT / slug / "index.html"
            assert f.exists(), f"Missing {f}"
            assert f.stat().st_size > 1000, f"{f} too small"

    def test_sitemap_has_static_anchors_and_published_slugs(self):
        assert SITEMAP.exists()
        content = SITEMAP.read_text(encoding="utf-8")
        for anchor in ["<loc>/</loc>", "<loc>/#about</loc>", "<loc>/#projects</loc>",
                       "<loc>/#skills</loc>", "<loc>/#journal</loc>", "<loc>/#contact</loc>"]:
            assert anchor in content, f"sitemap missing {anchor}"
        r = requests.get(f"{BASE_URL}/api/posts")
        for p in r.json():
            assert f"<loc>/blog/{p['slug']}/</loc>" in content


# -------- Live SEO surface for a served blog page --------
class TestBlogHtmlSEO:
    def test_seeded_blog_page_seo_surface(self):
        r = requests.get(f"{BASE_URL}/api/posts")
        slug = r.json()[0]["slug"]
        title = r.json()[0]["title"]

        page = requests.get(f"{BASE_URL}/blog/{slug}/")
        assert page.status_code == 200, f"GET /blog/{slug}/ returned {page.status_code}"
        html = page.text

        # <title> contains post title AND site title
        m = re.search(r"<title>([^<]+)</title>", html)
        assert m, "no <title>"
        title_text = m.group(1)
        assert "Akash Puri" in title_text
        assert title.split(":")[0][:20] in title_text or title in title_text

        # meta description
        assert re.search(r'<meta\s+name="description"\s+content="[^"]+"', html), "no meta description"

        # canonical
        assert re.search(rf'<link\s+rel="canonical"\s+href="/blog/{slug}/"', html), "no/wrong canonical"

        # og:*
        assert 'property="og:type" content="article"' in html
        assert 'property="og:title"' in html
        assert 'property="og:image"' in html
        assert f'property="og:url" content="/blog/{slug}/"' in html

        # twitter
        assert 'name="twitter:card" content="summary_large_image"' in html

        # JSON-LD Article
        jsonld = re.search(r'<script type="application/ld\+json">(.+?)</script>', html, re.S)
        assert jsonld, "no JSON-LD"
        body = jsonld.group(1)
        assert '"@type": "Article"' in body
        assert '"headline"' in body
        assert "'Akash Puri'" in body or '"Akash Puri"' in body
        assert "datePublished" in body
        assert f"/blog/{slug}/" in body  # mainEntityOfPage.@id


# -------- CRUD → filesystem lifecycle --------
class TestCRUDBlogFiles:
    SLUG_A = "test-blog-file-e2e"
    SLUG_B = "test-blog-renamed"

    def _cleanup(self, admin_client, mongo_db):
        # remove any test docs and folders that may linger from a previous crashed run
        for s in [self.SLUG_A, self.SLUG_B]:
            mongo_db.posts.delete_many({"slug": s})
            d = BLOG_ROOT / s
            if d.exists():
                import shutil
                shutil.rmtree(d, ignore_errors=True)

    def test_full_lifecycle(self, admin_client, mongo_db):
        self._cleanup(admin_client, mongo_db)

        payload = {
            "slug": self.SLUG_A,
            "title": "Iteration 6 E2E Blog File",
            "date": "January 15, 2026",
            "excerpt": "End-to-end coverage for static blog file generation.",
            "body": "# Heading\n\nThis is body content that is long enough to give more than one minute of reading time. " * 30,
            "imageURL": "https://example.com/hero.png",
            "postLink": "#",
            "tags": ["Testing", "Iteration6"],
            "published": True,
        }

        # (a) CREATE → file exists + HTTP GET 200
        r = admin_client.post(f"{BASE_URL}/api/admin/posts", json=payload)
        assert r.status_code == 200, r.text
        post = r.json()
        post_id = post["id"]

        try:
            f = BLOG_ROOT / self.SLUG_A / "index.html"
            assert f.exists(), "Blog file not written after POST"

            page = requests.get(f"{BASE_URL}/blog/{self.SLUG_A}/")
            assert page.status_code == 200
            assert "Akash Puri" in page.text
            assert payload["title"] in page.text

            # Sitemap updated
            assert f"<loc>/blog/{self.SLUG_A}/</loc>" in SITEMAP.read_text(encoding="utf-8")

            # (b) UNPUBLISH → folder removed
            upd = dict(payload); upd["published"] = False
            r = admin_client.put(f"{BASE_URL}/api/admin/posts/{post_id}", json=upd)
            assert r.status_code == 200
            assert not (BLOG_ROOT / self.SLUG_A).exists(), "Folder should be removed on unpublish"
            # HTTP: not served as article (page.text should not contain generated <title>)
            page = requests.get(f"{BASE_URL}/blog/{self.SLUG_A}/", allow_redirects=True)
            # CRA fallback OR 404 is acceptable, but page must NOT be the generated article
            assert payload["title"] not in page.text or page.status_code == 404
            # Sitemap: slug removed
            assert f"<loc>/blog/{self.SLUG_A}/</loc>" not in SITEMAP.read_text(encoding="utf-8")

            # (c) REPUBLISH → file back
            upd["published"] = True
            r = admin_client.put(f"{BASE_URL}/api/admin/posts/{post_id}", json=upd)
            assert r.status_code == 200
            assert (BLOG_ROOT / self.SLUG_A / "index.html").exists()
            assert f"<loc>/blog/{self.SLUG_A}/</loc>" in SITEMAP.read_text(encoding="utf-8")

            # (d) RENAME slug → old folder gone, new folder present
            upd["slug"] = self.SLUG_B
            r = admin_client.put(f"{BASE_URL}/api/admin/posts/{post_id}", json=upd)
            assert r.status_code == 200, r.text
            assert r.json()["slug"] == self.SLUG_B
            assert not (BLOG_ROOT / self.SLUG_A).exists(), "Old slug folder must be removed"
            assert (BLOG_ROOT / self.SLUG_B / "index.html").exists(), "New slug folder must exist"
            sm = SITEMAP.read_text(encoding="utf-8")
            assert f"<loc>/blog/{self.SLUG_A}/</loc>" not in sm
            assert f"<loc>/blog/{self.SLUG_B}/</loc>" in sm

            # (e) DELETE → folder removed
            r = admin_client.delete(f"{BASE_URL}/api/admin/posts/{post_id}")
            assert r.status_code == 200
            assert not (BLOG_ROOT / self.SLUG_B).exists()
            assert f"<loc>/blog/{self.SLUG_B}/</loc>" not in SITEMAP.read_text(encoding="utf-8")

        finally:
            self._cleanup(admin_client, mongo_db)
