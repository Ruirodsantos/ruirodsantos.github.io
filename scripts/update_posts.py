#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Update posts from Newsdata.io with enrichment from the original article.

What it does:
- Fetches recent AI news (short query to avoid API query-length issues).
- For each item, downloads the source URL and extracts main text with trafilatura.
- Builds a 150–300 word summary: intro + key points + why-it-matters + link.
- Filters out thin/irrelevant content (sports, paywall notices, duplicates).
- Writes Jekyll posts into _posts/YYYY-MM-DD-slug.md

Requirements:
  pip install requests python-slugify trafilatura

Environment:
  NEWS_API_KEY (preferred) or NEWSDATA_API_KEY
"""

import os
import re
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests
from slugify import slugify
import trafilatura


# --------------------
# Config
# --------------------
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY") or os.getenv("NEWSDATA_API_KEY")

QUERY = '("artificial intelligence" OR AI OR "machine learning")'
LANG = "en"
CATEGORY = "technology"

MAX_POSTS = 5
POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(exist_ok=True)

EXCLUDE_KEYWORDS = {
    "bundesliga", "premier league", "rangers", "celtic", "guardiola",
    "brighton", "manchester city", "derbies", "broadcasts",
    "football", "soccer",
    "ONLY AVAILABLE IN PAID PLANS".lower(),
    "Only available in paid plans".lower(),
}

MIN_SUMMARY_WORDS = 140     # target ~150–300 words
MAX_EXCERPT_LEN = 220

PLACEHOLDER_IMAGE = None    # e.g. "/assets/og-default.jpg" if you want one


# --------------------
# Helpers
# --------------------
def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.replace("\u00a0", " ").replace("\u200b", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def looks_irrelevant(text: str) -> bool:
    t = text.lower()
    if any(k in t for k in EXCLUDE_KEYWORDS):
        return True
    # must plausibly be about AI
    if not re.search(r"\b(ai|artificial intelligence|machine learning|genai|generative ai)\b", t):
        return True
    return False

def fetch_html_main_text(url: str) -> str:
    """
    Downloads and extracts the main article text using trafilatura.
    Returns empty string if not possible.
    """
    if not url or not url.startswith("http"):
        return ""
    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=True, timeout=20)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False) or ""
        return clean_text(text)
    except Exception:
        return ""

def bulletize_from_text(text: str, limit: int = 6) -> List[str]:
    """
    Make 4–6 readable bullets from the extracted text.
    Simple heuristic: pick medium-length sentences that look informative.
    """
    if not text:
        return []
    # split into sentences (lightweight)
    parts = re.split(r"(?<=[.!?])\s+", text)
    # filter mid-length sentences
    candidates = [p.strip() for p in parts if 60 <= len(p.strip()) <= 220]
    # dedupe & cap
    seen = set()
    bullets = []
    for c in candidates:
        k = c.lower()
        if k in seen:
            continue
        seen.add(k)
        bullets.append(c)
        if len(bullets) >= limit:
            break
    # if too few, fall back to slightly shorter sentences
    if len(bullets) < 4:
        more = [p.strip() for p in parts if 40 <= len(p.strip()) <= 240 and p.strip() not in bullets]
        for m in more:
            if len(bullets) >= limit:
                break
            bullets.append(m)
    # clip overly long bullets
    clipped = []
    for b in bullets[:limit]:
        if len(b) > 200:
            b = b[:197].rstrip() + "..."
        clipped.append(b)
    return clipped[:limit]

def pick_image(article: Dict[str, Any]) -> Optional[str]:
    for key in ("image_url", "image", "thumbnail"):
        u = clean_text(article.get(key))
        if u and u.startswith("http"):
            return u
    return PLACEHOLDER_IMAGE

def build_summary(title: str, source_name: str, link: str, body_text: str, description: str) -> str:
    """
    Compose a 150–300 word summary:
      - Intro (what happened)
      - Key points (bullets)
      - Why it matters (context)
      - Read more (link)
    """
    t = clean_text(title)
    d = clean_text(description)
    bt = clean_text(body_text)

    # intro: prefer description; fallback to snip of body
    intro = d if len(d.split()) >= 25 else (bt[:300] + "...") if len(bt) > 340 else d or t

    # bullets from body text
    bullets = bulletize_from_text(bt, limit=6)
    bullet_block = ""
    if bullets:
        bullet_block = "\n\n**Key points:**\n" + "\n".join(f"- {b}" for b in bullets[:6])

    # why it matters (short generic context)
    context = (
        "This update reflects the ongoing pace of AI adoption across products and research. "
        "Expect continued iteration around model efficiency, safety, and practical integrations."
    )

    read_more = f"\n\n[Read more at {source_name or 'source'}]({link})" if link else ""

    full = f"{intro}{bullet_block}\n\n**Why it matters:** {context}{read_more}"
    # ensure we hit a decent length
    if len(full.split()) < MIN_SUMMARY_WORDS and bt:
        extra = " " + " ".join(bt.split()[:120]) + "..."
        full += "\n\n" + extra

    # tidy
    full = re.sub(r"\n{3,}", "\n\n", full).strip()
    return full

def normalize_date(article: Dict[str, Any]) -> str:
    date_str = article.get("pubDate") or article.get("published_at") or ""
    dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d",
                "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(date_str, fmt)
            break
        except Exception:
            continue
    if not dt:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d")

def short_excerpt(text: str) -> str:
    txt = clean_text(text)
    if len(txt) > MAX_EXCERPT_LEN:
        txt = txt[:MAX_EXCERPT_LEN].rsplit(" ", 1)[0] + "..."
    return txt

def write_post(article: Dict[str, Any], summary: str) -> Optional[str]:
    title = clean_text(article.get("title"))
    if not title:
        return None

    date_for_name = normalize_date(article)
    slug = slugify(title)[:80] or "ai-news"
    filename = POSTS_DIR / f"{date_for_name}-{slug}.md"
    if filename.exists():
        return None

    image = pick_image(article)
    link = clean_text(article.get("link") or article.get("url") or "")
    source_name = clean_text(article.get("source_id") or article.get("source") or "")

    fm = {
        "layout": "post",
        "title": title.replace('"', '\\"'),
        "date": date_for_name,
        "categories": ["ai", "news"],
    }
    if image:
        fm["image"] = image

    # excerpt from description or summary
    excerpt_src = clean_text(article.get("description")) or summary
    fm["excerpt"] = short_excerpt(excerpt_src).replace('"', '\\"')

    # Build final markdown
    fm_yaml = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_yaml.append(f'{k}: [{", ".join(v)}]')
        else:
            fm_yaml.append(f'{k}: "{v}"')
    fm_yaml.append("---\n")

    src_block = ""
    if source_name or link:
        if link:
            label = source_name if source_name else "source"
            src_block = f"\n\nSource: [{label}]({link})"
        else:
            src_block = f"\n\nSource: {source_name}"

    md = "".join(line + "\n" for line in fm_yaml) + summary + src_block + "\n"
    filename.write_text(md, encoding="utf-8")
    print(f"✅ Created: {filename}")
    return str(filename)

def call_api(page: int = 1) -> Dict[str, Any]:
    params = {
        "apikey": API_KEY,
        "q": QUERY,
        "language": LANG,
        "category": CATEGORY,
        "page": page
    }
    r = requests.get(API_URL, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def fetch_articles(limit: int = MAX_POSTS) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise ValueError("NEWS_API_KEY (or NEWSDATA_API_KEY) not set.")
    items: List[Dict[str, Any]] = []
    page = 1
    while len(items) < limit and page <= 3:
        data = call_api(page)
        results = data.get("results") or []
        for art in results:
            if len(items) >= limit:
                break
            title = clean_text(art.get("title"))
            description = clean_text(art.get("description"))
            content = clean_text(art.get("content"))
            combined = f"{title}. {description}. {content}"
            if not title or looks_irrelevant(combined):
                continue
            items.append(art)
        page += 1
    return items[:limit]

def main():
    print("🧠 update_posts.py starting…")
    articles = fetch_articles(limit=MAX_POSTS)
    if not articles:
        print("ℹ️ No suitable articles found.")
        return

    created = 0
    for art in articles:
        title = clean_text(art.get("title"))
        link = clean_text(art.get("link") or art.get("url") or "")
        source_name = clean_text(art.get("source_id") or art.get("source") or "")

        # fetch original content
        body_text = fetch_html_main_text(link)
        # build rich summary
        summary = build_summary(title, source_name, link, body_text, art.get("description") or "")

        # minimal final quality check
        if len(summary.split()) < MIN_SUMMARY_WORDS:
            # fallback: append more from body_text
            extra = " " + " ".join(body_text.split()[:150])
            summary = (summary + extra).strip()

        if write_post(art, summary):
            created += 1

    print(f"🎉 Done. Created {created} post(s).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
