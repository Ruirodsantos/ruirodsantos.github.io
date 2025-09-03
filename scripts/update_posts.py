#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import json
import hashlib
import datetime as dt
from pathlib import Path

import requests
from slugify import slugify

# =========================
# Config
# =========================
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWSDATA_API_KEY") or os.getenv("NEWS_API_KEY")

POSTS_DIR = Path("_posts")
MAX_POSTS = 5
MAX_PAGES = 3          # tentativas de paginação (só se a API aceitar)
TIMEOUT = 20

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

EXCLUDE_PATTERNS = [
    r"\b(bundesliga|premier league|la liga|serie a|rangers|celtic|brighton|manchester city|espn|disney\+)\b",
    r"\b(scottish championship|derbies?)\b",
    r"ONLY AVAILABLE IN PAID PLANS",
]

MIN_EXCERPT_LEN = 80


# =========================
# Helpers
# =========================
def log(msg: str) -> None:
    print(msg, flush=True)


def ensure_api_key() -> None:
    if not API_KEY:
        raise ValueError(
            "❌ API_KEY não encontrada. Define `NEWSDATA_API_KEY` (ou `NEWS_API_KEY`) "
            "em Settings → Secrets and variables → Variables."
        )


def call_api(params: dict) -> dict:
    """Chama a API e devolve JSON; levanta exceção para 4xx/5xx."""
    r = requests.get(API_URL, params=params, timeout=TIMEOUT)
    if r.status_code == 422:
        # Mostra o motivo detalhado e a URL para debug
        try:
            payload = r.json()
        except Exception:
            payload = r.text
        log(f"⚠️ API error (422): {payload}")
        log(f"URL: {r.url}")
        r.raise_for_status()
    r.raise_for_status()
    return r.json()


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
    title = (item.get("title") or "").strip()
    description = (item.get("description") or "").strip()
    content = (item.get("content") or "").strip()

    body = content or description or ""
    if body.strip().lower() == title.strip().lower():
        body = ""
    return title, body


def parse_date(item: dict) -> dt.datetime:
    raw = item.get("pubDate") or item.get("pubdate") or ""
    try:
        iso = raw.replace("Z", "").split(" ")[0]
        return dt.datetime.strptime(iso, "%Y-%m-%d")
    except Exception:
        return dt.datetime.utcnow()


def dedupe_key(item: dict) -> str:
    basis = (item.get("link") or "") + "|" + (item.get("title") or "")
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def post_filename(pub_date: dt.datetime, title: str) -> Path:
    slug = slugify(title)[:60]
    date_str = pub_date.date().isoformat()
    return POSTS_DIR / f"{date_str}-{slug}.md"


def build_post_md(item: dict) -> tuple[Path, str]:
    pub = parse_date(item)
    title, body = choose_text(item)
    image = item.get("image_url") or item.get("image")

    if not body and item.get("description"):
        body = item["description"].strip()

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

    if body:
        lines.append(body.strip())
        lines.append("")

    source_name = (item.get("source_id") or item.get("source") or "source").strip()
    link = (item.get("link") or "").strip()
    if link:
        lines.append(f"Source: [{source_name}]({link})")

    content = "\n".join(fm + lines).strip() + "\n"
    path = post_filename(pub, title)
    return path, content


def quality_ok(item: dict) -> bool:
    title, body = choose_text(item)
    text = " ".join([title or "", body or "", item.get("description") or ""]).strip()

    if not title or len(title) < 10:
        return False

    if is_excluded(text):
        return False

    if not text_contains_any(title + " " + (item.get("description") or ""), KEYWORDS):
        return False

    if (item.get("content") or "").strip().lower() == "only available in paid plans":
        return False

    excerpt = (item.get("description") or "").strip()
    if len(excerpt) < MIN_EXCERPT_LEN:
        if len((item.get("content") or "").strip()) < MIN_EXCERPT_LEN:
            return False

    if excerpt and excerpt.strip().lower() == (title or "").strip().lower():
        return False

    return True


def fetch_latest(limit: int = MAX_POSTS) -> list[dict]:
    """
    Busca até `limit` items da Newsdata tentando variantes seguras de parâmetros.
    Evitamos `category` e, se houver 422, caímos para a query mais simples.
    """
    ensure_api_key()

    query = " OR ".join(KEYWORDS)
    results: list[dict] = []
    seen: set[str] = set()

    log("🧠 Fetching latest AI articles...")

    # Variantes de parâmetros para contornar 422/UnsupportedFilter:
    # 1) mais simples (sem paginação)
    # 2) com page=1 (alguns planos aceitam)
    PARAM_VARIANTS = [
        lambda page: {"apikey": API_KEY, "q": query, "language": "en"},
        lambda page: {"apikey": API_KEY, "q": query, "language": "en", "page": page},
    ]

    for page in range(1, MAX_PAGES + 1):
        success_this_page = False

        for mk in PARAM_VARIANTS:
            params = mk(page)
            try:
                data = call_api(params)
            except requests.HTTPError as e:
                # 422 aqui -> tenta próxima variante, e só falha de vez se todas rebentarem
                if e.response is not None and e.response.status_code == 422:
                    continue
                raise

            items = data.get("results") or data.get("data") or []
            for it in items:
                h = dedupe_key(it)
                if h in seen:
                    continue
                seen.add(h)

                if quality_ok(it):
                    results.append(it)
                    if len(results) >= limit:
                        return results

            success_this_page = True
            break  # não precisamos de tentar outras variantes para este page

        # se nenhuma variante funcionou neste page, pára o ciclo
        if not success_this_page:
            break

        time.sleep(0.5)

    return results


def write_post(path: Path, content: str) -> bool:
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
