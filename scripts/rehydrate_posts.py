#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rehidrata posts Jekyll que já existem em _posts/:
 - Se o body estiver vazio ou muito curto, gera 2–4 parágrafos a partir do título/excerpt.
 - Remove frases de paywall (e.g., "ONLY AVAILABLE IN PAID PLANS").
 - Mantém o front-matter, substitui apenas o corpo quando necessário.

Opcional: limitar por datas com variáveis de ambiente:
  REHYDRATE_SINCE=YYYY-MM-DD   (inclusive)
  REHYDRATE_UNTIL=YYYY-MM-DD   (inclusive)
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from datetime import datetime

POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(exist_ok=True)

MIN_BODY_CHARS = 500
BANNED_PHRASES = {
    "ONLY AVAILABLE IN PAID PLANS",
    "Only available in paid plans",
    "Only for subscribers",
}

REHYDRATE_SINCE = os.getenv("REHYDRATE_SINCE")  # '2025-06-04'
REHYDRATE_UNTIL = os.getenv("REHYDRATE_UNTIL")  # '2025-06-13'

def log(x: str):
    print(x, flush=True)

def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()

def expand_article(title: str, description: str, raw_content: str, source: str) -> str:
    """Mesma lógica do update_posts.py: gera 2–4 parágrafos legíveis."""
    t = strip_html(title)
    d = strip_html(description)
    c = strip_html(raw_content)

    bullets = []
    for line in (c or "").split("\n"):
        L = line.strip(" •-*–—\t")
        if 40 <= len(L) <= 160 and not L.endswith(":"):
            bullets.append(L)
        if len(bullets) >= 5:
            break

    p1 = (
        f"{t}. This article looks at why this story matters for the AI ecosystem and "
        f"what you should know right now."
        if t else
        "This article highlights a recent development in artificial intelligence."
    )

    if d and not d.lower().startswith("http"):
        p2 = (f"{d} "
              "Beyond the headline, the update ties into broader momentum around practical AI adoption, "
              "model efficiency, and real-world integration.")
    else:
        p2 = (c[:300] + "...") if c and len(c) > 320 else \
             "In short, the announcement reflects the steady pace of innovation across the AI stack."

    p3 = ""
    if bullets:
        items = "\n".join(f"- {b}" for b in bullets[:4])
        p3 = f"**Key points:**\n{items}"

    p4 = f"Looking ahead, we expect ongoing iteration and more practical deployments. Source: {source}."

    parts = [p1, p2]
    if p3:
        parts.append(p3)
    parts.append(p4)
    body = "\n\n".join(parts)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    if len(body) < MIN_BODY_CHARS and c:
        extra = re.sub(r"\s+", " ", c).strip()
        body = f"{body}\n\n{extra[:600]}..."

    return body

def split_front_matter(text: str) -> tuple[str, str]:
    """
    Divide o ficheiro em (front_matter, body). Se não tiver FM, devolve ("", texto).
    """
    if text.startswith("---"):
        parts = text.split("\n", 2)
        # garante uma segunda '---'
        m = re.search(r"^---\s*$", text, flags=re.M)
        if m:
            # encontra a segunda '---' após a primeira linha
            end = re.search(r"^---\s*$", text[m.end():], flags=re.M)
            if end:
                fm = text[:m.end() + end.end()]
                body = text[m.end() + end.end():]
                return fm.strip(), body.lstrip()
    return "", text

def parse_front_matter(fm: str) -> dict:
    """
    Parser simples (sem PyYAML) para chaves comuns.
    Aceita linhas tipo: key: value   ou   key: "value"
    """
    meta = {}
    for line in fm.splitlines():
        if not line or line.strip() in {"---"}:
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"')
        meta[k] = v
    return meta

def date_in_range(date_str: str) -> bool:
    """
    Verifica se a data (YYYY-MM-DD) está dentro de REHYDRATE_SINCE/UNTIL (se definidos).
    """
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except Exception:
        return True
    if REHYDRATE_SINCE:
        try:
            if d < datetime.strptime(REHYDRATE_SINCE, "%Y-%m-%d").date():
                return False
        except Exception:
            pass
    if REHYDRATE_UNTIL:
        try:
            if d > datetime.strptime(REHYDRATE_UNTIL, "%Y-%m-%d").date():
                return False
        except Exception:
            pass
    return True

def needs_rehydrate(body: str) -> bool:
    if len(body.strip()) < MIN_BODY_CHARS:
        return True
    for b in BANNED_PHRASES:
        if b.lower() in body.lower():
            return True
    return False

def clean_body(body: str) -> str:
    for b in BANNED_PHRASES:
        body = re.sub(re.escape(b), "", body, flags=re.I)
    # remove excesso de linhas vazias
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()

def rehydrate_file(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    fm, body = split_front_matter(raw)
    meta = parse_front_matter(fm)

    date = meta.get("date", "")
    if date and not date_in_range(date):
        return False

    title = meta.get("title", "").strip()
    excerpt = meta.get("excerpt", "").strip()
    source = meta.get("source", "").strip()

    original_body = body
    body = clean_body(body)

    if not needs_rehydrate(body):
        return False

    new_body = expand_article(title, excerpt, body, source)
    if len(new_body) <= len(body):
        # ainda assim melhora (remove paywall, normaliza)
        new_body = body if body else new_body

    final = (fm + "\n\n" if fm else "") + new_body.strip() + "\n"
    if final != raw:
        path.write_text(final, encoding="utf-8")
        return True
    return False

def main():
    updated = 0
    files = sorted(POSTS_DIR.glob("*.md"))
    if not files:
        log("ℹ️ Nenhum ficheiro em _posts/.")
        return
    log(f"🔧 A rehidratar {len(files)} posts...")
    if REHYDRATE_SINCE or REHYDRATE_UNTIL:
        log(f"   • Janela: {REHYDRATE_SINCE or '…'} até {REHYDRATE_UNTIL or '…'}")

    for f in files:
        try:
            if rehydrate_file(f):
                updated += 1
                log(f"✅ Updated: {f.name}")
        except Exception as e:
            log(f"⚠️ Skip {f.name}: {e}")

    log(f"🎉 Concluído. Atualizados {updated} post(s).")

if __name__ == "__main__":
    main()
