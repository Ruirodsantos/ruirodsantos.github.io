# scripts/update_posts.py
import os
import re
import json
import hashlib
from pathlib import Path
import datetime as dt
from typing import List, Dict, Tuple

import requests
from slugify import slugify


# --------- Config ---------
POSTS_DIR = Path("_posts")
POSTS_DIR.mkdir(exist_ok=True)

MAX_POSTS = 5
MIN_BODY_CHARS = 140  # skip one-liners/low-value
TODAY_UTC = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

# Newsdata.io
NEWSDATA_URL = "https://newsdata.io/api/1/news"
NEWSDATA_KEY = os.getenv("NEWS_API_KEY")  # <-- repository variable for newsdata.io

# NewsAPI.org (fallback)
NEWSAPI_URL = "https://newsapi.org/v2/everything"
NEWSAPI_KEY = os.getenv("NEWSAPI_ORG_KEY")  # <-- repository variable for newsapi.org

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


# --------- Helpers ---------
def clean_text(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def good_enough(text: str, min_chars: int = MIN_BODY_CHARS) -> bool:
    return bool(text) and len(text.strip()) >= min_chars


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


def make_post_md(article: Dict, date_str: str, source: str, link: str, content: str, title: str) -> str:
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

    body_lines = []
    if link:
        body_lines.append(f"**Source:** [{source}]({link})\n")
    body_lines.append(content)

    return front_matter + "\n".join(body_lines).strip() + "\n"


def extract_ymd(value: str) -> str:
    """
    Attempt to normalize to YYYY-MM-DD from various date strings.
    """
    if not value:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if m:
        return m.group(1)
    # 2025-09-02T12:34:56Z
    m = re.match(r"(\d{4}-\d{2}-\d{2})T", value)
    if m:
        return m.group(1)
    return ""


# --------- Providers ---------
def fetch_newsdata() -> List[Dict]:
    """
    Try Newsdata with progressively simpler parameters to avoid 422.
    Returns a list of 'results' items or [].
    """
    if not NEWSDATA_KEY:
        return []

    q_full = " OR ".join(KEYWORDS)
    candidates = [
        {"q": q_full, "language": "en", "category": "technology"},
        {"q": q_full, "language": "en"},
        {"q": "artificial intelligence OR generative ai OR llm", "language": "en"},
        {"q": "ai", "language": "en"},
        {"q": "ai"},  # last-resort
    ]

    headers = {"User-Agent": "ai-discovery-bot/1.0"}
    last_err = None

    for params in candidates:
        params = {"apikey": NEWSDATA_KEY, **params}
        try:
            resp = requests.get(NEWSDATA_URL, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results") or []
            if results:
                return results
        except requests.HTTPError as e:
            last_err = e
            # 422 → try next candidate
            if resp is not None and resp.status_code == 422:
                continue
            break
        except Exception as e:
            last_err = e
            break

    if last_err:
        print(f"⚠️ Newsdata error: {last_err}")
    return []


def fetch_newsapi() -> List[Dict]:
    """
    Fallback to NewsAPI.org if available.
    Returns list of articles (NewsAPI schema) or [].
    """
    if not NEWSAPI_KEY:
        return []

    q_full = " OR ".join(KEYWORDS)
    params = {
        "q": q_full,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 50,
        "apiKey": NEWSAPI_KEY,
    }
    headers = {"User-Agent": "ai-discovery-bot/1.0"}
    try:
        resp = requests.get(NEWSAPI_URL, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("articles") or []
    except Exception as e:
        print(f"⚠️ NewsAPI error: {e}")
        return []


# --------- Normalizers ---------
def normalize_newsdata(items: List[Dict]) -> List[Tuple[str, str, str, str]]:
    """
    Map Newsdata results to (date, title, content, link)
    """
    normalized = []
    for a in items:
        title = clean_text(a.get("title") or "")
        link = a.get("link") or a.get("url") or ""
        source = clean_text(a.get("source_id") or a.get("source") or "source")
        descr = clean_text(a.get("description") or "")
        content = clean_text(a.get("content") or descr)
        date_str = extract_ymd(a.get("pubDate") or "")
        normalized.append((date_str, title, content, link, source))
    return normalized


def normalize_newsapi(items: List[Dict]) -> List[Tuple[str, str, str, str]]:
    """
    Map NewsAPI articles to (date, title, content, link)
    """
    normalized = []
    for a in items:
        title = clean_text(a.get("title") or "")
        link = a.get("url") or ""
        source_name = clean_text((a.get("source") or {}).get("name") or "source")
        descr = clean_text(a.get("description") or "")
        content = clean_text(a.get("content") or descr)
        date_str = extract_ymd(a.get("publishedAt") or "")
        normalized.append((date_str, title, content, link, source_name))
    return normalized


# --------- Main flow ---------
def main():
    # 1) Try Newsdata
    items = fetch_newsdata()
    normalized = normalize_newsdata(items) if items else []

    # 2) Fallback to NewsAPI.org if nothing usable from Newsdata
    if not normalized:
        print("ℹ️ Falling back to NewsAPI.org …")
        articles = fetch_newsapi()
        normalized = normalize_newsapi(articles)

    if not normalized:
        print("ℹ️ No articles from any provider.")
        return

    created = 0
    skipped_date = 0
    skipped_short = 0
    skipped_dupe = 0

    for date_str, title, content, link, source in normalized:
        if created >= MAX_POSTS:
            break
        if not title or not content:
            continue

        # Only today's posts (UTC)
        if date_str != TODAY_UTC:
            skipped_date += 1
            continue

        if not good_enough(content):
            skipped_short += 1
            continue

        if already_exists_by_url(link):
            skipped_dupe += 1
            continue

        path = build_filename(date_str, title)
        if path.exists():
            skipped_dupe += 1
            continue

        md = make_post_md(
            article={},
            date_str=date_str,
            source=source,
            link=link,
            content=content,
            title=title,
        )
        path.write_text(md, encoding="utf-8")
        created += 1
        print(f"✅ Created: {path}")

    if created:
        print(f"🎉 Done. Created {created} post(s).")
    else:
        print(
            f"ℹ️ No posts created. "
            f"Skipped (date != today): {skipped_date}, "
            f"Skipped (too short): {skipped_short}, "
            f"Skipped (duplicates): {skipped_dupe}."
        )


if __name__ == "__main__":
    main()
