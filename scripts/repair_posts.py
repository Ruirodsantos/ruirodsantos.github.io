#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Repair Jekyll posts in _posts/ that have an empty/too-short body.
- Keeps existing front matter as-is.
- Writes a safe fallback paragraph using title/source/link/excerpt.
- By default, scans the last N days, but can scan all files.
"""

import os
import re
import datetime as dt
from pathlib import Path
from typing import Tuple, Dict

POSTS_DIR = Path("_posts")
MIN_BODY_LEN = 60              # if body shorter than this → repair
SCAN_DAYS = 30                 # repair only last N days; set to 0 for all

FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

def parse_front_matter(text: str) -> Tuple[Dict[str, str], str]:
    """
    Return (front_matter_dict, body_markdown).
    If no front matter, return ({}, original_text).
    """
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    raw_yaml, body = m.group(1), m.group(2)

    fm: Dict[str, str] = {}
    for line in raw_yaml.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        fm[k] = v
    return fm, body

def make_fallback(title: str, source: str, link: str, excerpt: str) -> str:
    base = excerpt or f"This article titled “{title}” was reported by {source or 'the source'}."
    tail = ""
    if link:
        tail = f" Read more at [{source or 'source'}]({link})."
    return (base.strip() + tail).strip()

def within_days(p: Path, days: int) -> bool:
    if days <= 0:
        return True
    # filenames are like YYYY-MM-DD-slug.md
    try:
        y, m, d = p.name[:10].split("-")
        file_date = dt.date(int(y), int(m), int(d))
        return (dt.date.today() - file_date).days <= days
    except Exception:
        return True  # if it doesn’t match, just include it

def repair_file(p: Path) -> bool:
    txt = p.read_text(encoding="utf-8")
    fm, body = parse_front_matter(txt)

    body_stripped = body.strip()
    if len(body_stripped) >= MIN_BODY_LEN:
        return False  # looks fine

    title  = fm.get("title", p.stem)
    source = fm.get("source", "")
    link   = fm.get("link", "")
    excerpt= fm.get("excerpt", "")

    fallback = make_fallback(title, source, link, excerpt)

    # Reassemble file keeping original front matter block
    m = FRONT_RE.match(txt)
    if not m:
        # no front matter – create one
        new_txt = (
            f'---\n'
            f'title: "{title}"\n'
            f'---\n\n'
            f'{fallback}\n'
        )
    else:
        front_block = m.group(1)
        new_txt = f"---\n{front_block}\n---\n\n{fallback}\n"

    p.write_text(new_txt, encoding="utf-8")
    return True

def main() -> None:
    if not POSTS_DIR.exists():
        print("No _posts/ directory found.")
        return

    fixed = 0
    checked = 0
    for p in sorted(POSTS_DIR.glob("*.md")):
        if not within_days(p, SCAN_DAYS):
            continue
        checked += 1
        if repair_file(p):
            fixed += 1
            print(f"✅ Repaired: {p}")
    print(f"Done. Checked: {checked}, repaired: {fixed}")

if __name__ == "__main__":
    main()
