#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Update AI blog posts from Newsdata API.
- Fetches up to MAX_POSTS fresh tech/AI articles
- Applies quality filters
- Adds fallback image if missing
- Writes enriched .md posts into _posts/

Env vars:
  NEWSDATA_API_KEY  (preferido)  ou  NEWS_API_KEY (alternativa)

Requisitos:
  pip install requests python-slugify
"""

from __future__ import annotations

import os
import re
import sys
import json
import textwrap
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import requests
from slugify import slugify

# ---------- Configuração ----------
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY") or os.getenv("NEWS_API_KEY")

# Palavras-chave (mantidas curtas para não exceder limite de query)
KEYWORDS = [
    'ai', 'artificial intelligence', 'machine learning',
    'openai', 'anthropic', 'meta ai', 'google ai'
]
LANG = "en"
CATEGORY = "technology"
COUNTRY = None           # 'us' ou None – Newsdata às vezes filtra demais por país
MAX_POSTS = 5            # quantos posts criar por execução
POSTS_DIR = "_posts"
FALLBACK_IMAGE = "/assets/ai-hero.jpg"   # deve existir no repositório
USER_AGENT = "ai-discovery-bot/1.0 (+github actions)"

# ---------- Utilidades ----------

def debug(msg: str) -> None:
    print(msg, flush=True)

def safe_get(d: Dict[str, Any], *keys: str) -> Optional[str]:
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return str(cur) if cur is not None else None

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    # remove múltiplos espaços/newlines, e caracteres estranhos
    s = re.sub(r"\s+", " ", s).strip()
    return s

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

def pick_image(article: Dict[str, Any]) -> str:
    """
    Tenta apanhar uma imagem credível do item da API.
    Cai em FALLBACK_IMAGE se nada existir.
    """
    candidates = [
        safe_get(article, "image_url"),
        safe_get(article, "image"),           # outros esquemas
        safe_get(article, "source_icon"),
        safe_get(article, "source", "icon")
    ]
    for url in candidates:
        if url and isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
    return FALLBACK_IMAGE

def shorten(s: str, max_len: int = 280) -> str:
    s = clean_text(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"

def build_query() -> str:
    # Junta as keywords com OR e corta se estourar 100 chars
    parts = [f'"{kw}"' if " " in kw else kw for kw in KEYWORDS]
    query = " OR ".join(parts)
    if len(query) > 95:
        query = '"artificial intelligence" OR ai OR "machine learning"'
    return query

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
    # Levanta HTTPError se 4xx/5xx
    r.raise_for_status()
    return r.json()

def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    """
    Vai buscar artigos até 'limit' utilizando paginação simples.
    Aplica filtros mínimos de qualidade.
    """
    if not API_KEY:
        raise ValueError("NEWS_API_KEY (ou NEWSDATA_API_KEY) not set.")

    debug("🧠 update_posts.py starting…")
    debug("📰 Fetching latest AI articles...")

    collected: List[Dict[str, Any]] = []
    page = 1
    while len(collected) < limit and page <= 3:
        try:
            data = call_api(page=page)
        except requests.HTTPError as e:
            # Mostrar URL útil no log
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

            # filtros de base
            if not title or not link:
                continue
            if has_low_value_markers(desc) or has_low_value_markers(content) or has_low_value_markers(title):
                continue
            if too_similar(title, desc) and len(desc) < 60:
                # praticamente sem informação
                continue

            item_norm = {
                "title": title,
                "description": desc,
                "content": content,
                "link": link,
                "source_id": source_id or "source",
                "image": pick_image(item),
                # published date pode vir em vários campos; se não vier, usa now UTC
                "pubDate": clean_text(safe_get(item, "pubDate"))
                           or clean_text(safe_get(item, "published_at"))
                           or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            collected.append(item_norm)

        page += 1

    return collected[:limit]

def enrich_text(title: str, desc: str, content: str, source: str, link: str) -> str:
    """
    Gera um conteúdo ampliado (sem usar serviços externos), baseado em título/descrição/conteúdo.
    É melhor do que uma linha só, e ajuda a aprovação do AdSense.
    """
    # base
    base = clean_text(content) or clean_text(desc)
    base = shorten(base, 700)

    # “Porque interessa” – heurístico simples
    why = []
    title_low = title.lower()
    if any(k in title_low for k in ["stock", "earnings", "valuation", "market"]):
        why.append("Impacto nos mercados e na avaliação de empresas.")
    if any(k in title_low for k in ["policy", "regulation", "law", "ban"]):
        why.append("Mudanças regulatórias podem redefinir o panorama competitivo.")
    if any(k in title_low for k in ["chip", "gpu", "hardware", "inference"]):
        why.append("Infraestrutura de hardware influencia performance e custo de IA.")
    if any(k in title_low for k in ["research", "paper", "breakthrough", "study"]):
        why.append("Avanços de investigação podem abrir novos casos de uso.")
    if not why:
        why.append("Relevante para o ecossistema de IA e seus casos de uso.")

    bullets: List[str] = []
    for part in re.split(r"[.;]\s+", base)[:4]:
        part = clean_text(part)
        if part and 25 <= len(part) <= 220:
            bullets.append(part)

    # Montagem
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
    fm = {
        "layout": "post",
        "title": title.replace('"', '\\"'),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "excerpt": shorten(description, 300),
        "categories": ["ai", "news"],
        "image": article.get("image") or FALLBACK_IMAGE,
        "source": article.get("source_id") or "source",
        "source_url": article.get("link"),
    }

    # YAML manual simples para evitar libs extra
    fm_lines = ["---"]
    fm_lines.append(f'layout: {fm["layout"]}')
    fm_lines.append(f'title: "{fm["title"]}"')
    fm_lines.append(f'date: {fm["date"]}')
    fm_lines.append(f'excerpt: "{fm["excerpt"].replace(\'"\', "\\\\\"")}"')
    fm_lines.append('categories: [ai, news]')
    fm_lines.append(f'image: "{fm["image"]}"')
    fm_lines.append(f'source: "{fm["source"]}"')
    fm_lines.append(f'source_url: "{fm["source_url"]}"')
    fm_lines.append("---")

    md = "\n".join(fm_lines) + "\n\n" + body + "\n"
    return md

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

# ---------- Main ----------

def main() -> None:
    try:
        articles = fetch_articles(limit=MAX_POSTS)
        if not articles:
            debug("ℹ️ No articles found.")
            sys.exit(0)

        created = 0
        for art in articles:
            path = write_post(art)
            if path:
                created += 1
                debug(f"✅ Post criado: {path}")

        if created == 0:
            debug("ℹ️ Nothing new to write.")
        else:
            debug(f"🎉 Done. {created} post(s) written.")
    except Exception as e:
        debug(f"❌ Erro: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
