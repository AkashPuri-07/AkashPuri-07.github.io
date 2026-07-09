# Akash Puri Portfolio — PRD & Progress Snapshot

## Original Problem Statement
User wanted to rebuild an existing HTML portfolio (Akash Puri — Programmatic & Display Advertising Specialist, 9+ yrs, Dentsu) into a bright, luxurious, cinematic editorial site. Explicit constraint: **vanilla HTML/CSS/JS only** (no React/Next). Libraries via CDN: GSAP, ScrollTrigger, vanilla-tilt.

## Architecture
- **Public site**: served via CRA `public/index.html` (React entry `/app/frontend/src/index.js` is a no-op). Portfolio journal section fetches from `GET /api/posts`.
- **Backend**: FastAPI at `/app/backend/server.py` with MongoDB. Journal CRUD, Emergent Google OAuth, contact messages + Resend email.
- **Admin**: vanilla HTML/JS at `/app/frontend/public/admin/index.html` (+ mirror at `/admin.html`). Two tabs: Journal + Messages.
- **Blog reading pages** (IN PROGRESS): static HTML per post at `/app/frontend/public/blog/{slug}/index.html`.

## Design Tokens
- BG `#f6f4ef` ivory, ink `#14130f`, accent gold `#b89968` → `#8f7443`.
- **Fonts**: portfolio + admin = Fraunces headers + Inter body. **Blog reading pages = Source Serif 4 headers + Inter body** (user asked for more professional/readable fonts on blog pages).

## Auth Model
- Emergent Google OAuth. Allow-list `ADMIN_EMAILS=akashpuri7@gmail.com`. Session token cookie (7-day).

## What's Been Implemented (chronological)
- **MVP** — editorial redesign, GSAP + vanilla-tilt animations, contact form (iteration_1: PASS).
- **Fonts/portrait/SEO** — Syne→Fraunces, personal photo, canonical/OG/Twitter/JSON-LD (iteration_1 verified).
- **Brand assets** — Nano-Banana favicon + og-image 1200×630 (iteration_2: PASS).
- **Sitemap + robots** — added.
- **Admin dashboard + Journal CRUD** — Google OAuth, allow-list, dynamic Journal (iteration_3: PASS).
- **Contact form → email + admin inbox** — Resend delivery, Messages tab (iteration_4 caught HTML corruption → iteration_5: PASS 100%).

## IN PROGRESS: /blog/{slug}/ static reading pages
User approved a static preview (Source Serif 4 fonts). Then said **"done ship it"**. User is now on break — resume from step 3 below.

### Approved design (see previous chat + git for preview screenshots)
- Sticky topbar with brand + "Back to Journal" arrow
- Reading progress bar at top
- Editorial eyebrow, huge Source Serif 4 title, Inter lede
- Author card with photo/role, date, computed reading time
- Hero image with peach glow shadow
- Prose: Source Serif 4 headings + Inter body, gold `em`, gold code chips, dark `pre` blocks
- Pull-quote (auto-detected from first `>` blockquote in markdown, if between 30–240 chars)
- Share bar (LinkedIn, Twitter/X, Copy link)
- Author card
- Related posts (2 most-recent other published)
- Dark CTA card driving back to `/#contact`

### Progress so far
- [x] `markdown` + `bleach` installed and added to `requirements.txt`
- [x] Created `/app/backend/blog_renderer.py` — the full renderer (fonts, prose styles, SEO, JSON-LD Article schema, pull-quote auto-detect, related posts, reading-time). Public API: `write_post_file(post, all_published)`, `remove_post_file(slug)`, `regenerate_all(published_posts)`, `build_sitemap_urls(published)`.
- [x] Created empty dir `/app/frontend/public/blog/`
- [ ] Wire renderer into `/app/backend/server.py`:
  - [ ] Import from `blog_renderer`
  - [ ] On startup after seed: call `blog_renderer.regenerate_all(published_posts_list)`
  - [ ] After `POST /api/admin/posts` → call `write_post_file(post, all_published)`
  - [ ] After `PUT  /api/admin/posts/{id}` → same
  - [ ] After `DELETE /api/admin/posts/{id}` → `remove_post_file(slug)`
  - [ ] Note: `write_post_file` internally handles unpublish (removes file). Any state change needs the *fresh* list of all published posts, so fetch once and pass through.
- [ ] Update `sitemap.xml` — either statically list current posts OR dynamically generate via `GET /api/sitemap.xml`. Simplest: at post save/delete, regenerate `/app/frontend/public/sitemap.xml` with all `/blog/{slug}/` URLs appended (keep the 6 existing anchor URLs). Consider having `blog_renderer` own it.
- [ ] Update portfolio Journal cards to link to `/blog/{slug}/` if `postLink` is empty or `#`. In `/app/frontend/public/index.html` `renderPosts()`, change:
  ```js
  href="${post.postLink || '#'}"  →  href="${(post.postLink && post.postLink !== '#') ? post.postLink : '/blog/' + post.slug + '/'}"
  ```
- [ ] Verify with `testing_agent_v3`:
  - Publishing a new post creates `/blog/{slug}/index.html` (200)
  - Editing regenerates the file
  - Unpublishing / deleting removes the file (404 on subsequent GET)
  - SEO tags per post (canonical, og:image, JSON-LD Article present)
  - Portfolio Journal cards now link to `/blog/{slug}/`
  - Reading-time computed reasonable
  - Sitemap includes new URLs
  - Full regression (admin, messages, portfolio)

### Files touched this iteration (WIP)
| Path | Status |
|---|---|
| `/app/backend/blog_renderer.py` | ✅ Created |
| `/app/backend/requirements.txt` | ✅ Includes `markdown` and `bleach` |
| `/app/frontend/public/blog/` | ✅ Empty folder created |
| `/app/frontend/public/blog-preview.html` | Deleted (was mock) |
| `/app/backend/server.py` | ⏳ NEEDS wiring calls to blog_renderer on save/update/delete + startup |
| `/app/frontend/public/index.html` (portfolio) | ⏳ NEEDS renderPosts() href change |
| `/app/frontend/public/sitemap.xml` | ⏳ NEEDS blog URLs (optional: dynamic regen) |
| `/app/test_reports/iteration_6.json` | Not yet created — call `testing_agent_v3` after wiring |

### Resume command for next session
> "Continue the blog reading pages — wire blog_renderer into server.py, update portfolio Journal card hrefs, regenerate sitemap, then run testing_agent."

## Prioritized Backlog (post-blog-pages)

### P0
- Register real domain → swap canonical, og:url, sitemap `<loc>`, robots.txt Sitemap: line to absolute URLs

### P1
- Contact form auto-reply email to sender
- Simple rate-limiting on `POST /api/messages`

### P2
- Cal.com/Calendly embed above contact
- Image upload via object storage (instead of manual imageURL entry)
- Analytics on CTA clicks

## Key File Map
| Path | Purpose |
|---|---|
| `/app/frontend/public/index.html` | Public portfolio |
| `/app/frontend/public/admin/index.html` + `/admin.html` | Admin dashboard (Journal + Messages tabs) |
| `/app/frontend/public/blog/{slug}/index.html` | (WIP) Per-post reading pages |
| `/app/frontend/public/sitemap.xml`, `robots.txt` | SEO |
| `/app/frontend/public/favicon*.png/ico`, `apple-touch-icon.png`, `og-image.png` | Brand assets |
| `/app/frontend/src/index.js` | No-op (React neutralized) |
| `/app/backend/server.py` | FastAPI: auth + posts + messages CRUD |
| `/app/backend/blog_renderer.py` | (NEW WIP) Static blog page renderer |
| `/app/backend/.env` | MONGO_URL, DB_NAME, CORS_ORIGINS, EMERGENT_LLM_KEY, ADMIN_EMAILS, EMERGENT_EMAIL_KEY, EMAIL_FROM_NAME, CONTACT_INBOX |
| `/app/memory/test_credentials.md` | Test session seeding |

## Test Reports
- iteration_1..3 all PASS 100%
- iteration_4 caught HTML corruption (bug)
- iteration_5 PASS 100% after fix
- iteration_6 PASS 100% (blog pages + section rhythm — 43/43 backend, 100% frontend)

## Status: LIVE — iteration_6 (blog reading pages + section rhythm) PASS 100%
