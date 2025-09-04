#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-updater for AI Discovery Blog.

What it does
------------
1) Fetches fresh AI/tech news from Newsdata.io (or NEWS_API_KEY alias).
2) Quality filters (skips one-liners / paywalled markers).
3) Chooses an image for each post in this order:
    - Article's own image_url (downloaded & cached locally).
    - Topic-based hero (policy / chips / markets / research / health / edu).
    - Rotating generic heroes (ai-hero-1.svg ... ai-hero-9.svg if present).
    - Fallback: /assets/ai-hero.svg
4) Writes enriched markdown files to _posts/.

Env vars
--------
NEWSDATA_API_KEY   (preferred)
NEWS_API_KEY       (alias)

Dependencies
------------
pip install requests python-slugify
"""

from __future__ import annotations

import os
import re
import sys
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, unquote, splitext

import requests
from slugify import slugify

# ---------------- Configuration ----------------

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY") or os.getenv("NEWS_API_KEY")

KEYWORDS = [
    "ai", "artificial intelligence", "machine learning",
    "openai", "anthropic", "meta ai", "google ai"
]
LANG = "en"
CATEGORY = "technology"
COUNTRY = None           # None or 'us' (country filter sometimes reduces recall)
MAX_POSTS = 5

POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"     # downloaded images go here
GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/1.1 (+github actions)"

# Topic heroes (optional files you may add to /assets/)
TOPIC_HEROES = {
    "policy": "/assets/topic-policy.svg",
    "chips": "/assets/topic-chips.svg",
    "markets": "/assets/topic-markets.svg",
    "research": "/assets/topic-research.svg",
    "health": "/assets/topic-health.svg",
    "edu": "/assets/topic-edu.svg",
}

# Generic rotation pool (the ones that actually exist will be used)
ROTATE_CANDIDATES = [
    "/assets/ai-hero-1.svg",
    "/assets/ai-hero-2.svg",
    "/assets/ai-hero-3.svg",
    "/assets/ai-hero-4.svg",
    "/assets/ai-hero-5.svg",
    "/assets/ai-hero-6.svg",
    "/assets/ai-hero-7.svg",
    "/assets/ai-hero-8.svg",
    "/assets/ai-hero-9.svg",
]

# ---------------- Utilities ----------------

def debug(msg: str) -> None:
    print(msg, flush=True)

def safe_get(d: Dict[str, Any], *keys: str) -> Optional[str]:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return str(cur) if cur is not None else None

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def too_similar(a: str, b: str) -> bool:
    a = clean_text(a).lower()
    b = clean_text(b).lower()
    return a == b or (a and b and (a in b or b in a))

def has_low_value_markers(t: str) -> bool:
    t_low = t.lower()
    markers = [
        "only available in paid plans",
        "subscribe to read",
        "sign in to continue",
        "under construction",
    ]
    return any(m in t_low for m in markers)

def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)

def shorten(s: str, max_len: int = 280) -> str:
    s = clean_text(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"

def build_query() -> str:
    parts = [f'"{kw}"' if " " in kw else kw for kw in KEYWORDS]
    q = " OR ".join(parts)
    if len(q) > 95:
        q = '"artificial intelligence" OR ai OR "machine learning"'
    return q

def call_api(page: Optional[int] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "apikey": API_KEY,
        "q": build_query(),
        "language": LANG,
        "category": CATEGORY,
    }
    if COUNTRY:
        params["country"] = COUNTRY
    if page:
        params["page"] = page

    headers = {"User-Agent": USER_AGENT}
    r = requests.get(API_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------------- Image helpers ----------------

IMG_EXT_WHITELIST = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

def is_image_url(url: str) -> bool:
    try:
        path = urlparse(url).path
        ext = splitext(path)[1].lower()
        if ext in IMG_EXT_WHITELIST:
            return True
        return False
    except Exception:
        return False

def guess_ext_from_ct(content_type: str) -> str:
    if not content_type:
        return ".jpg"
    ct = content_type.lower()
    if "svg" in ct:
        return ".svg"
    if "webp" in ct:
        return ".webp"
    if "png" in ct:
        return ".png"
    if "gif" in ct:
        return ".gif"
    return ".jpg"

def download_and_cache_image(url: str, title: str) -> Optional[str]:
    """
    Tries to download a remote image and write it under assets/cache/.
    Returns the public site path (e.g. /assets/cache/filename.jpg) or None on failure.
    """
    try:
        headers = {"User-Agent": USER_AGENT, "Referer": "https://github.com"}
        resp = requests.get(url, headers=headers, timeout=20, stream=True)
        resp.raise_for_status()

        ct = resp.headers.get("Content-Type", "")
        if "image" not in (ct or "").lower():
            return None

        # filename
        parsed = urlparse(url)
        name = os.path.basename(parsed.path) or slugify(title)
        name = unquote(name)
        base, ext = os.path.splitext(name)
        if not ext or ext.lower() not in IMG_EXT_WHITELIST:
            ext = guess_ext_from_ct(ct)

        # keep it deterministic but unique-ish per url
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        filename = f"{slugify(base)}-{h}{ext}"

        ensure_dir(ASSET_CACHE_DIR)
        abs_path = os.path.join(ASSET_CACHE_DIR, filename)

        # size cap ~ 3 MB just to be safe
        bytes_read = 0
        with open(abs_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                f.write(chunk)
                bytes_read += len(chunk)
                if bytes_read > 3 * 1024 * 1024:
                    # too big; delete and abort
                    try:
                        f.close()
                        os.remove(abs_path)
                    except Exception:
                        pass
                    return None

        # return public URL path
        return f"/{ASSET_CACHE_DIR}/{filename}"
    except Exception:
        return None

def detect_topic(title: str, desc: str) -> Optional[str]:
    t = f"{title} {desc}".lower()
    if any(k in t for k in ["policy", "regulation", "ban", "law", "eu ai act"]):
        return "policy"
    if any(k in t for k in ["gpu", "chip", "nvidia", "amd", "hardware", "datacenter"]):
        return "chips"
    if any(k in t for k in ["stock", "shares", "earnings", "market", "valuation"]):
        return "markets"
    if any(k in t for k in ["research", "paper", "arxiv", "breakthrough", "study"]):
        return "research"
    if any(k in t for k in ["health", "medical", "doctor", "biotech", "hospital"]):
        return "health"
    if any(k in t for k in ["classroom", "education", "students", "teachers", "school"]):
        return "edu"
    return None

def pick_rotating_hero(title: str) -> str:
    """Rotate across whatever ai-hero-*.svg exist; otherwise fallback."""
    existing = [p for p in ROTATE_CANDIDATES if os.path.exists(p.lstrip("/"))]
    if not existing:
        return GENERIC_FALLBACK
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(existing)
    return existing[idx]

def pick_image_for_article(item: Dict[str, Any], title: str, desc: str) -> str:
    """
    1) Try article image_url -> download/cache -> local path
    2) else topic hero (if file exists)
    3) else rotating generic hero
    4) else fallback
    """
    # 1) Article’s own image?
    url_candidates = [
        safe_get(item, "image_url"),
        safe_get(item, "image"),
        safe_get(item, "source_icon"),
        safe_get(item, "source", "icon"),
    ]
    for url in url_candidates:
        if url and url.startswith(("http://", "https://")):
            local = download_and_cache_image(url, title)
            if local:
                return local

    # 2) Topic hero
    topic = detect_topic(title, desc or "")
    if topic:
        candidate = TOPIC_HEROES.get(topic)
        if candidate and os.path.exists(candidate.lstrip("/")):
            return candidate

    # 3) Rotate generics
    return pick_rotating_hero(title)

# ---------------- Fetch & build ----------------

def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("NEWS_API_KEY (or NEWSDATA_API_KEY) not set.")

    debug("🧠 update_posts.py starting…")
    debug("📰 Fetching latest AI articles...")

    collected: List[Dict[str, Any]] = []
    page = 1
    while len(collected) < limit and page <= 3:
        try:
            data = call_api(page=page)
        except requests.HTTPError as e:
            debug(f"❌ API HTTP error on page {page}: {e}")
            break
        except Exception as e:
            debug(f"❌ API error on page {page}: {e}")
            break

        results = data.get("results") or data.get("articles") or []
        if not results:
            break

        for item in results:
            if len(collected) >= limit:
                break

            title = clean_text(safe_get(item, "title"))
            desc = clean_text(safe_get(item, "description"))
            content = clean_text(safe_get(item, "content"))
            link = clean_text(safe_get(item, "link")) or clean_text(safe_get(item, "url"))
            source_id = clean_text(safe_get(item, "source_id")) or clean_text(safe_get(item, "source"))

            if not title or not link:
                continue
            if has_low_value_markers(desc) or has_low_value_markers(content) or has_low_value_markers(title):
                continue
            if too_similar(title, desc) and len(desc) < 60:
                continue

            # image selection (may download/copy)
            chosen_image = pick_image_for_article(item, title, desc)

            pub = (
                clean_text(safe_get(item, "pubDate"))
                or clean_text(safe_get(item, "published_at"))
                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            )

            item_norm = {
                "title": title,
                "description": desc,
                "content": content,
                "link": link,
                "source_id": source_id or "source",
                "image": chosen_image or GENERIC_FALLBACK,
                "pubDate": pub,
            }
            collected.append(item_norm)

        page += 1

    return collected[:limit]

def enrich_text(title: str, desc: str, content: str, source: str, link: str) -> str:
    base = clean_text(content) or clean_text(desc)
    base = shorten(base, 700)

    why = []
    tl = title.lower()
    if any(k in tl for k in ["stock", "earnings", "valuation", "market"]):
        why.append("Impacto nos mercados e na avaliação de empresas.")
    if any(k in tl for k in ["policy", "regulation", "law", "ban"]):
        why.append("Mudanças regulatórias podem redefinir o panorama competitivo.")
    if any(k in tl for k in ["chip", "gpu", "hardware", "inference"]):
        why.append("Infraestrutura de hardware influencia performance e custo de IA.")
    if any(k in tl for k in ["research", "paper", "breakthrough", "study"]):
        why.append("Avanços de investigação podem abrir novos casos de uso.")
    if not why:
        why.append("Relevante para o ecossistema de IA e seus casos de uso.")

    bullets: List[str] = []
    for part in re.split(r"[.;]\s+", base)[:4]:
        part = clean_text(part)
        if part and 25 <= len(part) <= 220:
            bullets.append(part)

    pieces = []
    pieces.append("### TL;DR")
    pieces.append(shorten(base, 240) or "Resumo breve do que foi anunciado/aconteceu no mundo da IA.")
    pieces.append("\n### Por que importa")
    for w in why:
        pieces.append(f"- {w}")
    if bullets:
        pieces.append("\n### Detalhes rápidos")
        for b in bullets:
            pieces.append(f"- {b}")
    pieces.append("\n> Fonte: ")
    pieces.append(f"[{source}]({link})")
    return "\n".join(pieces).strip()

def build_markdown(article: Dict[str, Any]) -> str:
    title = article["title"]
    description = article.get("description") or ""
    body = enrich_text(title, description, article.get("content", ""), article["source_id"], article["link"])

    # front matter
    safe_title = title.replace('"', '\\"')
    safe_excerpt = (article.get("description") or "").replace('"', '\\"')

    fm_lines = [
        "---",
        "layout: post",
        f'title: "{safe_title}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{shorten(safe_excerpt, 300)}"',
        'categories: [ai, news]',
        f'image: "{article.get("image") or GENERIC_FALLBACK}"',
        f'source: "{(article.get("source_id") or "source").replace(\'"\', "\\\"")}"',
        f'source_url: "{article.get("link")}"',
        "---",
    ]

    return "\n".join(fm_lines) + "\n\n" + body + "\n"

def make_filename(title: str, date_str: Optional[str] = None) -> str:
    date_part = (date_str or datetime.now(timezone.utc).date().isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")

def write_post(article: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    path = make_filename(article["title"], article.get("pubDate"))
    if os.path.exists(path):
        debug(f"↩︎ Skipping (already exists): {os.path.basename(path)}")
        return None
    content = build_markdown(article)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path

# ---------------- Main ----------------

def main() -> None:
    try:
        ensure_dir(ASSET_CACHE_DIR)
        articles = fetch_articles(limit=MAX_POSTS)
        if not articles:
            debug("ℹ️ No articles found.")
            sys.exit(0)

        created = 0
        for art in articles:
            path = write_post(art)
            if path:
                created += 1
                debug(f"✅ Post created: {path}")

        if created == 0:
            debug("ℹ️ Nothing new to write.")
        else:
            debug(f"🎉 Done. {created} post(s) written.")
    except Exception as e:
        debug(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
