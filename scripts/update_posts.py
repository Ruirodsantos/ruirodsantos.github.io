#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gerador/atualizador de posts para o Jekyll a partir da Newsdata.io

- Busca notícias de IA
- Filtra ruído/baixa qualidade
- Cria até 5 posts por execução com conteúdo mínimo útil
- Preenche imagem e fonte quando disponíveis

Requisitos:
  pip install requests python-slugify

Variáveis de ambiente aceites para a API:
  NEWS_API_KEY            (preferida)
  NEWSDATA_API_KEY        (alternativa/compatibilidade)
"""

import os
import re
import json
import textwrap
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import requests
from slugify import slugify


# =======================
# Configuração do script
# =======================

API_URL = "https://newsdata.io/api/1/news"

# Usa NEWS_API_KEY por padrão; cai para NEWSDATA_API_KEY se necessário
API_KEY = os.getenv("NEWS_API_KEY") or os.getenv("NEWSDATA_API_KEY")

# Consulta curta para evitar "UnsupportedQueryLength"
# (manter curta é importante com a Newsdata)
QUERY = '("artificial intelligence" OR AI OR "machine learning")'

LANG = "en"
CATEGORY = "technology"

# Número máximo de posts por execução
MAX_POSTS = 5

# Pasta Jekyll dos posts
POSTS_DIR = "_posts"

# Palavras a excluir (ruído típico que passou no feed)
EXCLUDE_KEYWORDS = {
    "bundesliga", "premier league", "rangers", "celtic", "guardiola",
    "brighton", "manchester city", "derbies", "broadcasts",
    "football", "soccer",
    "only available in paid plans",  # corta cedo
}

# Limiares de qualidade
MIN_WORDS = 80  # mínimo de palavras úteis no corpo
MAX_EXCERPT_LEN = 220  # tamanho do excerpt front matter

# Placeholder (se quiseres usar uma imagem fixa por defeito, define aqui um path do repo)
PLACEHOLDER_IMAGE = None  # ex.: "/assets/og-default.jpg"


# =======================
# Utilitários
# =======================

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.replace("\u00a0", " ").replace("\u200b", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def looks_like_low_value(text: str) -> bool:
    """Heurística para conteúdo fraco/indesejado."""
    t = text.lower()

    # corta se tiver mensagens de paywall/indisponível
    if "only available in paid plans" in t or "only available" in t:
        return True

    # corta se conter palavras de ruído (desporto)
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return True

    return False

def bulletize_from_description(desc: str) -> List[str]:
    """Gera 3–5 bullets simples a partir do description."""
    desc = clean_text(desc)
    if not desc:
        return []

    # separa por pontuação. mantemos simples
    parts = re.split(r"[.;:!?]\s+", desc)
    parts = [p.strip() for p in parts if len(p.strip()) > 0]
    # remove duplicados curtinhos
    uniq = []
    for p in parts:
        if len(p) < 12:
            continue
        if p not in uniq:
            uniq.append(p)

    bullets = uniq[:5]
    # se não chegar, cria frases genéricas
    while len(bullets) < 3 and len(bullets) < len(uniq):
        bullets.append(uniq[len(bullets)])

    # corta cada bullet para ~140 chars para não ficar gigante
    clipped = []
    for b in bullets:
        if len(b) > 140:
            b = b[:137].rstrip() + "..."
        clipped.append(b)
    return clipped[:5]

def build_body(article: Dict[str, Any]) -> str:
    """Constrói corpo do post com garantias de qualidade mínima."""
    raw_content = clean_text(article.get("content"))
    desc = clean_text(article.get("description"))
    title = clean_text(article.get("title") or "")
    link = article.get("link") or article.get("url") or ""

    # remove frases de paywall/baixa qualidade
    def strip_low_value(txt: str) -> str:
        t = re.sub(r"\bONLY AVAILABLE.*?$", "", txt, flags=re.IGNORECASE)
        t = re.sub(r"\bSubscribe now.*?$", "", t, flags=re.IGNORECASE)
        return clean_text(t)

    raw_content = strip_low_value(raw_content)
    desc = strip_low_value(desc)

    # Se o conteúdo veio vazio ou muito curto, usa o description + resumo
    core = raw_content if len(raw_content.split()) >= 60 else desc

    # evita repetir título
    if core.lower() == title.lower():
        core = ""

    # Se mesmo assim estiver curto, monta um corpo mínimo útil
    if len(core.split()) < 60:
        # parágrafo introdutório
        intro = core if core else f"{title} — latest development in AI."

        bullets = bulletize_from_description(desc or title)
        bullets_block = ""
        if bullets:
            bullets_md = "\n".join([f"- {b}" for b in bullets])
            bullets_block = f"\n\n**In short:**\n{bullets_md}"

        read_more = f"\n\n[Read more]({link})" if link else ""
        body = clean_text(intro) + bullets_block + read_more
    else:
        body = core
        # acrescenta fonte se fizer sentido
        if link and "http" in link and link not in body:
            body = body + f"\n\n[Read more]({link})"

    return body.strip()


def pick_image(article: Dict[str, Any]) -> Optional[str]:
    """Escolhe a melhor imagem disponível."""
    for key in ("image_url", "image", "thumbnail"):
        url = clean_text(article.get(key))
        if url and url.startswith("http"):
            return url
    return PLACEHOLDER_IMAGE  # pode ser None


def is_relevant(article: Dict[str, Any]) -> bool:
    """Relevância rápida (evita ruído)."""
    title = clean_text(article.get("title"))
    desc = clean_text(article.get("description"))

    if not title:
        return False

    text = f"{title}. {desc}".lower()
    if looks_like_low_value(text):
        return False

    # tem de mencionar IA de forma plausível
    if not re.search(r"\b(ai|artificial intelligence|machine learning)\b", text):
        return False

    return True


def ensure_posts_dir():
    os.makedirs(POSTS_DIR, exist_ok=True)


def call_api(params: Dict[str, Any]) -> Dict[str, Any]:
    """Chama a API e devolve JSON, ou levanta para o caller."""
    r = requests.get(API_URL, params=params, timeout=25)
    # se a Newsdata devolver erro, deixa claro no log
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        print(f"URL: {r.url}")
        raise
    return r.json()


def fetch_latest(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    """
    Busca artigos (pode paginar) respeitando o limite e as regras de qualidade.
    """
    if not API_KEY:
        raise ValueError("API_KEY não encontrada. Define NEWS_API_KEY (ou NEWSDATA_API_KEY).")

    results: List[Dict[str, Any]] = []
    page = 1

    while len(results) < limit and page <= 3:  # até 3 páginas por segurança
        params = {
            "apikey": API_KEY,
            "q": QUERY,
            "language": LANG,
            "category": CATEGORY,
            "page": page,
        }

        data = call_api(params)
        # Formato Newsdata: {"status": "success", "results": [ ... ]}
        items = data.get("results") or []
        if not isinstance(items, list) or not items:
            break

        for art in items:
            if len(results) >= limit:
                break

            if not is_relevant(art):
                continue

            title = clean_text(art.get("title"))
            desc = clean_text(art.get("description"))
            cont = clean_text(art.get("content"))

            # bloco de baixa qualidade
            all_txt = f"{title}\n{desc}\n{cont}".lower()
            if looks_like_low_value(all_txt):
                continue

            # evita título == description
            if title and desc and title.strip().lower() == desc.strip().lower():
                continue

            # cria corpo e verifica tamanho
            body_candidate = build_body(art)
            if len(body_candidate.split()) < MIN_WORDS:
                # ainda insuficiente → descartar
                continue

            # passou!
            art["_body"] = body_candidate
            results.append(art)

        page += 1

    return results[:limit]


def build_front_matter(article: Dict[str, Any]) -> Dict[str, Any]:
    """Constrói front matter YAML em dicionário."""
    title = clean_text(article.get("title"))
    date_str = article.get("pubDate") or article.get("published_at") or ""
    # Normaliza a data para YYYY-MM-DD
    dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(date_str, fmt)
            break
        except Exception:
            continue
    if not dt:
        dt = datetime.now(timezone.utc)

    date_for_name = dt.strftime("%Y-%m-%d")
    img = pick_image(article)

    fm = {
        "layout": "post",
        "title": title.replace('"', '\\"'),
        "date": date_for_name,
        "categories": ["ai", "news"],
    }

    if img:
        fm["image"] = img

    # excerpt curto para a listagem
    excerpt_src = clean_text(article.get("description") or article.get("content") or "")
    excerpt_src = re.sub(r"\s+", " ", excerpt_src).strip()
    excerpt = excerpt_src[:MAX_EXCERPT_LEN].rstrip()
    if excerpt:
        fm["excerpt"] = excerpt

    return fm, date_for_name


def write_post(article: Dict[str, Any]) -> Optional[str]:
    """Escreve o ficheiro .md no _posts e devolve o nome, ou None se já existir."""
    ensure_posts_dir()

    title = clean_text(article.get("title"))
    fm, date_for_name = build_front_matter(article)
    slug = slugify(title)[:80] or "ai-news"
    filename = f"{POSTS_DIR}/{date_for_name}-{slug}.md"

    if os.path.exists(filename):
        print(f"• Já existe: {filename} (salta)")
        return None

    # Corpo
    body = article.get("_body") or build_body(article)
    # Fonte
    source_name = clean_text(article.get("source_id") or article.get("source") or "")
    source_url = clean_text(article.get("link") or article.get("url") or "")

    source_block = ""
    if source_name or source_url:
        # tenta mostrar "Source: <nome>" com link se houver
        if source_url:
            label = source_name if source_name else "source"
            source_block = f"\n\nSource: [{label}]({source_url})"
        else:
            source_block = f"\n\nSource: {source_name}"

    # Monta conteúdo final
    # Front matter YAML
    fm_yaml_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            v_str = ", ".join(v)
            fm_yaml_lines.append(f"{k}: [{v_str}]")
        else:
            fm_yaml_lines.append(f'{k}: "{v}"')
    fm_yaml_lines.append("---\n")

    final_md = "".join(l + "\n" for l in fm_yaml_lines) + body + source_block + "\n"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(final_md)

    print(f"✅ Criado: {filename}")
    return filename


def main():
    print("🧠 Running update_posts.py...")
    if not API_KEY:
        raise ValueError("NEWS_API_KEY (ou NEWSDATA_API_KEY) não definido no repositório.")

    print("📰 Fetching latest AI articles...")
    articles = fetch_latest(limit=MAX_POSTS)

    if not articles:
        print("⚠️ Nada para publicar (filtros de qualidade podem ter removido tudo).")
        return

    created = 0
    for art in articles:
        if write_post(art):
            created += 1

    print(f"🎉 Done. {created} post(s) criados.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Erro: {e}")
        raise
