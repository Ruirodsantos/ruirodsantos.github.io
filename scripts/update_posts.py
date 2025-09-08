#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Daily updater:
- Fetch 10 AI articles (with images) from Newsdata.io
- Write Markdown posts into _posts/
- Keep only current month's posts (delete older posts)
- Cache remote images into assets/cache
Env:
  NEWS_API_KEY  (your Newsdata key, e.g. pub_***)
Requires:
  pip install requests python-slugify
"""

from __future__ import annotations
import os, re, sys, hashlib, glob, shutil
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")  # single key as requested

LANG = "en"
CATEGORY = "technology"
MAX_POSTS = 10

KEYWORDS = ['"artificial intelligence"', "ai", '"machine learning"']
QUERY = " OR ".join(KEYWORDS)  # short to avoid 100-char limit

POSTS_DIR = "_posts"
CACHE_DIR = "assets/cache"
FALLBACK = "/assets/ai-hero.svg"
USER_AGENT = "ai-discovery-bot/2.0 (+github actions)"

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

def log(m: str): print(m, flush=True)

def clean(s: Optional[str]) -> str:
    if not s: return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def ensure_dirs():
    os.makedirs(POSTS_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    gp = os.path.join(CACHE_DIR, ".gitkeep")
    if not os.path.exists(gp):
        open(gp, "w", encoding="utf-8").write("")

def call_api(page: int) -> Dict[str, Any]:
    params = {
        "apikey": API_KEY,
        "q": QUERY,
        "language": LANG,
        "category": CATEGORY,
        "page": page,
    }
    r = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json()

def guess_ext(ct: str) -> str:
    ct = (ct or "").lower()
    if "svg" in ct: return ".svg"
    if "webp" in ct: return ".webp"
    if "png" in ct: return ".png"
    if "gif" in ct: return ".gif"
    return ".jpg"

def cache_image(url: str, title: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, stream=True)
        resp.raise_for_status()
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "image" not in ct:
            return None
        base = os.path.basename(urlparse(url).path) or slugify(title)
        root, ext = os.path.splitext(base)
        if ext.lower() not in IMG_EXT:
            ext = guess_ext(ct)
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        fn = f"{slugify(root) or 'img'}-{h}{ext}"
        abs_path = os.path.join(CACHE_DIR, fn)
        with open(abs_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                if chunk: f.write(chunk)
        return f"/{CACHE_DIR}/{fn}"
    except Exception:
        return None

def fetch_articles(limit: int) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise RuntimeError("NEWS_API_KEY not set.")
    log("📰 Fetching articles...")
    out: List[Dict[str, Any]] = []
    seen_titles = set()
    page = 1
    while len(out) < limit and page <= 5:
        data = call_api(page)
        results = data.get("results") or []
        if not results: break
        for it in results:
            if len(out) >= limit: break
            title = clean(it.get("title"))
            desc = clean(it.get("description"))
            link = clean(it.get("link"))
            image_url = clean(it.get("image_url") or it.get("image"))
            if not title or not link: continue
            if title.lower() in seen_titles: continue
            # require image
            if not image_url.startswith(("http://", "https://")): continue
            local_img = cache_image(image_url, title) or FALLBACK
            out.append({
                "title": title,
                "desc": desc,
                "link": link,
                "image": local_img,
                "source": clean(it.get("source_id") or it.get("source") or "source"),
                "pub": clean(it.get("pubDate") or it.get("published_at") or datetime.now(timezone.utc).isoformat()),
            })
            seen_titles.add(title.lower())
        page += 1
    return out[:limit]

def yml(s: str) -> str: return clean(s).replace('"', r'\"')

def build_md(a: Dict[str, Any]) -> str:
    fm = [
        "---",
        "layout: post",
        f'title: "{yml(a["title"])}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{yml(a["desc"][:300])}"',
        "categories: [ai, news]",
        f'image: "{a["image"]}"',
        f'source: "{yml(a["source"])}"',
        f'source_url: "{yml(a["link"])}"',
        "---",
    ]
    body = a["desc"] or "Quick update from the AI world."
    return "\n".join(fm) + "\n\n" + body + "\n"

def make_filename(title: str, date_str: Optional[str]) -> str:
    d = (date_str or datetime.now(timezone.utc).date().isoformat())[:10]
    return os.path.join(POSTS_DIR, f"{d}-{slugify(title)[:80] or 'post'}.md")

def write_posts(items: List[Dict[str, Any]]) -> int:
    count = 0
    for a in items:
        path = make_filename(a["title"], a["pub"])
        if os.path.exists(path): 
            continue
        open(path, "w", encoding="utf-8").write(build_md(a))
        count += 1
    return count

def keep_only_current_month():
    now = datetime.now(timezone.utc)
    prefix = now.strftime("%Y-%m-")
    for p in glob.glob(os.path.join(POSTS_DIR, "*.md")):
        name = os.path.basename(p)
        if not name.startswith(prefix):
            os.remove(p)

def main():
    ensure_dirs()
    items = fetch_articles(MAX_POSTS)
    written = write_posts(items)
    keep_only_current_month()
    log(f"✅ Done. Written: {written}, kept only current month posts.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ Error: {e}")
        sys.exit(1)
