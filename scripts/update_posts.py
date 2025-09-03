#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import json
import time
import hashlib
import datetime as dt
from pathlib import Path

import requests
from slugify import slugify


# =========================
# Config
# =========================
API_URL = "https://newsdata.io/api/1/news"
API_KEY = (
    os.getenv("NEWSDATA_API_KEY")
    or os.getenv("NEWS_API_KEY")  # fallback se tiveres guardado com este nome
)

POSTS_DIR = Path("_posts")
MAX_POSTS = 5               # quantos posts novos por execução
MAX_PAGES = 4               # quantas páginas da API vamos tentar no máximo
TIMEOUT = 20

# Query base (ampla, mas focada em IA)
KEYWORDS = [
    "artificial intelligence",
    "ai",
    "machine learning",
    "llm",
    "openai",
    "anthropic",
    "google ai",
    "meta ai",
    "generative ai",
]

# Palavras/expressões a excluir (para cortar futebol/TV, etc.)
EXCLUDE_PATTERNS = [
    r"\b(bundesliga|premier league|la liga|serie a|rangers|celtic|brighton|manchester city|espn|disney\+)\b",
    r"\b(scottish championship|derbies?)\b",
    r"ONLY AVAILABLE IN PAID PLANS",
]

# Critérios mínimos de qualidade
MIN_EXCERPT_LEN = 80


# =========================
# Helpers
# =========================
def log(msg: str) -> None:
    print(msg, flush=True)


def ensure_api_key() -> None:
    if not API_KEY:
        raise ValueError(
            "❌ API_KEY não encontrada. Define `NEWSDATA_API_KEY` "
            "(ou `NEWS_API_KEY`) nas variáveis do repositório (Settings → Secrets and variables → Variables)."
        )


def call_api(params: dict) -> dict:
    """Chama a API e devolve JSON; levanta para 4xx/5xx (para Action falhar visivelmente)."""
    try:
        r = requests.get(API_URL, params=params, timeout=TIMEOUT)
        # As 422 podem acontecer com paginação incorreta; aqui deixamos visível
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        # Mostra URL completo no log da Action para debugging
        log(f"⚠️ API error ({r.status_code}): {r.text}\nURL: {r.url}")
        raise
    except requests.RequestException as e:
        log(f"⚠️ Network error: {e}")
        raise


def text_contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def is_excluded(text: str) -> bool:
    if not text:
        return False
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            return True
    return False


def choose_text(item: dict) -> tuple[str, str]:
    """Devolve (title, body) escolhendo entre fields da Newsdata, limpando repetição título==excerto."""
    title = (item.get("title") or "").strip()
    # Newsdata traz normalmente: description (resumo) e content (quando disponível)
    description = (item.get("description") or "").strip()
    content = (item.get("content") or "").strip()

    # conteúdo preferido
    body = content or description or ""

    # Evitar body igual ao título
    if body.strip().lower() == title.strip().lower():
        body = ""

    return title, body


def parse_date(item: dict) -> dt.datetime:
    """Extrai data (pubDate) de forma resiliente; devolve datetime UTC."""
    raw = item.get("pubDate") or item.get("pubdate") or ""
    # formatos comuns: "2025-09-02 14:30:00 UTC" ou "2025-09-02T14:30:00Z"
    try:
        # tenta cortar até à data apenas (YYYY-MM-DD)
        iso = raw.replace("Z", "").split(" ")[0]  # "2025-09-02"
        return dt.datetime.strptime(iso, "%Y-%m-%d")
    except Exception:
        return dt.datetime.utcnow()


def dedupe_key(item: dict) -> str:
    """Hash simples para evitar duplicados pelo link/title."""
    basis = (item.get("link") or "") + "|" + (item.get("title") or "")
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def post_filename(pub_date: dt.datetime, title: str) -> Path:
    slug = slugify(title)[:60]
    date_str = pub_date.date().isoformat()
    return POSTS_DIR / f"{date_str}-{slug}.md"


def build_post_md(item: dict) -> tuple[Path, str]:
    """Cria (path, markdown) para o item."""
    pub = parse_date(item)
    title, body = choose_text(item)
    image = item.get("image_url") or item.get("image")

    # fallback se não houver corpo
    if not body and item.get("description"):
        body = item["description"].strip()

    # front matter seguro (evitar aspas partidas)
    safe_title = title.replace('"', "'")

    fm = [
        "---",
        "layout: post",
        f'title: "{safe_title}"',
        f"date: {pub.date().isoformat()}",
        "---",
        "",
    ]

    lines = []
    if image:
        lines.append(f"![{title}]({image})")
        lines.append("")

    # corpo mínimo, senão não vale a pena
    if body:
        lines.append(body.strip())
        lines.append("")

    # fonte
    source_name = (item.get("source_id") or item.get("source") or "source").strip()
    link = (item.get("link") or "").strip()
    if link:
        lines.append(f"Source: [{source_name}]({link})")

    content = "\n".join(fm + lines).strip() + "\n"
    path = post_filename(pub, title)
    return path, content


def quality_ok(item: dict) -> bool:
    """Filtra desporto, paywall e posts fracos."""
    title, body = choose_text(item)
    text = " ".join([title or "", body or "", item.get("description") or ""]).strip()

    if not title or len(title) < 10:
        return False

    # bloquear conteúdos irrelevantes (ex.: eventos desportivos)
    if is_excluded(text):
        return False

    # tem de bater em termos de IA (no título ou descrição)
    if not text_contains_any(title + " " + (item.get("description") or ""), KEYWORDS):
        return False

    # força um corpo minimamente útil
    if (item.get("content") or "").strip().lower() == "only available in paid plans":
        return False

    excerpt = (item.get("description") or "").strip()
    if len(excerpt) < MIN_EXCERPT_LEN:
        # se houver content razoável, aceitamos
        if len((item.get("content") or "").strip()) < MIN_EXCERPT_LEN:
            return False

    # evitar “excerto == título”
    if excerpt and excerpt.strip().lower() == (title or "").strip().lower():
        return False

    return True


def fetch_latest(limit: int = MAX_POSTS) -> list[dict]:
    """Busca até `limit` items da Newsdata, navegando 1..MAX_PAGES."""
    ensure_api_key()

    query = " OR ".join(KEYWORDS)
    results: list[dict] = []
    seen_hashes: set[str] = set()

    log("🧠 Fetching latest AI articles...")

    for page in range(1, MAX_PAGES + 1):
        params = {
            "apikey": API_KEY,
            "q": query,
            "language": "en",
            "category": "technology",
            "page": page,
        }
        data = call_api(params)

        items = data.get("results") or data.get("data") or []
        if not items:
            break

        for it in items:
            h = dedupe_key(it)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            if quality_ok(it):
                results.append(it)
                if len(results) >= limit:
                    return results

        # se ainda não atingimos o limite, continua para próxima página
        time.sleep(0.5)

    return results


def write_post(path: Path, content: str) -> bool:
    """Escreve o ficheiro se ainda não existir. Devolve True se criou."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    try:
        items = fetch_latest(limit=MAX_POSTS)
    except Exception as e:
        log(f"❌ Falha na API: {e}")
        return 1

    if not items:
        log("ℹ️ Sem itens novos após filtros de qualidade.")
        return 0

    created = 0
    for it in items:
        path, md = build_post_md(it)
        if write_post(path, md):
            created += 1
            log(f"✅ Post criado: {path}")
        else:
            log(f"↩️ Já existia: {path.name}")

    if created == 0:
        log("ℹ️ Nenhum ficheiro novo foi criado (todos já existiam).")
    else:
        log(f"🎉 {created} post(s) criados.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
