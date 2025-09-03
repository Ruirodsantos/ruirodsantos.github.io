#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Repairs Jekyll posts in _posts/ with empty/very short bodies or “ONLY AVAILABLE IN PAID PLANS”.
- Keeps front matter keys if present (title, date, source, link, excerpt, image, etc.).
- Writes a clean fallback paragraph so {{ content }} actually shows something.
- Logs each file repaired.
"""

from __future__ import annotations
import re
from pathlib import Path
import datetime as dt
from typing import Dict, Tuple

POSTS_DIR = Path("_posts")

# Any body that is shorter than this (after stripping markdown/html) is auto-repaired:
MIN_BODY_CHARS = 60

# If body contains any of these phrases, we also repair it:
BAD_PHRASES = {
    "ONLY AVAILABLE IN PAID PLANS",
    "Only available in paid plans",
    "Only available in paid plan",
}

# Scan horizon (days). 0 = scan ALL posts.
SCAN_DAYS = 365

FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")  # strip any html tags in body when measuring

def parse_front_matter(text: str) -> Tuple[Dict[str, str], str, bool]:
    """
    Return (front_matter_dict, body_markdown, has_front_matter).
    """
    m = FRONT_RE.match(text)
    if not m:
        return {}, text, False
    raw_yaml, body = m.group(1), m.group(2)
    fm: Dict[str, str] = {}
    # extremely simple yaml: key: value, keep as strings
    for line in raw_yaml.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        fm[k] = v
    return fm, body, True

def serialize_front_matter(fm: Dict[str, str]) -> str:
    lines = []
    for k, v in fm.items():
        # quote values that may contain commas/colons/quotes
        if not (v.startswith('"') and v.endswith('"')):
            if any(ch in v for ch in [":", '"']):
                v = v.replace('"', '\\"')
                v = f'"{v}"'
        lines.append(f"{k}: {v}")
    return "\n".join(lines)

def clean_len(s: str) -> int:
    s = s.strip()
    s = TAG_RE.sub("", s)  # drop any html
    return len(s)

def needs_repair(body: str) -> bool:
    if clean_len(body) < MIN_BODY_CHARS:
        return True
    # also repair if it contains any blacklisted phrases
    low = body.lower()
    for bad in BAD_PHRASES:
        if bad.lower() in low:
            return True
    return False

def fallback_paragraph(fm: Dict[str, str]) -> str:
    title   = fm.get("title", "AI news")
    source  = fm.get("source", "") or fm.get("source_id", "")
    link    = fm.get("link", "")
    excerpt = fm.get("excerpt", "")

    bits = []
    if excerpt:
        bits.append(excerpt.strip())
    else:
        bits.append(f"This article is about “{title}.”")

    if source and link:
        bits.append(f" Read more at [{source}]({link}).")
    elif link:
        bits.append(f" Read more at [{link}]({link}).")

    # Guarantee at least MIN_BODY_CHARS
    para = ("".join(bits)).strip()
    if clean_len(para) < MIN_BODY_CHARS:
        para += " This summary was auto-generated to ensure the post displays meaningful content."

    return para.strip()

def within_days(p: Path, days: int) -> bool:
    if days <= 0:
        return True
    try:
        y, m, d = p.name[:10].split("-")
        file_date = dt.date(int(y), int(m), int(d))
        return (dt.date.today() - file_date).days <= days
    except Exception:
        return True

def repair_file(p: Path) -> bool:
    text = p.read_text(encoding="utf-8")
    fm, body, has_fm = parse_front_matter(text)

    if not has_fm:
        # create minimal FM if missing
        fm = {"title": p.stem.replace("-", " ").title()}
        new_body = fallback_paragraph(fm)
        new_text = f"---\n{serialize_front_matter(fm)}\n---\n\n{new_body}\n"
        p.write_text(new_text, encoding="utf-8")
        return True

    if not needs_repair(body):
        return False

    new_body = fallback_paragraph(fm)
    front_block = serialize_front_matter(fm)
    new_text = f"---\n{front_block}\n---\n\n{new_body}\n"
    p.write_text(new_text, encoding="utf-8")
    return True

def main() -> None:
    if not POSTS_DIR.exists():
        print("No _posts/ directory found.")
        return

    checked = fixed = 0
    for p in sorted(POSTS_DIR.glob("*.md")):
        if not within_days(p, SCAN_DAYS):
            continue
        checked += 1
        if repair_file(p):
            fixed += 1
            print(f"✅ Repaired: {p}")
    print(f"Done. Checked: {checked} | Repaired: {fixed}")

if __name__ == "__main__":
    main()
