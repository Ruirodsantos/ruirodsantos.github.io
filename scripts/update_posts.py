#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gera posts diários de IA a partir do Newsdata.io.

- Usa apenas a env var NEWSDATA_API_KEY
- Faz chamadas paginadas (até apanhar N artigos)
- Escreve markdown em _posts/
- Falha com exit code se:
  * não houver API key
  * a chamada à API falhar
  * zero artigos retornados
"""

from __future__ import annotations

import os
import sys
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import requests
from slugify import slugify

# ---------------- Config ----------------
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY")  # <- só esta
LANG = "en"
CATEGORY = "technology"
MAX_POSTS = 10                     # queres 10 por dia
POSTS_DIR = "_posts"
USER_AGENT = "ai-discovery-bot/2.0 (+github actions)"

# query super curta para não dar 422 de comprimento
QUERY = 'ai'

# -------------- utils -------------------
def log(msg: str) -> None:
    print(msg, flush=True)

def clean(s: Optional[str]) -> str:
    if not s: return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def yml(s: str) -> str:
    return clean(s).replace('"', r'\"')

def shorten(s: str, n: int) -> str:
    s = clean(s)
    if len(s) <= n: return s
    return s[:n-1].rstrip() + "…"

# -------------- API ---------------------
def call_api(page: int) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "apikey": API_KEY,
        "q": QUERY,               # manter curto
        "language": LANG,
        "category": CATEGORY,
        "page": page,
    }
    headers = {"User-Agent": USER_AGENT}
    # máscara na impressão
    masked = {**params, "apikey": "***"}
    log(f"🔎 GET {API_URL} params={masked}")
    r = requests.get(API_URL, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise RuntimeError("NEWSDATA_API_KEY not set")

    log("🧠 Fetching articles (category=technology)...")
    items: List[Dict[str, Any]] = []
    page = 1

    while len(items) < limit and page <= 5:
        data = call_api(page)
        results = data.get("results") or []
        if not results:
            break

        for it in results:
            if len(items) >= limit:
                break
            title = clean(it.get("title"))
            link = clean(it.get("link"))
            desc = clean(it.get("description"))
            if not title or not link:
                continue
            items.append({
                "title": title,
                "link": link,
                "desc": desc,
                "source": clean(it.get("source_id") or it.get("source") or "source"),
                "pub": clean(it.get("pubDate") or it.get("published_at") or ""),
            })
        page += 1

    return items[:limit]

# -------------- posts -------------------
def fm_lines(a: Dict[str, Any]) -> List[str]:
    return [
        "---",
        "layout: post",
        f'title: "{yml(a["title"])}"',
        f'date: {datetime.now(timezone.utc).date().isoformat()}',
        f'excerpt: "{yml(shorten(a.get("desc",""), 300))}"',
        "categories: [ai, news]",
        # usa sempre o herói genérico por agora; depois podes ligar rotação/imagens
        'image: "/assets/ai-hero.svg"',
        f'source: "{yml(a.get("source","source"))}"',
        f'source_url: "{yml(a.get("link",""))}"',
        "---",
    ]

def build_md(a: Dict[str, Any]) -> str:
    body = a.get("desc") or ""
    return "\n".join(fm_lines(a)) + "\n\n" + body + "\n"

def filename_for(title: str, pub: Optional[str]) -> str:
    date_part = (pub or datetime.now(timezone.utc).isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")

def write_posts(items: List[Dict[str, Any]]) -> int:
    ensure_dir(POSTS_DIR)
    written = 0
    for a in items:
        path = filename_for(a["title"], a.get("pub"))
        if os.path.exists(path):
            log(f"↩︎ skip (exists) {os.path.basename(path)}")
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_md(a))
        written += 1
        log(f"✅ wrote {path}")
    return written

# -------------- main --------------------
def main() -> None:
    try:
        ensure_dir(POSTS_DIR)
        arts = fetch_articles(MAX_POSTS)
        if not arts:
            raise RuntimeError("API returned 0 articles")
        n = write_posts(arts)
        if n == 0:
            log("ℹ️ No new posts to write.")
        else:
            log(f"🎉 Done: {n} new post(s).")
    except requests.HTTPError as e:
        # mostra URL já vem impresso acima; aqui falha claramente
        log(f"❌ HTTP {e.response.status_code}: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
