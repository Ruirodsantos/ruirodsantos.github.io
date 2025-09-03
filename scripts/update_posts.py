# scripts/update_posts.py
import os
import re
import json
import hashlib
import datetime as dt
from pathlib import Path

import requests
from slugify import slugify

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")  # set in repo “Variables”
MAX_POSTS = 5

POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(exist_ok=True)

KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "generative ai",
    "llm",
    "openai",
    "anthropic",
    "google ai",
    "meta ai",
]

def clean_text(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def good_enough(text: str, min_chars: int = 140) -> bool:
    return text and len(text.strip()) >= min_chars

def today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

def fetch_latest() -> list[dict]:
    """Fetch latest results without date params (free plan safe)."""
    if not API_KEY:
        raise ValueError("API_KEY not found. Define repo variable NEWS_API_KEY.")
    q = " OR ".join(KEYWORDS)

    params = {
        "apikey": API_KEY,
        "q": q,
        "language": "en",
        "category": "technology",
        # No from_date / to_date to avoid 422 on free plan
        "page": 1,
    }
    resp = requests.get(API_URL, params=params, timeout=30)
    # print("DEBUG URL:", resp.url)  # uncomment for troubleshooting
    resp.raise_for_status()
    data = resp.json()
    return data.get("results") or []

def build_filename(date_str: str, title: str) -> Path:
    slug = slugify(title)[:70] or "post"
    return POSTS_DIR / f"{date_str}-{slug}.md"

def already_exists_by_url(url: str) -> bool:
    tag = hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:12]
    for p in POSTS_DIR.glob("*.md"):
        try:
            if tag in p.read_text(encoding="utf-8", errors="ignore"):
                return True
        except Exception:
            pass
    return False

def make_post_md(article: dict, date_str: str) -> str:
    title = clean_text(article.get("title") or "")
    source = clean_text(article.get("source_id") or article.get("source") or "source")
    link = article.get("link") or article.get("url") or ""
    description = clean_text(article.get("description") or "")
    content = clean_text(article.get("content") or description)

    dedupe_tag = hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:12]

    fm = {
        "layout": "post",
        "title": title.replace('"', '\\"'),
        "date": date_str,
        "categories": ["ai", "news"],
        "source": source,
        "original_url": link,
        "_dedupe": dedupe_tag,
    }
    front_matter = "---\n" + "\n".join(
        f'{k}: "{v}"' if isinstance(v, str) else f"{k}: {json.dumps(v)}"
        for k, v in fm.items()
    ) + "\n---\n"

    body = []
    if link:
        body.append(f"**Source:** [{source}]({link})\n")
    body.append(content or description)

    return front_matter + "\n".join(body).strip() + "\n"

def main():
    created = 0
    items = fetch_latest()
    if not items:
        print("ℹ️ API returned no results.")
        return

    today = today_utc()

    for a in items:
        if created >= MAX_POSTS:
            break

        title = (a.get("title") or "").strip()
        if not title:
            continue

        pub = (a.get("pubDate") or a.get("publishedAt") or "").strip()
        m = re.match(r"(\d{4}-\d{2}-\d{2})", pub)
        date_str = m.group(1) if m else today
        if date_str != today:
            continue  # keep only today's

        content = clean_text(a.get("content") or a.get("description") or "")
        if not good_enough(content):
            continue

        url = a.get("link") or a.get("url") or ""
        if url and already_exists_by_url(url):
            continue

        path = build_filename(date_str, title)
        if path.exists():
            continue

        md = make_post_md(a, date_str)
        path.write_text(md, encoding="utf-8")
        created += 1
        print(f"✅ Created: {path}")

    print(f"🎉 Done. Created {created} post(s)." if created else "ℹ️ No new posts created for today.")

if __name__ == "__main__":
    main()
