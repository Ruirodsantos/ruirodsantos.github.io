#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Minimal stable updater for AI posts (Newsdata).
- Simple query: q=ai (avoids 422 from fancy filters)
- Writes up to MAX_POSTS markdown files into _posts/
- Picks article image if present, else rotates a few local SVGs, else /assets/ai-hero.svg
"""

from __future__ import annotations
import os, re, sys, hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")  # <- single source of truth

LANG = "en"
MAX_POSTS = 10          # 10 per run
POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
GENERIC_FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/sep3-stable/1.0"

ROTATE_CANDIDATES = [
    "/assets/ai-hero-1.svg",
    "/assets/ai-hero-2.svg",
    "/assets/ai-hero-3.svg",
    "/assets/ai-hero-4.svg",
    "/assets/ai-hero-5.svg",
]

IMG_EXT_OK = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

def dbg(msg: str) -> None:
    print(msg, flush=True)

def clean(s: Optional[str]) -> str:
    if not s: return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def strip_paid(s: Optional[str]) -> str:
    """Remove Newsdata placeholders for paid content."""
    s = clean(s)
    if not s:
        return ""
    # Newsdata uses several phrases that all start with "ONLY AVAILABLE IN".
    # A simple regex keeps the helper future-proof for any plan combination.
    if re.search(r"only available in.+plans", s, re.I):
        return ""
    return s

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def yml(s: str) -> str:
    return clean(s).replace('"', r'\"')

def shorten(s: str, n: int=280) -> str:
    s = clean(s)
    return s if len(s) <= n else s[:n-1].rstrip() + "…"

def guess_ext(ct: str) -> str:
    ct = (ct or "").lower()
    if "svg" in ct: return ".svg"
    if "webp" in ct: return ".webp"
    if "png" in ct: return ".png"
    if "gif" in ct: return ".gif"
    return ".jpg"

def download_image(url: str, title: str) -> Optional[str]:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, stream=True)
        r.raise_for_status()
        ct = (r.headers.get("Content-Type") or "").lower()
        if "image" not in ct: return None
        name = os.path.basename(urlparse(url).path) or slugify(title)
        base, ext = os.path.splitext(name)
        if ext.lower() not in IMG_EXT_OK:
            ext = guess_ext(ct)
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        fname = f"{slugify(base) or 'img'}-{h}{ext}"
        ensure_dir(ASSET_CACHE_DIR)
        ap = os.path.join(ASSET_CACHE_DIR, fname)
        with open(ap, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk: f.write(chunk)
        return f"/{ASSET_CACHE_DIR}/{fname}"
    except Exception:
        return None

def rotate_hero(title: str) -> str:
    existing = [p for p in ROTATE_CANDIDATES if os.path.exists(p.lstrip("/"))]
    if not existing:
        return GENERIC_FALLBACK
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(existing)
    return existing[idx]

def pick_image(item: Dict[str, Any], title: str) -> str:
    for k in ("image_url", "image"):
        url = clean(item.get(k))
        if url and url.startswith(("http://", "https://")):
            local = download_image(url, title)
            if local:
                return local
    return rotate_hero(title)

def call_api(page: int) -> Dict[str, Any]:
    # super simple query -> avoids 422 traps
    params = {
        "apikey": API_KEY,
        "q": "ai",
        "language": LANG,
        "page": page
    }
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(API_URL, params=params, headers=headers, timeout=25)
    # Log the final URL for debugging
    dbg(f"GET {r.url}")
    r.raise_for_status()
    return r.json()

def fetch_articles(limit: int) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise SystemExit("NEWS_API_KEY not set (repo → Settings → Secrets → Actions).")
    dbg("🧠 Fetching articles (q=ai)…")
    out: List[Dict[str, Any]] = []
    page = 1
    while len(out) < limit and page <= 3:
        data = call_api(page)
        results = data.get("results") or []
        if not results:
            break
        for it in results:
            if len(out) >= limit: break
            title = strip_paid(it.get("title"))
            link  = clean(it.get("link") or it.get("url"))
            if not title or not link:
                continue
            desc  = strip_paid(it.get("description") or it.get("content") or "")
            src   = clean(it.get("source_id") or it.get("source") or "source")
            pub   = clean(it.get("pubDate") or it.get("published_at") or "")
            img   = pick_image(it, title)
            out.append({
                "title": title, "description": desc, "link": link,
                "source": src, "image": img,
                "pubDate": pub or datetime.now(timezone.utc).isoformat()
            })
        page += 1
    return out[:limit]

def fm_and_body(a: Dict[str, Any]) -> str:
    fm = [
        "---",
        "layout: post",
        f'title: "{yml(a["title"])}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{shorten(a.get("description",""), 300)}"',
        "categories: [ai, news]",
        f'image: "{a.get("image") or GENERIC_FALLBACK}"',
        f'source: "{yml(a.get("source","source"))}"',
        f'source_url: "{yml(a.get("link",""))}"',
        "---",
    ]
    body = a.get("description") or ""
    return "\n".join(fm) + "\n\n" + body + "\n"

def make_filename(title: str, pub: Optional[str]) -> str:
    date_part = (pub or datetime.now(timezone.utc).date().isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")

def write_article(a: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    path = make_filename(a["title"], a.get("pubDate"))
    if os.path.exists(path):
        dbg(f"↩︎ Skip (exists): {os.path.basename(path)}")
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(fm_and_body(a))
    dbg(f"✅ Wrote: {path}")
    return path

def main():
    try:
        ensure_dir(ASSET_CACHE_DIR)
        # keep the folder in git
        gk = os.path.join(ASSET_CACHE_DIR, ".gitkeep")
        if not os.path.exists(gk):
            open(gk, "w").close()

        arts = fetch_articles(MAX_POSTS)
        if not arts:
            dbg("No articles fetched.")
            return
        created = sum(1 for a in arts if write_article(a))
        dbg(f"🎉 Done. Created {created} post(s).")
    except requests.HTTPError as e:
        # show body to help debugging Newsdata errors
        try:
            body = e.response.text[:500]
        except Exception:
            body = "(no body)"
        dbg(f"HTTP error: {e} — body: {body}")
        sys.exit(1)
    except Exception as e:
        dbg(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
