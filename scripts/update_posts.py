import os
import re
import textwrap
from datetime import datetime, timedelta, timezone

import requests
from dateutil import parser as dateparser
from slugify import slugify

# === CONFIG ===
API_URL = "https://newsdata.io/api/1/news"
API_KEY = os.getenv("NEWS_API_KEY")  # <-- you already created this secret
MAX_POSTS = 5                        # how many posts to create per run
POSTS_DIR = "_posts"

# keywords (kept short so we don't trigger 422 Unprocessable Entity)
QUERY = "artificial intelligence OR AI OR machine learning OR generative ai OR llm"
LANG = "en"
CATEGORY = "technology"  # safe category for Newsdata


def ensure_api_key():
    if not API_KEY:
        raise ValueError("❌ API key not found. Define the repository secret NEWS_API_KEY.")


def dt_utcnow():
    """UTC 'now' with tzinfo (avoid deprecated utcnow())."""
    return datetime.now(timezone.utc)


def sanitize_title(title: str) -> str:
    """Make a YAML/filename-safe title."""
    title = title.strip()
    # replace double quotes for YAML
    title = title.replace('"', '\\"')
    return title


def best_date(article: dict) -> datetime.date:
    """Figure out the best date to use for filename/front-matter."""
    for key in ("pubDate", "pub_date", "date", "published_at"):
        val = article.get(key)
        if val:
            try:
                d = dateparser.parse(val)
                if not d.tzinfo:
                    d = d.replace(tzinfo=timezone.utc)
                return d.date()
            except Exception:
                pass
    # fallback to today UTC
    return dt_utcnow().date()


def short_excerpt(text: str, limit: int = 220) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return (text[: limit - 1] + "…") if len(text) > limit else text


def fetch_latest():
    """
    Get latest items for the last 24h. If the full query 422s,
    retry once with a simpler query w/o category.
    """
    now = dt_utcnow()
    since = now - timedelta(hours=24)

    def _call(params):
        r = requests.get(API_URL, params=params, timeout=30)
        # let caller see the status if not ok
        if r.status_code == 422:
            # bubble to retry branch
            r.raise_for_status()
        r.raise_for_status()
        return r.json()

    base_params = {
        "apikey": API_KEY,
        "q": QUERY,
        "language": LANG,
        "category": CATEGORY,
        "from_date": since.strftime("%Y-%m-%d"),
        "to_date": now.strftime("%Y-%m-%d"),
        "page": 1,
    }

    try:
        data = _call(base_params)
    except requests.HTTPError:
        # Retry with a smaller query set (avoid category + long query)
        retry_params = {
            "apikey": API_KEY,
            "q": "artificial intelligence OR AI",
            "language": LANG,
            "from_date": since.strftime("%Y-%m-%d"),
            "to_date": now.strftime("%Y-%m-%d"),
            "page": 1,
        }
        data = _call(retry_params)

    items = data.get("results", []) or []

    # Keep only items that have enough content to be useful
    cleaned = []
    seen_titles = set()
    for a in items:
        title = (a.get("title") or "").strip()
        desc = (a.get("description") or "").strip()
        link = a.get("link")
        if not title or not desc or not link:
            continue
        # de-dup by normalized title
        norm = re.sub(r"\s+", " ", title.lower())
        if norm in seen_titles:
            continue
        seen_titles.add(norm)
        cleaned.append(a)

    # sort by their publication date (desc)
    def _ts(article):
        try:
            return dateparser.parse(article.get("pubDate") or article.get("pub_date") or "")
        except Exception:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    cleaned.sort(key=_ts, reverse=True)
    return cleaned[:MAX_POSTS]


def build_markdown(article: dict) -> str:
    title = sanitize_title(article["title"])
    date = best_date(article)
    link = article.get("link")
    src_name = article.get("source_id") or "Source"
    image = article.get("image_url") or ""
    excerpt = short_excerpt(article.get("content") or article.get("description") or "")

    fm_lines = [
        "---",
        'layout: post',
        f'title: "{title}"',
        f"date: {date}",
    ]
    if image:
        fm_lines.append(f'image: "{image}"')
    fm_lines.append('categories: [ai, news]')
    fm_lines.append("---")
    front_matter = "\n".join(fm_lines)

    body = textwrap.dedent(
        f"""
        {excerpt}

        Read more at: [{src_name}]({link})
        """
    ).strip()

    return f"{front_matter}\n\n{body}\n"


def write_post(article: dict) -> str:
    """Write a post file and return the path."""
    date = best_date(article)
    slug = slugify(article["title"])[:60]
    filename = f"{date}-{slug}.md"
    path = os.path.join(POSTS_DIR, filename)
    os.makedirs(POSTS_DIR, exist_ok=True)
    content_md = build_markdown(article)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content_md)
    return path


def main():
    ensure_api_key()
    items = fetch_latest()
    if not items:
        print("⚠️ No fresh items found in the last 24h.")
        return
    written = []
    for art in items:
        try:
            written.append(write_post(art))
        except Exception as e:
            print(f"❌ Skipped one item: {e}")
    if written:
        print("✅ Created posts:")
        for p in written:
            print(" -", p)
    else:
        print("⚠️ Nothing written (all items skipped).")


if __name__ == "__main__":
    main()
