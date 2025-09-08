#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI Discovery Blog — Auto updater (Newsdata.io)

- Busca notícias de IA via Newsdata
- Tolerante a 422/400: tenta queries cada vez mais simples
- Gera posts Jekyll em _posts/
- Trata imagens: download/cache -> heróis por tópico -> rotação -> fallback

Requisitos:
  pip install requests python-slugify

ENV:
  NEWS_API_KEY   (colocado em Settings → Secrets and variables → Actions)
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
API_KEY = os.getenv("NEWS_API_KEY")

# palavras-chave curtas (para não estourar limite)
KEYWORDS = ["ai", "artificial intelligence", "machine learning", "openai", "anthropic", "google ai", "meta ai"]
LANG = "en"
MAX_POSTS = 10

POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"
USER_AGENT = "ai-discovery-bot/1.4 (+github actions)"

# imagens
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

# ---------------- API helpers ----------------
def build_query_rich() -> str:
    # versão “rica”, ainda curta
    parts = ['"artificial intelligence"', "ai", '"machine learning"', "openai", "anthropic", '"google ai"', '"meta ai"']
    q = " OR ".join(parts)
    # Newsdata tem limite ~100 chars; garantir abaixo disso
    if len(q) > 95:
        q = '"artificial intelligence" OR ai OR "machine learning"'
    return q

def build_query_simple() -> str:
    return '"artificial intelligence" OR ai OR "machine learning"'

def call_api_with_fallbacks(page: int = 1) -> Dict[str, Any]:
    """
    Tenta variantes de parâmetros até uma funcionar.
    Ordem:
      1) q=rico + language=en + category=technology
      2) q=rico + language=en
      3) q=ai + language=en
    """
    headers = {"User-Agent": USER_AGENT}
    variants: List[Dict[str, Any]] = [
        {"q": build_query_rich(), "language": LANG, "category": "technology", "page": page},
        {"q": build_query_rich(), "language": LANG, "page": page},
        {"q": "ai", "language": LANG, "page": page},
    ]

    last_err: Optional[Exception] = None
    for i, params in enumerate(variants, start=1):
        # remove None/False
        params = {k: v for k, v in params.items() if v}
        try:
            r = requests.get(API_URL, params={"apikey": API_KEY, **params}, headers=headers, timeout=20)
            # se 422/400, tentar próximo
            if r.status_code in (400, 422):
                debug(f"⚠️  API {r.status_code} com variante {i}: {r.url}")
                last_err = requests.HTTPError(f"{r.status_code} for {r.url}")
                continue
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            last_err = e
            debug(f"⚠️  HTTPError com variante {i}: {e}")
            continue
        except Exception as e:
            last_err = e
            debug(f"⚠️  Erro com variante {i}: {e}")
            continue

    # se todas falharem:
    if last_err:
        raise last_err
    raise RuntimeError("API call failed for all variants")

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

        name = os.path.basename(urlparse(url).path) or slugify(title)
        base, ext = os.path.splitext(name)
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
    for k in ("image_url", "image"):
        url = clean_text(item.get(k))
        if url and url.startswith(("http://", "https://")):
            local = download_and_cache_image(url, title)
            if local:
                return local
    topic = detect_topic(title, desc)
    if topic:
        cand = TOPIC_HEROES.get(topic)
        if cand and os.path.exists(cand.lstrip("/")):
            return cand
    return pick_rotating_hero(title)

# ---------------- Fetch & build posts ----------------
def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("NEWS_API_KEY not set.")

    debug("📰 Fetching articles...")
    collected: List[Dict[str, Any]] = []
    page = 1

    while len(collected) < limit and page <= 3:
        data = call_api_with_fallbacks(page=page)
        results = data.get("results") or data.get("articles") or []
        if not results:
            break

        for item in results:
            if len(collected) >= limit:
                break

            title = clean_text(item.get("title"))
            desc = clean_text(item.get("description") or item.get("summary"))
            link = clean_text(item.get("link") or item.get("url"))
            source_id = clean_text(item.get("source_id") or item.get("source") or "source")
            pubdate = clean_text(item.get("pubDate") or item.get("published_at") or "")

            if not title or not link:
                continue

            image_path = pick_image(item, title, desc)
            collected.append({
                "title": title,
                "description": desc,
                "link": link,
                "source_id": source_id,
                "image": image_path,
                "pubDate": pubdate or datetime.now(timezone.utc).isoformat(),
            })

        page += 1

    return collected[:limit]

def build_markdown(article: Dict[str, Any]) -> str:
    safe_title = yml_escape(article["title"])
    safe_excerpt = yml_escape(article.get("description") or "")
    image = article.get("image") or GENERIC_FALLBACK
    source = yml_escape(article.get("source_id") or "source")
    source_url = yml_escape(article.get("link") or "")

    fm = [
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
    # conteúdo simples; se quiser, dá para enriquecer depois
    body = article.get("description") or ""
    return "\n".join(fm) + "\n\n" + body + "\n"

def make_filename(title: str, date_str: Optional[str] = None) -> str:
    date_part = (date_str or datetime.now(timezone.utc).date().isoformat())[:10]
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
def main():
    try:
        ensure_dir(ASSET_CACHE_DIR)
        if not os.path.exists(os.path.join(ASSET_CACHE_DIR, ".gitkeep")):
            open(os.path.join(ASSET_CACHE_DIR, ".gitkeep"), "w").close()

        articles = fetch_articles()
        if not articles:
            debug("ℹ️ No articles found.")
            return

        created = 0
        for art in articles:
            if write_post(art):
                created += 1

        debug(f"🎉 Done. {created} new post(s).")
    except Exception as e:
        debug(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
