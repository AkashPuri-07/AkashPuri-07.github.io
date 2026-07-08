# Akash Puri Portfolio — PRD & Progress Snapshot

## Original Problem Statement
User wanted to rebuild an existing HTML portfolio (Akash Puri — Programmatic & Display Advertising Specialist, 9+ yrs, Dentsu) into a bright, luxurious, cinematic editorial site. Explicit constraint: **vanilla HTML/CSS/JS only** (no React/Next). Libraries via CDN: GSAP, ScrollTrigger, vanilla-tilt.

Source HTML: https://customer-assets.emergentagent.com/job_my-gallery-26/artifacts/eaf1hogl_portfolio.html

## Architecture
- Site served through CRA's `public/index.html` (React entry `/app/frontend/src/index.js` is a no-op).
- Backend (`/app/backend/server.py`) is **unused** by the portfolio — kept intact but the site does not call it. Contact form is client-side only.
- Assets (favicon set + og:image) live at `/app/frontend/public/`.

## Design Tokens (locked)
- **Background**: `#f6f4ef` (ivory) with peach + rose gradient ambient blobs.
- **Accent**: champagne gold `#b89968` → `#8f7443` + iridescent pearl gradient.
- **Ink**: `#14130f` primary, `#4a4740` secondary, `#8a857b` tertiary.
- **Fonts**: Fraunces (variable serif, editorial) for headers + Inter for body. Loaded via Google Fonts.
- **Glass**: `rgba(255,255,255,0.55)` + 18px backdrop-blur, 1px hairline borders.

## User Personas
- **Primary**: hiring managers / clients evaluating Akash's programmatic ad expertise.
- **Secondary**: recruiters, brand marketing leads, agency partners.

## Core Requirements (static)
1. Vanilla HTML/CSS/JS — no React/Next.
2. GSAP + ScrollTrigger scroll animations + vanilla-tilt 3D on portrait/cards.
3. Data-driven `projects` and `portfolioPosts` arrays for easy content updates.
4. `prefers-reduced-motion` accessibility.
5. SEO compliant.

## What's Been Implemented (chronological)

### Dec 2025 — MVP (iteration_1: PASS 100%)
- Full editorial redesign of the original portfolio HTML.
- Sections: Hero, About, Projects (6 cards, filterable), Metrics (animated counters), Skills, **Journal (new)**, Contact.
- GSAP hero word-mask reveal + scroll-triggered fade/rise on all `.reveal` elements.
- vanilla-tilt on portrait + all project & journal cards with iridescent sheen sweeps.
- Client-side contact form with success state.
- Data arrays: `projects[]`, `portfolioPosts[]` in a single `<script>` block.

### Dec 2025 — Bug fixes (iteration_1 verified)
- **Font**: Syne → Fraunces (variable, optical-sized).
- **Hero portrait**: Unsplash stub → user's uploaded photo (`zuanw3ir_IMG_20211102_101125.webp`).
- **Broken 3rd journal image** replaced with working Unsplash URL.
- **SEO added**: canonical, robots, description, keywords, full Open Graph, Twitter card, JSON-LD Person schema.

### Dec 2025 — Brand assets (iteration_2: PASS 100%)
- Generated favicon "A" monogram + og:image background via Gemini Nano Banana (script: `/app/scripts/generate_brand_images.py`).
- Composed final og:image (1200×630) with Fraunces/Inter text overlay via PIL (script: `/app/scripts/process_brand_images.py`).
- Assets served: `favicon.ico`, `favicon-32.png`, `favicon-192.png`, `favicon-512.png`, `apple-touch-icon.png`, `og-image.png`.
- Canonical + og:url set to `/` with TODO comment pending real domain.
- Added light/dark `theme-color` variants.

### Dec 2025 — SEO extras
- `sitemap.xml` created with all 6 section anchors + TODO for domain replacement.
- `robots.txt` created allowing all crawlers + sitemap reference.

## Prioritized Backlog (remaining)
### P0 — before going live
- [ ] User to register a real domain (support_agent guidance already delivered — Namecheap/Cloudflare/Porkbun; then Emergent "Link domain → Entri" flow).
- [ ] Replace canonical `href="/"`, `og:url` content, and all 6 `<loc>` URLs in `sitemap.xml` with the absolute domain.
- [ ] Update the `Sitemap:` line in `robots.txt` to the absolute URL.

### P1 — nice to have
- [ ] Wire contact form to Resend (Emergent-managed) for real email delivery.
- [ ] Real project artefacts / case-study PDFs behind an email gate (lead-gen).
- [ ] Replace placeholder Unsplash images in `portfolioPosts` with real article hero images once articles are written.

### P2 — future
- [ ] Add a "Book a 15-min intro call" Cal.com/Calendly embed above the contact section (higher conversion than form for consultative work).
- [ ] Add analytics (PostHog is already loaded by the platform; verify events fire on CTA clicks).
- [ ] Progressive image loading / WebP + AVIF sources.

## Key File Map
| Path | Purpose |
|---|---|
| `/app/frontend/public/index.html` | Full portfolio (HTML + inline CSS + inline JS + CDN libs) |
| `/app/frontend/public/sitemap.xml` | Sitemap with section anchors |
| `/app/frontend/public/robots.txt` | Crawler rules |
| `/app/frontend/public/favicon.ico` + `favicon-*.png` + `apple-touch-icon.png` | Icon set |
| `/app/frontend/public/og-image.png` | 1200×630 social share card |
| `/app/frontend/src/index.js` | No-op (React neutralized) |
| `/app/scripts/generate_brand_images.py` | Gemini Nano Banana favicon + og background generator |
| `/app/scripts/process_brand_images.py` | PIL post-processing: text overlay + favicon resize + .ico bundle |
| `/app/backend/.env` | Contains `EMERGENT_LLM_KEY` for future image generation regenerations |

## Test Reports
- `/app/test_reports/iteration_1.json` — PASS 100% (font/portrait/journal/SEO/regression)
- `/app/test_reports/iteration_2.json` — PASS 100% (favicon set + og:image 1200×630 + canonical TODO + regression)

## Status: PAUSED
User requested a break on 8 Jul 2026. All progress saved. Site is fully functional at the preview URL. Resume by asking for any P0/P1/P2 item above.
