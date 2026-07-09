"""
Static site builder for the Journal section.

Reads posts/posts.json (the single source of truth — no database, no server)
and regenerates:
  - /blog/{slug}/index.html  for every published post
  - /sitemap.xml

Run this locally after editing posts/posts.json:
    pip install markdown bleach --break-system-packages
    python3 scripts/build_blog.py

The homepage's Journal grid does NOT need this script — it fetches
posts/posts.json directly in the browser at page load. This script only
pre-renders the individual full-article pages (for clean URLs + SEO) and
the sitemap.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Iterable

import bleach
import markdown

ROOT = Path(__file__).resolve().parent.parent
POSTS_JSON = ROOT / "posts" / "posts.json"
BLOG_ROOT = ROOT / "blog"
SITEMAP_PATH = ROOT / "sitemap.xml"

SITE_TITLE = "Akash Puri"
AUTHOR_NAME = "Akash Puri"
AUTHOR_ROLE = "Account Manager, Display · Dentsu"
AUTHOR_IMG = "https://customer-assets.emergentagent.com/job_my-gallery-26/artifacts/zuanw3ir_IMG_20211102_101125.webp"
DEFAULT_HERO = "/og-image.png"
CANONICAL_ORIGIN = ""  # empty -> relative URLs; set to "https://akashpuri.com" once a custom domain is live

MD_EXTS = ["extra", "sane_lists", "smarty", "toc"]
ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "pre", "code", "blockquote", "figure", "figcaption", "img",
    "hr", "table", "thead", "tbody", "tr", "th", "td", "br", "span", "div",
]
ALLOWED_ATTRS = {"*": ["class", "id"], "a": ["href", "title", "rel", "target"], "img": ["src", "alt", "title", "loading"]}


def _reading_time_minutes(body_md: str) -> int:
    words = len(re.findall(r"\S+", body_md or ""))
    return max(1, round(words / 220))


def _first_blockquote(body_md: str) -> str | None:
    if not body_md:
        return None
    lines = []
    for line in body_md.splitlines():
        if line.startswith(">"):
            lines.append(line.lstrip(">").strip())
        elif lines:
            break
    text = " ".join(lines).strip()
    return text or None


def _render_body_html(body_md: str) -> str:
    if not body_md:
        return "<p><em>Full article coming soon.</em></p>"
    raw = markdown.markdown(body_md, extensions=MD_EXTS, output_format="html5")
    return bleach.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=False)


def _absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if CANONICAL_ORIGIN:
        return CANONICAL_ORIGIN.rstrip("/") + "/" + url.lstrip("/")
    return url


def _related(all_posts: list[dict], current_slug: str, n: int = 2) -> list[dict]:
    others = [p for p in all_posts if p.get("slug") != current_slug and p.get("published")]
    others.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return others[:n]


def _related_html(related: list[dict]) -> str:
    if not related:
        return ""
    cards = []
    for p in related:
        cards.append(f"""
        <a href="/blog/{html.escape(p['slug'])}/" class="related-card">
          <div class="r-date">{html.escape(p.get('date',''))}</div>
          <div class="r-title">{html.escape(p.get('title',''))}</div>
          <p class="r-excerpt">{html.escape(p.get('excerpt',''))}</p>
        </a>""")
    return f"""
      <div class="related">
        <h3 class="related-title">Keep reading</h3>
        <div class="related-grid">{''.join(cards)}</div>
      </div>
    """


def _tags_html(tags: list[str]) -> str:
    if not tags:
        return ""
    pills = "".join(f'<span class="tag-pill">{html.escape(t)}</span>' for t in tags if t)
    return f'<div class="tags-row">{pills}</div>' if pills else ""


def _pull_quote_html(body_md: str) -> str:
    q = _first_blockquote(body_md)
    if not q or len(q) < 30 or len(q) > 240:
        return ""
    return f"""
      <div class="pull-quote">
        <p>&ldquo;{html.escape(q)}&rdquo;</p>
        <cite>{html.escape(AUTHOR_NAME)}</cite>
      </div>
    """


def _post_html(post: dict, related: list[dict]) -> str:
    title = post.get("title") or "Untitled"
    slug = post.get("slug")
    date = post.get("date", "")
    excerpt = post.get("excerpt", "")
    body_md = post.get("body", "")
    body_html = _render_body_html(body_md)
    hero_img = post.get("imageURL") or DEFAULT_HERO
    tags = post.get("tags") or []
    minutes = _reading_time_minutes(body_md)

    seo_desc = (excerpt or "").strip().replace("\n", " ")[:200]
    canonical = f"/blog/{slug}/"
    og_image = _absolute(hero_img or DEFAULT_HERO)
    tags_line = " · ".join([html.escape(t.upper()) for t in tags[:2]]) if tags else "JOURNAL"

    jsonld_dict = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": seo_desc,
        "image": [og_image] if og_image else [],
        "datePublished": post.get("created_at", ""),
        "dateModified": post.get("updated_at", post.get("created_at", "")),
        "author": {"@type": "Person", "name": AUTHOR_NAME, "jobTitle": AUTHOR_ROLE, "image": AUTHOR_IMG},
        "publisher": {"@type": "Person", "name": AUTHOR_NAME},
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "keywords": ", ".join(tags),
    }
    jsonld = json.dumps(jsonld_dict, ensure_ascii=False, separators=(",", ":"))

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)} | {html.escape(SITE_TITLE)}</title>
    <meta name="description" content="{html.escape(seo_desc)}" />
    <meta name="author" content="{html.escape(AUTHOR_NAME)}" />
    <link rel="canonical" href="{canonical}" />
    <meta name="robots" content="index, follow, max-image-preview:large" />

    <!-- Open Graph -->
    <meta property="og:type" content="article" />
    <meta property="og:title" content="{html.escape(title)}" />
    <meta property="og:description" content="{html.escape(seo_desc)}" />
    <meta property="og:image" content="{html.escape(og_image)}" />
    <meta property="og:image:alt" content="{html.escape(title)}" />
    <meta property="og:url" content="{canonical}" />
    <meta property="article:published_time" content="{html.escape(post.get('created_at',''))}" />
    <meta property="article:modified_time" content="{html.escape(post.get('updated_at', post.get('created_at','')))}" />
    <meta property="article:author" content="{html.escape(AUTHOR_NAME)}" />
    {''.join(f'<meta property="article:tag" content="{html.escape(t)}" />' for t in tags)}

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{html.escape(title)}" />
    <meta name="twitter:description" content="{html.escape(seo_desc)}" />
    <meta name="twitter:image" content="{html.escape(og_image)}" />

    <!-- Favicons -->
    <link rel="icon" href="/favicon.ico" sizes="any" />
    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
    <meta name="theme-color" content="#f6f4ef" />

    <!-- Fonts: Source Serif 4 (headings) + Inter (body) -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;0,8..60,700;1,8..60,400;1,8..60,500&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet" />

    <script type="application/ld+json">{jsonld}</script>

    <style>
      :root {{
        --bg: #f6f4ef; --ink: #14130f; --ink-2: #4a4740; --ink-3: #8a857b;
        --line: rgba(20,19,15,0.06); --line-strong: rgba(20,19,15,0.12);
        --gold: #b89968; --gold-deep: #8f7443;
        --pearl: linear-gradient(135deg, #f3e3c8 0%, #e6c9c1 35%, #cfd8e8 70%, #d8e0d1 100%);
        --ease: cubic-bezier(0.16, 1, 0.3, 1);
      }}
      * {{ box-sizing: border-box; }}
      html {{ scroll-behavior: smooth; }}
      body {{
        margin: 0; background: var(--bg); color: var(--ink);
        font-family: 'Inter', system-ui, sans-serif; font-size: 17px; line-height: 1.7;
        -webkit-font-smoothing: antialiased; overflow-x: hidden; position: relative;
      }}
      body::before, body::after {{
        content: ''; position: fixed; width: 60vw; height: 60vw;
        border-radius: 50%; filter: blur(120px); opacity: 0.4;
        z-index: 0; pointer-events: none;
      }}
      body::before {{ top: -30vw; right: -20vw; background: radial-gradient(circle, #f3e3c8 0%, transparent 60%); }}
      body::after  {{ bottom: -20vw; left: -20vw; background: radial-gradient(circle, #e6d1e0 0%, transparent 60%); }}

      .progress {{ position: fixed; top: 0; left: 0; right: 0; height: 3px;
                   background: rgba(184,153,104,0.1); z-index: 100; }}
      .progress-fill {{ height: 100%; background: linear-gradient(90deg, #d4b47a, #8f7443);
                        width: 0%; transition: width 0.15s var(--ease); }}

      .topbar {{ position: sticky; top: 0; z-index: 50;
        backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
        background: rgba(246,244,239,0.72); border-bottom: 1px solid var(--line); }}
      .topbar-inner {{ display: flex; align-items: center; justify-content: space-between;
        padding: 18px 32px; max-width: 1240px; margin: 0 auto; }}
      .brand {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600; font-size: 1.05rem;
                display: flex; align-items: center; gap: 10px; color: var(--ink); text-decoration: none; }}
      .brand .dot {{ width: 10px; height: 10px; border-radius: 50%;
                     background: linear-gradient(135deg, #d4b47a, #8f7443);
                     box-shadow: 0 0 0 3px rgba(184,153,104,0.15); }}
      .back-link {{ display: inline-flex; align-items: center; gap: 8px;
                    font-size: 0.88rem; color: var(--ink-2); font-weight: 500;
                    transition: color 0.3s var(--ease); text-decoration: none; }}
      .back-link:hover {{ color: var(--gold-deep); }}
      .back-link .arrow {{ transition: transform 0.3s var(--ease); }}
      .back-link:hover .arrow {{ transform: translateX(-4px); }}

      article {{ max-width: 720px; margin: 0 auto; padding: 64px 32px 96px;
                 position: relative; z-index: 1; }}
      .eyebrow {{ display: inline-flex; align-items: center; gap: 10px;
                  font-size: 0.72rem; letter-spacing: 0.22em; text-transform: uppercase;
                  color: var(--gold-deep); font-weight: 600; margin-bottom: 24px; }}
      .eyebrow::before {{ content: ''; width: 28px; height: 1px; background: var(--gold-deep); }}
      article h1 {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600;
                    font-size: clamp(2.1rem, 4.5vw, 3.25rem); letter-spacing: -0.02em;
                    line-height: 1.15; margin: 0 0 24px; color: var(--ink); }}
      .lede {{ font-family: 'Inter', system-ui, sans-serif; font-weight: 400;
               font-size: 1.2rem; line-height: 1.55; color: var(--ink-2); margin: 0 0 32px; }}

      .meta {{ display: flex; align-items: center; gap: 24px; padding: 24px 0;
               border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
               margin-bottom: 48px; flex-wrap: wrap; }}
      .meta-author {{ display: flex; align-items: center; gap: 12px; }}
      .meta-author img {{ width: 44px; height: 44px; border-radius: 50%; object-fit: cover;
                          box-shadow: 0 4px 12px -4px rgba(120,100,60,0.3); }}
      .meta-author .name {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600;
                            font-size: 0.98rem; color: var(--ink); }}
      .meta-author .role {{ font-size: 0.78rem; color: var(--ink-3); letter-spacing: 0.04em; }}
      .meta-sep {{ width: 1px; height: 30px; background: var(--line-strong); }}
      .meta-facts {{ display: flex; gap: 20px; font-size: 0.82rem; color: var(--ink-3);
                     letter-spacing: 0.06em; text-transform: uppercase; }}

      .hero-img {{ width: 100%; aspect-ratio: 16 / 9; border-radius: 20px; overflow: hidden;
                   margin-bottom: 56px; background: var(--pearl);
                   box-shadow: 0 24px 60px -30px rgba(120,100,60,0.4); }}
      .hero-img img {{ width: 100%; height: 100%; object-fit: cover; }}

      .tags-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 32px; }}
      .tag-pill {{ font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase;
                   font-weight: 500; padding: 4px 12px; border-radius: 999px;
                   background: rgba(184,153,104,0.1); color: var(--gold-deep); }}

      .prose {{ font-size: 1.1rem; color: var(--ink); line-height: 1.75;
                font-family: 'Inter', system-ui, sans-serif; }}
      .prose h2 {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600;
                   font-size: 1.6rem; letter-spacing: -0.01em; line-height: 1.3;
                   margin: 56px 0 20px; color: var(--ink); }}
      .prose h3 {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600;
                   font-size: 1.25rem; margin: 40px 0 14px; }}
      .prose p {{ margin: 0 0 22px; color: var(--ink-2); }}
      .prose strong {{ color: var(--ink); font-weight: 600; }}
      .prose em {{ font-style: italic; color: var(--gold-deep); }}
      .prose ul, .prose ol {{ padding-left: 24px; margin: 0 0 22px; color: var(--ink-2); }}
      .prose li {{ margin-bottom: 10px; }}
      .prose a {{ color: var(--gold-deep); text-decoration: underline;
                  text-decoration-thickness: 1px; text-underline-offset: 3px; }}
      .prose a:hover {{ color: var(--ink); }}
      .prose blockquote {{ margin: 32px 0; padding: 8px 0 8px 24px;
                           border-left: 3px solid var(--gold);
                           font-family: 'Source Serif 4', Georgia, serif;
                           font-style: italic; font-weight: 400; font-size: 1.15rem;
                           color: var(--ink); line-height: 1.55; }}
      .prose code {{ background: rgba(184,153,104,0.12); color: var(--gold-deep);
                     padding: 2px 8px; border-radius: 5px;
                     font-family: 'SF Mono', Menlo, Monaco, monospace; font-size: 0.92em; }}
      .prose pre {{ background: var(--ink); color: #f0e9d8; padding: 20px 24px;
                    border-radius: 12px; overflow-x: auto;
                    font-family: 'SF Mono', Menlo, monospace;
                    font-size: 0.88rem; line-height: 1.55; margin: 32px 0; }}
      .prose pre code {{ background: transparent; color: inherit; padding: 0; }}
      .prose hr {{ border: none; height: 1px; background: var(--line-strong); margin: 48px 0; }}
      .prose img {{ max-width: 100%; height: auto; border-radius: 14px; margin: 24px 0; }}

      .pull-quote {{ margin: 56px -32px; padding: 48px; background: var(--pearl);
                     border-radius: 24px; text-align: center; }}
      .pull-quote p {{ font-family: 'Source Serif 4', Georgia, serif;
                       font-style: italic; font-weight: 500; font-size: 1.55rem;
                       line-height: 1.4; color: var(--ink); margin: 0 0 20px;
                       letter-spacing: -0.005em; }}
      .pull-quote cite {{ font-style: normal; font-size: 0.82rem; color: var(--gold-deep);
                          font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; }}

      .share {{ margin: 64px 0 48px; padding: 32px; border: 1px solid var(--line);
                border-radius: 16px; background: rgba(255,255,255,0.55);
                backdrop-filter: blur(12px); display: flex; align-items: center;
                justify-content: space-between; gap: 20px; flex-wrap: wrap; }}
      .share .label {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600; font-size: 1.05rem; }}
      .share-btns {{ display: flex; gap: 10px; }}
      .share-btn {{ display: inline-flex; align-items: center; justify-content: center;
                    width: 42px; height: 42px; border-radius: 999px; background: #fff;
                    border: 1px solid var(--line); color: var(--ink-2); cursor: pointer;
                    transition: all 0.3s var(--ease); text-decoration: none; }}
      .share-btn:hover {{ border-color: var(--gold-deep); color: var(--gold-deep);
                          transform: translateY(-2px); }}
      .share-btn svg {{ width: 18px; height: 18px; }}

      .author-card {{ margin-top: 48px; padding: 32px; border: 1px solid var(--line);
                       border-radius: 20px; background: rgba(255,255,255,0.55);
                       backdrop-filter: blur(12px); display: flex; gap: 24px; align-items: center; }}
      .author-card img {{ width: 80px; height: 80px; border-radius: 50%; object-fit: cover; flex-shrink: 0; }}
      .author-card h4 {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 1.2rem;
                         font-weight: 600; margin: 0 0 4px; color: var(--ink); }}
      .author-card p {{ margin: 0; font-size: 0.92rem; color: var(--ink-2); }}
      .author-card .link {{ color: var(--gold-deep); font-weight: 500; font-size: 0.88rem;
                             margin-top: 8px; display: inline-block; text-decoration: none; }}
      .author-card .link:hover {{ text-decoration: underline; }}
      @media (max-width: 600px) {{ .author-card {{ flex-direction: column; text-align: center; }} }}

      .related {{ margin-top: 96px; padding-top: 48px; border-top: 1px solid var(--line); }}
      .related-title {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600;
                        font-size: 1.6rem; margin: 0 0 32px; letter-spacing: -0.01em; }}
      .related-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
      @media (max-width: 640px) {{ .related-grid {{ grid-template-columns: 1fr; }} }}
      .related-card {{ padding: 24px; background: rgba(255,255,255,0.55); border: 1px solid var(--line);
                       border-radius: 16px; text-decoration: none; transition: all 0.3s var(--ease); display: block; }}
      .related-card:hover {{ border-color: rgba(184,153,104,0.35); transform: translateY(-3px);
                             box-shadow: 0 12px 32px -12px rgba(120,100,60,0.25); }}
      .related-card .r-date {{ font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase;
                                color: var(--gold-deep); font-weight: 600; }}
      .related-card .r-title {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 1.1rem;
                                 font-weight: 600; margin: 10px 0 10px; color: var(--ink); line-height: 1.4; }}
      .related-card .r-excerpt {{ font-size: 0.9rem; color: var(--ink-2); margin: 0; }}

      .foot-cta {{ margin-top: 80px; padding: 48px 32px; text-align: center; background: var(--ink);
                   color: #f8f5ec; border-radius: 24px; }}
      .foot-cta h3 {{ font-family: 'Source Serif 4', Georgia, serif; font-weight: 600;
                      font-size: 1.65rem; margin: 0 0 12px; color: #f8f5ec;
                      letter-spacing: -0.01em; line-height: 1.3; }}
      .foot-cta p {{ color: rgba(248,245,236,0.72); margin: 0 0 24px; }}
      .foot-cta .btn {{ display: inline-flex; align-items: center; gap: 10px;
                        padding: 15px 32px; border-radius: 999px;
                        background: linear-gradient(135deg, #d4b47a, #8f7443);
                        color: #14130f; font-weight: 500; text-decoration: none;
                        transition: all 0.3s var(--ease); }}
      .foot-cta .btn:hover {{ transform: translateY(-2px);
                              box-shadow: 0 12px 32px -8px rgba(184,153,104,0.5); }}
    </style>
  </head>
  <body>
    <div class="progress"><div class="progress-fill" id="progressFill"></div></div>

    <div class="topbar">
      <div class="topbar-inner">
        <a href="/" class="brand"><span class="dot"></span> {html.escape(SITE_TITLE)}</a>
        <a href="/#journal" class="back-link"><span class="arrow">&larr;</span> Back to Journal</a>
      </div>
    </div>

    <article>
      <div class="eyebrow">Journal · {tags_line}</div>
      <h1>{html.escape(title)}</h1>
      <p class="lede">{html.escape(excerpt or '')}</p>

      <div class="meta">
        <div class="meta-author">
          <img src="{html.escape(AUTHOR_IMG)}" alt="{html.escape(AUTHOR_NAME)}" />
          <div>
            <div class="name">{html.escape(AUTHOR_NAME)}</div>
            <div class="role">{html.escape(AUTHOR_ROLE)}</div>
          </div>
        </div>
        <div class="meta-sep"></div>
        <div class="meta-facts">
          <span>{html.escape(date)}</span>
          <span>·</span>
          <span>{minutes} min read</span>
        </div>
      </div>

      {'<div class="hero-img"><img src="' + html.escape(hero_img) + '" alt="' + html.escape(title) + '" /></div>' if hero_img else ''}

      {_tags_html(tags)}

      <div class="prose">
        {body_html}
      </div>

      {_pull_quote_html(body_md)}

      <div class="share">
        <div class="label">Share this piece</div>
        <div class="share-btns">
          <a class="share-btn" target="_blank" rel="noopener" href="https://www.linkedin.com/sharing/share-offsite/?url={html.escape(canonical)}" title="LinkedIn"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.5 2h-17A1.5 1.5 0 002 3.5v17A1.5 1.5 0 003.5 22h17a1.5 1.5 0 001.5-1.5v-17A1.5 1.5 0 0020.5 2zM8 19H5v-9h3zM6.5 8.25A1.75 1.75 0 118.3 6.5a1.78 1.78 0 01-1.8 1.75zM19 19h-3v-4.74c0-1.42-.6-2-1.5-2A2.1 2.1 0 0012.5 15v4h-3v-9h3v1.3a3.11 3.11 0 012.7-1.4c1.55 0 3.36.86 3.36 3.66z"/></svg></a>
          <a class="share-btn" target="_blank" rel="noopener" href="https://twitter.com/intent/tweet?text={html.escape(title)}&url={html.escape(canonical)}" title="Twitter/X"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
          <button class="share-btn" type="button" onclick="navigator.clipboard.writeText(location.href).then(()=>this.title='Copied!')" title="Copy link"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg></button>
        </div>
      </div>

      <div class="author-card">
        <img src="{html.escape(AUTHOR_IMG)}" alt="{html.escape(AUTHOR_NAME)}" />
        <div>
          <h4>{html.escape(AUTHOR_NAME)}</h4>
          <p>Programmatic &amp; display specialist with 9+ years across agency floors and enterprise client tables. Currently at Dentsu, Pune.</p>
          <a href="/#contact" class="link">Get in touch &rarr;</a>
        </div>
      </div>

      {_related_html(related)}

      <div class="foot-cta">
        <h3>Have a campaign that needs a second look?</h3>
        <p>Whether it's a stalled account or a new brief — happy to chat.</p>
        <a href="/#contact" class="btn">Start a conversation &rarr;</a>
      </div>
    </article>

    <script>
      const fill = document.getElementById('progressFill');
      const article = document.querySelector('article');
      function updateProgress() {{
        const rect = article.getBoundingClientRect();
        const total = rect.height - window.innerHeight;
        const scrolled = -rect.top;
        const pct = Math.max(0, Math.min(100, (scrolled / total) * 100));
        fill.style.width = pct + '%';
      }}
      window.addEventListener('scroll', updateProgress, {{ passive: true }});
      updateProgress();
    </script>
  </body>
</html>
"""


def _write_post_file(post: dict, all_published: list[dict]) -> None:
    slug = post.get("slug")
    if not slug or not post.get("published"):
        return
    dest_dir = BLOG_ROOT / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    related = _related(all_published, slug)
    (dest_dir / "index.html").write_text(_post_html(post, related), encoding="utf-8")


def _regenerate_all(published_posts: list[dict]) -> None:
    valid_slugs = {p["slug"] for p in published_posts if p.get("slug")}
    if BLOG_ROOT.exists():
        for child in BLOG_ROOT.iterdir():
            if child.is_dir() and child.name not in valid_slugs:
                shutil.rmtree(child, ignore_errors=True)
    for p in published_posts:
        _write_post_file(p, published_posts)


def _write_sitemap(published_posts: Iterable[dict]) -> None:
    static_anchors = [
        ("/", 1.0, "monthly"),
        ("/#about", 0.8, "monthly"),
        ("/#projects", 0.9, "monthly"),
        ("/#skills", 0.6, "monthly"),
        ("/#journal", 0.8, "weekly"),
        ("/#contact", 0.7, "yearly"),
    ]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, prio, freq in static_anchors:
        lines.append(f"  <url><loc>{path}</loc><changefreq>{freq}</changefreq><priority>{prio}</priority></url>")
    for p in published_posts:
        if p.get("slug"):
            lines.append(f'  <url><loc>/blog/{p["slug"]}/</loc><changefreq>monthly</changefreq><priority>0.75</priority></url>')
    lines.append("</urlset>")
    SITEMAP_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    posts = json.loads(POSTS_JSON.read_text(encoding="utf-8"))
    published = [p for p in posts if p.get("published")]
    published.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    _regenerate_all(published)
    _write_sitemap(published)
    print(f"Built {len(published)} blog page(s) into {BLOG_ROOT} and regenerated {SITEMAP_PATH}")


if __name__ == "__main__":
    main()
