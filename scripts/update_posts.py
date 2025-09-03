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
API_KEY = os.getenv("NEWS_API_KEY")  # set in repo Variables, not Secrets
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
    s = re.sub(r"\s+", " ", s).strip()
    return s

def good_enough(text: str, min_chars: int = 140) -> bool:
    return text and len(text.strip()) >= min_chars

def today_utc_date_str() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%d")

def fetch_today_articles() -> list[dict]:
    """Fetch only today's items (UTC) from Newsdata.io."""
    if not API_KEY:
        raise ValueError("API_KEY not found. Define repo variable NEWS_API_KEY.")
    q = " OR ".join(KEYWORDS)

    params = {
        "apikey": API_KEY,
        "q": q,
        "language": "en",
        "category": "technology",
        # force today-only window (UTC)
        "from_date": today_utc_date_str(),
        "to_date": today_utc_date_str(),
        "page": 1,
    }
    resp = requests.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results") or []
    return results

def build_filename(date_str: str, title: str) -> Path:
    slug = slugify(title)[:70] or "post"
    return POSTS_DIR / f"{date_str}-{slug}.md"

def already_exists_by_url(url: str) -> bool:
    # Lightweight dedupe tag based on URL in file content
    tag = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
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

    # compact dedupe tag
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
    try:
        articles = fetch_today_articles()
    except Exception as e:
        print(f"❌ API error: {e}")
        raise

    if not articles:
        print("ℹ️ No results for today (UTC).")
        return

    # keep only items which truly have today's pubDate (UTC) and enough content
    today = today_utc_date_str()

    for a in articles:
        if created >= MAX_POSTS:
            break

        title = (a.get("title") or "").strip()
        if not title:
            continue

        pub = (a.get("pubDate") or a.get("publishedAt") or "").strip()
        # Extract YYYY-MM-DD; fallback to today if missing
        m = re.match(r"(\d{4}-\d{2}-\d{2})", pub)
        date_str = m.group(1) if m else today

        if date_str != today:
            # strictly show only today's posts
            continue

        # Text quality
        content = clean_text(a.get("content") or a.get("description") or "")
        if not good_enough(content):
            continue

        url = a.get("link") or a.get("url") or ""
        if url and already_exists_by_url(url):
            continue

        # Build and write file
        path = build_filename(date_str, title)
        if path.exists():
            # avoid duplicates by filename collision
            continue

        md = make_post_md(a, date_str)
        path.write_text(md, encoding="utf-8")
        created += 1
        print(f"✅ Created: {path}")

    if created == 0:
        print("ℹ️ No new posts created for today.")
    else:
        print(f"🎉 Done. Created {created} post(s).")

if __name__ == "__main__":
    main()
