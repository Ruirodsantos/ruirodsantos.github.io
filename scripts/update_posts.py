#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
update_posts.py  —  Gera posts Jekyll a partir do Newsdata.io (ou NEWS_API_KEY compatível).

- Lê a API key de NEWSDATA_API_KEY (preferido) ou NEWS_API_KEY.
- Busca notícias de IA/tech (query curta < 100 chars).
- Filtra itens fracos (p.ex. "ONLY AVAILABLE IN PAID PLANS", excerpt == título, etc).
- Garante uma imagem (da matéria; fallback: /assets/ai-hero.svg).
- Enriquecimento simples do corpo (TL;DR + porque importa + bullets).
- Escreve arquivos em _posts/YYYY-MM-DD-slug.md.

Requisitos:
  pip install requests python-slugify
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from slugify import slugify

# ---------------- Config ----------------

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY") or os.getenv("NEWS_API_KEY")

# Query curta para não estourar o limite de 100 chars do Newsdata
KEYWORDS = [
    "ai",
    "artificial intelligence",
    "machine learning",
    "openai",
    "anthropic",
    "meta ai",
    "google ai",
]

LANG = "en"
CATEGORY = "technology"
COUNTRY = None  # manter None para não filtrar demais
MAX_POSTS = 5
MAX_PAGES = 3
POSTS_DIR = "_posts"

# *** IMPORTANTE: você tem um SVG, então use-o como fallback ***
FALLBACK_IMAGE = "/assets/ai-hero.svg"

USER_AGENT = "ai-discovery-bot/1.0 (+github actions)"


# ---------------- Utils ----------------

def log(msg: str) -> None:
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
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s


def too_similar(a: str, b: str) -> bool:
    a2 = clean_text(a).lower()
    b2 = clean_text(b).lower()
    return bool(a2 and b2 and (a2 == b2 or a2 in b2 or b2 in a2))


def has_low_value_markers(t: str) -> bool:
    t2 = t.lower()
    markers = [
        "only available in paid plans",
        "only available in paid plan",
        "subscribe to read",
        "sign in to continue",
        "under construction",
    ]
    return any(m in t2 for m in markers)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def build_query() -> str:
    # Junta com OR, mas mantém < 100 chars
    parts = [f'"{k}"' if " " in k else k for k in KEYWORDS]
    q = " OR ".join(parts)
    if len(q) > 95:
        q = '"artificial intelligence" OR ai OR "machine learning"'
    return q


def pick_image(article: Dict[str, Any]) -> str:
    # Tenta campos comuns do Newsdata (ou variações) e cai para fallback SVG
    candidates = [
        safe_get(article, "image_url"),
        safe_get(article, "image"),
        safe_get(article, "source", "icon"),
        safe_get(article, "source_icon"),
    ]
    for url in candidates:
        if url and url.startswith(("http://", "https://")):
            return url
    return FALLBACK_IMAGE


def shorten(s: str, max_len: int) -> str:
    s2 = clean_text(s)
    return s2 if len(s2) <= max_len else s2[: max_len - 1].rstrip() + "…"


# ---------------- API ----------------

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
    # Mostra URL útil para debug
    log(f"URL: {r.url}")
    r.raise_for_status()
    data = r.json()

    # Newsdata retorna erro dentro de 200 às vezes
    if isinstance(data, dict) and data.get("status") == "error":
        raise requests.HTTPError(f"API error: {data}")

    return data


def fetch_articles(limit: int) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("NEWS_API_KEY (ou NEWSDATA_API_KEY) não está definido.")

    log("🧠 update_posts.py starting…")
    log("🗞️  Fetching latest AI articles…")

    out: List[Dict[str, Any]] = []
    page = 1
    while len(out) < limit and page <= MAX_PAGES:
        try:
            data = call_api(page=page)
        except requests.HTTPError as e:
            log(f"❌ Falha na API: {e}")
            break
        except Exception as e:
            log(f"❌ Erro inesperado: {e}")
            break

        results = data.get("results") or data.get("articles") or []
        if not results:
            break

        for item in results:
            if len(out) >= limit:
                break

            title = clean_text(safe_get(item, "title"))
            desc = clean_text(safe_get(item, "description"))
            content = clean_text(safe_get(item, "content"))
            link = clean_text(safe_get(item, "link")) or clean_text(safe_get(item, "url"))
            source_id = clean_text(safe_get(item, "source_id")) or clean_text(safe_get(item, "source"))
            pub = (
                clean_text(safe_get(item, "pubDate"))
                or clean_text(safe_get(item, "published_at"))
                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            )

            # Filtros de qualidade
            if not title or not link:
                continue
            if has_low_value_markers(title) or has_low_value_markers(desc) or has_low_value_markers(content):
                continue
            if too_similar(title, desc) and len(desc) < 60:
                continue

            out.append(
                {
                    "title": title,
                    "description": desc,
                    "content": content,
                    "link": link,
                    "source_id": source_id or "source",
                    "pubDate": pub,
                    "image": pick_image(item),
                }
            )

        page += 1

    return out[:limit]


# ---------------- Enriquecimento ----------------

def enrich_text(title: str, desc: str, content: str, source: str, link: str) -> str:
    base = clean_text(content) or clean_text(desc)
    base = shorten(base, 700)

    # “por que importa” heurístico
    why: List[str] = []
    tl = title.lower()
    if any(k in tl for k in ["stock", "earnings", "valuation", "market"]):
        why.append("Impacto nos mercados e na avaliação de empresas.")
    if any(k in tl for k in ["policy", "regulation", "law", "ban"]):
        why.append("Mudanças regulatórias podem redefinir o panorama competitivo.")
    if any(k in tl for k in ["chip", "gpu", "hardware", "inference"]):
        why.append("Infraestrutura de hardware influencia performance e custo de IA.")
    if any(k in tl for k in ["research", "paper", "breakthrough", "study"]):
        why.append("Avanços de pesquisa podem abrir novos casos de uso.")
    if not why:
        why.append("Relevante para o ecossistema de IA e seus casos de uso.")

    bullets: List[str] = []
    for part in re.split(r"[.;]\s+", base)[:4]:
        part = clean_text(part)
        if 25 <= len(part) <= 220:
            bullets.append(part)

    pieces: List[str] = []
    pieces.append("### TL;DR")
    pieces.append(shorten(base or title, 240))

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


# ---------------- Markdown / Writing ----------------

def yaml_escape(s: str) -> str:
    """Escapa aspas duplas para YAML de forma simples."""
    return clean_text(s).replace('"', '\\"')


def build_markdown(article: Dict[str, Any]) -> str:
    title = article["title"]
    desc = article.get("description", "") or ""
    body = enrich_text(title, desc, article.get("content", ""), article["source_id"], article["link"])

    # Valores já escapados (evita backslashes dentro de f-strings)
    title_esc = yaml_escape(title)
    excerpt_esc = yaml_escape(shorten(desc or title, 300))
    image_url = article.get("image") or FALLBACK_IMAGE
    source_esc = yaml_escape(article.get("source_id") or "source")
    source_url_esc = yaml_escape(article.get("link") or "")

    date_iso = datetime.now(timezone.utc).date().isoformat()

    fm_lines = [
        "---",
        "layout: post",
        f'title: "{title_esc}"',
        f"date: {date_iso}",
        f'excerpt: "{excerpt_esc}"',
        "categories: [ai, news]",
        f'image: "{image_url}"',
        f'source: "{source_esc}"',
        f'source_url: "{source_url_esc}"',
        "---",
    ]

    return "\n".join(fm_lines) + "\n\n" + body + "\n"


def make_filename(title: str, pub_date_iso: Optional[str]) -> str:
    date_part = (pub_date_iso or datetime.now(timezone.utc).date().isoformat())[:10]
    slug = slugify(title)[:80] or "post"
    return os.path.join(POSTS_DIR, f"{date_part}-{slug}.md")


def write_post(article: Dict[str, Any]) -> Optional[str]:
    ensure_dir(POSTS_DIR)
    path = make_filename(article["title"], article.get("pubDate"))
    if os.path.exists(path):
        log(f"↩︎ Skipping (already exists): {os.path.basename(path)}")
        return None
    md = build_markdown(article)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path


# ---------------- Main ----------------

def main() -> None:
    try:
        arts = fetch_articles(limit=MAX_POSTS)
        if not arts:
            log("ℹ️ Nenhum artigo encontrado.")
            sys.exit(0)

        created = 0
        for a in arts:
            p = write_post(a)
            if p:
                created += 1
                log(f"✅ Post criado: {p}")

        if created == 0:
            log("ℹ️ Nada novo para escrever.")
        else:
            log(f"🎉 Concluído. {created} post(s) escritos.")
    except Exception as e:
        log(f"❌ Erro: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
