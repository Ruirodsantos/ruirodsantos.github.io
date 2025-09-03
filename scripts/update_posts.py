import os
import re
import textwrap
import datetime as dt
from pathlib import Path
import requests
from slugify import slugify

# === Config ===
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY") or os.getenv("NEWSDATA_API_KEY")  # aceita qualquer um dos dois
if not API_KEY:
    raise ValueError("❌ API_KEY não encontrada. Define 'NEWS_API_KEY' (ou 'NEWSDATA_API_KEY') em Secrets/Variables.")

# Palavras-chave (mais amplas para variedade)
KEYWORDS = [
    "artificial intelligence", "AI", "machine learning", "generative ai",
    "openai", "anthropic", "google ai", "meta ai", "microsoft ai", "stability ai",
    "robotics", "lmm", "agents", "ai policy", "ai safety",
]

POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(exist_ok=True)

# Parâmetros de qualidade
MIN_DESC_CHARS = 140         # mínimo de chars na descrição/conteúdo
MAX_POSTS_PER_RUN = 5        # quantos posts gerar por execução
BLOCK_DUP_TITLES = True      # evita gerar posts com o mesmo título no mesmo dia

def today_iso():
    # usar UTC para consistência
    return dt.datetime.utcnow().date().isoformat()

def fetch_latest_variants():
    """
    Tenta algumas variantes de query para melhorar a taxa de acerto.
    Gera no máx. MAX_POSTS_PER_RUN items.
    """
    base_queries = [
        " OR ".join(KEYWORDS),
        "artificial intelligence OR generative ai OR machine learning",
        "openai OR anthropic OR google ai OR meta ai OR microsoft ai",
    ]
    items = []
    seen_ids = set()

    params_common = {
        "apikey": API_KEY,
        "language": "en",
        "page": 1,
    }

    last_err = None
    for q in base_queries:
        params = dict(params_common)
        params["q"] = q
        try:
            res = requests.get(API_URL, params=params, timeout=30)
            res.raise_for_status()
            data = res.json() or {}
            results = data.get("results") or []
            for art in results:
                aid = art.get("article_id") or art.get("link")
                if not aid or aid in seen_ids:
                    continue
                seen_ids.add(aid)
                items.append(art)
                if len(items) >= MAX_POSTS_PER_RUN:
                    return items
        except Exception as e:
            last_err = e
            continue

    if not items and last_err:
        # nada apanhado em nenhuma variante
        raise RuntimeError(f"All query variants failed. Last error: {last_err}")
    return items

def pick_image(article: dict) -> str | None:
    # newsdata.io possíveis chaves
    for key in ("image_url", "image", "thumbnail", "urlToImage"):
        url = article.get(key)
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None

def looks_low_quality(title: str, desc: str | None, content: str | None) -> bool:
    if not title or len(title) < 8:
        return True
    # usa content se existir, senão desc
    body = (content or "").strip() or (desc or "").strip()
    # remove espaços múltiplos
    body = re.sub(r"\s+", " ", body)
    # muito curto?
    if len(body) < MIN_DESC_CHARS:
        return True
    # igual ao título (quase)
    if body.lower().startswith(title.lower()):
        if len(body) <= len(title) + 10:
            return True
    return False

def normalize_excerpt(text: str, max_chars=300) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text[:max_chars].rstrip() + ("…" if len(text) > max_chars else "")

def filename_for(date_str: str, title: str) -> Path:
    base = slugify(title)[:60]
    return POSTS_DIR / f"{date_str}-{base}.md"

def already_exists(date_str: str, title: str) -> bool:
    # ver se existe ficheiro com a mesma data e título similar
    slug = slugify(title)[:60]
    pattern = f"{date_str}-{slug}.md"
    return (POSTS_DIR / pattern).exists()

def build_post_md(date_str: str, title: str, excerpt: str, source_name: str, url: str, image_url: str | None, body: str) -> str:
    fm_lines = [
        "---",
        f'title: "{title.replace("\\\"", "\\\\\\"")}"',
        f"date: {date_str}",
        'layout: post',
        "categories: [ai, news]",
    ]
    if image_url:
        fm_lines.append(f"image: {image_url}")
    fm_lines.append(f'excerpt: "{excerpt.replace("\\\"", "\\\\\\"")}"')
    fm_lines.append("---")

    md = "\n".join(fm_lines) + "\n\n"
    md += textwrap.dedent(f"""\
        {body}

        ---
        **Source:** [{source_name}]({url})
    """)
    return md

def main():
    date_str = today_iso()
    items = fetch_latest_variants()

    created = 0
    for art in items:
        title = (art.get("title") or "").strip()
        desc = (art.get("description") or art.get("summary") or "").strip()
        content = (art.get("content") or "").strip()
        url = art.get("link") or art.get("url") or "#"
        source_name = (art.get("source_id") or art.get("source") or "Source").strip()

        if looks_low_quality(title, desc, content):
            # salta fracos
            continue

        if BLOCK_DUP_TITLES and already_exists(date_str, title):
            continue

        image_url = pick_image(art)
        body = (content or desc).strip()
        excerpt = normalize_excerpt(body, max_chars=240)

        md = build_post_md(
            date_str=date_str,
            title=title,
            excerpt=excerpt,
            source_name=source_name,
            url=url,
            image_url=image_url,
            body=body
        )

        path = filename_for(date_str, title)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        created += 1

        if created >= MAX_POSTS_PER_RUN:
            break

    print(f"✅ Posts criados: {created}")

if __name__ == "__main__":
    main()
