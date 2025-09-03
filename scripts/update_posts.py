#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gera até N posts por dia a partir da Newsdata.io, com:
 - filtros de qualidade,
 - expansão automática de conteúdo,
 - imagem (se disponível),
 - de-duplicação por slug.

Requer variável de ambiente: NEWSDATA_API_KEY (ou NEWS_API_KEY)
"""

import os
import re
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from slugify import slugify  # pip install python-slugify
except Exception:
    # fallback super simples
    def slugify(s: str) -> str:
        s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
        s = re.sub(r"\s+", "-", s.strip())
        return s.lower()

# ------------------------------------------------------------
# Configurações
# ------------------------------------------------------------
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY") or os.getenv("NEWS_API_KEY")

POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(exist_ok=True)

# Q curta para evitar "UnsupportedQueryLength"
# (não use termos gigantes; 100 chars é o limite prático)
QUERY = "ai OR artificial intelligence OR machine learning"

LANG = "en"
CATEGORY = "technology"

# Quantidade máxima de posts a criar num run
MAX_POSTS = 5

# Critérios de qualidade/limpeza
MIN_BODY_CHARS = 500           # final expandido precisa ter ~500+ chars
MIN_EXCERPT_CHARS = 60         # excerpt mínimo
BANNED_PHRASES = {
    "ONLY AVAILABLE IN PAID PLANS",
    "Only available in paid plans",
    "Only for subscribers",
}
# Palavras/chaves que normalmente sinalizam desporto/TV/agenda
OFF_TOPIC_PATTERNS = [
    r"\b(Bundesliga|Premier League|Rangers|Celtic|Manchester City|derbies)\b",
    r"\bfixtures?\b",
    r"\bhighlights?\b",
]

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def log(msg: str):
    print(msg, flush=True)

def api_get(params: dict) -> dict:
    """Chama a API com tratamento de erro e logging de URL."""
    resp = requests.get(API_URL, params=params, timeout=25)
    if resp.status_code >= 400:
        log(f"❗ API error ({resp.status_code}): {resp.text}")
        log(f"URL: {resp.url}")
        resp.raise_for_status()
    data = resp.json()
    # A Newsdata devolve {"status":"error", "results": {"message": "..."}}
    if isinstance(data, dict) and data.get("status") == "error":
        log(f"⚠️ API error: {json.dumps(data)}")
        log(f"URL: {resp.url}")
        raise requests.HTTPError(data)
    return data

def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()

def looks_off_topic(text: str) -> bool:
    if not text:
        return False
    for pat in OFF_TOPIC_PATTERNS:
        if re.search(pat, text, flags=re.I):
            return True
    return False

def too_short(text: str, min_chars: int) -> bool:
    return len(text or "") < min_chars

def contains_banned(text: str) -> bool:
    if not text:
        return False
    for b in BANNED_PHRASES:
        if b.lower() in text.lower():
            return True
    return False

def uniquify_slug(date_str: str, base_slug: str) -> str:
    """Evita colisão de ficheiros (_posts/yyyy-mm-dd-slug.md)."""
    candidate = f"{date_str}-{base_slug}.md"
    p = POSTS_DIR / candidate
    if not p.exists():
        return candidate
    # acrescenta sufixo -2, -3, ...
    i = 2
    while True:
        candidate = f"{date_str}-{base_slug}-{i}.md"
        if not (POSTS_DIR / candidate).exists():
            return candidate
        i += 1

def build_excerpt(text: str) -> str:
    """Cria excerpt limpo com ~200 chars."""
    text = strip_html(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 200:
        text = text[:200].rsplit(" ", 1)[0] + "..."
    return text

# ------------------------------------------------------------
# Expansão de conteúdo (sem APIs externas)
# ------------------------------------------------------------
def expand_article(title: str, description: str, raw_content: str, source: str) -> str:
    """
    Gera 2–4 parágrafos com base no título + descrição + conteúdo bruto.
    A ideia é substituir textos vazios por algo legível e único.
    """
    t = strip_html(title)
    d = strip_html(description)
    c = strip_html(raw_content)

    # base “pontos” extraídos (muito simples, heurístico)
    bullets = []
    for line in (c or "").split("\n"):
        line = line.strip(" •-*–—\t")
        if 40 <= len(line) <= 160 and line[-1] != ":":
            bullets.append(line)
        if len(bullets) >= 5:
            break

    # 1) abertura
    p1 = (
        f"{t}. This article looks at why this story matters for the AI ecosystem and "
        f"what you should know right now."
        if t else
        "This article highlights a recent development in artificial intelligence."
    )

    # 2) contexto + descrição
    if d and not d.lower().startswith("http"):
        p2 = (
            f"{d} "
            "Beyond the headline, the update ties into broader momentum around practical AI adoption, "
            "model efficiency, and real-world integration."
        )
    else:
        # usa começo do conteúdo se a descrição for fraca
        p2 = (
            (c[:300] + "...") if c and len(c) > 320
            else "In short, the announcement reflects the steady pace of innovation across the AI stack."
        )

    # 3) bullets (se existirem)
    p3 = ""
    if bullets:
        items = "\n".join(f"- {b}" for b in bullets[:4])
        p3 = f"**Key points:**\n{items}"

    # 4) encerramento
    p4 = (
        f"Looking ahead, we expect ongoing iteration and more practical deployments. "
        f"Source: {source}."
    )

    # junta e normaliza
    parts = [p1, p2]
    if p3:
        parts.append(p3)
    parts.append(p4)

    body = "\n\n".join(parts)

    # “endireita” espaços
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    # garante tamanho mínimo
    if len(body) < MIN_BODY_CHARS and c:
        # acrescenta mais contexto do conteúdo original
        extra = re.sub(r"\s+", " ", c)
        body = f"{body}\n\n{extra[:600]}..."

    return body

# ------------------------------------------------------------
# Fetch + criação de posts
# ------------------------------------------------------------
def fetch_latest(limit: int = MAX_POSTS) -> list[dict]:
    """
    Busca os artigos mais recentes (1 página) respeitando a query curta.
    """
    params = {
        "apikey": API_KEY,
        "q": QUERY,
        "language": LANG,
        "category": CATEGORY,
        "page": 1,  # Uma página chega; erros anteriores foram por paginação/queries longas
    }
    data = api_get(params)
    results = data.get("results") or []
    # Newsdata por vezes devolve results = [] ou com estruturas diferentes
    items = []
    for r in results:
        if isinstance(r, dict):
            items.append(r)
        if len(items) >= limit:
            break
    return items

def create_post(article: dict) -> bool:
    """
    Constrói o ficheiro .md para o Jekyll.
    Retorna True se criou, False se ignorou.
    """
    title = (article.get("title") or "").strip()
    description = (article.get("description") or "").strip()
    content_raw = (article.get("content") or "").strip()
    link = article.get("link") or ""
    source = (article.get("source_id") or "").strip()
    image_url = article.get("image_url") or article.get("image") or ""

    # Vários filtros de qualidade
    base_text = " ".join([title, description, content_raw])
    if contains_banned(base_text):
        return False
    if looks_off_topic(base_text):
        return False
    if too_short(title, 15):
        return False

    # Expansão do corpo
    body = expand_article(title, description, content_raw, source)
    if too_short(body, MIN_BODY_CHARS):
        return False

    # Excerpt
    excerpt_src = description or content_raw or ""
    excerpt = build_excerpt(excerpt_src)
    if too_short(excerpt, MIN_EXCERPT_CHARS):
        # se excerpt for fraco, gera a partir do body
        excerpt = build_excerpt(body)

    # Data UTC (Jekyll yyyy-mm-dd)
    d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = slugify(title)[:70] or "ai-update"
    filename = uniquify_slug(d, slug)
    filepath = POSTS_DIR / filename

    # Evita duplicados pelo título (se já existir ficheiro com slug base)
    # (uniquify_slug já ajuda, mas se quiseres “não duplicar nunca”, usa este guard)
    existing = list(POSTS_DIR.glob(f"{d}-{slug}*.md"))
    if existing:
        # Já fizemos um post com este título hoje
        return False

    # Front-matter + conteúdo
    fm = {
        "layout": "post",
        "title": title.replace('"', '\\"'),
        "date": d,
        "excerpt": excerpt.replace('"', '\\"'),
        "categories": ["ai", "news"],
        "source": source,
        "link": link,
    }
    if image_url:
        fm["image"] = image_url

    front_matter = "---\n" + "\n".join(
        f'{k}: "{v}"' if isinstance(v, str) else f"{k}: {json.dumps(v)}"
        for k, v in fm.items()
    ) + "\n---\n"

    md = front_matter + "\n" + body + "\n"

    filepath.write_text(md, encoding="utf-8")
    log(f"✅ Created: {filepath}")
    return True

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
    if not API_KEY:
        raise ValueError("API_KEY não encontrada. Define NEWSDATA_API_KEY (ou NEWS_API_KEY) em Secrets/Variables.")

    log("🧠 Running update_posts.py...")
    log("📰 Fetching latest AI articles...")

    created = 0
    try:
        items = fetch_latest(limit=MAX_POSTS)
    except Exception as e:
        log(f"❗ Erro ao obter artigos: {e}")
        raise

    for art in items:
        try:
            if create_post(art):
                created += 1
        except Exception as e:
            log(f"⚠️ Skipped 1 article: {e}")

    if created == 0:
        log("ℹ️ No new quality posts created (filters may have skipped weak items).")
    else:
        log(f"🎉 Done. Created {created} post(s).")

if __name__ == "__main__":
    main()
