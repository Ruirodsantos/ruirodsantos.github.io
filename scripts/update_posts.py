#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-updater for AI Discovery Blog

- Vai à Newsdata e busca artigos sobre IA (sem filtros de datas — só paginação).
- Se a API devolver 422 (query inválida/comprida), volta a tentar com query reduzida.
- Imagens:
    1) tenta a imagem do próprio artigo (faz download para assets/cache/)
    2) se não houver, usa heróis por tópico (policy, chips, markets, research, health, edu)
    3) se não houver, roda heróis genéricos (ai-hero-1..5.svg) existentes no repo
    4) último fallback: /assets/ai-hero.svg
- Escreve .md em _posts/ com front-matter seguro.

Requisitos:  pip install requests python-slugify
Env:         NEWSDATA_API_KEY  (ou NEWS_API_KEY)
"""

from __future__ import annotations

import os
import re
import sys
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import requests
from slugify import slugify

# ---------------- Config ----------------
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY") or os.getenv("NEWS_API_KEY")

# Query curta (<100 chars) p/ evitar 422 do Newsdata
KEYWORDS = [
    '"artificial intelligence"', "ai", '"machine learning"', "openai", "anthropic"
]
LANG = "en"
CATEGORY = "technology"
MAX_POSTS = 5

POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
USER_AGENT = "ai-discovery-bot/1.4 (+github actions)"

# Imagens
GENERIC_FALLBACK = "/assets/ai-hero.svg"
TOPIC_HEROES = {
    "policy":   "/assets/topic-policy.svg",
    "chips":    "/assets/topic-chips.svg",
    "markets":  "/assets/topic-markets.svg",
    "research": "/assets/topic-research.svg",
    "health":   "/assets/topic-health.svg",
    "edu":      "/assets/topic-edu.svg",
}
ROTATE_CANDIDATES = [
    "/assets/ai-hero-1.svg",
    "/assets/ai-hero-2.svg",
    "/assets/ai-hero-3.svg",
    "/assets/ai-hero-4.svg",
    "/assets/ai-hero-5.svg",
]
IMG_EXT_WHITELIST = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}

# ---------------- Utils ----------------
def debug(msg: str) -> None:
    print(msg, flush=True)

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)

def yml_escape(s: str) -> str:
    return clean_text(s).replace('"', r'\"')

def shorten(s: str, max_len: int = 280) -> str:
    s = clean_text(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"

# ---------------- API ----------------
def build_query() -> str:
    # Mantém a query bem curta
    return " OR ".join(KEYWORDS)

def call_api(page: Optional[int] = None, q: Optional[str] = None) -> Dict[str, Any]:
    params = {
        "apikey": API_KEY,
        "q": q or build_query(),
        "language": LANG,
        "category": CATEGORY,
    }
    if page:
        params["page"] = page

    r = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json()

# ---------------- Image helpers ----------------
def guess_ext_from_ct(ct: str) -> str:
    ct = (ct or "").lower()
    if "svg" in ct: return ".svg"
    if "webp" in ct: return ".webp"
    if "png" in ct: return ".png"
    if "gif" in ct: return ".gif"
    return ".jpg"

def download_and_cache_image(url: str, title: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, stream=True)
        resp.raise_for_status()
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "image" not in ct:
            return None

        path_name = os.path.basename(urlparse(url).path) or slugify(title)
        base, ext = os.path.splitext(path_name)
        if ext.lower() not in IMG_EXT_WHITELIST:
            ext = guess_ext_from_ct(ct)

        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
        filename = f"{slugify(base) or 'img'}-{h}{ext}"

        ensure_dir(ASSET_CACHE_DIR)
        abs_path = os.path.join(ASSET_CACHE_DIR, filename)

        with open(abs_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                if chunk:
                    f.write(chunk)

        return f"/{ASSET_CACHE_DIR}/{filename}"
    except Exception as e:
        debug(f"img download fail: {e}")
        return None

def detect_topic(title: str, desc: str) -> Optional[str]:
    t = f"{title} {desc}".lower()
    if any(k in t for k in ["policy", "regulation", "law", "ban"]): return "policy"
    if any(k in t for k in ["gpu", "chip", "nvidia", "amd", "hardware"]): return "chips"
    if any(k in t for k in ["stock", "market", "shares", "revenue", "valuation"]): return "markets"
    if any(k in t for k in ["research", "paper", "breakthrough", "study"]): return "research"
    if any(k in t for k in ["health", "medical", "doctor", "clinical"]): return "health"
    if any(k in t for k in ["education", "school", "classroom", "student"]): return "edu"
    return None

def pick_rotating_hero(title: str) -> str:
    existing = [p for p in ROTATE_CANDIDATES if os.path.exists(p.lstrip("/"))]
    if not existing:
        return GENERIC_FALLBACK
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(existing)
    return existing[idx]

def pick_image(item: Dict[str, Any], title: str, desc: str) -> str:
    # 1) imagem do artigo
    for k in ("image_url", "image"):
        url = clean_text(item.get(k))
        if url and url.startswith(("http://", "https://")):
            local = download_and_cache_image(url, title)
            if local:
                return local
    # 2) herói por tópico
    topic = detect_topic(title, desc)
    if topic:
        candidate = TOPIC_HEROES.get(topic)
        if candidate and os.path.exists(candidate.lstrip("/")):
            return candidate
    # 3) rotação de genéricos
    return pick_rotating_hero(title)

# ---------------- Posts ----------------
def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("API KEY not set (NEWSDATA_API_KEY or NEWS_API_KEY).")

    debug("📰 Fetching AI news (page-based, no date filters)…")
    items: List[Dict[str, Any]] = []
    page = 1

    while len(items) < limit and page <= 5:
        try:
            data = call_api(page=page)
        except requests.HTTPError as e:
            if getattr(e.response, "status_code", None) == 422:
                debug("⚠️ 422 from API. Retrying with shorter query…")
                try:
                    data = call_api(page=page, q='ai OR "machine learning"')
                except Exception as e2:
                    debug(f"❌ API still failing on retry: {e2}")
                    break
            else:
                debug(f"❌ API HTTP error: {e}")
                break
        except Exception as e:
            debug(f"❌ API error: {e}")
            break

        results = data.get("results") or data.get("articles") or []
        if not results:
            break

        for it in results:
            if len(items) >= limit:
                break
            title = clean_text(it.get("title"))
            desc  = clean_text(it.get("description"))
            link  = clean_text(it.get("link") or it.get("url"))
            source_id = clean_text(it.get("source_id") or it.get("source") or "source")
            pubdate   = clean_text(it.get("pubDate") or it.get("published_at") or "")

            if not title or not link:
                continue

            items.append({
                "title": title,
                "description": desc,
                "link": link,
                "source_id": source_id,
                "image": pick_image(it, title, desc),
                "pubDate": pubdate or datetime.now(timezone.utc).isoformat(),
            })
        page += 1

    return items[:limit]

def front_matter(article: Dict[str, Any]) -> str:
    safe_title   = yml_escape(article["title"])
    safe_excerpt = yml_escape(article.get("description") or "")
    image        = article.get("image") or GENERIC_FALLBACK
    source       = yml_escape(article.get("source_id") or "source")
    source_url   = yml_escape(article.get("link") or "")

    lines = [
        "---",
        "layout: post",
        f'title: "{safe_title}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{shorten(safe_excerpt, 300)}"',
        "categories: [ai, news]",
        f'image: "{image}"',
        f'source: "{source}"',
        f'source_url: "{source_url}"',
        "---",
    ]
    return "\n".join(lines)

def build_markdown(article: Dict[str, Any]) -> str:
    body = article.get("description") or ""
    return front_matter(article) + "\n\n" + body + "\n"

def only_date(iso_ts: str) -> str:
    try:
        return iso_ts[:10]
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()

def make_filename(title: str, pubdate: Optional[str] = None) -> str:
    date_part = only_date(pubdate or datetime.now(timezone.utc).isoformat())
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")

def write_post(article: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    path = make_filename(article["title"], article.get("pubDate"))
    if os.path.exists(path):
        debug(f"↩︎ Skip (exists): {os.path.basename(path)}")
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_markdown(article))
    debug(f"✅ Wrote: {path}")
    return path

# ---------------- Main ----------------
def main() -> None:
    try:
        ensure_dir(ASSET_CACHE_DIR)
        # garante que a pasta vai ao repo
        gk = os.path.join(ASSET_CACHE_DIR, ".gitkeep")
        if not os.path.exists(gk):
            with open(gk, "w", encoding="utf-8") as fp:
                fp.write("")

        articles = fetch_articles(limit=MAX_POSTS)
        if not articles:
            debug("ℹ️ No articles returned.")
            sys.exit(0)

        created = 0
        for a in articles:
            if write_post(a):
                created += 1

        debug(f"🎉 Done. {created} new post(s).")
    except Exception as e:
        debug(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
