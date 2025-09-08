#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-updater para AI Discovery Blog (Newsdata.io).

- Busca artigos de IA (q=ai) em EN
- Evita usar "category" com "q" (causa HTTP 422 no Newsdata)
- Faz download de imagem do artigo (cache em assets/cache) quando possível
- Se falhar, usa heróis por tópico ou rotação de genéricos
- Escreve .md em _posts/ com front matter seguro

Requisitos:
  pip install requests python-slugify
Ambiente:
  NEWS_API_KEY (ou NEWSDATA_API_KEY)
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
API_KEY = os.getenv("NEWS_API_KEY") or os.getenv("NEWSDATA_API_KEY")

LANG = "en"
QUERY = "ai"            # Só q=ai (NÃO usar category junto para evitar 422)
MAX_POSTS = 10          # quantos posts criar por execução (ajusta à vontade)

POSTS_DIR = "_posts"
ASSET_CACHE_DIR = "assets/cache"

# Fallbacks de imagem
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
USER_AGENT = "ai-discovery-bot/2.0 (+github actions)"


# ---------------- Utils ----------------
def debug(msg: str) -> None:
    print(msg, flush=True)


def clean(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def shorten(s: str, max_len: int = 280) -> str:
    s = clean(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def yml(s: str) -> str:
    return clean(s).replace('"', r'\"')


def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


# ---------------- API ----------------
def call_api(page: int) -> Dict[str, Any]:
    params = {
        "apikey": API_KEY,
        "q": QUERY,          # <<< só query
        "language": LANG,
        "page": page,
    }
    headers = {"User-Agent": USER_AGENT}
    debug(f"🔎 GET {API_URL} params={params}")
    r = requests.get(API_URL, params=params, headers=headers, timeout=25)
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
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25, stream=True)
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
        debug(f"⚠️ img download fail: {e}")
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
    # 1) tenta imagem original
    for k in ("image_url", "image"):
        url = clean(item.get(k))
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


# ---------------- Fetch & build ----------------
def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("NEWS_API_KEY (ou NEWSDATA_API_KEY) não definido.")

    debug("🧠 Fetching AI articles...")
    posts: List[Dict[str, Any]] = []
    page = 1

    while len(posts) < limit and page <= 5:
        try:
            data = call_api(page)
        except requests.HTTPError as e:
            debug(f"❌ HTTP error: {e}")
            break
        except Exception as e:
            debug(f"❌ API error: {e}")
            break

        results = data.get("results") or []
        if not results:
            break

        for it in results:
            if len(posts) >= limit:
                break

            title = clean(it.get("title"))
            desc = clean(it.get("description"))
            link = clean(it.get("link")) or clean(it.get("url"))
            source_id = clean(it.get("source_id") or it.get("source") or "source")
            pubdate = clean(it.get("pubDate") or it.get("published_at") or "")

            if not title or not link:
                continue

            # filtro simples para garantir IA
            if " ai " not in f" {title.lower()} " and " artificial intelligence" not in title.lower():
                # se a API devolver algo off-topic, salta
                pass  # mantemos porque já usamos q=ai; remove este pass se quiseres filtrar mais

            image_path = pick_image(it, title, desc)

            posts.append({
                "title": title,
                "description": desc,
                "link": link,
                "source_id": source_id,
                "image": image_path,
                "pubDate": pubdate or datetime.now(timezone.utc).isoformat(),
            })

        page += 1

    return posts[:limit]


def build_markdown(article: Dict[str, Any]) -> str:
    safe_title = yml(article["title"])
    safe_excerpt = yml(article.get("description") or "")
    image = article.get("image") or GENERIC_FALLBACK
    source = yml(article.get("source_id") or "source")
    source_url = yml(article.get("link") or "")

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
    body = article.get("description") or ""
    if body:
        body += "\n\n"
    body += f"> Source: [{source}]({source_url})\n"
    return "\n".join(fm) + "\n\n" + body


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
        # garante que a pasta entra no repo
        gitkeep = os.path.join(ASSET_CACHE_DIR, ".gitkeep")
        if not os.path.exists(gitkeep):
            with open(gitkeep, "w", encoding="utf-8") as gk:
                gk.write("")

        articles = fetch_articles()
        created = 0
        for art in articles:
            if write_post(art):
                created += 1

        if created == 0:
            debug("ℹ️ Nothing new.")
        else:
            debug(f"🎉 Done. {created} new post(s).")
    except Exception as e:
        debug(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
