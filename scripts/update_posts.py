#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
scripts/update_posts.py
Gera posts Jekyll a partir da Newsdata API com filtros de qualidade.
- Pede até 5 artigos (podes alterar MAX_POSTS)
- Evita artigos de baixa qualidade (pagos, vazios, desporto, etc.)
- Usa paginação via nextPage
"""

import os
import re
import sys
import json
import time
import textwrap
import datetime as dt
from pathlib import Path

import requests
from slugify import slugify

# ==========================
# Configuração
# ==========================
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY") or os.getenv("NEWSDATA_API_KEY")

# Palavras AI (busca)
AI_QUERY_TERMS = [
    "artificial intelligence",
    "AI",
    "machine learning",
    "generative ai",
    "openai",
    "anthropic",
    "google ai",
    "meta ai",
    "llm",
]

# Palavras a evitar (desporto / temas fora de AI que têm aparecido)
BANNED_TERMS = [
    # futebol / desporto
    "premier league", "bundesliga", "rangers", "celtic", "guardiola",
    "manchester city", "brighton", "espn", "disney+", "derbies",
    # entretenimento / soap opera
    "general hospital", "soap opera",
    # artigos puramente regionais de tv
    "broadcasts:", "sunday:", "fixtures",
]

# Frases que indicam conteúdo fechado / fraco
PAID_WALL_MARKERS = [
    "only available in paid plans",
    "subscribe to read the full",
    "subscription required",
]

# Pastas/limites
POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(parents=True, exist_ok=True)

MAX_POSTS = int(os.getenv("MAX_POSTS", "5"))  # quantos posts criar
MIN_DESC_CHARS = 160                           # desc mínima aceitável
MIN_CONTENT_CHARS = 280                        # conteúdo mínimo aceitável

# ==========================
# Utilitários
# ==========================

def log(msg: str) -> None:
    print(msg, flush=True)

def today_ymd() -> str:
    return dt.datetime.utcnow().date().isoformat()

def sanitize_text(s: str) -> str:
    """Limpa espaços, remove html simples, normaliza quotes."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)    # remove tags html
    s = re.sub(r"\s+", " ", s).strip()
    return s

def too_sporty(text: str) -> bool:
    text_l = text.lower()
    return any(term in text_l for term in BANNED_TERMS)

def looks_paywalled(text: str) -> bool:
    text_l = text.lower()
    return any(marker in text_l for marker in PAID_WALL_MARKERS)

def good_quality(title: str, desc: str, content: str) -> bool:
    """Heurística simples de qualidade."""
    t = sanitize_text(title)
    d = sanitize_text(desc)
    c = sanitize_text(content)

    # não pode estar vazio
    if not t:
        return False

    # evitar títulos repetidos no excerpt
    if d and d.lower() == t.lower():
        return False

    # rejeitar paywall markers
    if looks_paywalled(d) or looks_paywalled(c):
        return False

    # rejeitar desporto / fora de tema óbvio
    if too_sporty(" ".join([t, d, c])):
        return False

    # algum conteúdo mínimo
    if (len(c) < MIN_CONTENT_CHARS) and (len(d) < MIN_DESC_CHARS):
        return False

    return True

def clamp_excerpt(text: str, max_chars: int = 240) -> str:
    text = sanitize_text(text)
    if len(text) <= max_chars:
        return text
    # corta por palavra
    return textwrap.shorten(text, width=max_chars, placeholder="…")

def pick_image(item: dict) -> str:
    """Tenta extrair uma imagem do item Newsdata."""
    for key in ("image_url", "image", "image_link", "thumbnail"):
        url = item.get(key)
        if url and isinstance(url, str) and url.startswith("http"):
            return url
    return ""

def api_key_or_die() -> str:
    if not API_KEY:
        raise RuntimeError("API_KEY não encontrada. Define NEWS_API_KEY (ou NEWSDATA_API_KEY) nas Actions.")
    return API_KEY

# ==========================
# API
# ==========================

def build_query() -> str:
    # liga termos com OR para cobrir várias variantes
    return " OR ".join(AI_QUERY_TERMS)

def call_api(params: dict) -> dict:
    """Chama API e valida erros usuais."""
    resp = requests.get(API_URL, params=params, timeout=30)
    try:
        data = resp.json()
    except Exception:
        resp.raise_for_status()
        # se chegou aqui, não é JSON
        raise

    # Newsdata por vezes devolve {"status":"error", "results":{"message": ...}}
    # ou HTTP 422 para filtros não suportados.
    if resp.status_code != 200 or data.get("status") != "success":
        # Mostrar URL para facilitar debug
        log(f"⚠️ API error ({resp.status_code}): {json.dumps(data) if isinstance(data, dict) else data}")
        log(f"URL: {resp.url}")
        resp.raise_for_status()

    return data

def fetch_latest(max_items: int = MAX_POSTS) -> list[dict]:
    """
    Vai buscar artigos usando paginação por nextPage.
    Só aceita artigos que passem os filtros de qualidade.
    """
    api_key_or_die()
    query = build_query()

    params = {
        "apikey": API_KEY,
        "q": query,
        "language": "en",
        "category": "technology",
        # A Newsdata usa paginação por nextPage (token). Não passar "page"!
        # Podemos também pedir data recente filtrando 'from_date' se necessário.
        # "from_date": today_ymd(),  # opcional – alguns planos não suportam este filtro
    }

    accepted: list[dict] = []
    next_page = None
    tries = 0

    while len(accepted) < max_items and tries < 8:  # limite de segurança
        if next_page:
            params["page"] = next_page  # apesar da doc, a resposta devolve 'nextPage' e aceita como 'page'
        else:
            # garantir que não fica 'page' pendurado entre ciclos
            params.pop("page", None)

        data = call_api(params)

        results = data.get("results") or []
        if not isinstance(results, list) or not results:
            break

        for it in results:
            if len(accepted) >= max_items:
                break

            title = sanitize_text(it.get("title", ""))
            desc = sanitize_text(it.get("description", ""))
            content = sanitize_text(it.get("content", "")) or desc

            if not good_quality(title, desc, content):
                continue

            accepted.append(it)

        # paginação
        next_page = data.get("nextPage")
        tries += 1
        if not next_page:
            break

        # respeitar a API
        time.sleep(0.4)

    return accepted[:max_items]

# ==========================
# Escrita do post
# ==========================

def build_markdown(item: dict) -> str:
    """Gera o conteúdo Markdown com front-matter."""
    title = sanitize_text(item.get("title", ""))
    desc = sanitize_text(item.get("description", ""))
    content = sanitize_text(item.get("content", "")) or desc

    # fallback: pequeno 'mini-resumo' se o content for curto
    if len(content) < MIN_CONTENT_CHARS:
        # criar um parágrafo a partir da desc + título
        base = desc if len(desc) >= 80 else (title + ". " + desc)
        content = clamp_excerpt(base, 900)

    image_url = pick_image(item)
    source_id = item.get("source_id") or item.get("source") or ""
    link = item.get("link") or item.get("url") or ""
    the_date = dt.datetime.utcnow().date().isoformat()

    # Sanitizar strings para YAML
    safe_title = title.replace('"', '\\"')
    safe_excerpt = clamp_excerpt(desc or content, 240).replace('"', '\\"')

    fm_lines = [
        "---",
        'layout: post',
        f'title: "{safe_title}"',
        f'date: {the_date}',
        'tags: [ai, news]',
    ]
    if image_url:
        fm_lines.append(f'image: "{image_url}"')
    if source_id:
        fm_lines.append(f'source: "{source_id}"')
    if link:
        fm_lines.append(f'link: "{link}"')
    fm_lines.append(f'excerpt: "{safe_excerpt}"')
    fm_lines.append("---")

    body_lines = []

    if image_url:
        # Mostra a imagem dentro do corpo também (o layout já a pode usar via front-matter)
        body_lines.append(f'![{safe_title}]({image_url})\n')

    body_lines.append(content)
    if link:
        body_lines.append(f'\n\n_Read more at: [{source_id or "source"}]({link})_')

    return "\n".join(fm_lines) + "\n\n" + "\n".join(body_lines).strip() + "\n"

def save_item(item: dict) -> str:
    """Guarda um item como ficheiro em _posts/."""
    title = sanitize_text(item.get("title", "untitled"))
    slug = slugify(title)[:70] or "post"
    date_prefix = today_ymd()
    filename = POSTS_DIR / f"{date_prefix}-{slug}.md"

    # Evitar sobrescrever se já existe (por ex. se o slug repetiu)
    idx = 2
    while filename.exists():
        filename = POSTS_DIR / f"{date_prefix}-{slug}-{idx}.md"
        idx += 1

    md = build_markdown(item)
    filename.write_text(md, encoding="utf-8")
    return str(filename)

# ==========================
# Main
# ==========================

def main() -> None:
    log("🧠 Running update_posts.py...")
    api_key_or_die()

    log("📰 Fetching latest AI articles...")
    items = fetch_latest(MAX_POSTS)

    if not items:
        log("ℹ️ No acceptable articles found. Nothing to do.")
        return

    created = []
    for it in items:
        try:
            path = save_item(it)
            created.append(path)
            log(f"✅ Created: {path}")
        except Exception as e:
            log(f"❌ Failed to save post: {e}")

    if created:
        log(f"🎉 Done. {len(created)} post(s) created.")
    else:
        log("ℹ️ No files created after filtering.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ Fatal error: {e}")
        sys.exit(1)
