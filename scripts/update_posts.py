import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from slugify import slugify

# === CONFIG ===
POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(parents=True, exist_ok=True)

DAILY_TARGET = 5  # how many posts per run
KEYWORDS = ["artificial intelligence", "machine learning", "AI", "AGI"]

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")

if not API_KEY:
    raise ValueError("API_KEY not found. Set NEWS_API_KEY in repo Variables.")

NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=1)

def parse_dt(any_date: str):
    if not any_date:
        return None
    fmts = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(any_date, f)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None

def safe_get(d: dict, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return default

def fetch_batch():
    query = " OR ".join(KEYWORDS)
    params = {
        "apikey": API_KEY,
        "q": query,
        "language": "en",
        "category": "technology",
    }
    r = requests.get(API_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("results", []) or []

def build_filename(dt: datetime, title: str) -> Path:
    slug = slugify(title)[:80]
    return POSTS_DIR / f"{dt.strftime('%Y-%m-%d')}-{slug}.md"

def sanitize(text: str) -> str:
    return text.replace('"', "'").replace("\n", " ").strip()

def make_front_matter(article: dict, dt: datetime, title: str, link: str, source: str, image: str, excerpt: str) -> str:
    yml = [
        "---",
        "layout: post",
        f'title: "{sanitize(title)}"',
        f"date: {dt.strftime('%Y-%m-%d')}",
        f'image: "{sanitize(image)}"' if image else "image:",
        f'excerpt: "{sanitize(excerpt)}"' if excerpt else "excerpt:",
        "categories: [ai, news]",
        "---",
        "",
        f"Source: [{source}]({link})" if link else "",
        "",
    ]
    return "\n".join(yml).strip() + "\n"

def create_post(article: dict):
    title = safe_get(article, "title", "name")
    if not title:
        return None

    link = safe_get(article, "link", "url")
    source = safe_get(article, "source_id", "source", "creator", default="Source")

    pub_txt = safe_get(article, "pubDate", "published_at", "published", "date")
    dt = parse_dt(pub_txt) or NOW
    if dt < CUTOFF:
        return None

    image = safe_get(article, "image_url", "image", "urlToImage", "image_link", default="")
    content = safe_get(article, "content", "full_description", default="") or ""
    description = safe_get(article, "description", "summary", default="") or ""
    excerpt = (description or content)[:240].strip()

    if len((description + content).strip()) < 120:
        return None

    fn = build_filename(dt, title)
    if fn.exists():
        return None

    md = make_front_matter(article, dt, title, link or "", str(source), image or "", excerpt)
    with open(fn, "w", encoding="utf-8") as f:
        f.write(md)
        f.write("\n" + (content or description) + "\n")

    return fn

def main():
    created = 0
    results = fetch_batch()

    for art in results:
        if created >= DAILY_TARGET:
            break
        fn = create_post(art)
        if fn:
            created += 1
            print(f"✅ Created: {fn}")

    if created == 0:
        print("ℹ️ No new posts created.")
    else:
        print(f"🎉 Done. Created {created} post(s).")

if __name__ == "__main__":
    main()
