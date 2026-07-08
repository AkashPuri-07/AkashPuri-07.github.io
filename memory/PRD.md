# Akash Puri Portfolio — PRD & Progress Snapshot

## Original Problem Statement
User wanted to rebuild an existing HTML portfolio (Akash Puri — Programmatic & Display Advertising Specialist, 9+ yrs, Dentsu) into a bright, luxurious, cinematic editorial site. Explicit constraint: **vanilla HTML/CSS/JS only** (no React/Next). Libraries via CDN: GSAP, ScrollTrigger, vanilla-tilt.

## Architecture
- Public site served via CRA `public/index.html` (React entry `/app/frontend/src/index.js` is a no-op).
- **Backend**: FastAPI at `/app/backend/server.py` with MongoDB (`test_database`). Now hosts CRUD API for Journal posts + Emergent Google OAuth session exchange.
- **Admin dashboard**: vanilla HTML/JS at `/app/frontend/public/admin/index.html` (also duplicated at `/admin.html`). Auth: Emergent Google OAuth allow-list.
- Portfolio journal section fetches posts from `GET /api/posts` at page load.

## Design Tokens (locked)
- Background `#f6f4ef` (ivory) with peach + rose gradient ambient blobs.
- Accent champagne gold `#b89968` → `#8f7443`.
- Ink `#14130f` / `#4a4740` / `#8a857b`.
- **Fonts**: Fraunces (variable serif) + Inter.
- Glass panels `rgba(255,255,255,0.55)` + 18px blur.

## User Personas
- Primary: hiring managers / clients evaluating Akash's programmatic ad expertise.
- Admin: Akash himself (single-user admin allow-list = `akashpuri7@gmail.com`).

## Auth Model
- Emergent-managed Google OAuth via `https://auth.emergentagent.com/` (redirect flow with `#session_id=` fragment).
- Backend exchanges `X-Session-ID` → Emergent `session-data` → issues httpOnly `session_token` cookie (7-day TTL).
- Allow-list: `ADMIN_EMAILS` env var (defaults to `akashpuri7@gmail.com`). Non-admin emails are rejected with 403 during session creation.
- Dual auth: cookie OR `Authorization: Bearer <session_token>` header both accepted.

## Journal Post Schema
```
id: uuid, slug: unique, title, date (string), excerpt, body (markdown),
imageURL, postLink, tags[], published (bool), created_at, updated_at
```

## What's Been Implemented (chronological)

### Dec 2025 — MVP (iteration_1: PASS 100%)
- Full editorial redesign, GSAP animations, vanilla-tilt 3D cards, filterable projects, animated counters, contact form (client-side).

### Dec 2025 — Bug fixes (iteration_1 verified)
- Font Syne → Fraunces. Hero portrait replaced with user's photo. Broken 3rd journal image fixed. Full SEO (canonical, robots, OG, Twitter, JSON-LD Person schema).

### Dec 2025 — Brand assets (iteration_2: PASS 100%)
- Gemini Nano Banana generated: favicon "A" monogram + og:image 1200×630 background.
- PIL composed final og:image with Fraunces/Inter text overlay.
- Full favicon set + og-image.png + apple-touch-icon.

### Dec 2025 — SEO extras
- `sitemap.xml` + `robots.txt` at `/app/frontend/public/`.

### Jan 2026 — Admin dashboard + persistence (iteration_3: PASS 100% — 24/24 backend, 100% frontend)
- Backend: `/api/auth/session` (Emergent OAuth exchange), `/api/auth/me`, `/api/auth/logout`; `/api/posts` (public list published), `/api/posts/{slug}` (public single); `/api/admin/posts` CRUD (list/get/create/update/delete) protected by admin allow-list.
- Frontend admin: full CRUD UI at `/admin/`, `/admin`, `/admin.html`, `/admin/index.html` — all resolve to the same page.
- Portfolio Journal now dynamic — fetches from `/api/posts` at load.
- 3 initial posts seeded on first startup (if empty collection).
- MongoDB collections: `users`, `user_sessions`, `posts`.

## Prioritized Backlog

### P0 — before deployment
- [ ] User to register a real domain (support_agent guidance: Namecheap/Cloudflare/Porkbun → Emergent Deploy → Link domain → Entri).
- [ ] Once live, swap `href="/"` in canonical, `content="/"` in og:url, `<loc>` URLs in sitemap.xml, `Sitemap:` in robots.txt to the absolute domain.
- [ ] Optional: rename Emergent project — support confirmed the "my-gallery" project name is set at project creation; either use a custom domain (recommended) or spin up a new project named "akashpuri" and migrate.

### P1
- [ ] Wire contact form to Resend for real email delivery.
- [ ] Add analytics/event tracking on CTA clicks.
- [ ] Add a `published_at` field so re-publishing an older draft doesn't jump it to the top (currently sorts by `created_at`).

### P2
- [ ] Public single-post page (`/blog/{slug}`) rendering markdown body with a nice reading layout.
- [ ] Cal.com or Calendly embed above contact section.
- [ ] Image upload via Emergent object storage instead of manual imageURL entry.
- [ ] Progressive image loading / WebP+AVIF sources.

## Key File Map
| Path | Purpose |
|---|---|
| `/app/frontend/public/index.html` | Public portfolio (fetches posts from /api/posts) |
| `/app/frontend/public/admin/index.html` + `/admin.html` | Admin dashboard (Google login → CRUD) |
| `/app/frontend/public/sitemap.xml`, `robots.txt` | SEO files |
| `/app/frontend/public/favicon*.png/ico`, `apple-touch-icon.png`, `og-image.png` | Brand assets |
| `/app/frontend/src/index.js` | No-op (React neutralized) |
| `/app/backend/server.py` | FastAPI: auth + posts CRUD |
| `/app/backend/.env` | `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `EMERGENT_LLM_KEY`, `ADMIN_EMAILS` |
| `/app/backend/tests/backend_test.py` | Pytest E2E suite (24 tests) |
| `/app/scripts/generate_brand_images.py` | Nano Banana favicon + og:image generator |
| `/app/scripts/process_brand_images.py` | PIL post-processing |
| `/app/memory/test_credentials.md` | Test session seeding instructions |

## Test Reports
- `iteration_1.json` — PASS 100% (font/portrait/journal/SEO/regression)
- `iteration_2.json` — PASS 100% (favicon + og:image 1200×630 + canonical TODO)
- `iteration_3.json` — PASS 100% (24/24 backend + full admin UI + public feed regression)

## Status: Admin dashboard live and persisting to Mongo. Portfolio journal now data-driven.
