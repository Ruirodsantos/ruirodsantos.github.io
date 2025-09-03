# scripts/update_posts.py
import os
import re
import json
import hashlib
from pathlib import Path
import datetime as dt

import requests
from slugify import slugify

API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")  # set as Repository Variable
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

# ---------- small helpers ----------
def clean_text(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def good_enough(text: str, min_chars: int = 140) -> bool:
    return text and len(text.strip()) >= min_chars

def today_utc_str() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

def build_filename(date_str: str, title: str) -> Path:
    slug = slugify(title)[:70] or "post"
    return POSTS_DIR / f"{date_str}-{slug}.md"

def already_exists_by_url(url: str) -> bool:
    if not url:
        return False
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

# ---------- API fetch with graceful fallback ----------
def fetch_latest() -> list[dict]:
    """
    Try progressively simpler parameter sets to avoid 422 errors on free tier.
    """
    if not API_KEY:
        raise ValueError("API key missing. Define repository variable NEWS_API_KEY.")

    q_full = " OR ".join(KEYWORDS)
    candidates = [
        # Most complete (often OK, but sometimes 422 on free tier)
        {"q": q_full, "language": "en", "category": "technology", "page": 1},
        # Drop category
        {"q": q_full, "language": "en", "page": 1},
        # Shorter query
        {"q": "artificial intelligence OR generative ai OR llm", "language": "en", "page": 1},
        # Minimal query (almost always accepted)
        {"q": "ai", "language": "en", "page": 1},
    ]

    headers = {"User-Agent": "ai-discovery-bot/1.0"}

    last_err = None
    for params in candidates:
        params = {"apikey": API_KEY, **params}
        try:
            resp = requests.get(API_URL, params=params, headers=headers, timeout=30)
            # Uncomment for debugging:
            # print("DEBUG URL:", resp.url)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if results:
                return results
        except requests.HTTPError as e:
            last_err = e
            # If 422, try the next simpler candidate
            if resp is not None and resp.status_code == 422:
                continue
            # For other HTTP errors, break early
            break
        except Exception as e:
            last_err = e
            break

    if last_err:
        raise last_err
    return []

# ---------- main ----------
def main():
    items = fetch_latest()
    if not items:
        print("ℹ️ API returned no results.")
        return

    today = today_utc_str()
    created = 0
    skipped_quality = 0
    skipped_date = 0
    skipped_dupe = 0

    for a in items:
        if created >= MAX_POSTS:
            break

        title = (a.get("title") or "").strip()
        if not title:
            continue

        # Normalize date to YYYY-MM-DD and keep only today (UTC)
        pub = (a.get("pubDate") or a.get("publishedAt") or "").strip()
        m = re.match(r"(\d{4}-\d{2}-\d{2})", pub)
        date_str = m.group(1) if m else today
        if date_str != today:
            skipped_date += 1
            continue

        content = clean_text(a.get("content") or a.get("description") or "")
        if not good_enough(content):
            skipped_quality += 1
            continue

        url = a.get("link") or a.get("url") or ""
        if already_exists_by_url(url):
            skipped_dupe += 1
            continue

        path = build_filename(date_str, title)
        if path.exists():
            skipped_dupe += 1
            continue

        md = make_post_md(a, date_str)
        path.write_text(md, encoding="utf-8")
        created += 1
        print(f"✅ Created: {path}")

    if created:
        print(f"🎉 Done. Created {created} post(s).")
    else:
        print(
            f"ℹ️ No posts created. "
            f"Skipped (date != today): {skipped_date}, "
            f"Skipped (too short): {skipped_quality}, "
            f"Skipped (duplicates): {skipped_dupe}."
        )

if __name__ == "__main__":
    main()
